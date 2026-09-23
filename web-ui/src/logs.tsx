import { reason } from "./live-node";
import { useEffect, useRef, useState } from "preact/hooks";

export interface LogEntry {
  id: string;
  timestamp: string;
  source: string;
  severity: "error" | "warning" | "info" | "unknown";
  message: string;
  truncated: boolean;
}
export interface LogPage {
  node_id: string;
  generation: number;
  collected_at: string | null;
  status: string;
  error_code: string | null;
  truncated: boolean;
  data: {
    entries: LogEntry[];
    next_cursor: string | null;
    revision: string;
    source: string;
    window_start: string | null;
    window_end: string | null;
    retained_count: number;
  };
}

export function validateLogPage(value: unknown, node: string): LogPage {
  const page = value as LogPage;
  if (
    !page ||
    page.node_id !== node ||
    !Number.isInteger(page.generation) ||
    !["ok", "unavailable"].includes(page.status) ||
    !page.data ||
    !Array.isArray(page.data.entries) ||
    page.data.entries.length > 500 ||
    typeof page.data.revision !== "string" ||
    (page.data.next_cursor !== null &&
      typeof page.data.next_cursor !== "string")
  )
    throw Error("Invalid log response");
  const ids = new Set<string>();
  for (const row of page.data.entries) {
    if (
      !row ||
      typeof row.id !== "string" ||
      ids.has(row.id) ||
      typeof row.timestamp !== "string" ||
      typeof row.message !== "string" ||
      row.message.length > 4096 ||
      row.source !== "container" ||
      !["error", "warning", "info", "unknown"].includes(row.severity)
    )
      throw Error("Invalid log entry");
    ids.add(row.id);
  }
  return page;
}

/** Remount on node/generation change: no response or cursor may cross that boundary. */
export function NodeLogs({
  nodeId,
  generation,
  active = true,
}: {
  nodeId: string;
  generation: number;
  active?: boolean;
}) {
  const [page, setPage] = useState<LogPage | null>(null);
  const [following, setFollowing] = useState(true);
  const follow = useRef(true);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState("");
  const [connection, setConnection] = useState("connecting");
  const [severity, setSeverity] = useState("all");
  const panel = useRef<HTMLDivElement>(null);
  const fetchPage = useRef<(cursor?: string | null) => void>(() => {});
  const cancelFetch = useRef<() => void>(() => {});

  useEffect(() => {
    if (!active) return;
    let disposed = false;
    let serial = 0;
    let controller: AbortController | undefined;
    let lastRevision: string | null = null;
    const endpoint = `/api/v1/nodes/${encodeURIComponent(nodeId)}/logs`;
    const load = async (cursor?: string | null) => {
      const request = ++serial;
      controller?.abort();
      controller = new AbortController();
      setLoading(true);
      try {
        const response = await fetch(
          endpoint + (cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""),
          { signal: controller.signal },
        );
        const raw = await response.json();
        if (disposed || request !== serial) return;
        if (!response.ok && !raw.data)
          throw Error(raw.error_code ?? `HTTP ${response.status}`);
        const next = validateLogPage(raw, nodeId);
        if (next.generation !== generation)
          throw Error("generation_mismatch — refresh topology");
        setPage(next);
        setFailure("");
        setPending(false);
        lastRevision = next.data.revision;
        if (panel.current && follow.current) panel.current.scrollTop = 0;
      } catch (e) {
        if (!disposed && request === serial)
          setFailure(e instanceof Error ? e.message : "Log request failed");
      } finally {
        if (!disposed && request === serial) setLoading(false);
      }
    };
    fetchPage.current = load;
    cancelFetch.current = () => {
      serial++;
      controller?.abort();
      setLoading(false);
    };
    void load();
    const events = new EventSource(endpoint + "/events");
    events.onopen = () => setConnection("connected");
    events.onerror = () => setConnection("reconnecting; polling continues");
    const changed = (event: Event) => {
      try {
        const state = JSON.parse((event as MessageEvent).data);
        if (state.node_id !== nodeId) return;
        if (follow.current) void load();
        else if (state.revision !== lastRevision || state.error_code)
          setPending(true);
      } catch {
        setFailure("Log update interrupted; checking again");
      }
    };
    events.addEventListener("logs.snapshot", changed);
    events.addEventListener("logs.changed", changed);
    const timer = setInterval(() => {
      if (follow.current) void load();
    }, 5000);
    return () => {
      disposed = true;
      serial++;
      controller?.abort();
      clearInterval(timer);
      events.close();
    };
  }, [nodeId, generation, active]);

  function toggleFollow() {
    const next = !follow.current;
    follow.current = next;
    setFollowing(next);
    if (next) fetchPage.current();
    else cancelFetch.current();
  }
  function older() {
    follow.current = false;
    setFollowing(false);
    fetchPage.current(page?.data.next_cursor);
  }
  const rows =
    page?.data.entries.filter(
      (e) => severity === "all" || e.severity === severity,
    ) ?? [];
  const status = failure
    ? `Logs unavailable: ${reason(failure)}`
    : page?.error_code
      ? `Logs unavailable: ${reason(page.error_code)}`
      : loading && !page
        ? "Loading node logs…"
        : page?.data.entries.length === 0
          ? "No events in this window"
          : `${page?.data.entries.length ?? 0} recent entries`;
  return (
    <section aria-label={`Logs for ${nodeId}`} class="logs-panel">
      <div class="log-controls">
        <button aria-pressed={following} onClick={toggleFollow}>
          {following ? "Pause" : "Follow latest"}
        </button>
        <button disabled={loading} onClick={() => fetchPage.current()}>
          Latest
        </button>
        <button disabled={loading || !page?.data.next_cursor} onClick={older}>
          Older
        </button>
        <label>
          Severity{" "}
          <select
            value={severity}
            onChange={(e) => setSeverity(e.currentTarget.value)}
          >
            <option value="all">All</option>
            {["error", "warning", "info", "unknown"].map((s) => (
              <option value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {pending && (
        <p class="log-new">
          New log entries available. Choose Follow latest to show them.
        </p>
      )}
      <p role="status" class="notice">
        {status}
      </p>
      <p class="log-meta">
        <span class="live-dot" />
        {following ? "Live stream" : "Paused"} ·{" "}
        {connection === "connected" ? "Connected" : connection}
        <br />
        Updated{" "}
        {page?.collected_at
          ? new Date(page.collected_at).toLocaleTimeString()
          : "waiting for collector"}{" "}
        · 15-minute window
        {page?.truncated ? " · truncated" : ""}
        {page?.error_code && rows.length ? " · showing earlier entries" : ""}
      </p>
      <div
        ref={panel}
        class="log-rows"
        tabIndex={0}
        aria-label="Node log entries"
      >
        {rows.map((entry) => (
          <article
            key={entry.id}
            class="log-entry"
            data-severity={entry.severity}
          >
            <div>
              <time dateTime={entry.timestamp}>{entry.timestamp}</time>{" "}
              <strong>{entry.severity}</strong>
            </div>
            <pre>
              {entry.message}
              {entry.truncated ? " [truncated]" : ""}
            </pre>
          </article>
        ))}
      </div>
    </section>
  );
}
