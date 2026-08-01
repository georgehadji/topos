.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := uv run

# On Windows: run these from Git Bash, or `make` inside the dev container.

## ── The gate ────────────────────────────────────────────────────────────────

.PHONY: check
check: lint types layers filesize test migrations ## Everything CI runs. Merge is blocked on this.
	@echo "✅ make check passed"

.PHONY: lint
lint: ## ruff format check + lint
	$(PY) ruff format --check src tests
	$(PY) ruff check src tests

.PHONY: fix
fix: ## autofix what is autofixable
	$(PY) ruff format src tests
	$(PY) ruff check --fix src tests

.PHONY: types
types: ## mypy --strict
	$(PY) mypy

.PHONY: layers
layers: ## enforce ARCHITECTURE.md layering
	$(PY) lint-imports --config .importlinter

.PHONY: filesize
filesize: ## no source file over 400 lines (context economics, see ARCHITECTURE.md)
	@bad=$$(find src tests -name '*.py' -exec awk 'END{if(NR>400) print FILENAME" ("NR" lines)"}' {} \;); \
	if [ -n "$$bad" ]; then echo "❌ files over 400 lines:"; echo "$$bad"; exit 1; fi
	@echo "✓ file sizes ok"

.PHONY: migrations
migrations: ## migrations apply cleanly and leave the database at head
	# NOT `alembic check`: that is autogenerate-based and needs a MetaData to
	# diff the schema against. Migrations here are hand-written and env.py
	# exposes no models (ARCHITECTURE.md > Data access: no ORM), so `check`
	# fails unconditionally. Applying to head is the check that means something.
	$(PY) alembic upgrade head
	@$(PY) alembic current 2>/dev/null | grep -q '(head)' \
	  || { echo "❌ database is not at migration head"; exit 1; }
	@echo "✓ migrations at head"

## ── Tests ───────────────────────────────────────────────────────────────────

.PHONY: test
test: ## unit + contract + golden
	$(PY) pytest

.PHONY: test-unit
test-unit: ## domain only — pure, fast, no mocks, no containers
	$(PY) pytest tests/unit -m "not contract and not e2e"

.PHONY: test-contract
test-contract: ## adapters against a real PostgreSQL
	$(PY) pytest tests/contract -m contract

.PHONY: test-golden
test-golden: ## Greek fixture regression (OCR, extraction, geocode)
	$(PY) pytest tests/golden -m golden

.PHONY: cov
cov: ## coverage, with domain/ held to a high bar
	$(PY) pytest --cov=topos --cov-report=term-missing --cov-report=html

## ── Eval ────────────────────────────────────────────────────────────────────

.PHONY: eval
eval: ## run the quality suite and print the PROGRESS.md measurement table
	$(PY) python -m eval.run --all

.PHONY: eval-greek-fts
eval-greek-fts: ## slice 0.5 — measure greek_cfg against the `simple` baseline
	$(PY) python -m eval.greek_fts_probe

.PHONY: cost
cost: ## LLM spend this month, from extraction_run
	$(PY) topos-cli cost --month current

## ── Dev stack ───────────────────────────────────────────────────────────────

.PHONY: up
up: ## start postgres + minio + api + worker
	docker compose up -d --build

.PHONY: down
down:
	docker compose down

.PHONY: logs
logs:
	docker compose logs -f api worker

.PHONY: db
db: ## psql into the dev database
	docker compose exec postgres psql -U topos -d topos

.PHONY: upgrade
upgrade: ## apply migrations
	$(PY) alembic upgrade head

.PHONY: revision
revision: ## new HAND-WRITTEN migration: make revision m="core schema"
	$(PY) alembic revision -m "$(m)"

.PHONY: seed
seed: ## load source registry + Thessaloniki gazetteer
	$(PY) topos-cli seed

## ── Ops ─────────────────────────────────────────────────────────────────────

.PHONY: backup
backup: ## base backup to object storage
	./infra/backup.sh

.PHONY: restore-drill
restore-drill: ## PITR into a throwaway container, timed. Run quarterly. Record in PROGRESS.md.
	./infra/restore-drill.sh

.PHONY: deploy
deploy: check ## deploy to the host (gated on `make check`)
	./infra/deploy.sh

## ── Meta ────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'
