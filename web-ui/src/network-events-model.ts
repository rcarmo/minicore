import type { TopologySnapshot } from "./types";

export type ScopeType = "node" | "link";
export type NetworkScope = { type: ScopeType; id: string };
export type ObserverKind = "routing" | "interfaces" | "igmp";
export type SourceHealth =
  | "ok"
  | "collection_timeout"
  | "collection_failed"
  | "invalid_observation"
  | "source_unavailable";

type Dict = Record<string, unknown>;

type BaseRecord = {
  scope: string;
  incarnation: string;
  acquired_monotonic: number;
  sampled_at: string;
  remaining_ms: number;
  data: unknown;
};

export interface InterfaceCounters {
  node_id?: string;
  interface: string;
  state:
    | "UP"
    | "DOWN"
    | "UNKNOWN"
    | "LOWERLAYERDOWN"
    | "DORMANT"
    | "NOTPRESENT"
    | "TESTING";
  tx_packets: number;
  rx_packets: number;
  tx_bytes: number;
  rx_bytes: number;
  tx_errors: number;
  rx_errors: number;
  tx_drops: number;
  rx_drops: number;
}

export interface RoutingPeer {
  protocol: "bgp" | "ospf";
  address: string;
  state: string;
}
export interface RoutingRoute {
  prefix: string;
  source: "bgp" | "rib" | "fib";
  nexthops: string[];
}
export interface IgmpRecordDetail {
  record_type: number;
  group: string;
  sources: string[];
}
export interface IgmpObservation {
  node_id?: string;
  interface?: string;
  version: 1 | 2 | 3;
  message_type:
    | "query"
    | "report"
    | "report_v1"
    | "report_v2"
    | "report_v3"
    | "leave";
  group: string | null;
  reporter: string | null;
  querier: string | null;
  sources: string[];
  records: IgmpRecordDetail[];
}

export type ValidatedRecord =
  | {
      kind: "interfaces";
      scope: string;
      incarnation: string;
      acquiredMonotonic: number;
      sampledAt: string;
      remainingMs: number;
      expiresAt: number;
      data: { interfaces: InterfaceCounters[] };
    }
  | {
      kind: "routing";
      scope: string;
      incarnation: string;
      acquiredMonotonic: number;
      sampledAt: string;
      remainingMs: number;
      expiresAt: number;
      data: { peers: RoutingPeer[]; routes: RoutingRoute[] };
    }
  | {
      kind: "igmp";
      scope: string;
      incarnation: string;
      acquiredMonotonic: number;
      sampledAt: string;
      remainingMs: number;
      expiresAt: number;
      data: IgmpObservation;
    };

export interface ValidatedEnvelope {
  observerEpoch: string;
  generation: number;
  scope: string;
  windowSeconds: 60;
  sourceHealth: SourceHealth;
  missedUpdates: number;
  truncated: boolean;
  omitted: number;
  records: ValidatedRecord[];
  sources?: Record<string, SourceHealth>;
  captureErrors?: Record<string, number>;
}

export interface ObserverEnvelope {
  observer_epoch: string;
  generation: number;
  scope: string;
  window_seconds: number;
  source_health: SourceHealth;
  missed_updates: number;
  truncated: boolean;
  omitted: number;
  records: BaseRecord[];
}

export interface DerivedRow {
  id: string;
  event: string;
  detail: string;
  at: string;
  source: string;
  nodeId?: string;
  linkId?: string;
  interface?: string;
  expanded?: string;
}

export interface SparklinePoint {
  x: number;
  primary: number;
  secondary?: number;
}

export interface NetworkEventsModel {
  status: string;
  sourceHealth: SourceHealth | "unknown";
  rows: DerivedRow[];
  sparkline: {
    mode: "events" | "traffic";
    points: SparklinePoint[];
    max: number;
  };
  clipped: boolean;
  ageMs: number | null;
  summary: string;
  rates: {
    label: string;
    txPackets: number | null;
    rxPackets: number | null;
    txBytes: number | null;
    rxBytes: number | null;
  }[];
}

