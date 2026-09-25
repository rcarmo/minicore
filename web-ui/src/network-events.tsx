import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { FloatingPanel } from "./floating-panel";
import type { TopologySnapshot } from "./types";
import {
  buildNetworkEventsModel,
  validateObserverEnvelope,
  type NetworkScope,
  type ObserverKind,
  type ValidatedEnvelope,
} from "./network-events-model";

const buttonStyle = {
  minHeight: "44px",
  minWidth: "44px",
  borderRadius: "999px",
  border: "1px solid rgba(255,255,255,.18)",
  background: "rgba(17,24,39,.72)",
  color: "inherit",
  padding: "0.5rem 0.9rem",
};

function Sparkline({
  model,
}: {
  model: ReturnType<typeof buildNetworkEventsModel>;
}) {
  const width = 180;
  const height = 40;
  const points = model.sparkline.points;
  const max = Math.max(1, model.sparkline.max);
  const path = (secondary = false) =>
    points
      .map((point, index) => {
        const value = secondary ? (point.secondary ?? 0) : point.primary;
        const x = (index / Math.max(1, points.length - 1)) * width;
        const y = height - (value / max) * (height - 4) - 2;
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      aria-label="Recent observer activity sparkline"
      style={{
        display: "block",
        borderRadius: "10px",
        background: "rgba(15,23,42,.7)",
      }}
    >
      <path
        d={`M0,${height - 2} L${width},${height - 2}`}
        stroke="rgba(255,255,255,.1)"
      />
      {!!points.length && (
        <path d={path(false)} fill="none" stroke="#7dd3fc" stroke-width="2" />
      )}
      {!!points.some((point) => point.secondary) && (
        <path d={path(true)} fill="none" stroke="#34d399" stroke-width="2" />
      )}
    </svg>
  );
}

function scopeOptions(snapshot: TopologySnapshot) {
  return [
    ...snapshot.nodes.map((node) => ({
      value: `node:${node.id}`,
      label: `${node.label} node`,
      scope: { type: "node", id: node.id } as NetworkScope,
    })),
    ...snapshot.links.map((link) => ({
      value: `link:${link.id}`,
      label: `${link.source} ↔ ${link.target} link`,
      scope: { type: "link", id: link.id } as NetworkScope,
    })),
  ];
}

export function NetworkEvents({
  snapshot,
  initialScope,
  onInspect,
  onClose,
}: {
  snapshot: TopologySnapshot;
  initialScope: { type: "node" | "link"; id: string };
  onInspect: (node: string, link?: string) => void;
  onClose: () => void;
}) {
  const [scope, setScope] = useState<NetworkScope>(initialScope);
  const [kind, setKind] = useState<ObserverKind>(
    initialScope.type === "link" ? "interfaces" : "routing",
  );
  const [paused, setPaused] = useState(false);
  const [pending, setPending] = useState(0);
  const [clock, setClock] = useState(() => performance.now());
  const [current, setCurrent] = useState<ValidatedEnvelope | null>(null);
  const [previous, setPrevious] = useState<ValidatedEnvelope | null>(null);
  const [failure, setFailure] = useState("");
  const [connection, setConnection] = useState("connecting");
  const [minimized, setMinimized] = useState(false);
  const accepted = useRef<ValidatedEnvelope | null>(null);
  const sourceClock = useRef<{ epoch: string; offset: number } | null>(null);
  const serial = useRef(0);
  const loading = useRef(false);
  const reload = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const lastTopId = useRef<string | null>(null);
  const options = useMemo(() => scopeOptions(snapshot), [snapshot]);
  const scopeValue = `${scope.type}:${scope.id}`;

  useEffect(() => setScope(initialScope), [initialScope.type, initialScope.id]);
  useEffect(() => {
    if (scope.type === "link" && kind === "routing") setKind("interfaces");
  }, [scope.type, kind]);
  useEffect(() => {
    const timer = setInterval(() => {
      const now = performance.now();
      setClock(now);
      if (accepted.current)
        accepted.current = {
          ...accepted.current,
          records: accepted.current.records.filter((r) => r.expiresAt > now),
        };
      setCurrent((v) =>
        v
          ? { ...v, records: v.records.filter((r) => r.expiresAt > now) }
          : null,
      );
      setPrevious((v) =>
        v
          ? { ...v, records: v.records.filter((r) => r.expiresAt > now) }
          : null,
      );
    }, 1000);
    return () => clearInterval(timer);
  }, []);
  const model = useMemo(
    () =>
      buildNetworkEventsModel({
        snapshot,
        scope,
        kind,
        current,
        previous,
        now: clock,
      }),
    [snapshot, scope, kind, current, previous, clock],
  );

  useEffect(() => {
    const top = model.rows[0]?.id ?? null;
    if (!paused && panel.current) panel.current.scrollTop = 0;
    else if (paused && top && lastTopId.current && top !== lastTopId.current)
      setPending((value) => value + 1);
    if (!paused) setPending(0);
    lastTopId.current = top;
  }, [model.rows, paused]);

  useEffect(() => {
    if (minimized) return;
    let disposed = false;
    const identity = `${snapshot.generation}:${scope.type}:${scope.id}:${kind}`;
    setFailure("");
    setCurrent(null);
    setPrevious(null);
    accepted.current = null;
    sourceClock.current = null;
    setPending(0);
    const endpoint = new URL("/api/v1/observer", location.origin);
    endpoint.searchParams.set("scope", scope.type);
    endpoint.searchParams.set(
      kind === "routing" && scope.type === "link"
        ? "link_id"
        : `${scope.type}_id`,
      scope.id,
    );
    if (scope.type === "node") endpoint.searchParams.set("node_id", scope.id);
    if (scope.type === "link") endpoint.searchParams.set("link_id", scope.id);
    endpoint.searchParams.set("kind", kind);

    const load = async () => {
      if (disposed || loading.current) {
        reload.current = true;
        return;
      }
      loading.current = true;
      reload.current = false;
      const requestId = ++serial.current;
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      const started = performance.now();
      try {
        const response = await fetch(endpoint, {
          signal: controller.signal,
          headers: { "Cache-Control": "no-store" },
        });
        const raw = await response.json().catch(() => ({}));
        const finished = performance.now();
        if (disposed || requestId !== serial.current) return;
        if (!response.ok)
          throw new Error(
            typeof raw?.error === "string"
              ? raw.error
              : `HTTP ${response.status}`,
          );
        const validated = validateObserverEnvelope(
          raw,
          snapshot,
          scope,
          kind,
          started,
          finished,
          finished,
        );
        const offset = Math.min(
          ...validated.records.map(
            (r) => r.expiresAt - r.acquiredMonotonic * 1000 - 60000,
          ),
        );
        if (Number.isFinite(offset)) {
          sourceClock.current = {
            epoch: validated.observerEpoch,
            offset:
              sourceClock.current?.epoch === validated.observerEpoch
                ? Math.min(offset, sourceClock.current.offset)
                : offset,
          };
          validated.records = validated.records
            .map((r) => ({
              ...r,
              expiresAt: Math.min(
                r.expiresAt,
                r.acquiredMonotonic * 1000 +
                  60000 +
                  sourceClock.current!.offset,
              ),
            }))
            .filter((r) => r.expiresAt > finished);
        }
        const old = accepted.current;
        const same =
          old &&
          old.observerEpoch === validated.observerEpoch &&
          old.generation === validated.generation &&
          old.scope === validated.scope;
        const prior = new Map(
          same
            ? old.records.map((r) => [
                `${r.incarnation}:${r.acquiredMonotonic}`,
                r.expiresAt,
              ])
            : [],
        );
        const normalized = {
          ...validated,
          records: validated.records.map((r) => ({
            ...r,
            expiresAt: Math.min(
              r.expiresAt,
              prior.get(`${r.incarnation}:${r.acquiredMonotonic}`) ??
                r.expiresAt,
            ),
          })),
        };
        setPrevious(same ? old : null);
        accepted.current = normalized;
        setCurrent(normalized);
        setFailure("");
      } catch (error) {
        if (
          !disposed &&
          requestId === serial.current &&
          !controller.signal.aborted
        )
          setFailure(
            error instanceof Error ? error.message : "Observer unavailable",
          );
      } finally {
        if (!disposed && requestId === serial.current) {
          loading.current = false;
          if (reload.current) void load();
        }
      }
    };

    void load();
    const poll = setInterval(() => void load(), 1000);
    let events: EventSource | null = null;
    try {
      events = new EventSource("/api/v1/observer/events");
      events.onopen = () => setConnection("connected");
      events.onerror = () => setConnection("reconnecting; polling continues");
      const invalidate = () => {
        if (!disposed) void load();
      };
      events.addEventListener("observer.changed", invalidate);
      events.addEventListener("observer.snapshot", invalidate);
    } catch {
      setConnection("polling only");
    }
    return () => {
      disposed = true;
      clearInterval(poll);
      abort.current?.abort();
      abort.current = null;
      loading.current = false;
      reload.current = false;
      events?.close();
      accepted.current = null;
      setCurrent(null);
      setPrevious(null);
      setConnection("connecting");
      lastTopId.current = null;
    };
  }, [snapshot.generation, scope.type, scope.id, kind, minimized]);

  const disabledRouting = scope.type === "link";
  const sourceHealth = current?.sourceHealth ?? "unknown";
  const sourceLabel = (health: string) =>
    ({
      ok: "Live",
      collection_timeout: "Collection timed out",
      collection_failed: "Source disconnected",
      invalid_observation: "Invalid source response",
      source_unavailable: "Source unavailable",
    })[health] ?? "Connecting…";
  const healthText = failure
    ? `Observer unavailable: ${failure}`
    : `${sourceLabel(current?.sourceHealth ?? "")} · ${connection}${model.clipped ? " · List shortened" : ""}`;

  return (
    <FloatingPanel
      title="Network events"
      onMinimize={setMinimized}
      heading={
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            style={buttonStyle}
            aria-label="Close Network events"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      }
    >
      <section
        class="network-events-panel"
        aria-label="Network events panel"
        style={{
          width: "min(38rem, calc(100vw - 2rem))",
          display: "grid",
          gap: "0.75rem",
          color: "#e5eefb",
        }}
      >
        <div style={{ display: "grid", gap: "0.5rem" }}>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span>Scope</span>
            <select
              aria-label="Network event scope"
              value={scopeValue}
              onChange={(event) => {
                const selected = options.find(
                  (option) => option.value === event.currentTarget.value,
                );
                if (selected) setScope(selected.scope);
              }}
              style={{
                minHeight: "44px",
                borderRadius: "12px",
                padding: "0.6rem",
              }}
            >
              {options.map((option) => (
                <option value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <div
            role="tablist"
            aria-label="Network event kinds"
            style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}
          >
            {(["routing", "interfaces", "igmp"] as ObserverKind[]).map(
              (tab) => {
                const disabled = tab === "routing" && disabledRouting;
                return (
                  <button
                    key={tab}
                    role="button"
                    aria-pressed={kind === tab}
                    disabled={disabled}
                    title={
                      disabled
                        ? "Routing is available only for node scopes"
                        : undefined
                    }
                    style={buttonStyle}
                    onClick={() => setKind(tab)}
                  >
                    {tab === "igmp"
                      ? "IGMP"
                      : tab[0]!.toUpperCase() + tab.slice(1)}
                  </button>
                );
              },
            )}
          </div>
          {disabledRouting && kind !== "routing" && (
            <p style={{ margin: 0, opacity: 0.8 }}>
              Select a router for routing events.
            </p>
          )}
        </div>

        <div style={{ display: "grid", gap: "0.35rem" }}>
          <p role="status" style={{ margin: 0 }}>
            {failure ? `Observer unavailable: ${failure}` : model.status}
          </p>
          <p style={{ margin: 0, opacity: 0.82 }}>
            {healthText}
            {model.ageMs !== null
              ? ` · age ${Math.max(0, Math.round(model.ageMs / 1000))}s`
              : ""}
          </p>
          {current?.sources && (
            <p>
              {Object.entries(current.sources).map(([node, status]) => (
                <span>
                  {node}: {sourceLabel(status)}{" "}
                </span>
              ))}
            </p>
          )}
          <Sparkline model={model} />
          {model.rates.length > 0 && (
            <table class="event-rates">
              <thead>
                <tr>
                  <th>Interface</th>
                  <th>TX pkt/s</th>
                  <th>RX pkt/s</th>
                  <th>TX B/s</th>
                  <th>RX B/s</th>
                </tr>
              </thead>
              <tbody>
                {model.rates.map((rate) => (
                  <tr>
                    <th>{rate.label}</th>
                    {[
                      rate.txPackets,
                      rate.rxPackets,
                      rate.txBytes,
                      rate.rxBytes,
                    ].map((v) => (
                      <td>{v === null ? "—" : v.toFixed(1)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            style={buttonStyle}
            aria-pressed={!paused}
            onClick={() => setPaused((value) => !value)}
          >
            {paused ? "Follow" : "Pause"}
          </button>
          <span style={{ alignSelf: "center", opacity: 0.82 }}>
            {paused && pending
              ? `${pending} newer event${pending === 1 ? "" : "s"}`
              : model.summary}
          </span>
        </div>

        <div
          ref={panel}
          class="network-events-rows"
          aria-label="Network event rows"
          tabIndex={0}
          style={{
            maxHeight: "22rem",
            overflow: "auto",
            display: "grid",
            gap: "0.5rem",
            paddingRight: "0.25rem",
          }}
        >
          {!model.rows.length ? (
            <p style={{ margin: 0 }}>
              {failure ? `Observer unavailable: ${failure}` : model.status}
            </p>
          ) : (
            model.rows.map((row) => (
              <article
                key={row.id}
                class="network-events-row"
                style={{
                  border: "1px solid rgba(148,163,184,.24)",
                  borderRadius: "16px",
                  padding: "0.7rem",
                  background: "rgba(15,23,42,.62)",
                  display: "grid",
                  gap: "0.35rem",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.5rem",
                    alignItems: "start",
                  }}
                >
                  <div>
                    <strong>{row.event}</strong>
                    <div style={{ opacity: 0.82 }}>{row.detail}</div>
                  </div>
                  <time
                    dateTime={row.at}
                    style={{ opacity: 0.7, whiteSpace: "nowrap" }}
                  >
                    {new Date(row.at).toLocaleTimeString()}
                  </time>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "0.5rem",
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <small>{row.source}</small>
                  {row.nodeId && (
                    <button
                      style={buttonStyle}
                      aria-label={`Inspect ${row.nodeId}${row.linkId ? ` on ${row.linkId}` : ""}`}
                      onClick={() => onInspect(row.nodeId!, row.linkId)}
                    >
                      Inspect source
                    </button>
                  )}
                </div>
                {row.expanded && (
                  <details>
                    <summary>Details</summary>
                    <p>{row.expanded}</p>
                  </details>
                )}
              </article>
            ))
          )}
        </div>
      </section>
    </FloatingPanel>
  );
}
