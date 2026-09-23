import { reason } from "./live-node";
import { useEffect, useState } from "preact/hooks";
export function NodeConfiguration({ nodeId }: { nodeId: string }) {
  const [files, setFiles] = useState<string[]>([]),
    [selected, setSelected] = useState(""),
    [content, setContent] = useState(""),
    [revision, setRevision] = useState(""),
    [error, setError] = useState(""),
    [redacted, setRedacted] = useState(false);
  const base = `/api/v1/nodes/${encodeURIComponent(nodeId)}/config`;
  useEffect(() => {
    const abort = new AbortController();
    setFiles([]);
    setSelected("");
    setContent("");
    setRevision("");
    setError("");
    fetch(base, { signal: abort.signal })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw Error(body.error_code);
        const data = body.data;
        if (
          data.node_id !== nodeId ||
          data.source !== "declared_baseline" ||
          !Array.isArray(data.files) ||
          data.files.length > 4
        )
          throw Error("Invalid configuration tree");
        const names = data.files.map((f: { name: string }) => f.name);
        if (
          names.some(
            (n: string) => !["frr.conf", "daemons", "network.json"].includes(n),
          )
        )
          throw Error("Invalid configuration file");
        if (!abort.signal.aborted) setFiles(names);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [nodeId]);
  useEffect(() => {
    if (!selected) return;
    const abort = new AbortController();
    setContent("");
    setRevision("");
    setError("");
    fetch(`${base}/${encodeURIComponent(selected)}`, { signal: abort.signal })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw Error(body.error_code);
        const data = body.data;
        if (
          data.node_id !== nodeId ||
          data.name !== selected ||
          data.source !== "declared_baseline" ||
          typeof data.content !== "string" ||
          data.content.length > 32768
        )
          throw Error("Invalid configuration response");
        if (!abort.signal.aborted) {
          setContent(data.content);
          setRevision(data.revision);
          setRedacted(data.redacted);
        }
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      });
    return () => abort.abort();
  }, [nodeId, selected]);
  return (
    <section aria-label={`Configuration for ${nodeId}`}>
      <p class="notice">Saved configuration</p>
      <details>
        <summary>Source details</summary>
        <p>Live running configuration has not been collected.</p>
      </details>
      <nav aria-label="Node configuration files" class="config-tree">
        <strong>configs/{nodeId}/</strong>
        {files.map((name) => (
          <button
            key={name}
            aria-pressed={name === selected}
            onClick={() => setSelected(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {error && <p role="alert">Configuration unavailable: {reason(error)}</p>}
      {selected && (
        <>
          <p class="log-meta">
            {selected} · SHA-256 {revision || "loading"}
            {redacted ? " · secrets hidden" : ""}
          </p>
          <pre class="config-content" aria-label="Configuration file contents">
            {content}
          </pre>
        </>
      )}
    </section>
  );
}
