export type ObservationState =
  | "up"
  | "degraded"
  | "down"
  | "unknown"
  | "unavailable"
  | "stale";
export interface Position {
  x: number;
  y: number;
  z: number;
}
export interface TopologyNode {
  id: string;
  label: string;
  role: "host" | "ce" | "pe" | "core";
  kind: "endpoint" | "router";
  container_state?: string;
  expected: boolean;
  state: ObservationState;
  position: Position;
  management_address?: string;
  protocols: string[];
  observed_at: string | null;
}
export interface TopologyLink {
  id: string;
  source: string;
  target: string;
  kind: "data";
  state: ObservationState;
  expected: boolean;
  observed_at: string | null;
}
export interface TopologySnapshot {
  schema_version: "1.0";
  lab_id: string;
  generation: number;
  revision: string;
  collected_at: string;
  source: "combined";
  runtime_status: "not_configured" | "available" | "partial" | "unavailable";
  nodes: TopologyNode[];
  links: TopologyLink[];
}