function asObject(value: unknown, label: string): Dict {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`Invalid ${label}`);
  return value as Dict;
}
function asString(value: unknown, label: string, pattern?: RegExp) {
  if (typeof value !== "string" || (pattern && !pattern.test(value)))
    throw new Error(`Invalid ${label}`);
  if (value.length > 128) throw Error(`Invalid ${label}`);
  return value;
}
function asInteger(
  value: unknown,
  label: string,
  maximum = Number.MAX_SAFE_INTEGER,
) {
  if (!Number.isInteger(value) || Number(value) < 0 || Number(value) > maximum)
    throw new Error(`Invalid ${label}`);
  return Number(value);
}
function asArray(value: unknown, label: string, maximum: number) {
  if (!Array.isArray(value) || value.length > maximum)
    throw new Error(`${label} too large`);
  return value;
}
function scopeString(scope: NetworkScope, kind: ObserverKind) {
  return `${scope.type}:${scope.id}:${kind}`;
}
function hasScope(snapshot: TopologySnapshot, scope: NetworkScope) {
  return scope.type === "node"
    ? snapshot.nodes.some((node) => node.id === scope.id)
    : snapshot.links.some((link) => link.id === scope.id);
}
function parseInterface(value: unknown): InterfaceCounters {
  const row = asObject(value, "interface row");
  const result: InterfaceCounters = {
    interface: asString(row.interface, "interface", /^[a-zA-Z0-9_.-]{1,32}$/),
    state: asString(row.state, "state") as InterfaceCounters["state"],
    tx_packets: asInteger(row.tx_packets, "tx_packets"),
    rx_packets: asInteger(row.rx_packets, "rx_packets"),
    tx_bytes: asInteger(row.tx_bytes, "tx_bytes"),
    rx_bytes: asInteger(row.rx_bytes, "rx_bytes"),
    tx_errors: asInteger(row.tx_errors, "tx_errors"),
    rx_errors: asInteger(row.rx_errors, "rx_errors"),
    tx_drops: asInteger(row.tx_drops, "tx_drops"),
    rx_drops: asInteger(row.rx_drops, "rx_drops"),
  };
  if (
    ![
      "UP",
      "DOWN",
      "UNKNOWN",
      "LOWERLAYERDOWN",
      "DORMANT",
      "NOTPRESENT",
      "TESTING",
    ].includes(result.state)
  )
    throw Error("Invalid interface state");
  if (row.node_id !== undefined)
    result.node_id = asString(row.node_id, "node_id", /^[a-z][a-z0-9]{1,15}$/);
  return result;
}
function parseRoutingPeer(value: unknown): RoutingPeer {
  const row = asObject(value, "routing peer");
  if (!["bgp", "ospf"].includes(String(row.protocol)))
    throw Error("Invalid routing protocol");
  return {
    protocol: asString(row.protocol, "protocol") as RoutingPeer["protocol"],
    address: asString(row.address, "address"),
    state: asString(row.state, "state"),
  };
}
function parseRoute(value: unknown): RoutingRoute {
  const row = asObject(value, "route");
  if (!["bgp", "rib", "fib"].includes(String(row.source)))
    throw Error("Invalid route source");
  const nexthops = asArray(row.nexthops, "route nexthops", 16).map((hop) =>
    asString(hop, "nexthop"),
  );
  return {
    prefix: asString(row.prefix, "prefix"),
    source: asString(row.source, "source") as RoutingRoute["source"],
    nexthops,
  };
}
function parseIgmp(value: unknown): IgmpObservation {
  const row = asObject(value, "igmp");
  const result: IgmpObservation = {
    version: asInteger(row.version, "version", 3) as 1 | 2 | 3,
    message_type: asString(
      row.message_type,
      "message_type",
    ) as IgmpObservation["message_type"],
    group: row.group == null ? null : asString(row.group, "group"),
    reporter: row.reporter == null ? null : asString(row.reporter, "reporter"),
    querier: row.querier == null ? null : asString(row.querier, "querier"),
    sources: asArray(row.sources, "igmp sources", 64).map((source) =>
      asString(source, "igmp source"),
    ),
    records: asArray(row.records, "igmp records", 64).map((record) => {
      const detail = asObject(record, "igmp record");
      return {
        record_type: asInteger(detail.record_type, "record_type", 6),
        group: asString(detail.group, "record group"),
        sources: asArray(detail.sources, "igmp record sources", 64).map(
          (source) => asString(source, "record source"),
        ),
      };
    }),
  };
  if (
    ![1, 2, 3].includes(result.version) ||
    ![
      "query",
      "report",
      "report_v1",
      "report_v2",
      "report_v3",
      "leave",
    ].includes(result.message_type) ||
    result.records.some((r) => r.record_type < 1)
  )
    throw Error("Invalid IGMP fields");
  if (row.node_id !== undefined)
    result.node_id = asString(row.node_id, "node_id", /^[a-z][a-z0-9]{1,15}$/);
  if (row.interface !== undefined)
    result.interface = asString(
      row.interface,
      "interface",
      /^[a-zA-Z0-9_.-]{1,32}$/,
    );
  return result;
}

