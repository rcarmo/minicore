# Implementation patterns

Minicore separates network evidence, transport and rendering. Each boundary validates inputs, limits resource use and reports failures explicitly.

## Browser

- Keep Three.js scene creation, picking and disposal in a lifecycle class. Release geometry, materials, observers and listeners on teardown.
- Let Preact own selection, filters, panels, cancellation and error state.
- Preserve inventory identities and coordinates across snapshots. Keep the main graph in 3D and diagnostic charts in 2D panels.
- Bound pixel ratio and rendering work. Measure frame time and retained resources; do not infer native GPU performance from software rendering.
- Fetch bounded detail on selection without replacing the graph. Reject late responses after scope, role or generation changes.
- Provide keyboard, pointer and touch input, reduced motion and an accessible WebGL fallback.
- Render logs and configuration as text. Never expose arbitrary filesystem paths or terminal execution.

## Services

- Use one asyncio HTTP/MCP listener with separate domain modules.
- Validate at both the API and restricted dispatcher boundaries. Build commands from fixed argument arrays.
- Share bounded diagnostic collection where callers request the same evidence. Background collection must not create agent-activity indicators.
- Snapshot mutable context before off-loop reads. Check generation before returning results.
- Hold mutation ownership through durable writes and cancellation drain. Reconcile uncertain outcomes through persisted state and idempotency keys.
- Use monotonic age for volatile retention. A repeated response must not extend the lifetime of an old observation.
- Keep declared, observed, unavailable, stale and malformed data distinct.

## Dependencies and tests

Pin source revisions and package versions, retain upstream licences and document local modifications. Review imported code before execution. Build assets before packaging; the runtime does not need frontend development dependencies.

Use the [testing methodology](methodology.md) for behavioural changes. Test normal and failure paths at the nearest boundary, then verify transport, browser and real-network behaviour separately.
