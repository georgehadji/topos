#!/usr/bin/env bash
# restore-drill.sh — Point-in-Time Recovery drill into a throwaway container
#
# Run quarterly. Record duration in PROGRESS.md.
#
# This spins up a throwaway postgres container, downloads the latest backup
# from object storage, restores it, verifies the restore, and tears down.
# It does NOT touch the production database.
#
# Prerequisites:
#   - Same as backup.sh
#   - Postgres 16 client tools (pg_restore, pg_isready)

set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=/dev/null
[ -f .env ] && . .env

: "${TOPOS_DB_DSN:=postgresql://topos:devonly@localhost:5432/topos}"
: "${TOPOS_S3_ENDPOINT:=http://localhost:9000}"
: "${TOPOS_S3_ACCESS_KEY:=topos}"
: "${TOPOS_S3_SECRET_KEY:=devonlydevonly}"
: "${TOPOS_S3_BUCKET:=topos-backups}"

RESTORE_CONTAINER="topos-restore-drill"
RESTORE_DB="topos_restore_drill"

START_EPOCH=$(date +%s)

echo "=== restore-drill: starting ==="

# ── Download latest backup ───────────────────────────────────────────────
echo "--- Downloading latest backup ---"
LATEST=$(curl -s "${TOPOS_S3_ENDPOINT}/${TOPOS_S3_BUCKET}/?prefix=postgres/" \
  | grep -oP 'topos-pg-\d+T[0-9]{6}Z\.tar\.zst' \
  | sort -r \
  | head -1)

if [ -z "$LATEST" ]; then
  echo "FATAL: no backup found in s3://${TOPOS_S3_BUCKET}/postgres/"
  exit 1
fi

echo "Latest backup: ${LATEST}"
BACKUP_FILE="/tmp/${LATEST}"
curl -s -o "$BACKUP_FILE" \
  "${TOPOS_S3_ENDPOINT}/${TOPOS_S3_BUCKET}/postgres/${LATEST}"

# ── Spin up throwaway container ──────────────────────────────────────────
echo "--- Starting throwaway postgres ---"
docker rm -f "$RESTORE_CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$RESTORE_CONTAINER" \
  -e POSTGRES_USER=topos \
  -e POSTGRES_PASSWORD=devonly \
  -e POSTGRES_DB="$RESTORE_DB" \
  topos-postgres:latest

# Wait for PG to be ready
for i in $(seq 1 20); do
  if docker exec "$RESTORE_CONTAINER" pg_isready -U topos >/dev/null 2>&1; then
    echo "Postgres ready after ${i}s"
    break
  fi
  if [ "$i" -eq 20 ]; then
    echo "FATAL: Postgres did not become ready"
    exit 1
  fi
  sleep 1
done

# ── Restore ──────────────────────────────────────────────────────────────
echo "--- Restoring backup ---"
docker exec -i "$RESTORE_CONTAINER" pg_restore \
  -U topos \
  -d "$RESTORE_DB" \
  --clean \
  --if-exists \
  < "$BACKUP_FILE"

# ── Verify ───────────────────────────────────────────────────────────────
echo "--- Verifying restore ---"
docker exec "$RESTORE_CONTAINER" psql -U topos -d "$RESTORE_DB" \
  -c "SELECT 'tables' AS check_name, count(*)::text AS result FROM information_schema.tables WHERE table_schema = 'public'"

docker exec "$RESTORE_CONTAINER" psql -U topos -d "$RESTORE_DB" \
  -c "SELECT 'extensions' AS check_name, string_agg(extname, ', ') AS result FROM pg_extension"

# ── Teardown ─────────────────────────────────────────────────────────────
echo "--- Cleaning up ---"
docker rm -f "$RESTORE_CONTAINER"
rm -f "$BACKUP_FILE"

ELAPSED=$(( $(date +%s) - START_EPOCH ))
echo "=== restore-drill: done (${ELAPSED}s) ==="
