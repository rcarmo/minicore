import { useEffect, useState } from "preact/hooks";
export function reason(code: string | null | undefined) {
  const reasons: Record<string, string> = {
    backend_not_configured: "Live collector not connected",
    collector_stale: "Collector stopped or delayed",
    node_unavailable: "Node unreachable",
    execution_timeout: "Collection timed out",
    ssh_authentication_failed: "Node authentication failed",
    host_key_mismatch: "Node identity check failed",
    parse_failure: "Invalid response from node",
    protocol_not_enabled: "Not enabled on this node",
    generation_changed: "Lab reset — refreshing",
    generation_mismatch: "Lab reset — refreshing",
    network_unreachable: "No route to destination",
    output_limit: "Response exceeded the collection limit",
  };
  return code ? (reasons[code] ?? code.replaceAll("_", " ")) : "";
}
type Source = {
  data: any;
  collected_at: string;
  error_code: string | null;
  source: string;
  generation: number;
  truncated?: boolean;
};
type Observations = {
  node_id: string;
  generation: number;
  data: { interfaces: Source; bgp: Source; ospf: Source };
};
export function useNodeObservations(
  nodeId: string | undefined,
  generation: number,
  enabled: boolean,
) {
  const [value, setValue] = useState<Observations | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    setValue(null);
    setError("");
    if (!nodeId || !enabled) return;
    let disposed = false,
      pending = false;
    const abort = new AbortController();
    const load = async () => {
      if (disposed || pending || document.hidden) return;
      pending = true;
      try {
        const r = await fetch(
          `/api/v1/nodes/${encodeURIComponent(nodeId)}/observations`,
          { signal: abort.signal },
        );
        if (!r.ok) throw Error(`Live inspection failed (${r.status})`);
        const v = (await r.json()) as Observations;
        if (
          v.node_id !== nodeId ||
          v.generation !== generation ||
          !v.data?.interfaces ||
          !v.data?.bgp ||
          !v.data?.ospf
        )
          throw Error("Invalid live observation");
        if (!disposed) {
          setValue(v);
          setError("");
        }
      } catch (e) {
        if (!disposed)
          setError(e instanceof Error ? e.message : "Node inspection failed");
      } finally {
        pending = false;
      }
    };
    void load();
    const timer = setInterval(load, 5000);
    document.addEventListener("visibilitychange", load);
    return () => {
      disposed = true;
      abort.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, [nodeId, generation, enabled]);
  return {
    value:
      value && value.node_id === nodeId && value.generation === generation
        ? value
        : null,
    error,
  };
}
export function LiveNode({
  observation,
  interfacesOnly = false,
}: {
  observation: ReturnType<typeof useNodeObservations>;
  interfacesOnly?: boolean;
}) {
  const { value, error } = observation;
  const interfaces = value?.data.interfaces;
  const list = Array.isArray(interfaces?.data) ? interfaces.data : [];
  return (
    <section class="live-node" aria-label="Live node observations">
      <p class="live-heading">
        <span class="live-dot" /> Live · refreshes every 5s
      </p>
      {error && (
        <p role="alert">{error} — last successful observations retained</p>
      )}
      {!value ? (
        <p>Connecting to node…</p>
      ) : (
        <>
          <small>
            Updated {new Date(interfaces!.collected_at).toLocaleTimeString()}
          </small>
          {interfaces?.error_code ? (
            <p>{reason(interfaces.error_code)}</p>
          ) : (
            <table aria-label="Live interfaces">
              <thead>
                <tr>
                  <th>Interface</th>
                  <th>State</th>
                  <th>Address</th>
                </tr>
              </thead>
              <tbody>
                {list.map((i: any) => (
                  <tr>
                    <th>{i.ifname}</th>
                    <td>
                      {i.operstate ?? (i.flags?.includes("UP") ? "UP" : "DOWN")}
                    </td>
                    <td>
                      {(i.addr_info ?? [])
                        .map((a: any) => `${a.local}/${a.prefixlen}`)
                        .join(", ") || "No address"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!interfacesOnly &&
            (["bgp", "ospf"] as const).map((protocol) => {
              const source = value.data[protocol];
              const peers =
                protocol === "bgp"
                  ? Object.entries(source.data?.ipv4Unicast?.peers ?? {})
                  : Object.entries(source.data ?? {});
              return (
                <div>
                  <h3>{protocol.toUpperCase()}</h3>
                  {source.error_code ? (
                    <p>{reason(source.error_code)}</p>
                  ) : peers.length ? (
                    <ul class="peer-list">
                      {peers.map(([peer, data]: [string, any]) => (
                        <li>
                          <span>{peer}</span>
                          <b>
                            {protocol === "bgp"
                              ? data.state
                              : Array.isArray(data)
                                ? data.map((n) => n.nbrState).join(", ")
                                : "No neighbor observation"}
                          </b>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No peers currently reported</p>
                  )}
                </div>
              );
            })}
        </>
      )}
    </section>
  );
}
