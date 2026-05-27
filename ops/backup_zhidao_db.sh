#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${ZHIDAO_DB_PATH:-/root/zhidao.db}"
BACKUP_DIR="${ZHIDAO_BACKUP_DIR:-/root/zhidao_backup/daily}"
OFFSITE_TARGET="${ZHIDAO_OFFSITE_TARGET:-}"
RETENTION_DAYS="${ZHIDAO_BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
RAW_BACKUP="${BACKUP_DIR}/zhidao_${STAMP}.db"
ARCHIVE="${RAW_BACKUP}.gz"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

DB_PATH="${DB_PATH}" RAW_BACKUP="${RAW_BACKUP}" python3 - <<'PY'
import os
import sqlite3

source_path = os.environ["DB_PATH"]
backup_path = os.environ["RAW_BACKUP"]
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
target = sqlite3.connect(backup_path)
with target:
    source.backup(target)
target.close()
source.close()
PY

chmod 600 "${RAW_BACKUP}"
gzip -f "${RAW_BACKUP}"
chmod 600 "${ARCHIVE}"
find "${BACKUP_DIR}" -type f -name 'zhidao_*.db.gz' -mtime "+${RETENTION_DAYS}" -delete

if [[ -z "${OFFSITE_TARGET}" ]]; then
  echo "Local backup created: ${ARCHIVE}" >&2
  echo "ZHIDAO_OFFSITE_TARGET is not configured; external backup was not uploaded." >&2
  exit 2
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "rclone is required for external backup upload." >&2
  exit 2
fi

rclone copy "${ARCHIVE}" "${OFFSITE_TARGET}"
echo "Backup uploaded: ${ARCHIVE} -> ${OFFSITE_TARGET}"
