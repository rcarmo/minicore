import { useEffect, useState } from "preact/hooks";
import type { TopologySnapshot } from "./types";

export type RoutingLayer = "Physical" | "AS" | "OSPF" | "BGP" | "Prefix";
type RecordValue = Record<string, unknown>;
type NodeEvidence = {
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
type RoutingEvidence = {
  generation: number;
  status: string;
  data: {
    prefix: string;
    nodes: NodeEvidence[];
    collected: number;
    atomic: false;
  };
};

export function RoutingLayers({
  snapshot,
  layer,
  onLayer,
  epoch,
}: {
  snapshot: TopologySnapshot;
  layer: RoutingLayer;
  onLayer: (layer: RoutingLayer) => void;
  epoch: string;
}) {
  const [prefix, setPrefix] = useState(
    snapshot.prefixes?.[0] ?? "10.200.8.0/29",
  );
  const [evidence, setEvidence] = useState<RoutingEvidence | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let disposed = false;
    const abort = new AbortController();
    setEvidence(null);
    setError("");
    if (!["BGP", "OSPF", "Prefix"].includes(layer)) return;
    void (async () => {
      try {
        const response = await fetch(
          `/api/v1/routing?prefix=${encodeURIComponent(prefix)}`,
          { signal: abort.signal },
        );
        if (!response.ok)
          throw Error(`Routing request failed (${response.status})`);
        const value = (await response.json()) as RoutingEvidence;
        if (
          value.generation !== snapshot.generation ||
          value.data?.prefix !== prefix ||
          !Array.isArray(value.data.nodes) ||
          value.data.nodes.length !== 6
        )
          throw Error("Invalid routing snapshot");
        if (!disposed) setEvidence(value);
      } catch (e) {
        if (!disposed)
          setError(e instanceof Error ? e.message : "Routing unavailable");
      }
    })();
    return () => {
      disposed = true;
      abort.abort();
    };
  }, [prefix, snapshot.generation, refresh, layer, epoch]);
  const routers = snapshot.nodes.filter((n) => n.kind === "router");
  const node = (id: string) =>
    evidence?.data.nodes.find((n) => n.node_id === id);
  const freshness = (n?: NodeEvidence) =>
    !n
      ? "not collected"
      : n.generation !== snapshot.generation
        ? "prior generation"
        : clock - Date.parse(n.collected_at) > 30000
          ? "stale"
          : "fresh";
  const bgpState = (id: string, address: string) => {
    const n = node(id);
    if (!n?.data || n.error_code) return n?.error_code ?? "not collected";
    const family = n.data.bgp_peers.ipv4Unicast as
      | { peers?: Record<string, { state?: string }> }
      | undefined;
    return `${family?.peers?.[address]?.state ?? "unknown"} · ${freshness(n)}`;
  };
  return (
    <section class="routing-layers" aria-label="Routing layers">
      <nav aria-label="Network layers">
        {(["Physical", "AS", "OSPF", "BGP", "Prefix"] as RoutingLayer[]).map(
          (value) => (
            <button
              aria-pressed={value === layer}
              onClick={() => onLayer(value)}
            >
              {value}
            </button>
          ),
        )}
      </nav>
      <p>
        Declared topology from inventory · overlays do not prove reachability.
        Observations are non-atomic, on demand; stale after 30s.
      </p>
      {layer === "AS" && (
        <ul>
          {[65000, 65001, 65002].map((asn) => (
            <li>
              AS {asn}:{" "}
              {routers
                .filter((n) => n.asn === asn)
                .map((n) => n.label)
                .join(", ")}
            </li>
          ))}
          <li>HOST1 / HOST2: attached endpoints, not BGP speakers</li>
        </ul>
      )}
      {layer === "OSPF" && (
        <>
          <h2>Declared area 0 interfaces</h2>
          <ul>
            {snapshot.links
              .filter((l) => l.ospf_area === "0")
              .map((l) => (
                <li>
                  {l.source} ({l.interfaces?.[0]}) ↔ {l.target} (
                  {l.interfaces?.[1]}) · area 0
                </li>
              ))}
          </ul>
          <details>
            <summary>
              Per-node OSPF observations — no inferred link health
            </summary>
            {routers.map((n) => (
              <div>
                <b>
                  {n.label} · {freshness(node(n.id))}
                </b>
                <pre>
                  {JSON.stringify(
                    node(n.id)?.data?.ospf_neighbors ?? {
                      status: node(n.id)?.error_code ?? "not collected",
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            ))}
          </details>
        </>
      )}
      {layer === "BGP" && (
        <>
          <h2>Declared logical sessions · not physical links</h2>
          <table aria-label="BGP endpoint observations">
            <thead>
              <tr>
                <th>Relationship</th>
                <th>Source observation</th>
                <th>Target observation</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.peerings?.map((p) => (
                <tr>
                  <th>
                    {p.source} ↔ {p.target} · {p.kind}
                  </th>
                  <td>{bgpState(p.source, p.target_address)}</td>
                  <td>{bgpState(p.target, p.source_address)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {["BGP", "OSPF", "Prefix"].includes(layer) && (
        <div class="routing-controls">
          <label>
            One prefix{" "}
            <select
              value={prefix}
              onChange={(e) => setPrefix(e.currentTarget.value)}
            >
              {snapshot.prefixes?.map((p) => (
                <option>{p}</option>
              ))}
            </select>
          </label>
          <button onClick={() => setRefresh((v) => v + 1)}>
            Collect routing evidence
          </button>
          <span role="status">
            {error ||
              (evidence
                ? `${evidence.status} · ${evidence.data.collected}/6 collected`
                : "Collecting…")}
          </span>
        </div>
      )}
      {layer === "Prefix" && (
        <>
          <h2>Exact prefix visibility</h2>
          <p>
            BGP paths ≠ IP RIB entries ≠ kernel forwarding entries ≠ sender
            advertisements. Received pre-policy routes: not collected.
          </p>
          <table aria-label="Exact prefix evidence">
            <thead>
              <tr>
                <th>Router / source</th>
                <th>BGP</th>
                <th>IP RIB</th>
                <th>Kernel FIB</th>
                <th>Peer exports</th>
              </tr>
            </thead>
            <tbody>
              {routers.map((router) => {
                const n = node(router.id),
                  data = n?.data;
                const unavailable = n?.error_code ?? "not collected";
                const paths = data?.bgp.paths;
                return (
                  <tr>
                    <th>
                      {router.label}
                      <small>
                        {n?.source ?? "node_dispatcher"} · {freshness(n)}
                        <br />
                        {n?.collected_at ?? "not collected"}
                      </small>
                    </th>
                    <td>
                      {data
                        ? `${Array.isArray(paths) ? paths.length : "unknown"} paths`
                        : unavailable}
                    </td>
                    <td>
                      {data
                        ? Object.hasOwn(data.rib, prefix)
                          ? "exact entry"
                          : "absent (exact)"
                        : unavailable}
                    </td>
                    <td>
                      {data ? `${data.fib.length} exact entries` : unavailable}
                    </td>
                    <td>
                      {data
                        ? data.advertised.map((a) => (
                            <div>
                              {a.peer}:{" "}
                              {a.present ? "advertised" : "not advertised"} ·{" "}
                              {a.source}
                            </div>
                          ))
                        : unavailable}
                      <details>
                        <summary>Observation detail</summary>
                        <pre>
                          {JSON.stringify(
                            n ?? { status: "not collected" },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
