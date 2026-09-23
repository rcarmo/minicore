import type { TopologySnapshot } from "./types";
import type { ProtocolFact, RoutingLayer } from "./routing-model";
export function Topology2D({
  snapshot,
  selected,
  onSelect,
  layer,
  activity,
  facts,
  compact = false,
  selectedFact,
  onFact,
  onLink,
  armed = false,
}: {
  snapshot: TopologySnapshot;
  selected?: string | null;
  onSelect?: (id: string) => void;
  layer: RoutingLayer;
  activity?: string[];
  facts: ProtocolFact[];
  compact?: boolean;
  selectedFact?: string | null;
  onFact?: (id: string) => void;
  onLink?: (id: string) => void;
  armed?: boolean;
}) {
  const byId = new Map(snapshot.nodes.map((n) => [n.id, n]));
  const point = (id: string) => {
    const n = byId.get(id)!;
    return {
      x: 60 + (n.position.x + 9) * 48.9,
      y: compact ? 130 + n.position.y * 30 : 180 + n.position.y * 50,
    };
  };
  const relations =
    layer === "BGP"
      ? (snapshot.peerings ?? [])
      : layer === "OSPF"
        ? snapshot.links.filter((l) => l.ospf_area === "0")
        : [];
  const height = compact ? 260 : 360;
  return (
    <div class={`topology-2d ${compact ? "compact-topology" : ""}`}>
      <svg
        role="img"
        aria-label={
          compact ? "Protocol relationship graph" : "2D network topology"
        }
        viewBox={`0 0 1000 ${height}`}
      >
        <title>
          {compact
            ? "Protocol relationships — endpoint evidence in table"
            : "Eight-node network topology"}
        </title>
        {(layer === "AS" || layer === "OSPF") &&
          [65000, 65001, 65002]
            .filter((asn) => layer === "AS" || asn === 65000)
            .map((asn) => {
              const nodes = snapshot.nodes.filter((n) => n.asn === asn),
                pts = nodes.map((n) => point(n.id));
              if (!pts.length) return null;
              const x = Math.min(...pts.map((p) => p.x)) - 42,
                y = Math.min(...pts.map((p) => p.y)) - 48,
                w = Math.max(...pts.map((p) => p.x)) - x + 42,
                h = Math.max(...pts.map((p) => p.y)) - y + 48;
              return (
                <g class="domain-band">
                  <rect x={x} y={y} width={w} height={h} rx="22" />
                  <text x={x + 10} y={y + 17}>
                    {layer === "OSPF" ? "Area 0" : `AS ${asn}`}
                  </text>
                </g>
              );
            })}
        {snapshot.links.map((link) => {
          const a = point(link.source),
            b = point(link.target);
          return (
            <line class="physical-edge" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
          );
        })}
        {relations.map((p, i) => {
          const a = point(p.source),
            b = point(p.target),
            fact = facts.find((f) => f.id === p.id),
            offset = compact ? 22 : 30;
          const path = `M ${a.x} ${a.y} Q ${(a.x + b.x) / 2} ${(a.y + b.y) / 2 - offset - (i % 3) * offset} ${b.x} ${b.y}`;
          return (
            <path
              class="protocol-edge"
              data-state={fact?.state ?? "unknown"}
              data-selected={p.id === selectedFact}
              d={path}
              onClick={() => onFact?.(p.id)}
            >
              <title>
                {fact?.text ?? `${p.source} ↔ ${p.target}: not collected`}
              </title>
            </path>
          );
        })}
        {snapshot.nodes.map((n) => {
          const p = point(n.id);
          return (
            <g
              transform={`translate(${p.x} ${p.y})`}
              class={`node-shape node-${n.role}`}
              data-selected={n.id === selected}
            >
              {activity?.includes(n.id) && <circle class="agent-ring" r="27" />}
              {n.kind === "router" ? (
                <circle r="18" />
              ) : (
                <rect x="-19" y="-14" width="38" height="28" rx="6" />
              )}
              <path
                class="node-mark"
                d={
                  n.kind === "router"
                    ? "M -9 0 H 9 M 0 -9 V 9"
                    : "M -10 -5 H 10 V 6 H -10 Z"
                }
              />
              {compact && (
                <text y="35" textAnchor="middle">
                  {n.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {!compact &&
        snapshot.nodes.map((n) => {
          const p = point(n.id);
          return (
            <button
              class="graph-label"
              data-selected={n.id === selected}
              data-agent-active={activity?.includes(n.id) ?? false}
              style={{ left: `${p.x / 10}%`, top: `${(p.y / height) * 100}%` }}
              onClick={() => onSelect?.(n.id)}
              aria-label={
                n.label + (activity?.includes(n.id) ? " — Agent access" : "")
              }
            >
              {n.label}
            </button>
          );
        })}
    </div>
  );
}
