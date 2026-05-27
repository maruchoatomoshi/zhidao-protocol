# ZHIDAO Recovery And Launch Checks

This runbook contains no participant IDs, credentials, or bot tokens. Keep real values only on the server.

## 1. Seed And Data Recovery

Deploy the current API and restart it. Startup safely recreates the shop catalog and default settings without overwriting live state.

```bash
curl -L https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py -o /root/zhidao_api.py
python3 -m py_compile /root/zhidao_api.py
systemctl restart zhidao_api.service
```

Run the server smoke check after installing it from this repository:

```bash
TEST_TELEGRAM_ID=YOUR_TEST_ACCOUNT_ID /usr/local/sbin/smoke_check_zhidao.sh
```

`achievements` is not auto-seeded: no authoritative achievement catalog exists in the repository history or retained API file. Restore it only from a known backup or after agreeing a new catalog.

## 2. Registration Test

Use two dedicated tester accounts before releasing activation codes:

1. Create a `student-only` row with `marzban_username = NULL`.
2. Create a VPN tester row whose `marzban_username` already exists in Marzban and has an active link.
3. If tester names are not in the participant list, add only their Telegram IDs to `REGISTRATION_BYPASS_IDS` in `zhidao_bot.service.d/override.conf`.
4. From each Telegram account, run `/start CODE`, complete registration, open Mini App from the bot button, choose a theme, open profile and shop.

Do not add testers to `ADMIN_IDS` merely to bypass registration validation.

## 3. Secrets And Environment Check

The API and bot must have the same live `BOT_TOKEN`; do not print token values.

```bash
for svc in zhidao_api.service zhidao_bot.service; do
  printf "%s: " "$svc"
  systemctl show "$svc" -p Environment --value \
    | grep -Eq '(^| )BOT_TOKEN=[0-9]+:[A-Za-z0-9_-]+($| )' \
    && echo "BOT_TOKEN format OK" || echo "BOT_TOKEN missing/invalid"
done
```

The API must also have:

```text
TELEGRAM_AUTH_REQUIRED=1
API_INTERNAL_TOKEN=<server-only random value>
EXPECTED_STUDENTS_FILE=/root/expected_students.txt
```

Do not commit server override files, `.env` values, participant names, admin IDs, or database backups.

## 4. External Daily Backup

Install the backup script and systemd units:

```bash
install -m 700 ops/backup_zhidao_db.sh /usr/local/sbin/backup_zhidao_db.sh
install -m 644 ops/zhidao-db-backup.service /etc/systemd/system/zhidao-db-backup.service
install -m 644 ops/zhidao-db-backup.timer /etc/systemd/system/zhidao-db-backup.timer
mkdir -p /etc/zhidao
chmod 700 /etc/zhidao
nano /etc/zhidao/backup.env
chmod 600 /etc/zhidao/backup.env
```

Configure an external `rclone` destination in `/etc/zhidao/backup.env`, test one upload, then enable daily backups:

```bash
systemctl daemon-reload
systemctl start zhidao-db-backup.service
systemctl enable --now zhidao-db-backup.timer
systemctl list-timers zhidao-db-backup.timer --no-pager
```

A local-only archive is not an adequate recovery plan for server loss.

## 5. Telegram Auth Smoke Test

The public API must reject unauthenticated changes:

```bash
curl -sk -i -X POST https://hk.marucho.icu:8443/api/user/set_path \
  -H "Origin: https://maruchoatomoshi.github.io" \
  -H "Content-Type: application/json" \
  -d '{"telegram_id":1,"path":"cyberpunk"}'
```

Expected result: `401 Unauthorized` and `access-control-allow-origin: *`.

With a real Telegram tester account verify these signed operations in Mini App:

- select theme;
- upload/change profile avatar;
- open own wallet, inventory and diary;
- buy and sell a cheap item if test balance allows;
- create/cancel a contract;
- as admin only: open users panel and presence overview.

Private wallet, VPN profile, inventory, diary and personal contract routes require Telegram authorization after the hardened API is deployed.
