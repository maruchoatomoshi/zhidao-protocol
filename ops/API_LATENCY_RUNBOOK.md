# ZHIDAO API Latency Runbook

Purpose: diagnose false "no connection" errors in Telegram Mini App when a POST reaches the API, succeeds, but the client receives the response too late or loses the WebView connection.

## What Was Added

`zhidao_api_ready.py` now logs request timings to `journalctl`.

Logged line format:

```text
ZHIDAO_API_TIMING request_id=<id> method=POST path=/api/... status=200 elapsed_ms=123.4 client=<ip> error=-
```

Response headers:

- `X-Request-ID`
- `X-Process-Time-ms`

Default behavior:

- Always logs key POST endpoints:
  - `/api/contracts`
  - `/api/contracts/{id}/accept`
  - `/api/contracts/{id}/complete`
  - `/api/contracts/{id}/cancel`
  - `/api/contracts/{id}/dispute`
  - `/api/admin/points`
  - `/api/admin/rep`
  - `/api/diary/stars/rate`
- Logs any `/api/*` request slower than `REQUEST_LOG_SLOW_MS`.
- Default slow threshold: `1500 ms`.

Optional env:

```ini
Environment="REQUEST_LOG_SLOW_MS=1500"
Environment="REQUEST_LOG_ALL=0"
```

Use `REQUEST_LOG_ALL=1` only temporarily. It can make journal noisy.

## Server Commands

Recent timing lines:

```bash
journalctl -u zhidao_api.service --since "10 minutes ago" --no-pager -l \
  | grep 'ZHIDAO_API_TIMING'
```

Slow API requests:

```bash
journalctl -u zhidao_api.service --since "1 hour ago" --no-pager -l \
  | grep 'ZHIDAO_API_TIMING' \
  | awk '$0 ~ /elapsed_ms=/ { print }'
```

Specific endpoint:

```bash
journalctl -u zhidao_api.service --since "1 hour ago" --no-pager -l \
  | grep 'ZHIDAO_API_TIMING' \
  | grep '/api/diary/stars/rate'
```

SQLite WAL status:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('/root/zhidao.db')
c = conn.cursor()
print('journal_mode:', c.execute('PRAGMA journal_mode').fetchone()[0])
print('busy_timeout:', c.execute('PRAGMA busy_timeout').fetchone()[0])
conn.close()
PY
```

## Interpretation

If `elapsed_ms` is small, for example `< 500 ms`, but the user sees "no connection", the delay is probably outside the handler:

- Telegram WebView network stack;
- mobile network;
- TLS/proxy;
- client-side timeout or aborted fetch.

If `elapsed_ms` is large, for example `> 2000 ms`, the delay is inside the API process:

- SQLite lock wait;
- synchronous DB writes inside `async def`;
- external HTTP call;
- slow Telegram send;
- single-worker queue under burst load.

If many requests become slow at once, check:

- mass diary rating scenario;
- repeated contract actions;
- SQLite write lock contention;
- uvicorn worker count;
- CPU/RAM pressure.

## SQLite Notes

The API now sets:

- `PRAGMA journal_mode=WAL` during startup;
- `PRAGMA synchronous=NORMAL` during startup;
- `timeout=30` and `PRAGMA busy_timeout=30000` for SQLite connections.

This helps with read/write concurrency and short lock bursts. It does not replace a real queue or PostgreSQL under heavy parallel writes.

## Uvicorn / Service Checks

Show unit:

```bash
systemctl cat zhidao_api.service
```

Check whether API runs with one worker or multiple:

```bash
systemctl cat zhidao_api.service | grep -E 'uvicorn|workers'
```

For SQLite, multiple workers can increase write lock contention. Prefer one worker unless the DB layer is redesigned.

## UX Rule

Do not show "Нет соединения" immediately after a POST timeout if the operation may have reached the server.

Better flow:

1. Show: "Операция отправлена. Проверяю результат..."
2. Reload the relevant server state.
3. If the state changed, show success.
4. If the state did not change, allow retry.
5. For create-like actions, use an idempotency key before allowing retry.

Critical idempotency candidates:

- contract creation;
- diary rating;
- admin point/REP mutation;
- gift sending;
- shop purchase.

## Recommended Architecture

Short-term:

- Keep normal API actions synchronous.
- Add request timing logs.
- After client timeout, reload state before showing failure.
- Disable duplicate submit buttons while operation is pending.

Medium-term:

- Add `client_request_id` for mutation endpoints.
- Store operation result by `client_request_id`.
- If client retries the same operation, return the original result instead of duplicating data.

Long-term:

- For expensive operations: `POST -> accepted operation_id -> poll status`.
- Move burst-heavy writes to a queue.
- Consider PostgreSQL if concurrent writes become common during the trip.
