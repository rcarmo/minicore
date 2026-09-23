SHELL := /bin/sh

.PHONY: install lint test check clean

install:
	@echo "Scaffold has no installable dependencies yet."

lint:
	@test -s README.md
	@test -s AGENTS.md
	@test -s SPEC.md
	@test -s docs/implementation-plan.md
	@echo "Scaffold lint passed."

test:
	@./tests/scaffold.sh

check: lint test

clean:
	@rm -rf .pytest_cache .ruff_cache build dist
