#!/usr/bin/env bash
# backup.sh — PostgreSQL base backup to object storage
#
# Generates a gzipped tar backup stream from the postgres container
# and uploads it to the S3-compatible object store.
#
# Idempotent and requires no postgres client tools or compression
# utilities on the host.

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

BACKUP_NAME="topos-pg-$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$(pwd)/infra/${BACKUP_NAME}.tar.gz"

echo "=== backup: ${BACKUP_NAME} ==="

# ── Ensure S3 Bucket Exists ──────────────────────────────────────────────
echo "Ensuring S3 bucket '${TOPOS_S3_BUCKET}' exists..."
curl -s -X PUT "${TOPOS_S3_ENDPOINT}/${TOPOS_S3_BUCKET}" >/dev/null || true

# ── Stream base backup from container directly to host file ──────────────
echo "Streaming pg_basebackup from container..."
docker compose exec -T postgres pg_basebackup \
  -h localhost \
  -p 5432 \
  -U topos \
  -Ft \
  -z \
  -X fetch \
  -D - > "$BACKUP_FILE"

# ── Upload to S3 ─────────────────────────────────────────────────────────
echo "Uploading backup to S3/MinIO..."
uv run python infra/upload_backup.py "$BACKUP_FILE" "postgres/${BACKUP_NAME}.tar.gz"

# ── Cleanup ──────────────────────────────────────────────────────────────
rm -f "$BACKUP_FILE"

echo "=== backup: done ==="