export function validateObserverEnvelope(
  value: unknown,
  snapshot: TopologySnapshot,
  scope: NetworkScope,
  kind: ObserverKind,
  requestStartedAt: number,
  receivedAt: number,
  now = receivedAt,
): ValidatedEnvelope {
  const raw = asObject(
    value,
    "observer envelope",
  ) as unknown as ObserverEnvelope;
  if (!hasScope(snapshot, scope)) throw new Error("Invalid scope selection");
  if (
    raw.generation !== snapshot.generation ||
    raw.scope !== scopeString(scope, kind) ||
    raw.window_seconds !== 60 ||
    typeof raw.observer_epoch !== "string" ||
    ![
      "ok",
      "collection_timeout",
      "collection_failed",
      "invalid_observation",
      "source_unavailable",
    ].includes(raw.source_health) ||
    !Number.isSafeInteger(raw.missed_updates) ||
    raw.missed_updates < 0 ||
    raw.observer_epoch.length > 128 ||
    !raw.observer_epoch ||
    typeof raw.truncated !== "boolean" ||
    !Number.isSafeInteger(raw.omitted) ||
    raw.omitted < 0
  )
    throw new Error("Invalid observer metadata");
  const records = asArray(raw.records, "observer records", 128);
  const encoded = new TextEncoder().encode(JSON.stringify(value)).length;
  if (encoded > 64 * 1024) throw new Error("Observer response too large");
  const fetchCost = Math.max(0, Math.floor(receivedAt - requestStartedAt));
  const seen = new Set<string>();
  const validated: ValidatedRecord[] = records.map((entry, index) => {
    const row = asObject(entry, `record ${index}`) as unknown as BaseRecord;
    if (
      row.scope !== raw.scope ||
      typeof row.incarnation !== "string" ||
      !Number.isFinite(row.acquired_monotonic) ||
      row.acquired_monotonic < 0 ||
      !row.incarnation ||
      row.incarnation.length > 128 ||
      typeof row.sampled_at !== "string" ||
      !Number.isFinite(Date.parse(row.sampled_at)) ||
      !Number.isFinite(row.remaining_ms) ||
      row.remaining_ms < 0 ||
      row.remaining_ms > 60000
    )
      throw new Error("Invalid observer record");
    const remainingMs = Math.max(0, Math.floor(row.remaining_ms - fetchCost));
    const expiresAt = receivedAt + remainingMs;
    if (kind === "interfaces") {
      const body = asObject(row.data, "interfaces payload");
      const interfaces = asArray(body.interfaces, "interfaces", 32).map(
        parseInterface,
      );
      const names = new Set<string>();
      for (const item of interfaces) {
        const key = `${item.node_id ?? ""}:${item.interface}`;
        if (names.has(key)) throw new Error("Duplicate interface identity");
        names.add(key);
      }
      return {
        kind,
        scope: row.scope,
        incarnation: row.incarnation,
        acquiredMonotonic: row.acquired_monotonic,
        sampledAt: row.sampled_at,
        remainingMs,
        expiresAt,
        data: { interfaces },
      };
    }
    if (kind === "routing") {
      const body = asObject(row.data, "routing payload");
      const peers = asArray(body.peers, "routing peers", 64).map(
        parseRoutingPeer,
      );
      const peerIds = new Set<string>();
      for (const peer of peers) {
        const key = `${peer.protocol}:${peer.address}`;
        if (peerIds.has(key))
          throw new Error("Duplicate routing peer identity");
        peerIds.add(key);
      }
      const routes = asArray(body.routes, "routes", 32).map(parseRoute);
      const routeIds = new Set<string>();
      for (const route of routes) {
        const key = `${route.source}:${route.prefix}`;
        if (routeIds.has(key)) throw new Error("Duplicate route identity");
        routeIds.add(key);
      }
      return {
        kind,
        scope: row.scope,
        incarnation: row.incarnation,
        acquiredMonotonic: row.acquired_monotonic,
        sampledAt: row.sampled_at,
        remainingMs,
        expiresAt,
        data: { peers, routes },
      };
    }
    const data = parseIgmp(row.data);
    return {
      kind,
      scope: row.scope,
      incarnation: row.incarnation,
      acquiredMonotonic: row.acquired_monotonic,
      sampledAt: row.sampled_at,
      remainingMs,
      expiresAt,
      data,
    };
  });
  for (const record of validated) {
    const key = `${record.incarnation}:${record.acquiredMonotonic}`;
    if (seen.has(key)) throw new Error("Duplicate observer record identity");
    seen.add(key);
  }
  return {
    observerEpoch: raw.observer_epoch,
    generation: raw.generation,
    scope: raw.scope,
    windowSeconds: 60,
    sourceHealth: raw.source_health,
    missedUpdates: raw.missed_updates,
    truncated: raw.truncated,
    omitted: raw.omitted,
    records: validated,
    captureErrors: (() => {
      const data =
        (raw as unknown as { capture_errors?: Record<string, unknown> })
          .capture_errors ?? {};
      if (Object.keys(data).length > 8) throw Error("Invalid source counters");
      return Object.fromEntries(
        Object.entries(data).map(([name, value]) => {
          if (
            ![
              "expired",
              "overflow",
              "parse",
              "truncated",
              "checksum_partial",
              "socket_unavailable",
              "kernel_drops",
              "rate_limit",
            ].includes(name)
          )
            throw Error("Invalid source counter");
          return [name, asInteger(value, "source loss")];
        }),
      );
    })(),
    sources: (() => {
      const value = (raw as unknown as { sources?: unknown }).sources;
      if (value === undefined) return undefined;
      const sources = asObject(value, "source health");
      if (Object.keys(sources).length > 2) throw Error("Too many sources");
      for (const [node, health] of Object.entries(sources)) {
        if (
          !snapshot.nodes.some((n) => n.id === node) ||
          ![
            "ok",
            "collection_timeout",
            "collection_failed",
            "invalid_observation",
            "source_unavailable",
          ].includes(String(health))
        )
          throw Error("Invalid source health");
      }
      return sources as Record<string, SourceHealth>;
    })(),
  };
}

