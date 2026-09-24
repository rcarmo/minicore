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
export function useFaultCapability() {
  const [capable, setCapable] = useState(false);
  useEffect(() => {
    const abort = new AbortController();
    void fetch("/api/v1/view", { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((v) => setCapable(v?.fault_control === true))
      .catch(() => setCapable(false));
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
          ? "Show God controls and fault status"
          : "God authentication required"
      }
    >
      <input
        type="checkbox"
        aria-label="God mode"
        checked={view === "god"}
        disabled={!capable}
        onChange={(e) => onChange(e.currentTarget.checked ? "god" : "agent")}
      />
      <span class="toggle-track" aria-hidden="true" />
      <span>God mode</span>
    </label>
  );
}
export function ControllerState({ value }: { value: unknown }) {
  const c = value as Record<string, unknown> | undefined;
  return (
    <section aria-label="Controller ground truth" class="controller-state">
      <strong>Fault status</strong>
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
