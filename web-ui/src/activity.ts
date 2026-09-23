import { useEffect, useState } from "preact/hooks";
export interface ActivitySnapshot {
  epoch: string;
  generation: number;
  revision: number;
  active: { node_id: string; request_id: string; expires_at: number }[];
  recent: { node_id: string; request_id: string; expires_at: number }[];
}
export function activityNodes(
  value: unknown,
  generation: number,
  now = Date.now() / 1000,
): string[] {
  const data = value as ActivitySnapshot;
  if (
    !data ||
    data.generation !== generation ||
    typeof data.epoch !== "string" ||
    !Number.isInteger(data.revision) ||
    !Array.isArray(data.active) ||
    !Array.isArray(data.recent) ||
    data.active.length + data.recent.length > 128
  )
    throw Error("Invalid activity snapshot");
  const nodes = new Set<string>();
  for (const r of [...data.active, ...data.recent]) {
    if (
      !r ||
      typeof r.node_id !== "string" ||
      typeof r.request_id !== "string" ||
      typeof r.expires_at !== "number" ||
      !Number.isFinite(r.expires_at)
    )
      throw Error("Invalid activity record");
    if (r.expires_at > now && r.expires_at <= now + 25) nodes.add(r.node_id);
  }
  return [...nodes].sort();
}
export function useActivity(generation: number) {
  const [nodes, setNodes] = useState<string[]>([]);
  useEffect(() => {
    let current: ActivitySnapshot | null = null,
      disposed = false,
      serial = 0;
    const controller = new AbortController();
    const apply = (value: unknown) => {
      try {
        activityNodes(value, generation);
        const next = value as ActivitySnapshot;
        if (current?.epoch === next.epoch && next.revision < current.revision)
          return;
        current = next;
        setNodes(activityNodes(next, generation));
      } catch {
        current = null;
        setNodes([]);
      }
    };
    const events = new EventSource("/api/v1/activity/events");
    events.addEventListener("activity.snapshot", (event) => {
      serial++;
      if (!disposed) {
        try {
          apply(JSON.parse((event as MessageEvent).data));
        } catch {
          current = null;
          setNodes([]);
        }
      }
    });
    const fetchState = async () => {
      const request = ++serial;
      try {
        const r = await fetch("/api/v1/activity", {
          signal: controller.signal,
        });
        if (!r.ok) throw Error("Activity unavailable");
        const data = await r.json();
        if (!disposed && request === serial) apply(data);
      } catch {
        if (!disposed && request === serial) {
          current = null;
          setNodes([]);
        }
      }
    };
    events.onerror = () => {
      void fetchState();
    };
    void fetchState();
    const expire = setInterval(() => {
      if (current) setNodes(activityNodes(current, generation));
    }, 100);
    const poll = setInterval(fetchState, 5000);
    return () => {
      disposed = true;
      controller.abort();
      events.close();
      clearInterval(expire);
      clearInterval(poll);
    };
  }, [generation]);
  return nodes;
}
