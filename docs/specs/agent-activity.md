# Agent activity cue

Ordinary authorised node-directed MCP requests light a cyan/magenta activity ring on the addressed node. Selection, topology position and health colouring stay separate.

The server starts activity after authorisation and argument validation, and clears it in a guaranteed completion path for success, unavailable backend, exception and cancellation. Browser inspection, topology discovery, background collection, denied calls and God fault mutations do not create this cue. `ping` highlights only its execution node. The cue records request activity, not successful SSH contact or packet delivery.

`GET /api/v1/activity` and `GET /api/v1/activity/events` use the same access policy as topology. `activity.snapshot` carries only bounded request metadata: server epoch, node ID, generation, lifecycle state, timestamps and revision data. It does not expose arguments, result bodies, credentials, scenario labels or controller audit. Shared role credentials do not identify separate operators.

Store bounds are a process epoch, monotonic revision, 128 records, 20-second active lease and 0.9-second completed hold. Generation change clears older records. The browser rejects stale generations and revisions, reconciles on reconnect or poll, and retires lost-finish highlights after the bounded deadline. Polling is every 5 seconds. SSE wakes the UI immediately on request-state changes. Slow viewers do not block diagnostics.

The graph draws one pair of rings per active node. The ring stays visible while any request for that node is active. Pulse and 600 ms fade are disabled under reduced motion. The accessible node list adds `Agent access`. There is no camera motion, traffic trail or activity dashboard.

Browser God visibility is separate. This stream represents ordinary permitted diagnostic access only.
