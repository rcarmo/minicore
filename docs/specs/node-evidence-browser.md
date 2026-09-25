# Node evidence browser

The docked node inspector is the 2D evidence surface attached to the 3D topology workbench.

Current tabs are Summary, Interfaces, Routing, Logs and Configuration. Summary and Interfaces use live node observations from `GET /api/v1/nodes/{id}/observations`. Routing uses `GET /api/v1/nodes/{id}/routes`. Logs and Configuration are defined in [log-streaming.md](log-streaming.md) and [configuration-browser.md](configuration-browser.md).

## Inspector contract

Selecting a node opens a docked 2D panel without leaving the graph. The panel identifies the selected node and exposes bounded factual evidence for troubleshooting in the synthetic IP lab. Selection is reflected in the URL without embedding credentials or log content.

Tabs:

1. *Summary* — identity, role, container state, live interface summary and live BGP or OSPF summary.
2. *Interfaces* — measured interface state and addresses, refreshed every 5 seconds while open.
3. *Routing* — bounded route response and raw evidence, refreshed every 5 seconds while open.
4. *Logs* — bounded container log pages with follow and pause behaviour.
5. *Configuration* — redacted declared baseline files.

The graph remains the main visual context. The inspector is an accessible Preact panel, not a terminal emulator.

## Bounds and update model

The inspector fetches authoritative HTTP responses for the selected node. SSE is used where the underlying feature defines it, such as logs. Generation labels prevent old evidence from being mixed with new state after reset. Stale or unavailable data remains explicit rather than silently disappearing.

## Out of scope

- Arbitrary filesystem browsing, terminal access or command execution.
- Configuration editing, service restart or direct fault control from the inspector.