function labelForScope(snapshot: TopologySnapshot, scope: NetworkScope) {
  if (scope.type === "node")
    return (
      snapshot.nodes.find((node) => node.id === scope.id)?.label ?? scope.id
    );
  const link = snapshot.links.find((item) => item.id === scope.id);
  return link ? `${link.source} ↔ ${link.target}` : scope.id;
}

function compatible(a: ValidatedEnvelope, b: ValidatedEnvelope) {
  return (
    a.scope === b.scope &&
    a.generation === b.generation &&
    a.observerEpoch === b.observerEpoch &&
    a.sourceHealth === "ok" &&
    b.sourceHealth === "ok" &&
    !a.truncated &&
    !b.truncated &&
    !a.omitted &&
    !b.omitted &&
    a.missedUpdates === b.missedUpdates
  );
}
function pair(a: ValidatedRecord | undefined, b: ValidatedRecord) {
  return (
    !!a &&
    a.kind === b.kind &&
    a.incarnation === b.incarnation &&
    b.acquiredMonotonic > a.acquiredMonotonic &&
    b.acquiredMonotonic - a.acquiredMonotonic <= 15
  );
}
function sourceLink(
  snapshot: TopologySnapshot,
  node: string | undefined,
  iface: string | undefined,
) {
  return snapshot.links.find(
    (l) =>
      (l.source === node && l.interfaces?.[0] === iface) ||
      (l.target === node && l.interfaces?.[1] === iface),
  )?.id;
}
function healthLabel(health: SourceHealth | undefined, kind: ObserverKind) {
  if (health === "collection_timeout") return "Collection timed out";
  if (health === "collection_failed") return "Source disconnected";
  if (health === "invalid_observation") return "Invalid source response";
  return kind === "igmp" ? "IGMP capture unavailable" : "Observer unavailable";
}
export function buildNetworkEventsModel({
  snapshot,
  scope,
  kind,
  current,
  previous,
  now,
}: {
  snapshot: TopologySnapshot;
  scope: NetworkScope;
  kind: ObserverKind;
  current: ValidatedEnvelope | null;
  previous: ValidatedEnvelope | null;
  now: number;
}): NetworkEventsModel {
  const label = labelForScope(snapshot, scope),
    expected = scopeString(scope, kind);
  if (
    current &&
    (current.scope !== expected || current.generation !== snapshot.generation)
  )
    current = null;
  const healthy =
    !!current &&
    current.sourceHealth === "ok" &&
    !current.truncated &&
    !current.omitted;
  const records = new Map<string, ValidatedRecord>();
  if (current) {
    const history =
      previous && compatible(previous, current)
        ? [...previous.records, ...current.records]
        : current.records;
    for (const r of history)
      if (r.kind === kind && r.scope === expected && r.expiresAt > now) {
        const id = `${r.incarnation}:${r.acquiredMonotonic}`;
        const old = records.get(id);
        records.set(
          id,
          old ? { ...r, expiresAt: Math.min(old.expiresAt, r.expiresAt) } : r,
        );
      }
  }
  const samples = [...records.values()]
    .sort((a, b) => a.acquiredMonotonic - b.acquiredMonotonic)
    .slice(-128);
  const rows: DerivedRow[] = [],
    rates: NetworkEventsModel["rates"] = [];
  const points = Array.from({ length: 12 }, (_, x) => ({
    x,
    primary: 0,
    secondary: 0,
  }));
  const latest = samples.at(-1);
  const latestBySource = new Map(samples.map((r) => [r.incarnation, r]));
  const priorBySource = new Map<string, ValidatedRecord>();
  const bucket = (r: ValidatedRecord) =>
    11 -
    Math.min(11, Math.max(0, Math.floor((60000 - (r.expiresAt - now)) / 5000)));
  const add = (
    r: ValidatedRecord,
    event: string,
    detail: string,
    identity: string,
    nodeId?: string,
    iface?: string,
    expanded?: string,
  ) => {
    rows.push({
      id: `${r.incarnation}:${r.acquiredMonotonic}:${identity}`,
      event,
      detail,
      at: r.sampledAt,
      source: nodeId && iface ? `${nodeId} / ${iface}` : label,
      nodeId: nodeId ?? (scope.type === "node" ? scope.id : undefined),
      linkId:
        scope.type === "link" ? scope.id : sourceLink(snapshot, nodeId, iface),
      interface: iface,
      expanded,
    });
    points[bucket(r)].primary++;
  };
  for (let index = 0; index < samples.length; index++) {
    const r = samples[index],
      old = priorBySource.get(r.incarnation);
    priorBySource.set(r.incarnation, r);
    const ownHealth =
      r.kind === "interfaces" && scope.type === "link" && current?.sources
        ? r.data.interfaces.every(
            (i) => !!i.node_id && current!.sources![i.node_id] === "ok",
          )
        : healthy;
    const canCompare =
      ownHealth && !current?.truncated && !current?.omitted && pair(old, r);
    if (r.kind === "routing") {
      const before = canCompare && old?.kind === "routing" ? old.data : null;
      const peers = new Map(
        before?.peers.map((p) => [`${p.protocol}:${p.address}`, p]),
      );
      for (const p of r.data.peers) {
        const prior = peers.get(`${p.protocol}:${p.address}`);
        if (!before || !prior || prior.state !== p.state)
          add(
            r,
            prior ? "Peer state changed" : `Peer ${p.state}`,
            `${p.protocol.toUpperCase()} ${p.address} · ${prior ? prior.state + " → " : ""}${p.state}`,
            `peer:${p.protocol}:${p.address}`,
            undefined,
            undefined,
            prior ? `Previous state: ${prior.state}` : undefined,
          );
      }
      const routes = new Map(
        before?.routes.map((p) => [`${p.source}:${p.prefix}`, p]),
      );
      const present = new Set(
        r.data.routes.map((p) => `${p.source}:${p.prefix}`),
      );
      for (const p of r.data.routes) {
        const prior = routes.get(`${p.source}:${p.prefix}`),
          hops = [...p.nexthops].sort();
        if (
          !before ||
          !prior ||
          JSON.stringify([...prior.nexthops].sort()) !== JSON.stringify(hops)
        )
          add(
            r,
            !before
              ? "Route present"
              : !prior
                ? "Route added"
                : "Next hop changed",
            `${p.source.toUpperCase()} ${p.prefix} · ${hops.join(", ") || "direct"}`,
            `route:${p.source}:${p.prefix}`,
            undefined,
            undefined,
            prior
              ? `Previous next hops: ${prior.nexthops.join(", ") || "direct"}`
              : undefined,
          );
      }
      if (before)
        for (const p of before.routes)
          if (!present.has(`${p.source}:${p.prefix}`))
            add(
              r,
              "Route withdrawn",
              `${p.source.toUpperCase()} ${p.prefix}`,
              `withdraw:${p.source}:${p.prefix}`,
            );
    } else if (r.kind === "interfaces") {
      const before =
        canCompare && old?.kind === "interfaces"
          ? new Map(
              old.data.interfaces.map((i) => [
                `${i.node_id ?? ""}:${i.interface}`,
                i,
              ]),
            )
          : new Map<string, InterfaceCounters>();
      let totalTx = 0,
        totalRx = 0,
        validRate = false;
      for (const i of r.data.interfaces) {
        const id = `${i.node_id ?? ""}:${i.interface}`,
          prior = before.get(id),
          node = i.node_id ?? (scope.type === "node" ? scope.id : undefined);
        const reset =
          prior &&
          (["tx_packets", "rx_packets", "tx_bytes", "rx_bytes"] as const).some(
            (k) => i[k] < prior[k],
          );
        if (!prior || prior.state !== i.state)
          add(
            r,
            `Interface ${i.state}`,
            `${i.interface}${prior ? " · " + prior.state + " → " + i.state : ""}`,
            `interface:${id}`,
            node,
            i.interface,
            `TX ${i.tx_packets} packets / ${i.tx_bytes} bytes; RX ${i.rx_packets} packets / ${i.rx_bytes} bytes; errors ${i.tx_errors + i.rx_errors}; drops ${i.tx_drops + i.rx_drops}`,
          );
        if (reset)
          add(
            r,
            "Counters reset",
            i.interface,
            `reset:${id}`,
            node,
            i.interface,
          );
        const dt = old ? r.acquiredMonotonic - old.acquiredMonotonic : 0,
          ok = !!prior && !reset && dt > 0;
        const tx = ok ? (i.tx_packets - prior.tx_packets) / dt : null,
          rx = ok ? (i.rx_packets - prior.rx_packets) / dt : null;
        if (ok) {
          validRate = true;
          totalTx += tx!;
          totalRx += rx!;
        }
        if (r === latestBySource.get(r.incarnation))
          rates.push({
            label: node ? `${node} / ${i.interface}` : i.interface,
            txPackets: tx,
            rxPackets: rx,
            txBytes: ok ? (i.tx_bytes - prior.tx_bytes) / dt : null,
            rxBytes: ok ? (i.rx_bytes - prior.rx_bytes) / dt : null,
          });
      }
      // Per-node totals include all TX/RX directions. For a link, each sender is
      // counted once; receiver copies are deliberately excluded from chart totals.
      if (validRate) {
        const b = bucket(r);
        points[b].primary = scope.type === "link" ? totalTx : totalTx + totalRx;
        points[b].secondary = 0;
      }
    } else {
      const p = r.data,
        node = p.node_id ?? (scope.type === "node" ? scope.id : undefined);
      add(
        r,
        p.message_type === "query"
          ? "Query"
          : p.message_type === "leave"
            ? "Leave"
            : p.message_type === "report_v3"
              ? "IGMPv3 report"
              : "Report",
        `${p.group ?? (p.records.length ? p.records.map((v) => v.group).join(", ") : "General query")}`,
        `igmp`,
        node,
        p.interface,
        `IGMPv${p.version} · ${p.reporter ?? p.querier ?? "sender unavailable"}${p.records.length ? " · " + p.records.map((v) => `type ${v.record_type}: ${v.group} [${v.sources.join(", ")}]`).join("; ") : ""}`,
      );
    }
  }
  const flags = [
    current?.truncated || current?.omitted ? "Response incomplete" : "",
    current?.missedUpdates ? "Updates dropped" : "",
  ].filter(Boolean);
  let status = !current
    ? "Collecting…"
    : current.sourceHealth !== "ok"
      ? healthLabel(current.sourceHealth, kind)
      : !samples.length
        ? kind === "igmp"
          ? "No recent IGMP reports"
          : "Collecting…"
        : rows.length
          ? `${rows.length} recent events`
          : "No changes in the last 60s";
  if (flags.length) status += " · " + flags.join(" · ");
  rows.reverse();
  return {
    sourceHealth: current?.sourceHealth ?? "unknown",
    status,
    rows: rows.slice(0, 256),
    clipped: rows.length > 256,
    summary: `${label} · ${status}`,
    ageMs: latest ? Math.max(0, 60000 - (latest.expiresAt - now)) : null,
    rates,
    sparkline: {
      mode: kind === "interfaces" ? "traffic" : "events",
      points,
      max: Math.max(1, ...points.map((p) => p.primary)),
    },
  };
}
