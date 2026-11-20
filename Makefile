SHELL := /bin/sh
PYTHON ?= python3
COMPOSE := docker compose -f compose/compose.json
export PATH := $(PATH):$(HOME)/.bun/bin
export PW_DISABLE_TS_ESM := 1
export PYTHONPATH := $(CURDIR)/vendor/umcp:$(CURDIR)/mcp-service/src:$(CURDIR)/tests:$(CURDIR)/router-image/dispatcher
.PHONY: install generate lint test check build up down status observe lab-up smoke clean start stop restart rebuild help bdd-events
help:
	@printf '%s\n' \
		'make start       Start the complete lab, wait for readiness, and collect logs' \
		'make stop        Stop collection and containers; preserve credentials and state' \
		'make restart     Stop, then start the complete lab' \
		'make rebuild     Check and rebuild management, then start the lab' \
		'make status      Show all inventoried node states' \
		'make acceptance  Run canonical checks and current acceptance scenarios' \
		'make bdd-events  Run the network events browser and model scenarios' \
		'make watch-logs / stop-logs       Control the log collector' \
		'make observer-start / observer-stop  Opt-in routing counters' \
		'make host-fault-start / host-fault-stop  Opt-in targeted faults' \
		'Restore active faults before stopping or restarting; see the runbook.'
start:
	$(COMPOSE) --profile lab up -d --wait
	$(MAKE) watch-logs
stop:
	$(MAKE) stop-logs
	$(MAKE) down
restart:
	$(MAKE) stop
	$(MAKE) start
rebuild:
	$(MAKE) build
	$(MAKE) start
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
	cd web-ui && bun run --bun lint
	bun scripts/topology.ts --check
	$(PYTHON) -m compileall -q mcp-service/src tests router-image/dispatcher scripts/host-fault-controller.py scripts/observer-host.py
	cd web-ui && bun run --bun typecheck
	cd web-ui && bun run scripts/features.ts
	test -s SPEC.md

git-check:
	git diff --check

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
	cd web-ui && bun test src
check: lint test
	cd web-ui && bun run --bun build
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
	cd web-ui && bun run --bun format
bdd: acceptance
logs-once:
	bun scripts/log-collector.ts --once
logs-follow:
	bun scripts/log-collector.ts --duration 600
bdd-logs:
	cd web-ui && bun x --bun bddgen -c playwright.logs.config.ts && bun x --bun playwright test -c playwright.logs.config.ts

coverage-update:
	cd web-ui && bun run scripts/features.ts --write
bdd-python:
	mkdir -p reports
	.venv/bin/behave --format json --outfile reports/bdd-python.json $$(cd web-ui && bun run scripts/feature-paths.ts python)
bdd-web:
	cd web-ui && bun run --bun test:bdd
bdd-events:
	cd web-ui && bun run --bun build
	cd web-ui && bun x --bun bddgen -c playwright.bdd.config.ts && bun x --bun playwright test -c playwright.bdd.config.ts --grep 'Volatile network events panel|Validate isolated network event models'
acceptance: check bdd-python bdd-web
	cd web-ui && bun run scripts/verify-acceptance.ts
router-build:
	$(COMPOSE) --profile lab build p1
watch-logs:
	bun scripts/log-watcher.ts start
stop-logs:
	bun scripts/log-watcher.ts stop
bdd-boot:
	cd web-ui && bun x --bun bddgen -c playwright.boot.config.ts && bun x --bun playwright test -c playwright.boot.config.ts
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
	cd web-ui && bun x --bun bddgen -c playwright.bdd.config.ts && bun x --bun playwright test -c playwright.matrix.config.ts
live-ui-faults:
	cd web-ui && bun x --bun bddgen -c playwright.faults.config.ts && bun x --bun playwright test -c playwright.faults.config.ts
bootstrap:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements-dev.lock
	cd web-ui && bun install --frozen-lockfile
live-performance:
	cd web-ui && bun x --bun bddgen -c playwright.performance.config.ts && bun x --bun playwright test -c playwright.performance.config.ts
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

live-health:
	.venv/bin/behave features/operations/live_management_health.feature
