import type { TopologySnapshot } from "./types";

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Expected a topology object");
  return value as Record<string, unknown>;
}
const states = ["up", "down", "degraded", "unknown", "unavailable", "stale"];
export function validateSnapshot(value: unknown): TopologySnapshot {
  const snapshot = object(value);
  if (snapshot.schema_version !== "1.0")
    throw new Error("Unsupported topology schema");
  if (
    !Array.isArray(snapshot.nodes) ||
    !Array.isArray(snapshot.links) ||
    snapshot.nodes.length > 128 ||
    snapshot.links.length > 512
  )
    throw new Error("Topology response is incomplete or too large");
  if (
    typeof snapshot.revision !== "string" ||
    typeof snapshot.lab_id !== "string" ||
    !Number.isInteger(snapshot.generation) ||
    Number(snapshot.generation) < 1 ||
    typeof snapshot.collected_at !== "string"
  )
    throw new Error("Topology revision metadata is missing");
  const ids = new Set<string>();
  for (const raw of snapshot.nodes) {
    const node = object(raw),
      position = object(node.position);
    if (
      typeof node.id !== "string" ||
      ids.has(node.id) ||
      !/^[a-z][a-z0-9]{1,15}$/.test(node.id) ||
      typeof node.label !== "string" ||
      !["host", "ce", "pe", "core"].includes(String(node.role)) ||
      !["endpoint", "router"].includes(String(node.kind)) ||
      !states.includes(String(node.state)) ||
      !Array.isArray(node.protocols) ||
      !node.protocols.every((v) => typeof v === "string") ||
      ![position.x, position.y, position.z].every(
        (v) => typeof v === "number" && Number.isFinite(v),
      )
    )
      throw new Error("Invalid topology node");
    ids.add(node.id);
  }
  const linkIds = new Set<string>();
  for (const raw of snapshot.links) {
    const link = object(raw);
    if (
      typeof link.id !== "string" ||
      linkIds.has(link.id) ||
      !ids.has(String(link.source)) ||
      !ids.has(String(link.target)) ||
      link.source === link.target ||
      !states.includes(String(link.state))
    )
      throw new Error("Invalid topology link");
    linkIds.add(link.id);
  }
  return snapshot as unknown as TopologySnapshot;
}

export function topologyChanged(
  previous: TopologySnapshot | null,
  next: TopologySnapshot,
): boolean {
  return (
    previous?.revision !== next.revision ||
    previous?.generation !== next.generation
  );
}
