import { reason } from "./live-node";
import { useEffect, useState } from "preact/hooks";
export function NodeRoutes({ nodeId }: { nodeId: string }) {
  const [result, setResult] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    setLoading(true);
    setError("");
    setResult(null);
    const load = async () => {
      if (pending || document.hidden || controller.signal.aborted) return;
      pending = true;
      try {
        const response = await fetch(
          `/api/v1/nodes/${encodeURIComponent(nodeId)}/routes`,
          { signal: controller.signal },
        );
        const data = await response.json();
        if (controller.signal.aborted) return;
        if (data.node_id !== nodeId || !("data" in data))
          throw Error("Invalid route response");
        setResult(data);
        setError(
          !response.ok || data.error_code
            ? reason(data.error_code ?? "Route query failed")
            : "",
        );
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Could not load routes");
      } finally {
        pending = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [nodeId]);
  return (
    <section aria-label={`Routes for ${nodeId}`}>
      <p class="notice">
        {loading
          ? "Collecting routes…"
          : error
            ? `Routing unavailable: ${error}`
            : "Live routes · refreshes every 5s"}
      </p>
      {result && (
        <>
          <p class="log-meta">
            Updated {new Date(result.collected_at).toLocaleTimeString()} ·{" "}
            {result.duration_ms} ms
          </p>
          {!error && (
            <pre aria-label="Node routing evidence" class="config-content">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          )}
          <details>
            <summary>Response details</summary>
            <pre class="config-content">{result.raw_evidence}</pre>
          </details>
        </>
      )}
    </section>
  );
}
