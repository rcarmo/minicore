import { useEffect, useState } from "preact/hooks";
export type ViewMode = "agent" | "god";
export function useGodCapability() {
  const [capable, setCapable] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/v1/view", { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : { can_god: false }))
      .then((v) => {
        if (!abort.signal.aborted) setCapable(v.can_god === true);
      })
      .catch(() => {});
    return () => abort.abort();
  }, []);
  return capable;
}
export function VisibilityToggle({
  view,
  capable,
  onChange,
}: {
  view: ViewMode;
  capable: boolean;
  onChange: (view: ViewMode) => void;
}) {
  return (
    <label
      class="god-toggle"
      title={
        capable
          ? "Read-only full lab visibility"
          : "God authentication required"
      }
    >
      <input
        type="checkbox"
        checked={view === "god"}
        disabled={!capable}
        onChange={(e) => onChange(e.currentTarget.checked ? "god" : "agent")}
      />{" "}
      God mode <strong>{view === "god" ? "God view" : "Agent view"}</strong>
    </label>
  );
}
export function ControllerState({ value }: { value: unknown }) {
  const c = value as Record<string, unknown> | undefined;
  return (
    <section aria-label="Controller ground truth" class="controller-state">
      <strong>Controller ground truth</strong>
      <p>{typeof c?.state === "string" ? c.state : "unavailable"}</p>
      {c?.scenario_id && <p>Scenario: {String(c.scenario_id)}</p>}
      {c?.node_id && (
        <p>
          Target: {String(c.node_id)} {String(c.interface ?? "")}
        </p>
      )}
      {c?.error_code && <p>{String(c.error_code)}</p>}
    </section>
  );
}
