#!/usr/bin/env bash
# backup.sh — PostgreSQL base backup to object storage
#
# Uses pg_basebackup to create a full backup, tars + compresses it,
# and uploads to the S3-compatible object store (MinIO in dev, the
# same S3 endpoint in production — see ARCHITECTURE.md).
#
# Run hourly via cron/systemd timer. Retention is handled externally
# (object storage lifecycle policies).
#
# Prerequisites:
#   - .env with TOPOS_S3_* and POSTGRES_* variables
#   - pg_basebackup (postgresql-client-16)
#   - curl + awscli or MinIO client

set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=/dev/null
[ -f .env ] && . .env

: "${TOPOS_DB_DSN:=postgresql://topos:devonly@localhost:5432/topos}"
: "${TOPOS_S3_ENDPOINT:=http://localhost:9000}"
: "${TOPOS_S3_ACCESS_KEY:=topos}"
: "${TOPOS_S3_SECRET_KEY:=devonlydevonly}"
: "${TOPOS_S3_BUCKET:=topos-backups}"

BACKUP_NAME="topos-pg-$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/tmp/${BACKUP_NAME}"
BACKUP_FILE="/tmp/${BACKUP_NAME}.tar.zst"

# Extract PG host/port from DSN
PG_HOST=$(echo "$TOPOS_DB_DSN" | sed -E 's|.*://[^:]+:[^@]+@([^:/]+).*|\1|')
PG_PORT=$(echo "$TOPOS_DB_DSN" | sed -E 's|.*://[^:]+:[^@]+@[^:]+:([0-9]+)/.*|\1|')
PG_PORT=${PG_PORT:-5432}

echo "=== backup: ${BACKUP_NAME} ==="

# ── Take base backup ─────────────────────────────────────────────────────
# Ex- container — runs against the docker-compose postgres
docker compose exec -T postgres pg_basebackup \
  -h localhost \
  -p 5432 \
  -U topos \
  -D "$BACKUP_DIR" \
  -Ft \
  -z \
  -P

# ── Tar + compress ───────────────────────────────────────────────────────
# (Already -z, but wrap in single archive)
if [ -f "$BACKUP_FILE" ]; then rm -f "$BACKUP_FILE"; fi
tar -C /tmp -cf "${BACKUP_FILE}" "${BACKUP_NAME}" 2>/dev/null || \
tar -I zstd -C /tmp -cf "${BACKUP_FILE}" "${BACKUP_NAME}"

# ── Upload to S3 ─────────────────────────────────────────────────────────
# Try aws CLI first, fall back to curl-based upload (MinIO)
if command -v aws &>/dev/null; then
  aws s3 cp "$BACKUP_FILE" "s3://${TOPOS_S3_BUCKET}/postgres/${BACKUP_NAME}.tar.zst" \
    --endpoint-url "$TOPOS_S3_ENDPOINT"
elif command -v mc &>/dev/null; then
  mc cp "$BACKUP_FILE" "topos/${TOPOS_S3_BUCKET}/postgres/${BACKUP_NAME}.tar.zst"
else
  # curl-based PUT to MinIO-style S3
  curl -s -X PUT \
    "${TOPOS_S3_ENDPOINT}/${TOPOS_S3_BUCKET}/postgres/${BACKUP_NAME}.tar.zst" \
    -H "Content-Type: application/zstd" \
    -H "Authorization: Bearer ${TOPOS_S3_SECRET_KEY}" \
    --data-binary "@$BACKUP_FILE"
fi

# ── Cleanup ──────────────────────────────────────────────────────────────
rm -rf "$BACKUP_DIR" "$BACKUP_FILE"

echo "=== backup: done ==="
