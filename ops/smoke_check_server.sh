#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://127.0.0.1:8443}"
TOKEN_FILE="${API_INTERNAL_TOKEN_FILE:-/root/.zhidao_internal_token}"
TEST_TELEGRAM_ID="${TEST_TELEGRAM_ID:-}"

if [[ ! -s "${TOKEN_FILE}" ]]; then
  echo "Missing internal-token file: ${TOKEN_FILE}" >&2
  exit 1
fi

TOKEN="$(cat "${TOKEN_FILE}")"
CURL=(curl -fsSk -H "x-internal-token: ${TOKEN}")

echo "API settings:"
"${CURL[@]}" "${API_URL}/api/settings"
echo

echo "Seeded shop item count:"
"${CURL[@]}" "${API_URL}/api/shop?telegram_id=0" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["items"]))'

if [[ -n "${TEST_TELEGRAM_ID}" ]]; then
  echo "Test user profile:"
  "${CURL[@]}" "${API_URL}/api/user/${TEST_TELEGRAM_ID}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("full_name"), d.get("status"), d.get("has_vpn"))'
fi

echo "Database summary:"
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("/root/zhidao.db")
for table in ("users", "expected_students", "shop_items", "achievements", "settings"):
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        count = "MISSING"
    print(f"{table}: {count}")
conn.close()
PY

echo "Unauthorized mutation must return 401 and CORS:"
headers="$(
  curl -sk -D - -o /dev/null -X POST "${API_URL}/api/user/set_path" \
    -H "Origin: https://maruchoatomoshi.github.io" \
    -H "Content-Type: application/json" \
    -d '{"telegram_id":1,"path":"cyberpunk"}'
)"
printf '%s\n' "${headers}" | grep -Ei '^HTTP/|^access-control-allow-origin:'
printf '%s\n' "${headers}" | grep -qE '^HTTP/[^ ]+ 401 ' || {
  echo "Auth smoke test failed: mutation did not return 401." >&2
  exit 1
}

if [[ -n "${TEST_TELEGRAM_ID}" ]]; then
  echo "Private profile read without Telegram auth must return 401:"
  profile_status="$(curl -sk -o /dev/null -w '%{http_code}' "${API_URL}/api/points/${TEST_TELEGRAM_ID}")"
  [[ "${profile_status}" == "401" ]] || {
    echo "Auth smoke test failed: private points returned HTTP ${profile_status}." >&2
    exit 1
  }
  echo "HTTP ${profile_status}"
fi

echo "Server smoke check completed. Complete Telegram Mini App actions manually with a real signed session."
