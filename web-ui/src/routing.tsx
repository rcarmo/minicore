import { useEffect, useRef, useState } from "preact/hooks";
import { reason } from "./live-node";
import { FloatingPanel } from "./floating-panel";
import { Topology2D } from "./topology-2d";
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
  epoch,
  onFacts,
}: {
  snapshot: TopologySnapshot;
  layer: RoutingLayer;
  epoch: string;
  onFacts: (facts: ProtocolFact[]) => void;
}) {
  const [minimized, setMinimized] = useState(false);
  const [following, setFollowing] = useState(true);
  const [selectedFact, setSelectedFact] = useState<string | null>(null);
  useEffect(() => setSelectedFact(null), [layer, epoch, snapshot.generation]);
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
    if (minimized) return;
    let pending = false;
    const load = async () => {
      if (disposed || pending || document.hidden) return;
      pending = true;
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
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = following ? setInterval(load, 5000) : undefined;
    document.addEventListener("visibilitychange", load);
    return () => {
      disposed = true;
      abort.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, [scopeKey, refresh, layer, following, minimized]);
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
    <FloatingPanel title="Routing diagnostics" onMinimize={setMinimized}>
      <section class="routing-layers" aria-label="Routing layers">
        <p class="live-heading">
          <span class="live-dot" />
          {following ? "Live · refreshes every 5s" : "Paused"}{" "}
          {times.length
            ? `· Updated ${new Date(Math.max(...times)).toLocaleTimeString()}`
            : "· Connecting…"}
        </p>
        <button
          aria-pressed={following}
          onClick={() => setFollowing((v) => !v)}
        >
          {following ? "Pause live routing" : "Follow live routing"}
        </button>
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
            <li>HOST1 / HOST2: endpoints</li>
          </ul>
        )}
        {layer === "OSPF" && (
          <>
            <h2>Area 0 interfaces</h2>
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
              <summary>OSPF response details</summary>
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
            <h2>{layer === "BGP" ? "BGP sessions" : "OSPF neighbours"}</h2>
            <div class="protocol-workbench">
              <Topology2D
                snapshot={snapshot}
                layer={layer}
                facts={facts}
                compact
                selectedFact={selectedFact}
                onFact={setSelectedFact}
              />
              <div class="protocol-table-scroll">
                <table aria-label={`${layer} endpoint observations`}>
                  <thead>
                    <tr>
                      <th>Relationship</th>
                      <th>State at each end</th>
                    </tr>
                  </thead>
                  <tbody>
                    {facts.map((p) => (
                      <tr>
                        <th>
                          <button
                            aria-label={`Inspect ${p.source} ↔ ${p.target}`}
                            aria-pressed={selectedFact === p.id}
                            onClick={() => setSelectedFact(p.id)}
                          >
                            {p.source} ↔ {p.target}
                          </button>
                        </th>
                        <td>{p.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {facts.find((p) => p.id === selectedFact) && (
              <section
                class="relationship-detail"
                aria-label="Selected protocol relationship"
              >
                <p>{facts.find((p) => p.id === selectedFact)!.text}</p>
                <button onClick={() => setSelectedFact(null)}>
                  Clear relationship selection
                </button>
              </section>
            )}
          </>
        )}
        {["BGP", "OSPF", "Prefix"].includes(layer) && (
          <div class="routing-controls">
            <label>
              Prefix{" "}
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
            Collection time range: {skew} ms ·{" "}
            {error
              ? "Refresh failed — showing the last update"
              : "Live collection"}
          </p>
        )}
        {layer === "Prefix" && (
          <section aria-label="Routing comparison">
            <h3>Changes since last update</h3>
            {changes === null ? (
              <p>
                {error || (evidence && !complete(evidence))
                  ? "Comparison unavailable — refresh incomplete"
                  : "Waiting for two fresh updates"}
              </p>
            ) : changes.length ? (
              <ul>
                {changes.map((change) => (
                  <li>{change}</li>
                ))}
              </ul>
            ) : (
              <p>No changes</p>
            )}
            <small>Compares the last two complete updates.</small>
          </section>
        )}
        {layer === "Prefix" && (
          <>
            <h2>Prefix routes</h2>
            <details>
              <summary>Sources</summary>
              <p>
                BGP paths, IP routes, kernel forwarding entries and peer
                exports. Received routes are not collected.
              </p>
            </details>
            <table aria-label="Exact prefix evidence">
              <thead>
                <tr>
                  <th>Router</th>
                  <th>BGP</th>
                  <th>IP RIB</th>
                  <th>Kernel FIB</th>
                  <th>Sent to peers</th>
                </tr>
              </thead>
              <tbody>
                {routers.map((router) => {
                  const n = node(router.id),
                    data = n?.data;
                  const unavailable = n
                    ? reason(n.error_code) || "Waiting for observation"
                    : "Connecting…";
                  const paths = data?.bgp.paths;
                  return (
                    <tr>
                      <th>
                        {router.label}
                        <small>
                          {freshness(n)}
                          <br />
                          {n?.collected_at
                            ? new Date(n.collected_at).toLocaleTimeString()
                            : "Waiting for update"}
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
                        {data
                          ? `${data.fib.length} exact entries`
                          : unavailable}
                      </td>
                      <td>
                        {data
                          ? data.advertised.map((a) => (
                              <div>
                                {a.peer}: {a.present ? "sent" : "not sent"}
                              </div>
                            ))
                          : unavailable}
                        <details>
                          <summary>Response details</summary>
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
    </FloatingPanel>
  );
}
