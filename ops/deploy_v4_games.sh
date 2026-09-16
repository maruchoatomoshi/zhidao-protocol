#!/usr/bin/env bash
# One approved Hainan release. Does not touch nginx, VPN, credentials or roster.
set -Eeuo pipefail
# Git checkout must produce code readable by the service account. Backups live
# in an explicitly private directory; a global 077 breaks root-owned checkout.
umask 022

repo=/opt/zhidao-v4
db=/var/lib/zhidao-v4/zhidao.db
target=ea906f3e411e019e5fdbfdaef06b6cd912fcada0
# A reviewed full SHA may be passed explicitly; without it the pinned release above is deployed.
target="${1:-$target}"
[[ "$target" =~ ^[0-9a-f]{40}$ ]] || { echo 'Expected a full reviewed commit SHA.'; exit 1; }
public_health=https://china.marucho.icu:8443/api/v4/health
# Deploy backups kept on this disk, newest first; older ones are removed after a
# successful release. Each holds the database and the previous code.
keep_backups=10

[[ $(id -u) == 0 ]] || { echo 'Run from the root Termius session.'; exit 1; }
cd "$repo"
[[ $(git rev-parse --show-toplevel) == "$repo" ]]
[[ -f "$db" && -x "$repo/.venv/bin/python" ]]
git diff --quiet
git diff --cached --quiet
git cat-file -e "$target^{commit}"
# The expected schema is the newest migration in the target release, so a new
# migration no longer needs a hand edit here. Verify it BEFORE stopping services
# or changing files, and never deploy a release older than the running schema.
target_schema=$(git ls-tree -r --name-only "$target" -- migrations/v4 | sed -n 's|migrations/v4/\([0-9][0-9][0-9][0-9]\)_.*\.sql$|\1|p' | sort | tail -n 1)
[[ "$target_schema" =~ ^[0-9]{4}$ ]] || { echo 'Target release has no V4 migrations. Nothing changed.'; exit 1; }
expected_schema=$((10#$target_schema))
current_schema=$(curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8770/api/v4/health |
  "$repo/.venv/bin/python" -c 'import json, sys; print(int(json.load(sys.stdin)["schema_version"]))') ||
  { echo 'Running API health did not report its schema. Nothing changed.'; exit 1; }
(( expected_schema >= current_schema )) || {
  echo "Target schema $expected_schema is older than running schema $current_schema. Nothing changed."; exit 1;
}
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
printf 'Release: %s\nPrevious: %s\nBackup: %s\nSchema: %s -> %s\n' "$target" "$old" "$backup" "$current_schema" "$expected_schema"

stopped=0
changed=0
readable_code() {
  git ls-files -z -- zhidao_v4 migrations/v4 | xargs -0 -r chmod a+r
  find "$repo/zhidao_v4" "$repo/migrations/v4" -type d -exec chmod a+rx {} +
}
# The database runs in WAL: SQLite keeps "$db-wal" and "$db-shm" beside it.
# The checks in this script open the database as root; if one of them leaves
# those files owned by root, the www-data service can no longer write. Hand
# them back to the database owner before anything else opens the file.
own_wal_files() {
  local file
  for file in "$db-wal" "$db-shm"; do
    if [[ -e $file ]]; then
      chown --reference="$db" "$file"
    fi
  done
}
# Only directories this script creates are candidates, and never the backup of
# the release in progress.
prune_backups() {
  local dir
  local -a stale
  mapfile -t stale < <(ls -1dt /var/lib/zhidao-v4/deploy-backup-* | tail -n +$((keep_backups + 1)))
  for dir in "${stale[@]}"; do
    if [[ $dir == /var/lib/zhidao-v4/deploy-backup-* && -d $dir && $dir != "$backup" ]]; then
      rm -rf -- "$dir"
      echo "Removed old deploy backup: $dir"
    fi
  done
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
  own_wal_files
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
own_wal_files

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
own_wal_files
systemctl start zhidao-v4

"$repo/.venv/bin/python" - "$expected_schema" <<'PY'
import json
import sys
import time
from urllib.request import urlopen
from urllib.error import HTTPError
expected_schema = int(sys.argv[1])
base = 'http://127.0.0.1:8770'
for attempt in range(20):
    try:
        with urlopen(base + '/api/v4/health', timeout=2) as r:
            health = json.load(r)
        assert health['status'] == 'ok' and health['schema_version'] == expected_schema, health
        assert health['journal_mode'] == 'wal', health
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
assert 'readability.css?v=' in page and 'data-target="games"' in page
assert 'gameGuide' in page and 'desktop-collection.svg' in page
for asset in ('readability.css', 'games.css', 'games.js', 'game-outage.js', 'virus.js', 'assets/icons/desktop-collection.svg'):
    with urlopen(base + '/app/' + asset, timeout=5) as r:
        assert r.status == 200
        from pathlib import Path
        assert r.read() == (Path('/opt/zhidao-v4/zhidao_v4/static/app') / asset).read_bytes(), asset
try:
    urlopen(base + '/api/v4/cases/context', timeout=5)
except HTTPError as error:
    assert error.code == 401
else:
    raise AssertionError('Personal case context unexpectedly public')
print(f'Local smoke: schema {expected_schema}, WAL; cases rules and release assets 200; personal API 401')
PY

systemctl start zhidao-v4-bot
systemctl is-active --quiet zhidao-v4
systemctl is-active --quiet zhidao-v4-bot
# The release is live locally from here on; nothing below rolls it back.
trap - ERR INT TERM
printf 'LOCAL_OK %s\nBACKUP %s\n' "$target" "$backup"
prune_backups || echo 'WARNING: could not prune old deploy backups; the release itself is fine.'

# What people actually reach goes through nginx and TLS on 8443. A local green
# with a public red is not a finished release: say so and exit non-zero. Code is
# not rolled back — the cause is outside the app (nginx, certificate, network).
public_ok=0
for attempt in 1 2 3 4 5; do
  if public=$(curl --fail --silent --show-error --max-time 15 "$public_health") &&
     "$repo/.venv/bin/python" -c '
import json, sys
health = json.loads(sys.argv[1])
assert health["status"] == "ok" and health["schema_version"] == int(sys.argv[2]) and health["journal_mode"] == "wal"
' "$public" "$expected_schema"; then
    public_ok=1
    break
  fi
  sleep 3
done
if [[ $public_ok == 1 ]]; then
  printf 'DEPLOY_OK %s\n%s\n' "$target" "$public"
else
  echo "PUBLIC_CHECK_FAILED $target: local services run the new release, but $public_health did not confirm schema $expected_schema in WAL. Send this output for diagnosis."
  exit 2
fi
