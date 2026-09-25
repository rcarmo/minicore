SHELL := /bin/sh
PYTHON ?= python3
COMPOSE := docker compose -f compose/compose.json
export PYTHONPATH := $(CURDIR)/vendor/umcp:$(CURDIR)/mcp-service/src:$(CURDIR)/tests:$(CURDIR)/router-image/dispatcher
.PHONY: install generate lint test check build up down status observe lab-up smoke clean
install:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements-dev.txt
	cd web-ui && bun install --frozen-lockfile
generate:
	bun scripts/topology.ts
lint:
	.venv/bin/ruff check mcp-service/src tests features router-image/dispatcher scripts/host-fault-controller.py scripts/observer-host.py
	.venv/bin/ruff format --check mcp-service/src tests features router-image/dispatcher scripts/host-fault-controller.py scripts/observer-host.py
	.venv/bin/mypy mcp-service/src --explicit-package-bases
	cd web-ui && bun run lint
	bun scripts/topology.ts --check
	$(PYTHON) -m compileall -q mcp-service/src tests router-image/dispatcher scripts/host-fault-controller.py scripts/observer-host.py
	cd web-ui && bun run typecheck
	cd web-ui && bun run scripts/features.ts
	test -s SPEC.md

git-check:
	git diff --check

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
	cd web-ui && bun test src
check: lint test
	cd web-ui && bun run build
	$(COMPOSE) config --quiet
build: check
	$(COMPOSE) build management
up:
	$(COMPOSE) up -d --wait management
down:
	$(COMPOSE) --profile lab down
status:
	bun scripts/lab.ts status
observe:
	bun scripts/lab.ts observe
lab-up:
	bun scripts/lab.ts up
smoke:
	$(PYTHON) tests/smoke.py
browser: bdd-web
clean:
	rm -rf web-ui/dist .pytest_cache .ruff_cache
format:
	.venv/bin/ruff format mcp-service/src tests features router-image/dispatcher scripts/host-fault-controller.py scripts/observer-host.py
	cd web-ui && bun run format
bdd: acceptance
logs-once:
	bun scripts/log-collector.ts --once
logs-follow:
	bun scripts/log-collector.ts --duration 600
bdd-logs:
	cd web-ui && bunx bddgen -c playwright.logs.config.ts && bunx playwright test -c playwright.logs.config.ts

coverage-update:
	cd web-ui && bun run scripts/features.ts --write
bdd-python:
	mkdir -p reports
	.venv/bin/behave --format json --outfile reports/bdd-python.json $$(cd web-ui && bun run scripts/feature-paths.ts python)
bdd-web:
	cd web-ui && bun run test:bdd
acceptance: check bdd-python bdd-web
	cd web-ui && bun run scripts/verify-acceptance.ts
router-build:
	$(COMPOSE) --profile lab build p1
watch-logs:
	bun scripts/log-watcher.ts start
stop-logs:
	bun scripts/log-watcher.ts stop
bdd-boot:
	cd web-ui && bunx bddgen -c playwright.boot.config.ts && bunx playwright test -c playwright.boot.config.ts
mcp-client:
	PYTHONPATH=$(PYTHONPATH) .venv/bin/behave features/integration/mcp_independent_client.feature

ssh-provision:
	bun scripts/provision-ssh.ts
live-routes:
	.venv/bin/behave features/diagnostics/live_routes.feature
live-faults:
	.venv/bin/behave features/operations/live_faults.feature
live-isolation:
	PYTHONPATH=vendor/umcp:mcp-service/src:tests:router-image/dispatcher .venv/bin/behave features/operations/live_isolation.feature
live-recovery:
	PYTHONPATH=vendor/umcp:mcp-service/src:tests:router-image/dispatcher .venv/bin/behave features/operations/live_recovery.feature
browser-matrix:
	cd web-ui && bunx bddgen -c playwright.bdd.config.ts && bunx playwright test -c playwright.matrix.config.ts
live-ui-faults:
	cd web-ui && bunx bddgen -c playwright.faults.config.ts && bunx playwright test -c playwright.faults.config.ts
bootstrap:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements-dev.lock
	cd web-ui && bun install --frozen-lockfile
live-performance:
	cd web-ui && bunx bddgen -c playwright.performance.config.ts && bunx playwright test -c playwright.performance.config.ts
host-fault-start:
	sh scripts/host-fault-service.sh start
host-fault-stop:
	sh scripts/host-fault-service.sh stop

live-targeted:
	.venv/bin/behave features/operations/live_targeted.feature
observer-start:
	sh scripts/observer-service.sh start
observer-stop:
	sh scripts/observer-service.sh stop
live-observer:
	.venv/bin/behave features/operations/live_observer.feature
observer-capture-start:
	sh scripts/observer-capture-service.sh start
observer-capture-stop:
	sh scripts/observer-capture-service.sh stop
