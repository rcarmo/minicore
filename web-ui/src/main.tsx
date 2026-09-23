import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { NetworkScene } from "./graph";
import { NodeLogs } from "./logs";
import { validateSnapshot } from "./topology";
import type { TopologySnapshot } from "./types";
import "./styles.css";

function App() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<NetworkScene>();
  const [snapshot, setSnapshot] = useState<TopologySnapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(
    location.hash.slice(1) || null,
  );
  const [error, setError] = useState("");
  const [graphError, setGraphError] = useState("");
  const [tab, setTab] = useState("Summary");
  const [stream, setStream] = useState("reconnecting");
  const [lastFetched, setLastFetched] = useState("not fetched");
  const selected = snapshot?.nodes.find((n) => n.id === selectedId);

  function select(id: string | null) {
    setSelectedId(id);
    history.replaceState(null, "", id ? `#${id}` : location.pathname);
  }

  useEffect(() => {
    let disposed = false;
    let pending = false;
    let inFlight = false;
    const abort = new AbortController();
    try {
      if (!canvas.current?.getContext("webgl2"))
        throw Error("WebGL2 unavailable — use the node and link lists below");
      scene.current = new NetworkScene(canvas.current, (node) =>
        select(node?.id ?? null),
      );
    } catch (e) {
      setGraphError(e instanceof Error ? e.message : "Graph unavailable");
    }
    async function load() {
      if (inFlight) {
        pending = true;
        return;
      }
      inFlight = true;
      try {
        const response = await fetch("/api/v1/topology", {
          signal: abort.signal,
        });
        if (!response.ok)
          throw Error(`Topology request failed (${response.status})`);
        const next = validateSnapshot(await response.json());
        if (disposed) return;
        setSnapshot(next);
        scene.current?.setSnapshot(next);
        setLastFetched(new Date().toISOString());
        setError("");
      } catch (e) {
        if (!disposed)
          setError(e instanceof Error ? e.message : "Topology unavailable");
      } finally {
        inFlight = false;
        if (pending && !disposed) {
          pending = false;
          void load();
        }
      }
    }
    void load();
    const poll = setInterval(load, 15000);
    const events = new EventSource("/api/v1/events");
    events.onopen = () => setStream("connected");
    events.onerror = () => setStream("reconnecting; polling continues");
    events.addEventListener("topology.changed", load);
    events.addEventListener("topology.snapshot", load);
    const resume = () => {
      if (!document.hidden) void load();
    };
    document.addEventListener("visibilitychange", resume);
    return () => {
      disposed = true;
      abort.abort();
      clearInterval(poll);
      events.close();
      document.removeEventListener("visibilitychange", resume);
      scene.current?.dispose();
    };
  }, []);

  useEffect(() => {
    scene.current?.select(selectedId);
  }, [selectedId, snapshot]);

  return (
    <main>
      <header>
        <div>
          <strong>MINICORE</strong>
          <span>Network workbench</span>
        </div>
        <dl>
          <dt>Lab</dt>
          <dd>{snapshot?.lab_id ?? "loading"}</dd>
          <dt>Generation</dt>
          <dd>{snapshot?.generation ?? "—"}</dd>
          <dt>Updates</dt>
          <dd data-state={stream}>{stream}</dd>
        </dl>
      </header>
      <section class="workspace">
        <div class="graph">
          <canvas ref={canvas} aria-label="Interactive network topology" />
          <div class="graph-heading">
            <b>
              {snapshot?.nodes.length ?? 0} nodes /{" "}
              {snapshot?.links.length ?? 0} links
            </b>
            <p>Expected topology · observed routing unknown</p>
          </div>
          <div class="legend">
            Drag: orbit · Right drag: pan · Scroll/pinch: zoom
            <br />
            Dashed links: expected, not observed
          </div>
          <div class="graph-tools">
            <button onClick={() => scene.current?.reset()}>Reset view</button>
          </div>
          {(error || graphError) && (
            <div class="error" role="alert">
              {error || graphError}
            </div>
          )}
        </div>
        <aside aria-label="Node inspector">
          <h2>{selected?.label ?? "Select a node"}</h2>
          {selected ? (
            <>
              <p class="role">
                {selected.role.toUpperCase()} · {selected.kind}
              </p>
              <nav aria-label="Node evidence sections">
                {["Summary", "Interfaces", "Routing", "Logs"].map((name) => (
                  <button
                    aria-pressed={tab === name}
                    onClick={() => setTab(name)}
                  >
                    {name}
                  </button>
                ))}
              </nav>
              {tab === "Summary" ? (
                <dl>
                  <dt>Observed state</dt>
                  <dd>{selected.state}</dd>
                  <dt>Container</dt>
                  <dd>{selected.container_state ?? "unknown"}</dd>
                  <dt>Expected</dt>
                  <dd>yes</dd>
                  <dt>Protocols</dt>
                  <dd>{selected.protocols.join(", ") || "none"}</dd>
                  <dt>Observed at</dt>
                  <dd>{selected.observed_at ?? "not collected"}</dd>
                </dl>
              ) : tab === "Logs" ? (
                <NodeLogs
                  key={`${selected.id}:${snapshot?.generation}`}
                  nodeId={selected.id}
                  generation={snapshot!.generation}
                />
              ) : (
                <p class="notice">
                  {tab} evidence unavailable: backend_not_configured
                </p>
              )}
              <h3>Connections</h3>
              <ul>
                {snapshot?.links
                  .filter(
                    (l) => l.source === selected.id || l.target === selected.id,
                  )
                  .map((l) => (
                    <li key={l.id}>
                      {l.source} ↔ {l.target} <small>({l.state})</small>
                    </li>
                  ))}
              </ul>
            </>
          ) : (
            <p>Choose a device to browse its state, connections and logs.</p>
          )}
          <details open={!selected || !!graphError}>
            <summary>All nodes · accessible view</summary>
            <ul class="node-list">
              {snapshot?.nodes.map((n) => (
                <li key={n.id}>
                  <button
                    onClick={() => select(n.id)}
                    aria-pressed={n.id === selectedId}
                  >
                    {n.label}
                  </button>{" "}
                  <small>
                    {n.role} / {n.state}
                  </small>
                </li>
              ))}
            </ul>
          </details>
          <details>
            <summary>All connections</summary>
            <ul>
              {snapshot?.links.map((l) => (
                <li key={l.id}>
                  {l.source} ↔ {l.target}
                </li>
              ))}
            </ul>
          </details>
        </aside>
      </section>
      <footer>
        Runtime collection: {snapshot?.runtime_status ?? "unknown"} · Revision{" "}
        {snapshot?.revision ?? "—"} · Last fetch {lastFetched}
      </footer>
    </main>
  );
}
render(<App />, document.getElementById("app")!);
