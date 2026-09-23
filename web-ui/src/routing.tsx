import { useEffect, useRef, useState } from "preact/hooks";
import type { TopologySnapshot } from "./types";

import {
  compareRouting,
  complete,
  freshness as sampleFreshness,
  protocolFacts,
  validateRouting,
  type RoutingEvidence,
  type NodeEvidence,
  type RoutingLayer,
  type ProtocolFact,
} from "./routing-model";
export type { RoutingLayer } from "./routing-model";

export function RoutingLayers({
  snapshot,
  layer,
  onLayer,
  epoch,
  onFacts,
}: {
  snapshot: TopologySnapshot;
  layer: RoutingLayer;
  onLayer: (layer: RoutingLayer) => void;
  epoch: string;
  onFacts: (facts: ProtocolFact[]) => void;
}) {
  const [prefix, setPrefix] = useState(
    snapshot.prefixes?.[0] ?? "10.200.8.0/29",
  );
  const [storedEvidence, setEvidence] = useState<RoutingEvidence | null>(null);
  const [previous, setPrevious] = useState<RoutingEvidence | null>(null);
  const lastGood = useRef<RoutingEvidence | null>(null);
  const scope = useRef("");
  const declaration = JSON.stringify([
    snapshot.nodes.map((n) => [n.id, n.router_id, n.asn, n.ospf_areas]),
    snapshot.peerings,
    snapshot.links.map((l) => [
      l.id,
      l.source,
      l.target,
      l.interfaces,
      l.ospf_area,
    ]),
  ]);
  const scopeKey = `${epoch}:${snapshot.generation}:${prefix}:${declaration}`;
  const evidence = scope.current === scopeKey ? storedEvidence : null;
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
    const nextScope = scopeKey;
    if (scope.current !== nextScope) {
      scope.current = nextScope;
      lastGood.current = null;
      setPrevious(null);
      setEvidence(null);
    }
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
        const value = validateRouting(await response.json(), snapshot, prefix);
        if (!disposed) {
          if (complete(value)) {
            setPrevious(lastGood.current);
            lastGood.current = value;
          }
          setEvidence(value);
        }
      } catch (e) {
        if (!disposed)
          setError(e instanceof Error ? e.message : "Routing unavailable");
      }
    })();
    return () => {
      disposed = true;
      abort.abort();
    };
  }, [scopeKey, refresh, layer]);
  const routers = snapshot.nodes.filter((n) => n.kind === "router");
  const node = (id: string) =>
    evidence?.data.nodes.find((n) => n.node_id === id);
  const freshness = (n?: NodeEvidence) =>
    sampleFreshness(n, snapshot.generation, clock);
  const facts = protocolFacts(snapshot, error ? null : evidence, layer, clock);
  useEffect(() => {
    onFacts(facts);
  }, [snapshot, evidence, error, layer, clock, onFacts]);
  useEffect(() => () => onFacts([]), [onFacts]);
  const changes = error ? null : compareRouting(previous, evidence, clock);
  const times =
    evidence?.data.nodes.map((n) => Date.parse(n.collected_at)) ?? [];
  const skew = times.length ? Math.max(...times) - Math.min(...times) : 0;
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
      {["BGP", "OSPF"].includes(layer) && (
        <>
          <h2>
            {layer === "BGP"
              ? "Declared logical sessions · not physical links"
              : "OSPF interface endpoint observations"}
          </h2>
          <table aria-label={`${layer} endpoint observations`}>
            <thead>
              <tr>
                <th>Relationship</th>
                <th>Independent endpoint observations</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((p) => (
                <tr>
                  <th>
                    {p.source} ↔ {p.target}
                  </th>
                  <td>{p.text}</td>
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
                ? `${evidence.status} · ${evidence.data.collected}/${routers.length} collected`
                : "Collecting…")}
          </span>
        </div>
      )}
      {["BGP", "OSPF", "Prefix"].includes(layer) && (
        <p>
          Collection skew: {skew} ms ·{" "}
          {error
            ? "Refresh failed; retained sample timestamp unchanged"
            : "No atomic cross-node snapshot"}
        </p>
      )}
      {layer === "Prefix" && (
        <section aria-label="Routing comparison">
          <h3>Two-sample comparison</h3>
          {changes === null ? (
            <p>
              {error || (evidence && !complete(evidence))
                ? "Comparison unavailable — failed or partial refresh is not withdrawal"
                : "Need two complete fresh samples in this prefix and generation"}
            </p>
          ) : changes.length ? (
            <ul>
              {changes.map((change) => (
                <li>{change}</li>
              ))}
            </ul>
          ) : (
            <p>No observed changes</p>
          )}
          <small>
            At most two successful samples retained. Stale, truncated or
            cross-generation comparisons are suppressed.
          </small>
        </section>
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
