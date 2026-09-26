# Behavioural specifications

Each feature has exactly one lifecycle tag:

- `@implemented`: current behaviour with executable bindings and one runner tag: `@python`, `@browser` or `@host`.
- `@planned`: unbound design scenarios under `features/planned/`, excluded from acceptance execution. Some describe behaviour now covered by narrower implemented scenarios; the tag classifies the scenario's binding, not whether every capability it mentions is absent.
- `@external`: opt-in tests that require a running lab or other explicit prerequisites.

The generated [coverage map](../docs/development/behavior-coverage.md) lists features, scenarios, runners and expanded case counts. Execution reports establish which cases passed.

## Run tests

Run these commands from the repository root:

```sh
make bootstrap         # locked Python and Bun dependencies
make coverage-update   # regenerate the map after editing Gherkin
make acceptance        # checks, implemented scenarios and report reconciliation
make bdd-python        # Behave service, model, security and HTTP tests
make bdd-web           # Playwright-BDD browser and host-tool tests
make bdd-logs          # live FRR logs; requires p1 and the collector
make bdd-boot           # live node boot, peers, packets and collector lifecycle
```

Install Chromium with `cd web-ui && bunx playwright install chromium`. Missing dependencies fail the tests. `make browser` is an alias for `bdd-web`; `make bdd` is an alias for `acceptance`.

`make check` runs lint, typing, unit tests, generated-file checks, the frontend build and Compose validation. Use `make acceptance` to run and reconcile implemented Gherkin as well.

## Acceptance checks

- The Cucumber parser rejects missing or conflicting lifecycle/runner tags and duplicate scenario names.
- Behave receives only inventoried `@implemented @python` files.
- Playwright-BDD binds implemented browser and host features. Missing steps fail generation.
- The final check matches JSON results to exact feature, scenario and outline-case identities. Every implemented case must pass. Missing, duplicate, unexpected, skipped, undefined, failed or flaky results fail the check.
- A stale coverage map fails `make check`. An implemented feature omitted from a runner fails report reconciliation.

Run `make acceptance` for fresh evidence: it executes both runners before checking their reports. Running the report checker alone validates the supplied reports; it cannot establish when or against which source revision they were produced.

Browser acceptance starts a disposable service on loopback with temporary observations and credentials. It refuses to reuse an existing listener. Host-tool tests use temporary project copies and a recording Docker executable to check command mapping, validation and persistence. Live routing and forwarding require the separate lab suites. `make smoke` checks the running management service through its published Compose port.

## Change behaviour

Follow the [development methodology](../docs/development/methodology.md): write Gherkin, demonstrate a behavioural failure for a new feature or fix, implement the change, run acceptance and commit. Existing behaviour may use passing characterisation tests. Keep unit tests alongside acceptance bindings where they isolate a failure more precisely.
