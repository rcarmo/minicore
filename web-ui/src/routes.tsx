import { useEffect, useState } from "preact/hooks";
export function NodeRoutes({ nodeId }: { nodeId: string }) {
  const [result, setResult] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setResult(null);
    fetch(`/api/v1/nodes/${encodeURIComponent(nodeId)}/routes`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json();
        if (controller.signal.aborted) return;
        if (data.node_id !== nodeId || !("data" in data))
          throw Error("invalid_route_response");
        setResult(data);
        if (!response.ok || data.error_code)
          setError(data.error_code ?? "route_query_failed");
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [nodeId]);
  return (
    <section aria-label={`Routes for ${nodeId}`}>
      <p class="notice">
        {loading
          ? "Collecting routes…"
          : error
            ? `Routing evidence unavailable: ${error}`
            : "Observed IPv4 routing table"}
      </p>
      {result && (
        <>
          <p class="log-meta">
            Node {nodeId} · {result.collected_at} · generation{" "}
            {result.generation} · {result.duration_ms} ms
          </p>
          {!error && (
            <pre aria-label="Node routing evidence" class="config-content">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          )}
          <details>
            <summary>Raw route evidence</summary>
            <pre class="config-content">{result.raw_evidence}</pre>
          </details>
        </>
      )}
    </section>
  );
}
