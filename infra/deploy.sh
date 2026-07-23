#!/usr/bin/env bash
# deploy.sh — deploy to the single host (ARCHITECTURE.md §Shape)
# Gated on `make check` (see Makefile). Designed for a single-engineer
# team with no ops team. Idempotent.
#
# Prerequisites:
#   - The host has Docker + docker-compose-plugin installed
#   - .env is present with production secrets
#   - The host is an EU-resident VM (constraint L8)
#
# Usage: ./infra/deploy.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== deploy: starting ==="

# ── Pre-flight ───────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "FATAL: .env not found. Create it from .env.example with production values."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "FATAL: Docker is not running."
  exit 1
fi

# ── Pull or build images ─────────────────────────────────────────────────
echo "--- Building images ---"
docker compose build --pull

# ── Apply migrations ─────────────────────────────────────────────────────
echo "--- Running any pending migrations ---"
docker compose run --rm api alembic upgrade head

# ── Start stack ──────────────────────────────────────────────────────────
echo "--- Starting services ---"
docker compose up -d --remove-orphans

# ── Smoke test ───────────────────────────────────────────────────────────
echo "--- Smoke testing /healthz ---"
for i in $(seq 1 12); do
  if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "Healthz OK after ${i}s"
    break
  fi
  if [ "$i" -eq 12 ]; then
    echo "FATAL: API did not become healthy within 12s"
    exit 1
  fi
  sleep 1
done

echo "=== deploy: done ==="
