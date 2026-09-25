# Network workbench

Preact manages browser state and controls; Three.js renders the main 3D topology. Diagnostic panels show interfaces, neighbours, routes, logs, declared configuration and network events. The declared topology renders even when router observations are unavailable. Node and link lists provide an accessible fallback when WebGL is unavailable.

Selected-node interfaces and routing refresh every five seconds. Logs support Follow/Pause, Latest/Older pagination and severity filters. God-authorised sessions can inspect controller state and use the fixed fault toolbar. The observer retains network events for at most 60 seconds.

## Build and test

Bun manages frontend dependencies and tasks. From `web-ui/`:

```sh
bun install --frozen-lockfile
bun run lint
bun run check          # type checks, unit tests and build
bun run test:bdd        # browser and host-tool acceptance
```

`bun run test:browser` is an alias for `test:bdd`. Browser acceptance requires the repository's Python test environment and Chromium; see [test setup](../features/README.md).

Production assets in `dist/` are copied into the Python image and served locally without a CDN. Deterministic browser acceptance starts a disposable service at `http://127.0.0.1:19123`. Live-log tests use `MINICORE_URL`, defaulting to `http://127.0.0.1:19000`.

See the [visualisation contract](../docs/specs/visualization.md), [routing layers](../docs/specs/routing-visualization.md) and [runbook](../docs/operations/runbook.md).
