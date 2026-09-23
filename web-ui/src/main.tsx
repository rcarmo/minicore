import { render } from "preact";
import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import type { ProtocolFact } from "./routing-model";
import { FaultToolbar, useFaultControls } from "./fault-toolbar";
import { FloatingPanel } from "./floating-panel";
import { NetworkScene } from "./graph";
import {
  ControllerState,
  VisibilityToggle,
  useGodCapability,
  useFaultCapability,
  type ViewMode,
} from "./visibility";
import { useActivity } from "./activity";
import { RoutingLayers, type RoutingLayer } from "./routing";
import { LiveNode, useNodeObservations } from "./live-node";
import { NodeRoutes } from "./routes";
import { NodeLogs } from "./logs";
import { NodeConfiguration } from "./configuration";
import { validateSnapshot } from "./topology";
import type { TopologySnapshot } from "./types";
import "./styles.css";

function App() {
  const [facts, setFacts] = useState<ProtocolFact[]>([]);
  const [layer, setLayer] = useState<RoutingLayer>("Physical");
  const [view, setView] = useState<ViewMode>("agent");
  const capable = useGodCapability();
  const faultCapable = useFaultCapability();
  const changeView = (next: ViewMode) => {
    setSnapshot(null);
    setView(next);
  };
  const linkAction = useRef<(id: string) => void>();
  const faultAction = useRef<(id: string | null) => void>();
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<NetworkScene>();
  const [snapshot, setSnapshot] = useState<TopologySnapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(
    location.hash.slice(1) || null,
  );
  const [error, setError] = useState("");
  const [graphError, setGraphError] = useState("");
  const [inspectorMinimized, setInspectorMinimized] = useState(false);
  const [tab, setTab] = useState("Summary");
  const [stream, setStream] = useState("reconnecting");
  const [lastFetched, setLastFetched] = useState("not fetched");
  const activityNodes = useActivity(snapshot?.generation ?? 1);
  useEffect(() => {
    scene.current?.setActivity(activityNodes);
  }, [activityNodes, snapshot]);
  useEffect(() => {
    scene.current?.setLayer(layer);
  }, [layer, snapshot]);
  const updateFacts = useCallback((facts: ProtocolFact[]) => {
    setFacts(facts);
    scene.current?.setProtocolFacts(facts);
  }, []);
  const refreshFault = useCallback(
    () => document.dispatchEvent(new Event("visibilitychange")),
    [],
  );
  const fault = useFaultControls(
    view === "god" && capable && faultCapable,
    snapshot?.generation ?? 1,
    refreshFault,
  );
  const observation = useNodeObservations(
    selectedId ?? undefined,
    snapshot?.generation ?? 1,
    !inspectorMinimized && (tab === "Summary" || tab === "Interfaces"),
  );
  const selected = snapshot?.nodes.find((n) => n.id === selectedId);

  function select(id: string | null) {
    if (id && view === "god" && fault.mode !== "inspect") {
      fault.target("node", id);
      return;
    }
    setSelectedId(id);
    history.replaceState(null, "", id ? `#${id}` : location.pathname);
  }
  faultAction.current = select;
  linkAction.current = (id) => fault.target("link", id);
  useEffect(() => {
    scene.current?.setFaultArmed(
      view === "god" && faultCapable && fault.mode !== "inspect",
    );
  }, [view, faultCapable, fault.mode, snapshot]);

  useEffect(() => {
    setGraphError("");
    try {
      if (!canvas.current?.getContext("webgl2"))
        throw Error("WebGL2 unavailable — use the node and link lists below");
      scene.current = new NetworkScene(
        canvas.current,
        (node) => faultAction.current?.(node?.id ?? null),
        (id) => linkAction.current?.(id),
      );
      if (snapshot) scene.current.setSnapshot(snapshot);
      scene.current.setLayer(layer);
      scene.current.setProtocolFacts(facts);
    } catch (e) {
      setGraphError(e instanceof Error ? e.message : "Graph unavailable");
    }
    return () => {
      scene.current?.dispose();
      scene.current = undefined;
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let pending = false;
    let inFlight = false;
    const abort = new AbortController();
    async function load() {
      if (inFlight) {
        pending = true;
        return;
      }
      inFlight = true;
      try {
        const response = await fetch(`/api/v1/topology?view=${view}`, {
          signal: abort.signal,
        });
        if (!response.ok) {
          if (view === "god" && [401, 403].includes(response.status)) {
            setSnapshot(null);
            setView("agent");
          }
          throw Error(`Topology request failed (${response.status})`);
        }
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
    const events = new EventSource(`/api/v1/events?view=${view}`);
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
    };
  }, [view]);

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
      <div class="view-toolbar">
        <VisibilityToggle view={view} capable={capable} onChange={changeView} />
        <nav aria-label="Network layers">
          {(["Physical", "AS", "OSPF", "BGP", "Prefix"] as RoutingLayer[]).map(
            (name) => (
              <button
                aria-pressed={layer === name}
                onClick={() => setLayer(name)}
              >
                {name}
              </button>
            ),
          )}
        </nav>
      </div>
      {view === "god" && capable && faultCapable && (
        <FaultToolbar control={fault} />
      )}
      <section class="workspace" data-fault-mode={fault.mode}>
        <div class="graph">
          <div class="graph-scene">
            <canvas ref={canvas} aria-label="Interactive network topology" />
          </div>
          <div class="graph-heading">
            <b>
              {snapshot?.nodes.length ?? 0} nodes /{" "}
              {snapshot?.links.length ?? 0} links
            </b>
            <p>
              {snapshot?.nodes.filter((n) => n.container_state === "running")
                .length ?? 0}{" "}
              running · {layer} view
            </p>
          </div>
          <div class="legend">
            Drag: orbit · Right drag: pan · Scroll/pinch: zoom
            <br />
            Dashed: physical connections · Teal: peers connected · Amber:
            disagreement · Muted: awaiting observation
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
        <FloatingPanel
          title="Node inspector"
          kind="inspector"
          onMinimize={setInspectorMinimized}
        >
          <aside aria-label="Node inspector">
            <h2>{selected?.label ?? "Select a node"}</h2>
            {view === "god" && snapshot && (
              <ControllerState
                value={
                  (snapshot as unknown as { controller?: unknown }).controller
                }
              />
            )}

            {selected ? (
              <>
                <p class="role">
                  {selected.role.toUpperCase()} · {selected.kind}
                </p>
                <nav aria-label="Node evidence sections">
                  {[
                    "Summary",
                    "Interfaces",
                    "Routing",
                    "Logs",
                    "Configuration",
                  ].map((name) => (
                    <button
                      aria-pressed={tab === name}
                      onClick={() => setTab(name)}
                    >
                      {name}
                    </button>
                  ))}
                </nav>
                {tab === "Summary" ? (
                  <>
                    <p class="node-runtime">
                      Container{" "}
                      {selected.container_state === "unknown"
                        ? "status pending"
                        : selected.container_state}
                    </p>
                    <LiveNode observation={observation} />
                  </>
                ) : tab === "Interfaces" ? (
                  <LiveNode observation={observation} interfacesOnly />
                ) : tab === "Routing" ? (
                  <NodeRoutes key={selected.id} nodeId={selected.id} />
                ) : tab === "Configuration" ? (
                  <NodeConfiguration key={selected.id} nodeId={selected.id} />
                ) : tab === "Logs" ? (
                  <NodeLogs
                    key={`${selected.id}:${snapshot?.generation}`}
                    nodeId={selected.id}
                    generation={snapshot!.generation}
                    active={!inspectorMinimized}
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
                      (l) =>
                        l.source === selected.id || l.target === selected.id,
                    )
                    .map((l) => (
                      <li key={l.id}>
                        {l.source} ↔ {l.target}
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
                      {n.role} /{" "}
                      {n.container_state === "unknown"
                        ? "waiting for collection"
                        : n.container_state}
                      {activityNodes.includes(n.id) ? " · Agent access" : ""}
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
        </FloatingPanel>
      </section>
      {snapshot && layer !== "Physical" && (
        <RoutingLayers
          key={`${view}:${snapshot.generation}`}
          snapshot={snapshot}
          layer={layer}
          epoch={view}
          onFacts={updateFacts}
        />
      )}
      <footer>
        Runtime collection: {snapshot?.runtime_status ?? "unknown"} · Revision{" "}
        {snapshot?.revision ?? "—"} · Last fetch {lastFetched}
      </footer>
    </main>
  );
}
render(<App />, document.getElementById("app")!);
