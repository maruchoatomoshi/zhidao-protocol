#!/usr/bin/env bash
set -euo pipefail

# ZHIDAO WAL watchdog.
# Alerts via Telegram when the SQLite WAL file grows beyond the threshold or
# when "database is locked" errors appear in recent service logs.
# Both incidents of 2026-06-09 were visible hours in advance as WAL growth —
# this check turns a three-day crisis into a five-minute fix.

DB_PATH="${ZHIDAO_DB_PATH:-/root/zhidao.db}"
WAL_PATH="${DB_PATH}-wal"
WAL_LIMIT_BYTES="${ZHIDAO_WAL_LIMIT_BYTES:-8388608}"   # 8 MB default
JOURNAL_WINDOW="${ZHIDAO_WATCHDOG_JOURNAL_WINDOW:-10 minutes ago}"
BOT_TOKEN="${ZHIDAO_ALERT_BOT_TOKEN:-}"
CHAT_ID="${ZHIDAO_ALERT_CHAT_ID:-}"

alerts=()

if [[ -f "${WAL_PATH}" ]]; then
  wal_size="$(stat -c %s "${WAL_PATH}")"
  if (( wal_size > WAL_LIMIT_BYTES )); then
    alerts+=("WAL file is $(( wal_size / 1024 / 1024 )) MB (limit $(( WAL_LIMIT_BYTES / 1024 / 1024 )) MB): ${WAL_PATH}")
  fi
fi

locked_count="$(journalctl -u zhidao_api.service -u zhidao_bot.service \
  --since "${JOURNAL_WINDOW}" --no-pager 2>/dev/null \
  | grep -c "database is locked" || true)"
if (( locked_count > 0 )); then
  alerts+=("${locked_count} 'database is locked' errors in logs since ${JOURNAL_WINDOW}")
fi

slow_count="$(journalctl -u zhidao_api.service \
  --since "${JOURNAL_WINDOW}" --no-pager 2>/dev/null \
  | grep -c "ZHIDAO_SLOW_CONN" || true)"
if (( slow_count > 0 )); then
  alerts+=("${slow_count} ZHIDAO_SLOW_CONN entries in logs since ${JOURNAL_WINDOW}")
fi

if (( ${#alerts[@]} == 0 )); then
  exit 0
fi

message="⚠️ ZHIDAO WATCHDOG $(hostname) $(date -u +%H:%M)UTC"
for line in "${alerts[@]}"; do
  message+=$'\n'"• ${line}"
done
message+=$'\n'"Runbook: CLAUDE.md → 'If the server degrades again'"

echo "${message}" >&2

if [[ -n "${BOT_TOKEN}" && -n "${CHAT_ID}" ]]; then
  curl -sS --max-time 15 \
    -d "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${message}" \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" >/dev/null \
    || echo "Failed to deliver Telegram alert." >&2
else
  echo "ZHIDAO_ALERT_BOT_TOKEN / ZHIDAO_ALERT_CHAT_ID not set; alert logged only." >&2
fi

# Non-zero exit marks the systemd unit as failed so the alert is also visible
# in `systemctl --failed`.
exit 1
