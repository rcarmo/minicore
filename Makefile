SHELL := /bin/sh
PYTHON ?= python3
COMPOSE := docker compose -f compose/compose.json
export PYTHONPATH := $(CURDIR)/vendor/umcp:$(CURDIR)/mcp-service/src:$(CURDIR)/tests
.PHONY: install generate lint test check build up down status observe lab-up smoke clean
install:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements-dev.txt
	cd web-ui && bun install --frozen-lockfile
generate:
	bun scripts/topology.ts
lint:
	.venv/bin/ruff check mcp-service/src tests features
	.venv/bin/ruff format --check mcp-service/src tests features
	.venv/bin/mypy mcp-service/src --explicit-package-bases
	cd web-ui && bun run lint
	bun scripts/topology.ts --check
	$(PYTHON) -m compileall -q mcp-service/src tests
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
	.venv/bin/ruff format mcp-service/src tests features
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
