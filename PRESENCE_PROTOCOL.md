# ZHIDAO Presence Protocol

Backend foundation for morning wake-up and evening room checks.

## Check types

- `morning` - wake-up confirmation.
- `evening` - room / lights-out window confirmation.

## Status model

- `pending` - no answer yet.
- `confirmed` - child confirmed they are awake / in room.
- `free_time` - child used active `casino_walk` free-time item.
- `leave_requested` - child asked admins for leave.
- `admin_approved` - admin manually approved absence.
- `leave_rejected` - admin rejected leave; child must confirm again.
- `needs_attention` - three bot attempts passed; admins should wake/check the child.
- `penalized` - penalty was applied.
- `skipped` - check skipped manually.

Important: `confirmed` is not final during the evening window. A child can still request leave after confirming.

## Bot flow

### Start a check

Call once when the protocol starts.

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/start \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening","note":"21:00 room check"}'
```

Without `telegram_ids`, backend creates checks for all non-admin users.

### Send bot attempt

After sending each Telegram message to a child, mark the attempt:

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/attempt \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening","telegram_id":8222459731}'
```

If response has `needs_admin_alert: true`, bot should notify admins.

### Child buttons

`✅ Я в комнате` / `✅ Я проснулся`

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/confirm \
  -H "Content-Type: application/json" \
  -d '{"check_type":"evening","telegram_id":8222459731,"action":"confirm"}'
```

`🕐 Свободное время`

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/confirm \
  -H "Content-Type: application/json" \
  -d '{"check_type":"evening","telegram_id":8222459731,"action":"free_time"}'
```

Backend checks active `casino_walk`. If there is no active item, it returns `400 No active free time`.

`🙋 Нужен отгул`

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/confirm \
  -H "Content-Type: application/json" \
  -d '{"check_type":"evening","telegram_id":8222459731,"action":"request_leave","note":"к ребятам в комнату"}'
```

Bot should notify admins with approve/reject buttons.

### Admin approve/reject

Approve:

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/admin/approve \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening","telegram_id":8222459731,"reason":"admin_approved: parents walk until 21:45"}'
```

Reject:

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/admin/reject \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening","telegram_id":8222459731,"reason":"вернуться в комнату"}'
```

If rejected, bot should ask the child to confirm again.

### Escalate after three attempts

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/admin/escalate \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening"}'
```

Response returns `needs_attention` list for admin notifications.

### Apply final penalty

Use after admin wake-up/check window, not immediately after the first missed answer.

```bash
curl -X POST https://hk.marucho.icu:8443/api/presence/admin/penalize \
  -H "Content-Type: application/json" \
  -H "x-admin-id: 389741116" \
  -d '{"check_type":"evening","penalty_points":50}'
```

### Admin overview

```bash
curl "https://hk.marucho.icu:8443/api/presence/admin/overview?check_type=evening" \
  -H "x-admin-id: 389741116"
```

## Recommended schedules

### Morning

- Start check.
- Send attempt 1.
- Wait 10 minutes, send attempt 2.
- Wait 10 minutes, send attempt 3.
- Escalate to admins.
- Apply penalty only after admin safety window.

### Evening

- 21:00 start `evening`.
- Children can confirm, request leave, or use free time.
- Leave requests go to admins.
- 22:00 final review / escalation.
- Penalty only after admin wake-up/check window.

