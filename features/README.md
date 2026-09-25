# Behavioral specifications and executable coverage

## Status and source of truth

Each feature has exactly one status:

- **`@implemented`** — current behavior; one runner tag (`@python`, `@browser`, or `@host`) and executable bindings required.
- **`@planned`** — preserved unimplemented design requirements, physically separated in `features/planned/`. These are not silently skipped acceptance tests or evidence of completion.
- **`@external`** — opt-in real-lab scenario with explicit prerequisites; the FRR startup log demonstration and real node boot/routing/watcher suite. It is not part of deterministic acceptance.

The generated [coverage map](../docs/development/behavior-coverage.md) lists every feature, scenario, runner and expanded case count. It is a behavior inventory, not a line/branch coverage percentage or proof of the entire future system.

## Commands

```sh
make install           # Python test tools + frozen Bun dependencies
make coverage-update   # regenerate map after editing Gherkin
make acceptance        # fast checks + all implemented Gherkin + report reconciliation
make bdd-python        # Behave service/model/log/security contracts and real HTTP tests
make bdd-web           # Playwright-BDD browser and host-tool contracts
make browser           # compatibility alias for bdd-web
make bdd               # compatibility alias for acceptance
make bdd-logs          # opt-in actual FRR startup evidence (needs p1 + collector)
make bdd-boot          # boot all nodes, real peer/probe and watcher lifecycle checks
```

Install Chromium once with `cd web-ui && bunx playwright install chromium`. Missing browser/tool dependencies fail; they do not produce skip-based success.

`make check` validates syntax/classification, map freshness, generated topology, lint/typing, focused Python/Bun tests, production build and Compose syntax. **It does not replace `make acceptance`.**

## How the gate works

- Official Cucumber parser compiles all features/outlines and rejects missing/conflicting lifecycle/runner tags or duplicate scenario names.
- Python execution receives only inventoried `@implemented @python` files, so no unrelated planned skips enter the report.
- Playwright-BDD generation binds implemented browser/host features; missing steps fail generation.
- `make acceptance` reruns both suites, then reconciles JSON reports with the inventory: every current scenario and every outline case must be present and passed, under its exact feature/scenario identity. No undefined, skipped, failed, unexpectedly passed or retried-failing results count.
- A new implemented feature omitted from runner configuration fails the final gate. A stale map fails `make check`.

Browser acceptance launches an isolated loopback service with temporary observations/secrets and refuses to reuse a pre-existing listener. Host tests use temporary project copies and a recording Docker executable: they prove mapping, validation, limits and persistence, not router startup or forwarding. The public-port Compose smoke remains `make smoke`.

## Development order

Follow project `AGENTS.md`: Gherkin first, executable red test for new behavior/fixes, minimal implementation, green acceptance, documentation alignment, regular commit. Existing-behavior characterization may start green; do not invent historical red runs. Tests for core functions remain useful alongside acceptance bindings.
