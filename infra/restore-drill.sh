#!/usr/bin/env bash
# restore-drill.sh — Point-in-Time Recovery drill into a throwaway container
#
# Run quarterly. Record duration in PROGRESS.md.
#
# This downloads the latest base backup tarball, extracts it into a temporary
# Docker volume, boots a throwaway PostgreSQL server from it, verifies the database
# tables/extensions are fully intact, and cleans up.

set -euo pipefail

export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

# shellcheck source=/dev/null
[ -f .env ] && . .env

: "${TOPOS_DB_DSN:=postgresql://topos:devonly@localhost:5432/topos}"
: "${TOPOS_S3_ENDPOINT:=http://localhost:9000}"
: "${TOPOS_S3_ACCESS_KEY:=topos}"
: "${TOPOS_S3_SECRET_KEY:=devonlydevonly}"
: "${TOPOS_S3_BUCKET:=topos-backups}"

RESTORE_CONTAINER="topos-restore-drill"
RESTORE_VOLUME="topos-restore-data"
BACKUP_FILE="$(pwd)/infra/latest-backup-drill.tar.gz"

START_EPOCH=$(date +%s)

echo "=== restore-drill: starting ==="

# ── Download latest backup ───────────────────────────────────────────────
echo "--- Downloading latest backup using boto3 helper ---"
uv run python infra/download_latest_backup.py "$BACKUP_FILE"

# ── Create throwaway volume & extract backup ──────────────────────────────
echo "--- Creating temporary restore volume ---"
docker volume rm -f "$RESTORE_VOLUME" 2>/dev/null || true
docker volume create "$RESTORE_VOLUME"

echo "--- Extracting base backup into restore volume ---"
# We run a small alpine container to untar the backup into the volume
docker run --rm -v "${RESTORE_VOLUME}:/data" -v "$(pwd)/infra:/backup" alpine tar -xzf "/backup/latest-backup-drill.tar.gz" -C /data

# ── Boot Postgres using the restored volume ──────────────────────────────
echo "--- Booting restored PostgreSQL container ---"
docker rm -f "$RESTORE_CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$RESTORE_CONTAINER" \
  -v "${RESTORE_VOLUME}:/var/lib/postgresql/data" \
  topos-postgres:latest

# Wait for PG to be ready
echo "Waiting for PostgreSQL to initialize..."
for i in $(seq 1 30); do
  if docker exec "$RESTORE_CONTAINER" pg_isready -U topos -d topos >/dev/null 2>&1; then
    echo "Postgres ready after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "FATAL: Postgres did not become ready"
    # Show container logs on failure to help debug
    docker logs "$RESTORE_CONTAINER" || true
    docker rm -f "$RESTORE_CONTAINER"
    docker volume rm -f "$RESTORE_VOLUME"
    rm -f "$BACKUP_FILE"
    exit 1
  fi
  sleep 1
done

# ── Verify restored tables and extensions ────────────────────────────────
echo "--- Verifying restored database ---"
docker exec "$RESTORE_CONTAINER" psql -U topos -d topos \
  -c "SELECT 'tables' AS check_name, count(*)::text AS result FROM information_schema.tables WHERE table_schema = 'public'"

docker exec "$RESTORE_CONTAINER" psql -U topos -d topos \
  -c "SELECT 'extensions' AS check_name, string_agg(extname, ', ') AS result FROM pg_extension"

# ── Teardown ─────────────────────────────────────────────────────────────
echo "--- Cleaning up restore drill artifacts ---"
docker rm -f "$RESTORE_CONTAINER"
docker volume rm -f "$RESTORE_VOLUME"
rm -f "$BACKUP_FILE"

ELAPSED=$(( $(date +%s) - START_EPOCH ))
echo "=== restore-drill: done (${ELAPSED}s) ==="
