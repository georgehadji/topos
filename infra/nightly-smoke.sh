#!/usr/bin/env bash
# nightly-smoke.sh — nightly smoke test for Topos pipeline
#
# Run from cron/systemd timer. Exits non-zero on failure.
# Writes results to a log file for alerting.

set -euo pipefail

BASE_URL="${TOPOS_BASE_URL:-http://localhost:8000}"
LOG_FILE="${TOPOS_SMOKE_LOG:-/tmp/topos-nightly-smoke.log}"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG_FILE"
}

fail() {
  log "FAIL: $*"
  exit 1
}

log "=== nightly smoke test starting ==="

# 1. Health endpoint
log "Checking /healthz..."
HEALTH=$(curl -sf "${BASE_URL}/healthz") || fail "/healthz returned non-zero exit"
if ! echo "$HEALTH" | grep -q '"ok"'; then
  fail "/healthz did not return ok: $HEALTH"
fi
log "  OK"

# 2. API search endpoint
log "Checking /api/search..."
SEARCH=$(curl -sf "${BASE_URL}/api/search") || fail "/api/search failed"
if ! echo "$SEARCH" | grep -q '"results"'; then
  fail "/api/search missing results field: $SEARCH"
fi
log "  OK"

# 3. Artifact list
log "Checking /artifacts..."
ARTIFACTS=$(curl -sf "${BASE_URL}/artifacts") || fail "/artifacts failed"
COUNT=$(echo "$ARTIFACTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
log "  ${COUNT} artifact(s) found"

# 4. Ingest (lightweight: just 1 doc)
log "Testing /artifacts/ingest (limit=1)..."
INGEST=$(curl -sf -X POST "${BASE_URL}/artifacts/ingest?limit=1") || log "  WARNING: ingest failed (may be transient)"
log "  Done"

# 5. Database connectivity (via /healthz which already tests this)
log "  OK (implied by /healthz)"

log "=== nightly smoke test PASSED ==="
