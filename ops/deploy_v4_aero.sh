#!/usr/bin/env bash
# One approved Hainan release. Does not touch nginx, VPN, credentials or roster.
set -Eeuo pipefail
# Git checkout must produce code readable by the service account. Backups live
# in an explicitly private directory; a global 077 breaks root-owned checkout.
umask 022

repo=/opt/zhidao-v4
db=/var/lib/zhidao-v4/zhidao.db
target=ed4c593fc7c05706a5b6cf446ba69a46b1739046

[[ $(id -u) == 0 ]] || { echo 'Run from the root Termius session.'; exit 1; }
cd "$repo"
[[ $(git rev-parse --show-toplevel) == "$repo" ]]
[[ -f "$db" && -x "$repo/.venv/bin/python" ]]
git diff --quiet
git diff --cached --quiet
git cat-file -e "$target^{commit}"
old=$(git rev-parse HEAD)
git merge-base --is-ancestor "$old" "$target" || {
  echo 'Server history differs from this release. Nothing changed; ask for review.'; exit 1;
}
systemctl is-active --quiet zhidao-v4
systemctl is-active --quiet zhidao-v4-bot
[[ $(systemctl show zhidao-v4 -p User --value) == www-data ]]
[[ $(systemctl show zhidao-v4 -p WorkingDirectory --value) == "$repo" ]]
[[ $(df -Pk /var/lib/zhidao-v4 | awk 'END {print $4}') -gt 102400 ]]
"$repo/.venv/bin/python" - "$(systemctl show zhidao-v4 -p MainPID --value)" "$db" <<'PY'
import sys
from pathlib import Path
values = Path('/proc/' + sys.argv[1] + '/environ').read_bytes().split(b'\0')
env = dict(value.split(b'=', 1) for value in values if b'=' in value)
assert env.get(b'ZHIDAO_V4_DB_PATH') == sys.argv[2].encode(), 'Running API database path differs; review required'
print('Running API database path verified (no credentials displayed)')
PY

backup=$(mktemp -d /var/lib/zhidao-v4/deploy-backup-XXXXXXXX)
chmod 700 "$backup"
printf '%s\n' "$old" > "$backup/previous-commit.txt"
git archive "$old" zhidao_v4 migrations/v4 > "$backup/previous-code.tar"
printf 'Release: %s\nPrevious: %s\nBackup: %s\n' "$target" "$old" "$backup"

stopped=0
changed=0
readable_code() {
  git ls-files -z -- zhidao_v4 migrations/v4 | xargs -0 -r chmod a+r
  find "$repo/zhidao_v4" "$repo/migrations/v4" -type d -exec chmod a+rx {} +
}
rollback() {
  local code=$1
  trap - ERR INT TERM
  set +e
  echo 'Deployment stopped. Restoring previous code and starting services.'
  if [[ $changed == 1 ]]; then
    systemctl stop zhidao-v4-bot zhidao-v4
    if ! git switch --detach "$old"; then
      echo "Automatic code rollback failed. Services remain stopped. Backup: $backup"
      exit "$code"
    fi
    readable_code
  fi
  if [[ $stopped == 1 ]]; then
    systemctl start zhidao-v4
    systemctl start zhidao-v4-bot
    systemctl is-active zhidao-v4 zhidao-v4-bot
    # systemd 'active' immediately after start does not establish app readiness.
    recovered=0
    for attempt in {1..15}; do
      if curl --fail --silent --show-error --max-time 2 http://127.0.0.1:8770/api/v4/health; then
        recovered=1; break
      fi
      sleep 1
    done
    [[ $recovered == 1 ]] || echo 'WARNING: old API health still fails; recovery needs attention.'
  fi
  echo "Database was NOT replaced. Additive migration may remain. Backup: $backup"
  exit "$code"
}
trap 'rollback $?' ERR
trap 'rollback 130' INT TERM

stopped=1
systemctl stop zhidao-v4-bot zhidao-v4
# SQLite backup API includes any WAL contents; do not copy the live .db alone.
"$repo/.venv/bin/python" - "$db" "$backup/database.sqlite" <<'PY'
import sqlite3
import sys
from pathlib import Path
source = sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)
dest = sqlite3.connect(sys.argv[2])
try:
    source.backup(dest)
    assert dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not dest.execute('PRAGMA foreign_key_check').fetchall()
    print('Consistent SQLite backup: integrity_check=ok')
finally:
    dest.close()
    source.close()
PY
chmod 600 "$backup/database.sqlite"
sha256sum "$backup/database.sqlite" > "$backup/database.sha256"

changed=1
git merge --ff-only "$target"
readable_code
sudo -u www-data "$repo/.venv/bin/python" -c 'import zhidao_v4.api, zhidao_v4.cases'
sudo -u www-data "$repo/.venv/bin/python" -m zhidao_v4.migrations --db "$db"
# Check while both services are stopped, before legitimate user activity resumes.
"$repo/.venv/bin/python" - "$db" "$backup/database.sqlite" <<'PY'
import sqlite3
import sys
from pathlib import Path
old = sqlite3.connect(Path(sys.argv[2]).as_uri() + '?mode=ro', uri=True)
new = sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)
try:
    for table in ('v4_accounts', 'v4_external_identities', 'v4_seasons', 'v4_season_memberships'):
        assert old.execute(f'SELECT count(*) FROM {table}').fetchone() == new.execute(f'SELECT count(*) FROM {table}').fetchone(), table
    assert new.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not new.execute('PRAGMA foreign_key_check').fetchall()
    print('Identity/season counts unchanged; integrity and foreign keys OK')
finally:
    old.close()
    new.close()
PY
systemctl start zhidao-v4

"$repo/.venv/bin/python" - <<'PY'
import json
import time
from urllib.request import urlopen
from urllib.error import HTTPError
base = 'http://127.0.0.1:8770'
for attempt in range(20):
    try:
        with urlopen(base + '/api/v4/health', timeout=2) as r:
            health = json.load(r)
        assert health['status'] == 'ok' and health['schema_version'] == 6
        break
    except Exception:
        if attempt == 19:
            raise
        time.sleep(1)
with urlopen(base + '/api/v4/cases/rules', timeout=5) as r:
    assert r.status == 200 and json.load(r)
with urlopen(base + '/app/', timeout=5) as r:
    page = r.read().decode('utf-8')
    assert 'aero-desktop.css?v=' in page and 'aero-motion.js?v=' in page
assert 'journey-logo' in page and 'WELCOME TO HAINAN' not in page
for asset in ('aero-desktop.css', 'aero-motion.js', 'case-play.js', 'assets/zhidao-dragon-logo.png'):
    with urlopen(base + '/app/' + asset, timeout=5) as r:
        assert r.status == 200 and len(r.read()) > 100
try:
    urlopen(base + '/api/v4/cases/context', timeout=5)
except HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError('Personal case context unexpectedly public')
print('Local smoke: schema 6; cases rules and Aero assets 200; personal API 401')
PY

systemctl start zhidao-v4-bot
systemctl is-active --quiet zhidao-v4
systemctl is-active --quiet zhidao-v4-bot
trap - ERR INT TERM
printf 'DEPLOY_OK %s\nBACKUP %s\n' "$target" "$backup"
curl --fail --silent --show-error --max-time 15 https://china.marucho.icu:8443/api/v4/health ||
  echo 'External HTTPS check failed; local services passed. Send this output for diagnosis.'
printf '\n'
