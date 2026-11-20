import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { FloatingPanel } from "./floating-panel";
import type { TopologySnapshot } from "./types";
import {
  buildNetworkEventsModel,
  validateObserverEnvelope,
  type NetworkScope,
  type ObserverKind,
  type TrafficPoint,
  type ValidatedEnvelope,
} from "./network-events-model";

function EventSparkline({ counts }: { counts: number[] }) {
  const width = 180;
  const height = 40;
  const max = Math.max(1, ...counts);
  const path = counts
    .map((value, index) => {
      const x = (index / (counts.length - 1)) * width;
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
      class="event-sparkline"
    >
      <path
        d={`M0,${height - 2} L${width},${height - 2}`}
        stroke="rgba(255,255,255,.1)"
      />
      <path d={path} fill="none" stroke="#7dd3fc" stroke-width="2" />
    </svg>
  );
}

function InterfaceTraffic({
  label,
  history,
}: {
  label: string;
  history: TrafficPoint[];
}) {
  const tx = history.flatMap((p) =>
    p.txPackets === null ? [] : [p.txPackets],
  );
  const rx = history.flatMap((p) =>
    p.rxPackets === null ? [] : [p.rxPackets],
  );
  if (!tx.length && !rx.length)
    return <span class="event-meta">No samples</span>;
  const txPeak = Math.max(0, ...tx);
  const rxPeak = Math.max(0, ...rx);
  const scale = Math.max(1, Math.ceil(Math.max(txPeak, rxPeak)));
  const description = `${label}, last 60 seconds: TX peak ${txPeak.toFixed(1)}, RX peak ${rxPeak.toFixed(1)} packets per second`;
  const path = (direction: "txPackets" | "rxPackets") => {
    let priorAge: number | undefined;
    return history
      .map((point) => {
        const value = point[direction];
        if (value === null) {
          priorAge = undefined;
          return "";
        }
        const x = 1 + (1 - point.ageSeconds / 60) * 118;
        const y = 21 - (value / scale) * 19;
        const position = `${x.toFixed(1)},${y.toFixed(1)}`;
        const segment =
          priorAge !== undefined && priorAge - point.ageSeconds <= 3
            ? `L${position}`
            : `M${position}h0.1`;
        priorAge = point.ageSeconds;
        return segment;
      })
      .join(" ");
  };
  return (
    <div class="traffic-history">
      <svg viewBox="0 0 120 24" role="img" aria-label={description}>
        <title>{description}</title>
        <path class="traffic-axis" d="M1 21H119" />
        <path class="traffic-tx" d={path("txPackets")} />
        <path class="traffic-rx" d={path("rxPackets")} />
      </svg>
      <span class="event-meta" aria-hidden="true">
        0–{scale}
      </span>
    </div>
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
        <button aria-label="Close Network events" onClick={onClose}>
          Close
        </button>
      }
    >
      <section class="network-events-panel" aria-label="Network events panel">
        <div class="event-controls">
          <label class="event-scope">
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
            >
              {options.map((option) => (
                <option value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <div
            role="tablist"
            aria-label="Network event kinds"
            class="event-kinds"
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
            <p class="event-scope-hint">Select a router for routing events.</p>
          )}
        </div>

        <div class="event-evidence">
          <p role="status">
            {failure ? `Observer unavailable: ${failure}` : model.status}
          </p>
          <p class="event-meta">
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
          {current?.captureErrors &&
            Object.keys(current.captureErrors).length > 0 && (
              <p class="source-loss">
                {Object.entries(current.captureErrors).map(([name, count]) => (
                  <span>
                    {name.replaceAll("_", " ")}: {count}{" "}
                  </span>
                ))}
              </p>
            )}
          {kind !== "interfaces" && (
            <EventSparkline counts={model.eventCounts} />
          )}
          {model.rates.length > 0 && (
            <div class="event-rates-scroll">
              <table
                class="event-rates"
                aria-label="Interface rates and traffic history"
              >
                <thead>
                  <tr>
                    <th>Interface</th>
                    <th>TX pkt/s</th>
                    <th>RX pkt/s</th>
                    <th>TX B/s</th>
                    <th>RX B/s</th>
                    <th>
                      Last 60s · pkt/s{" "}
                      <span class="event-meta">(TX solid, RX dashed)</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {model.rates.map((rate) => (
                    <tr key={rate.label}>
                      <th scope="row">{rate.label}</th>
                      {[
                        rate.txPackets,
                        rate.rxPackets,
                        rate.txBytes,
                        rate.rxBytes,
                      ].map((v, index) => (
                        <td key={index}>{v === null ? "—" : v.toFixed(1)}</td>
                      ))}
                      <td>
                        <InterfaceTraffic
                          label={rate.label}
                          history={rate.history}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div class="event-follow">
          <button
            aria-pressed={!paused}
            onClick={() => setPaused((value) => !value)}
          >
            {paused ? "Follow" : "Pause"}
          </button>
          <span class="event-meta">
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
        >
          {!model.rows.length ? (
            <p>{failure ? `Observer unavailable: ${failure}` : model.status}</p>
          ) : (
            model.rows.map((row) => (
              <article key={row.id} class="network-events-row">
                <div class="event-row-heading">
                  <div>
                    <strong>{row.event}</strong>
                    <div class="event-meta">{row.detail}</div>
                  </div>
                  <time dateTime={row.at}>
                    {new Date(row.at).toLocaleTimeString()}
                  </time>
                </div>
                <div class="event-row-actions">
                  <small>{row.source}</small>
                  {row.nodeId && (
                    <button
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
