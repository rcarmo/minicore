# Engineering and testing methodology

Minicore develops observable behaviour through Gherkin acceptance tests, then verifies the affected Python, browser, container and network boundaries.

## Delivery loop

The mandatory sequence is defined in the project-root [AGENTS.md](../../AGENTS.md):

1. Refine one observable outcome, its acceptance criteria, non-goals and failure behaviour.
2. Write or update the domain Gherkin **before implementation changes**.
3. Bind the affected scenarios to executable acceptance tests and run them against unchanged code. For new behaviour and bug fixes, record the intended behavioural failure; missing steps and harness errors are not a valid red test.
4. Implement the smallest change required by the scenarios. Use YAGNI and common sense; add focused unit/contract coverage at changed boundaries.
5. Run the affected acceptance tests, `make check` and relevant container/network/browser suites to green.
6. Align features, code, API contracts, runbook and status documentation. Record evidence and limitations.
7. Commit the tested increment promptly.

For existing functionality, passing Gherkin characterisation is valid. Do not manufacture a red result or claim tests ran before implementation when they did not. Any discovered defect gets a failing regression scenario before its fix.

Maintain a coverage map linking implemented behaviour to features and executable tests. Keep planned acceptance specifications explicitly separate. Syntax parsing, skipped scenarios and no-op bindings are not behavioural proof. Do not weaken specifications merely to match incomplete code; identify scope changes for review.

Implementation must not outrun the behavioural specification. Gherkin is the system contract; focused unit and integration tests complement it.

## Test layers

| Layer | Purpose | Primary tooling |
|---|---|---|
| Static checks | Formatting, linting, typing, schemas, configuration validation, dependency policy | Ruff/typing for Python; Bun-managed TypeScript tooling; Compose/config validators |
| Unit | Parsers, normalisation, revisions, freshness, event reconciliation, validation, fixed dispatch | Python test runner; `bun test` |
| Contract | Topology snapshot/SSE schemas, MCP schemas, dispatcher protocol, stable errors | Schema fixtures and consumer/provider tests |
| Component | Python HTTP/MCP/assets/SSE service and isolated Preact components | Python tests; Bun DOM/component tests |
| Integration | Service-to-inventory, SSH dispatcher, FRR state, snapshot-to-SSE consistency | Docker Compose test profiles |
| BDD/E2E | Executable Gherkin behaviour through external APIs and browser | Cucumber-compatible runner and Bun-managed Playwright |
| Security/negative | Denied commands/targets, auth boundaries, malformed data, limits, cancellation | Automated adversarial fixtures and Compose tests |
| Scenario/recovery | Baseline, fault, observation, reset, repeatability | Operator scenario harness; evidence bundle |

## Gherkin rules

- Organise features by bounded domain, not implementation package.
- Describe observable outcomes and roles; avoid UI selectors, function names, and shell commands in scenarios.
- Give every scenario deterministic preconditions and assertions.
- Cover healthy, degraded, unavailable, stale, malformed, denied, timeout, reconnect, and recovery paths where applicable.
- Verify measured evidence, bounded access and repeatable troubleshooting exercises.
- Automate acceptance scenarios. Tags may select suites such as `@fast`, `@compose`, `@browser`, `@security`, and `@scenario`.

## Coding standards

- Keep domain logic independent of transports and frameworks.
- Use typed boundaries and versioned schemas; validate all external input.
- Prefer small modules, explicit dependencies, immutable snapshots, and deterministic output.
- Do not silently recover into apparently healthy state. Represent unknown, stale, unavailable, denied, and malformed states explicitly.
- Use structured logs with request/event correlation; never log credentials.
- Bound time, output, concurrency, retries, queues, and resource usage.
- Avoid speculative abstractions and dependencies. Pin and review third-party components.
- Add regression tests before fixing defects when reproducible.

## Front-end rules

- Bun owns front-end dependency installation, scripts, linting, type checking, tests, build, and Playwright execution.
- Preact owns UI state and accessible controls; Three.js owns graph rendering, picking, and camera behaviour.
- Separate topology state/reconciliation from rendering.
- Use stable semantic test hooks and accessible names rather than brittle CSS selectors.
- Preserve node identity and layout across polling and SSE updates.
- Test reduced motion, keyboard access, resize, high-DPI, WebGL failure, SSE loss, and stale snapshots.
- Build production assets reproducibly; the Python service serves only generated assets and does not invoke Bun at runtime.

## Python service rules

One Python service/container hosts static assets, topology HTTP endpoints, SSE, and uMCP. Keep these as separate internal modules with independently tested contracts. A failure in one transport must not corrupt topology state or imply network failure. The production image uses a non-root runtime and contains compiled web assets, not front-end development dependencies unless justified.

## Required checks

The canonical `make check` includes formatting, linting, typing, focused unit/contract tests, generation/classification checks and production build. `make acceptance` additionally runs every implemented Gherkin scenario and reconciles exact identities and results with the generated map. It is mandatory before declaring functional completion. `make smoke` and opt-in `make bdd-logs` cover live Compose and real-node evidence separately. No target may report success by skipping a configured test silently.

## Definition of done

- All acceptance criteria are satisfied and linked to evidence.
- Gherkin is added or updated and relevant scenarios are automated.
- Unit, contract, integration, and E2E coverage is appropriate to the changed boundary.
- Healthy and relevant failure paths pass.
- Formatting, linting, typing, schemas, and production builds pass.
- Security and operational impact are assessed.
- User-facing and operator documentation is current.
- Deferred work is explicit; unresolved limitations are not presented as complete.
- `make acceptance` passes with every implemented scenario bound and passing, plus affected live/extended suites.

MCP changes also require `make mcp-client` after rebuilding management. It uses an independent SDK against a disposable authenticated Compose endpoint; wire tests and in-process handlers alone do not establish client compatibility. Keep live backend expectations separate from unavailable-backend transport tests.

## Async Python services

Use asyncio wherever feasible across Python, including MCP, web HTTP/assets, SSE and observer services. Preserve the single `AsyncMCPServer` listener. Use bounded concurrent async I/O and subprocesses; isolate blocking dependencies and live request-path filesystem operations. Small pure parsers remain synchronous. Existing blocking paths require a separately tested migration, including cancellation, durable-write ordering and concurrent-client responsiveness. Test live-file responsiveness, cancellation drain and mutation ordering explicitly.
