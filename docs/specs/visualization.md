# Topology visualisation

The browser workbench is a bounded 3D network graph for the Minicore IP simulator.

## Surface

The browser provides:

- the main Preact and Three.js topology graph;
- stable node placement, pan, zoom, rotation and selection;
- the header God checkbox and targeted God fault toolbar;
- AS, OSPF, BGP and Prefix layer controls;
- the observer-backed Network events panel;
- periodic HTTP snapshots plus SSE invalidation;
- Summary, Interfaces, Routing, Logs and Configuration views in the node inspector.

The main graph always remains 3D. Diagnostic detail stays in 2D inspectors and panels.

## Responsibility boundary

Minicore owns declarative topology, runtime-state collection, bounded evidence APIs, factual node and link state, the graph, and the 2D evidence panels.

Agent view and the public evidence APIs exclude controller ground truth. God view can show bounded controller state for a God-authorised browser session.

## Update model

The UI loads a complete topology snapshot over HTTP, subscribes to SSE for low-latency invalidation and polls every 15 seconds to reconcile missed events. On reconnect it always reloads an authoritative snapshot. There is no replay queue or client-side delta history.

## References

Authoritative requirements are in [../../SPEC.md](../../SPEC.md). Visual constraints are in [visual-direction.md](visual-direction.md). Routing and observer detail is in [routing-visualization.md](routing-visualization.md), [routing-observer.md](routing-observer.md) and [network-events-panel.md](network-events-panel.md).
