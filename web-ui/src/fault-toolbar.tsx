import { useEffect, useRef, useState } from "preact/hooks";
export type FaultMode = "inspect" | "zap" | "dice";
export function useFaultControls(
  enabled: boolean,
  generation: number,
  refresh: () => void,
) {
  const [mode, setMode] = useState<FaultMode>("inspect");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Inspect");
  const gate = useRef(false);
  const epoch = useRef(0);
  const [pending, setPending] = useState<{
    path: string;
    body: Record<string, string>;
  } | null>(null);
  useEffect(() => {
    epoch.current++;
    setMode("inspect");
    setMessage("Inspect");
    setPending(null);
  }, [enabled, generation]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMode("inspect");
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const execute = async (path: string, body: Record<string, string>) => {
    if (!enabled || gate.current) return;
    gate.current = true;
    setBusy(true);
    setMode("inspect");
    setMessage("Applying fault…");
    const version = epoch.current;
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Minicore-Intent": "fault-control",
        },
        body: JSON.stringify(body),
      });
      const value = await response.json();
      if (version !== epoch.current) return;
      if (!response.ok || value.error_code)
        throw Error(value.error_code ?? `HTTP ${response.status}`);
      setPending(null);
      setMessage(
        `${value.data.state} · ${value.data.verified ? "confirmed" : "checking"}`,
      );
      refresh();
    } catch (e) {
      if (version === epoch.current) {
        setPending({ path, body });
        setMessage(
          `Request failed: ${e instanceof Error ? e.message : "request failed"} — check the fault status before retrying`,
        );
        refresh();
      }
    } finally {
      gate.current = false;
      setBusy(false);
    }
  };
  return {
    mode,
    busy,
    message,
    pending,
    arm: (m: FaultMode) => {
      if (enabled && !gate.current) {
        setMode(m);
        setMessage(
          m === "inspect"
            ? "Inspect"
            : m === "zap"
              ? "Click a node to stop its container or a link to kill the link"
              : "Click a target for one reversible random corruption",
        );
      }
    },
    target: (type: "node" | "link", id: string) => {
      if (enabled && mode !== "inspect")
        void execute("/api/v1/faults/apply", {
          mode,
          target_type: type,
          target_id: id,
          idempotency_key: crypto.randomUUID(),
        });
    },
    reset: () =>
      execute("/api/v1/faults/reset", { idempotency_key: crypto.randomUUID() }),
    retry: () => pending && execute(pending.path, pending.body),
  };
}
export function FaultToolbar({
  control,
}: {
  control: ReturnType<typeof useFaultControls>;
}) {
  return (
    <section class="fault-toolbar" aria-label="God fault controls">
      <div class="fault-buttons">
        <button
          aria-pressed={control.mode === "inspect"}
          onClick={() => control.arm("inspect")}
          disabled={control.busy}
        >
          Inspect
        </button>
        <button
          aria-label="Lightning — kill target"
          aria-pressed={control.mode === "zap"}
          onClick={() => control.arm("zap")}
          disabled={control.busy}
        >
          ⚡ Zap
        </button>
        <button
          aria-label="Dice — random corruption"
          aria-pressed={control.mode === "dice"}
          onClick={() => control.arm("dice")}
          disabled={control.busy}
        >
          ⚄ Corrupt
        </button>
        <button onClick={() => void control.reset()} disabled={control.busy}>
          Restore lab
        </button>
        {control.pending && (
          <button onClick={() => void control.retry()} disabled={control.busy}>
            Retry same request
          </button>
        )}
      </div>
      <span role="status" aria-label="Fault mode">
        {control.message}
      </span>
    </section>
  );
}
