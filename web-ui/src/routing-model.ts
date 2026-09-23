import type { TopologySnapshot } from "./types";
export type RoutingLayer = "Physical" | "AS" | "OSPF" | "BGP" | "Prefix";
type RecordValue = Record<string, unknown>;
export type NodeEvidence = {
  node_id: string;
  generation: number;
  collected_at: string;
  source: string;
  error_code: string | null;
  truncated: boolean;
  data: {
    prefix: string;
    bgp: RecordValue;
    rib: RecordValue;
    fib: RecordValue[];
    bgp_peers: RecordValue;
    ospf_neighbors: RecordValue;
    advertised: { peer: string; present: boolean; source: string }[];
    received: { status: string };
  } | null;
};
export type RoutingEvidence = {
  generation: number;
  status: string;
  data: {
    prefix: string;
    nodes: NodeEvidence[];
    collected: number;
    expected: number;
    atomic: false;
  };
};
export type ProtocolFact = {
  id: string;
  source: string;
  target: string;
  left: string;
  right: string;
  text: string;
  state: "up" | "conflict" | "unknown";
};

export function freshness(
  n: NodeEvidence | undefined,
  generation: number,
  now: number,
) {
  if (!n) return "not collected";
  if (n.generation !== generation) return "prior generation";
  const age = now - Date.parse(n.collected_at);
  return !Number.isFinite(age) || age < -5000
    ? "invalid time"
    : age > 30000
      ? "stale"
      : "fresh";
}
export function validateRouting(
  value: RoutingEvidence,
  topology: TopologySnapshot,
  prefix: string,
) {
  const ids = new Set(
    topology.nodes.filter((n) => n.kind === "router").map((n) => n.id),
  );
  if (
    value?.generation !== topology.generation ||
    value.data?.prefix !== prefix ||
    !Array.isArray(value.data?.nodes) ||
    value.data.nodes.length !== ids.size
  )
    throw Error("Invalid routing snapshot");
  for (const n of value.data.nodes) {
    if (
      !ids.delete(n.node_id) ||
      n.generation !== topology.generation ||
      !Number.isFinite(Date.parse(n.collected_at)) ||
      n.source !== "node_dispatcher" ||
      typeof n.truncated !== "boolean"
    )
      throw Error("Invalid routing node metadata");
    if (
      n.data &&
      (n.data.prefix !== prefix ||
        !Array.isArray(n.data.bgp?.paths) ||
        !n.data.rib ||
        typeof n.data.rib !== "object" ||
        !Array.isArray(n.data.fib) ||
        !Array.isArray(n.data.advertised) ||
        n.data.advertised.some(
          (a) =>
            typeof a.peer !== "string" ||
            typeof a.present !== "boolean" ||
            a.source !== "advertised_by_node",
        ))
    )
      throw Error("Invalid routing node evidence");
  }
  return value;
}
export function complete(value: RoutingEvidence) {
  return (
    value.status === "ok" &&
    value.data.nodes.every((n) => n.data && !n.error_code && !n.truncated)
  );
}
export function protocolFacts(
  snapshot: TopologySnapshot,
  evidence: RoutingEvidence | null,
  layer: RoutingLayer,
  now: number,
): ProtocolFact[] {
  const nodes = new Map(evidence?.data.nodes.map((n) => [n.node_id, n]) ?? []);
  const observed = (id: string, address: string, iface?: string) => {
    const n = nodes.get(id),
      age = freshness(n, snapshot.generation, now);
    if (!n?.data || n.error_code || n.truncated)
      return n?.error_code ?? (n?.truncated ? "truncated" : "not collected");
    if (layer === "BGP") {
      const peers = n.data.bgp_peers.ipv4Unicast as
        | { peers?: Record<string, { state?: string }> }
        | undefined;
      return `${peers?.peers?.[address]?.state ?? "not observed"} · ${age}`;
    }
    const entries = n.data.ospf_neighbors[address];
    const neighbor = Array.isArray(entries)
      ? entries.find(
          (v) =>
            typeof v.ifaceName === "string" &&
            v.ifaceName.split(":")[0] === iface,
        )
      : undefined;
    return `${neighbor?.nbrState ?? "not observed"} · ${age}`;
  };
  const relationships =
    layer === "BGP"
      ? (snapshot.peerings ?? []).map((p) => ({
          ...p,
          a: observed(p.source, p.target_address),
          b: observed(p.target, p.source_address),
        }))
      : layer === "OSPF"
        ? snapshot.links
            .filter((l) => l.ospf_area === "0")
            .map((l) => ({
              ...l,
              a: observed(
                l.source,
                snapshot.nodes.find((n) => n.id === l.target)?.router_id ?? "",
                l.interfaces?.[0],
              ),
              b: observed(
                l.target,
                snapshot.nodes.find((n) => n.id === l.source)?.router_id ?? "",
                l.interfaces?.[1],
              ),
            }))
        : [];
  return relationships.map((p) => {
    const healthy = (s: string) =>
      s === "Established · fresh" ||
      (s.startsWith("Full/") && s.endsWith(" · fresh"));
    const fresh = [p.a, p.b].every(
      (s) => s.endsWith(" · fresh") && !s.startsWith("not observed"),
    );
    return {
      id: p.id,
      source: p.source,
      target: p.target,
      left: p.a,
      right: p.b,
      text: `${p.source} ↔ ${p.target}: ${p.a} / ${p.b}`,
      state:
        healthy(p.a) && healthy(p.b) ? "up" : fresh ? "conflict" : "unknown",
    };
  });
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify(value.map(canonical).sort());
  if (value && typeof value === "object")
    return JSON.stringify(
      Object.fromEntries(
        Object.entries(value)
          .filter(
            ([k]) =>
              ![
                "age",
                "uptime",
                "uptimeMsec",
                "version",
                "tableVersion",
                "lastUpdate",
              ].includes(k),
          )
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => [k, canonical(v)]),
      ),
    );
  return JSON.stringify(value);
}
export function compareRouting(
  before: RoutingEvidence | null,
  after: RoutingEvidence | null,
  now: number,
): string[] | null {
  if (
    !before ||
    !after ||
    before.generation !== after.generation ||
    before.data.prefix !== after.data.prefix ||
    !complete(before) ||
    !complete(after)
  )
    return null;
  if (
    [...before.data.nodes, ...after.data.nodes].some(
      (n) => freshness(n, after.generation, now) !== "fresh",
    )
  )
    return null;
  const result: string[] = [];
  for (const n of after.data.nodes) {
    const old = before.data.nodes.find((v) => v.node_id === n.node_id);
    if (!old?.data || !n.data) return null;
    for (const [label, a, b] of [
      ["BGP", old.data.bgp.paths, n.data.bgp.paths],
      [
        "RIB",
        old.data.rib[after.data.prefix] ?? [],
        n.data.rib[after.data.prefix] ?? [],
      ],
      ["FIB", old.data.fib, n.data.fib],
      ["exports", old.data.advertised, n.data.advertised],
    ] as [string, unknown[], unknown[]][]) {
      if (canonical(a) !== canonical(b))
        result.push(
          `${n.node_id} · ${label}: ${!a.length ? "added" : !b.length ? "withdrawn" : "changed"}`,
        );
    }
  }
  return result;
}
