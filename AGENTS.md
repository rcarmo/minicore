# Minicore development instructions

## Purpose
Develop the IP network simulator and diagnostic interfaces defined in [SPEC.md](SPEC.md).

## Governing constraints
- Read `SPEC.md` and `docs/operations/known-limitations.md` before changes. Keep implementation and supporting contracts consistent with the specification.
- Do not provision remote resources, expose public ports, or deploy outside a local development host without explicit approval.
- Use only open-source routing software and synthetic data. Never import production routes, configuration or credentials.
- Enforce the accepted Operator/God MCP boundary in `docs/specs/mcp-capability-modes.md`; fault execution remains isolated behind a dedicated fixed-scenario controller.
- Never expose arbitrary shell commands, arbitrary targets, configuration writes, or unrestricted Docker control. God mode may invoke only the accepted predefined fault scenarios and reset contract.
- The MCP service must not mount the Docker socket, use host networking, run as root, or receive `NET_ADMIN`.
- Pin and verify dependencies, container digests, SSH host keys, and the inspected uMCP revision before acceptance.

## Mandatory development order: Gherkin first

This is the agreed project workflow, not optional documentation after coding:

1. Read the current implementation, relevant domain features and accepted decisions. Identify the smallest observable behaviour to change.
2. **Write or update the Gherkin scenarios before changing implementation.** Cover the normal outcome and relevant failure, authorisation, bounds and recovery cases. Keep scope small: YAGNI and common sense, not speculative frameworks or features.
3. Bind the affected scenarios to executable acceptance tests. Run them against the unchanged implementation and record the expected behavioural failure before implementing new behaviour or a bug fix. A missing step, syntax error or broken harness is not evidence of the intended failure.
4. Implement only what the scenarios require. Add focused unit/contract tests where they give clearer failure evidence; they complement, rather than replace, Gherkin acceptance coverage.
5. Run the affected acceptance scenarios, `make acceptance` (including `make check` and the coverage gate), and relevant live transport/Compose suites. Record actual results and limitations; never count syntax-only parsing, skips or no-op steps as passing behaviour.
6. Reconcile features, code, API contracts, runbook and status documentation. Commit the tested increment promptly, with traceable scenario/test evidence. Do not accumulate a whole feature uncommitted.

For existing-functionality coverage work, write and bind the missing Gherkin against the current code first. Passing characterisation tests are valid; do not fabricate a historical red run or deliberately break working code. If characterisation reveals a defect, retain the failing scenario and follow the red-to-green sequence above.

Keep implemented, executable behaviour separate from planned acceptance specifications. Maintain a coverage map from current behaviour to feature scenarios and actual tests. Mark unimplemented scenarios explicitly as planned; do not weaken requirements or silently rewrite tests to make the implementation appear complete. Proposed scope changes must be identified as such.

## Engineering workflow
- Use Python for the uMCP service and node dispatcher; use typed schemas and fixed executable argument arrays.
- Prefer asyncio wherever feasible in all Python code: asynchronous sockets, bounded concurrent collection, subprocess I/O, timers and cancellation/shutdown. This explicitly includes MCP, web HTTP/assets, SSE and observer services. Keep MCP and web on the existing shared AsyncMCPServer listener; do not introduce a synchronous server or unbounded per-request worker threads. Keep small pure parsers synchronous. Do not block the event loop with subprocess.run, time.sleep, blocking capture calls or filesystem I/O on live request paths; use bounded off-loop adapters or preloaded immutable data as appropriate. Existing synchronous code is migrated in separately tested increments, not silently rewritten during specification work.
- Prefer JSON output from FRR where supported. Preserve bounded raw evidence and never map parse failures to healthy empty results.
- Add tests with every behaviour change. Run `make check` before committing and `make acceptance` before functional completion.
- Keep generated evidence and secrets out of Git.
- Record unresolved assumptions and measured results in `docs/`.

## Specification and quality method
- Follow `docs/development/methodology.md`.
- The mandatory Gherkin-first sequence above governs every behaviour change; `docs/development/methodology.md` must stay aligned with it.
- Use the test layer closest to the behaviour and add boundary integration coverage.
- Front-end work uses Preact and Three.js, with all dependency, type, lint, test, build, and Playwright tasks managed through Bun.
- One Python service/container hosts generated assets, topology HTTP/SSE, and uMCP through separated internal modules.
- A defect fix should include a failing regression test first when reproducible.
- Completion requires traceable evidence, relevant failure-path coverage, documentation, and passing canonical checks.
- Use `docs/development/engineering-references.md` for reviewed engineering approaches and `docs/specs/visual-direction.md` for Minicore's distinct UI. Review external code and retain its licence before incorporating it.
- Node logs are bounded factual evidence. Never add arbitrary journal, file, command, regex, or terminal access to the UI/API.

- Canonical network is `inventory/topology.json`; run `make generate`, never hand-edit generated Compose/FRR output.
- Never return invented success for unavailable diagnostics, logs or fault backends. Live routing, isolation and fault recovery require separate real-network tests.
- Commit at tested milestones while working; do not accumulate an entire implementation uncommitted. Never commit runtime state, credentials or generated dependency caches.

## Executable coverage convention
- Every feature has exactly one lifecycle tag: `@implemented`, `@planned`, or `@external`.
- Implemented features have exactly one runner tag: `@python`, `@browser`, or `@host`. Add real assertions and run them; no generic pass-through bindings.
- Keep future requirements in `features/planned/`. Do not erase them or count them as completed functionality. `@external` tests have documented real-lab prerequisites and fail if those prerequisites are missing.
- After feature edits run `make coverage-update`. `docs/development/behavior-coverage.md` is generated, not hand-maintained.
- `make acceptance` reruns all current scenarios and verifies exact feature/scenario/outline identity and passing status. Parsing syntax, matching counts alone, skips or stale reports are not acceptance.
- Container-log contracts are in `docs/specs/log-streaming.md`; targeted fault contracts are in `docs/specs/god-fault-toolbar.md`. Planned scenarios do not count as passing.
