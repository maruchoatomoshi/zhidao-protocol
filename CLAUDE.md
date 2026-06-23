# CLAUDE.md

Context and working rules for Claude / Claude Code in the `ZHIDAO Protocol` repository.

This project is a Telegram Mini App plus a FastAPI backend file used for deployment. The app is intentionally game-like: cyberpunk / NetWatch / Genshin themes, points economy, cases, raids, diary scoring, Architect Protocol event, profile cards, inventory, and admin tools.

## Project Incident History

### 2026-05-27 — Великий датакрэш (The Great Data Crash)

Server/API/DB ended up in a near-empty state: `users=0`, `expected_students=0`, `shop_items=1`, `achievements=0`, `settings=0`. The environment had to be rebuilt from scratch:

- API and bot were in a reset/old state
- All users, admins, testers, shop items, settings and seed data were gone
- Had to reconfigure all systemd env vars: `ADMIN_IDS`, `ARCHITECT_IDS`, `TELEGRAM_AUTH_REQUIRED`, `API_INTERNAL_TOKEN`, `BOT_TOKEN`, `EXPECTED_STUDENTS_FILE`
- HTTPS/certificate was broken; restored via `certbot --nginx -d hk.marucho.icu`
- Restored the student list via `/root/expected_students.txt` (85 students)
- Manually re-added admins and test accounts: Марк, Юля, МЮ, Лиза, Илья, Тяньхао, 原马克
- Restored VPN/Marzban username bindings
- Restored shop inventory
- Re-verified registration, themes, profiles, Mini App, bot, API

This crash prompted the known-good backup approach and more careful handling of env/secrets.

### 2026-06-09 — Второй датакрэш (The Second Data Crash)

SQLite WAL/checkpoint experiments caused cascading 27–1463 second stalls on all write endpoints (shop purchases, point adjustments). Root causes identified and fixed:

- `wal_checkpoint(TRUNCATE/RESTART)` in a background loop competed with active writers — took 49–72 s and blocked everything
- `await asyncio.to_thread(startup_checkpoint)` inside `@app.on_event("startup")` blocked uvicorn from completing startup — port 8443 unreachable
- Per-request `sqlite3.connect()` scanned the entire WAL file on open (100–300 s when WAL was large)

Resolution: persistent thread-local connections (`_PersistentConn`), PASSIVE-only checkpoint loop (opt-in via env var), startup checkpoint as fire-and-forget background task. Rolled back to known-good backup:
```
/root/zhidao_known_good/zhidao_known_good_20260609_123206.tar.gz
sha256: d842860f72718193c24151f60e6ece7f0041a7dc6c201e770e50c2b840b2c07a
```

## Current Priority

**Backend is stable on the server.** The server runs a known-good version of `/root/zhidao_api.py` that was backed up on 2026-06-09:

```
/root/zhidao_known_good/zhidao_known_good_20260609_123206.tar.gz
sha256: d842860f72718193c24151f60e6ece7f0041a7dc6c201e770e50c2b840b2c07a
```

**CRITICAL: The repo's `zhidao_api_ready.py` diverged from the server during SQLite debugging on 2026-06-09.** Before deploying from the repo, compare the two files or verify with the user.

To check what's running vs what's in the repo:
```bash
diff /root/zhidao_api.py <(curl -sL https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py)
```

Monitoring command:
```bash
journalctl -u zhidao_api.service -u zhidao_bot.service --since "10 minutes ago" --no-pager -l \
  | grep -E "ZHIDAO_DB_WRITE|ZHIDAO_SLOW_CONN|ZHIDAO_WAL|database is locked|ERROR|Traceback"

ls -lh /root/zhidao.db*
```

Healthy state: no grep hits, WAL file ≤ 4MB.

Latest launch snapshot:

- `PROJECT_STATUS_2026-06-17.md` records the current repository state on commit `d01875e`.
- The current repo implementation uses `DB_WRITE_LOCK` plus a single-worker `DB_WRITE_EXECUTOR` and thread-local persistent SQLite connections. Treat this as the known current architecture; do not remove or rewrite it without benchmarking against the live server.
- Frontend feature freeze and launch lock are currently disabled in `js/config.js`.

## Repository Structure

Main files:

- `index.html` is the app shell and markup.
- `css/styles.css` contains all CSS.
- `js/*.js` contains classic browser scripts, not ES modules.
- `zhidao_api_ready.py` is the deployable FastAPI backend source.
- Root media files are used directly by GitHub Pages / raw GitHub URLs.

JavaScript file roles:

- `js/config.js`: Telegram WebApp fallback/bootstrap, API URL, global constants.
- `js/state.js`: shared runtime state such as current user, points, admin status, theme path.
- `js/api.js`: shared request helpers and thin backend wrappers where present.
- `js/ui.js`: page navigation, generic UI helpers, user loading, global utilities.
- `js/themes.js`: theme switching, path logic, CloudStorage/localStorage theme sync.
- `js/telegram-compat.js`: iOS / Telegram Mini App viewport and safe-area compatibility layer.
- `js/shop.js`: shop rendering, inventory, purchases, item use/gift/sell.
- `js/casino.js`: cases, roulette, Genshin prayers, implants/cards, case animation.
- `js/leaderboard.js`: main leaderboard, diary leaderboard, points/rating display.
- `js/diary.js`: diary stars page, extended diary archive, diary scoring, admin diary tools.
- `js/admin.js`: admin panels and admin-only actions.
- `js/raid.js`: raid UI and raid status/actions.
- `js/events.js`: generic event overlay functions.
- `js/architect-event.js`: Architect Protocol event, HUD, questions, music/effects, battle flow.
- `js/blackwall.js`: BlackWall visual/state logic.
- `js/schedule.js`, `js/announcements.js`, `js/laundry.js`, `js/achievements.js`, `js/team.js`: feature-specific sections.

Script loading is classic `<script src="..."></script>`. Do not convert to modules unless the whole app migration is planned.

## Important Project Rules

Do not break globals.

Many functions are called directly from inline HTML handlers such as `onclick="..."`. Avoid renaming public functions unless you update every caller.

Do not change API routes casually.

Frontend and backend are tightly coupled. If you add a route to `zhidao_api_ready.py`, also provide the server update command to the user.

Avoid broad rewrites.

This project was split from a monolithic `index.html`. Keep changes targeted and mechanical unless the user explicitly asks for redesign/refactor.

Be careful with encoding.

Some historical files may display mojibake in PowerShell output. Do not "fix" encoding globally unless specifically tasked. Use UTF-8-safe edits and check the browser visually when possible.

Use `apply_patch` for manual code edits.

Do not use destructive git commands. The user often has active work and expects changes to be preserved.

## Recent Work Summary

### Profile 2.0

Added and polished the operator profile concept:

- Profile card moved toward the main experience.
- Supports avatar, path, rank, title, showcase item, stats, and status line.
- Backend has `/api/profile/{telegram_id}` in `zhidao_api_ready.py`.
- Admin/Architect permissions are shown with Chinese labels:
  - Architect: `架构师`
  - System architect/admin variants may use admin-specific labels.
  - Normal user: `学生节点`

### Favorite showcase item

The profile can show a favorite implant/card-like operator item. Current implementation is lightweight and should not affect economy.

### Leaderboard polish

Main leaderboard has richer operator cards.

Alpha boss should be displayed as a highlighted block above the normal ranking, not as rank 1.

### Diary stars system

The old extended diary still exists but is now admin-only:

- `index.html`: the `АРХИВ` item has `id="diaryArchiveItem"` and is hidden by default.
- `js/diary.js`: `openDiaryPage()` blocks non-admins.
- `js/diary.js`: `syncDiaryAccessVisibility()` reveals the archive only for admins.
- `js/ui.js`: calls `syncDiaryAccessVisibility()` after loading user data.

The new intended flow for ordinary users:

- They should not use the extended diary archive.
- Admins use `ДНЕВНИК ★` to assign stars/bonus.
- Diary rating should show all ordinary users, even if they have zero diary scores.

Backend additions in `zhidao_api_ready.py`:

- `diary_stars` table.
- `GET /api/diary/stars/overview`
- `POST /api/diary/stars/rate`
- `GET /api/diary/stars/leaderboard`

If diary stars show `Ошибка загрузки`, first verify that the deployed backend really includes those routes.

### Architect Protocol

Architect Protocol is a central event/boss fight system.

Important assets:

- `architect_phase1.mp4`
- `architect_phase2.mp4`
- `architect_phase3.mp4`
- `Architect_phase1.png`
- `Architect_phase2.png`
- `Architect_phase3.png`
- `architect_phase1_music.mp3`
- `architect_phase2_music.mp3`
- `architect_phase3_music.mp3`
- `architect_ivent_win.png`
- `architect_ivent_lose.png`
- `entered_architect_event.mp3`
- `architect-arrival.ogg`

Recent direction:

- Full-screen battle video/background.
- Floating HUD, combat log, and command panel above media.
- Phase/button effects exist and can be polished further.
- iPhone/TG safe-area and question modal were partially stabilized.
- Avoid shrinking the boss media into a small stage area unless user asks.

Architect event action meanings:

- Attack: direct damage, especially useful in phase 1.
- Protocol: higher tactical damage, stronger in later phases.
- Sync: opens/helps vulnerability windows, control/support role.
- Stabilize: support action, manages pressure/overload and contributes support.

### Themes

Themes currently need ongoing visual polish:

- NetWatch dark/default.
- NetWatch light.
- Genshin light/dark.

Known focus areas:

- Avoid white-on-light text.
- Avoid overly acidic/bright Genshin event banners.
- Keep inventory cards readable in light themes.
- Keep case/prayer UI switching correctly for admins and normal users.

### Inventory

Inventory was improved toward a unified card standard:

- Image/avatar.
- Rarity/type.
- Charges/durability.
- Date obtained.
- Action affordances.

Implants/cards may still need per-item visual cleanup.

### Casino / cases

Frontend roulette was changed conceptually to show mixed case types in the same field while preserving backend economy. Backend probabilities should remain authoritative.

Do not change case probabilities without explicitly discussing economy.

### Economy

There is an `ECONOMY_PASSPORT.md`. Use it before changing rewards, prices, or limits.

Current principle:

- Backend economy is source of truth.
- Frontend should visualize outcomes, not decide rewards.
- 80 stars is an intentional threshold/guardrail before users can burn currency on cases.

## Deployment Notes

Frontend deploy:

- Push to `main` on GitHub.
- User checks GitHub Pages / raw assets through the Telegram Mini App.

Backend deploy:

- The server runs `zhidao_api.service`.
- The deployed file is `/root/zhidao_api.py`.
- Source of truth in repo is `zhidao_api_ready.py`.

Service checks:

```bash
systemctl status zhidao_api.service --no-pager
journalctl -u zhidao_api.service -n 120 --no-pager
```

The bot is a separate service:

```bash
systemctl status zhidao_bot.service --no-pager
```

Some admin IDs must be added both in backend and bot code if bot/admin behavior differs.

## Smoke Test Checklist

After frontend changes:

- App opens without console errors.
- Bottom navigation works.
- Home/profile card renders.
- Rating opens.
- Diary rating tab renders.
- `ДНЕВНИК ★` opens.
- Normal users do not see/open `АРХИВ`.
- Admins do see/open `АРХИВ`.
- Shop opens.
- Casino opens.
- Theme switching works.
- Architect overlay opens.
- Architect action buttons open a question and submit an answer.
- iPhone safe-area does not cover bottom nav or command panels.

After backend changes:

- `python3 -m py_compile /root/zhidao_api.py`
- `systemctl restart zhidao_api.service`
- `curl -k https://127.0.0.1:8443/api/user/<id>`
- `curl -k https://127.0.0.1:8443/api/profile/<id>`
- For diary stars:

```bash
curl -k "https://127.0.0.1:8443/api/diary/stars/overview?entry_date=2026-04-29" -H "X-Admin-Id: ADMIN_ID_EXAMPLE"
curl -k "https://127.0.0.1:8443/api/diary/stars/leaderboard" -H "X-Admin-Id: ADMIN_ID_EXAMPLE"
```

## Git Workflow

The user often asks to push directly.

Before commit:

```powershell
node --check js\diary.js
node --check js\ui.js
node --check js\leaderboard.js
git diff --check
git status --short
```

Commit and push:

```powershell
git add <changed files>
git commit -m "Short clear message"
git push origin main
```

Do not amend commits unless explicitly requested.

## Things To Avoid

- Do not globally "fix" mojibake based only on terminal output.
- Do not remove old systems unless the user explicitly says to delete them.
- Do not change economy values casually.
- Do not rename inline-handler functions.
- Do not introduce ES modules into the current app.
- Do not make Architect video a small contained box unless explicitly requested.
- Do not hide admin tools for admins while simplifying normal-user UX.

## SQLite / Backend — Hard Rules (learned 2026-06-09)

These rules exist because a series of WAL/checkpoint experiments caused cascading 27–1463 second stalls and a broken startup. Do not repeat them.

**Never run `wal_checkpoint(RESTART)` or `wal_checkpoint(TRUNCATE)` on a live background loop.** Both modes can compete with active writers and cause `database is locked` or 30–70 second stalls that block all API writes. If a checkpoint loop is needed, use `PASSIVE` only, accept that the WAL file won't shrink, and control WAL size via `wal_autocheckpoint`.

**Never add an `await asyncio.to_thread(startup_checkpoint)` inside `@app.on_event("startup")` before the server is ready.** This blocked uvicorn from completing startup — port 8443 was unreachable until manually killed. If a startup checkpoint is needed, run it as a fire-and-forget background task after `asyncio.create_task(...)`.

**The bot is a second writer process.** Any change that increases write lock hold time in the bot (e.g. doing Telegram sends before commit) can starve the API. The bot's `db_connect()` must: commit + close before any `await`, and set `PRAGMA wal_autocheckpoint=0` so it doesn't trigger auto-checkpoints.

**Do not add a dedicated writer executor or thread pool for DB writes** without benchmarking. An extra queue layer just adds latency on top of `DB_WRITE_LOCK`.

**Before any backend change:** check current server state first:
```bash
ls -lh /root/zhidao.db*
journalctl -u zhidao_api.service -n 20 --no-pager | grep -E "WRITE|SLOW|WAL|locked"
```

**If the server degrades again:**
1. Stop both services, run `python3 -c "import sqlite3; c=sqlite3.connect('/root/zhidao.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()"`, restart.
2. If that doesn't help, restore from `/root/zhidao_known_good/`.
3. Only then investigate root cause with logs before changing any code.

## Recommended Next Steps

1. Continue profile polish and UX features — backend is stable.
2. If slow writes return: check if the bot is holding a write transaction during async Telegram sends (the main historical cause).
3. After the trip: consider migrating the bot to API-only writes via `X-Internal-Token` so there is only one SQLite writer process.
4. PostgreSQL migration is plan B, only if SQLite continues to cause issues after the bot write isolation is done.
5. Expand event question pools (user request 2026-06-11): Architect has only 8 questions per action, WildAI Breach only 6 — questions visibly repeat every couple of uses. Seeds live in `ARCHITECT_QUESTION_SEEDS` / `WILD_AI_BREACH_QUESTION_SEEDS` in `zhidao_api_ready.py`; selection is `ORDER BY RANDOM() LIMIT 1` from `event_questions` with no recent-question memory. Note: seeding only runs when the table count for that event_code is 0, so adding seeds requires either deleting existing rows for that code or inserting new rows directly on the server DB.
6. **Feature brainstorm (2026-06-21) — scope is now considered final, no more new features planned beyond these two:**
   - **PvP duels between students**: build after the trip, not before — touches the live points economy and needs unhurried testing. Challenge another operator to a quiz/coinflip duel, wagering points. Reuses the existing quiz-question pattern (Architect/WildAI) and the existing points economy. Fills a real gap — the app currently has no student-vs-student interaction, only student-vs-system progression.
     - Draft mechanic discussed 2026-06-21 (not yet final — Mikhail Yuryevich/МЮ may add requirements around attendance/discipline control before this is built): **hybrid random** outcome (coinflip-style, optionally weighted slightly by rating/points rather than a live synced quiz, since two students are rarely online at the exact same moment); **asynchronous challenge flow** via the bot (A challenges B with a stake, B gets notified and accepts/declines whenever they next open the app — no need for both to be online simultaneously); **zero-sum wager** with fixed stake tiers (e.g. 10/25/50/100 points) rather than arbitrary amounts, so duels redistribute points instead of creating new ones (must not inflate the economy).
     - МЮ cares more about attendance/check-in discipline than fun features, so when revisiting this, consider whether duels should gate on attendance (e.g. only available to students who haven't missed a check-in) per his likely input.
   - **Trip Rewind / "yearbook"**: decided 2026-06-21 to build the feature itself *before* departure (not after) so it's fully tested and just needs flipping on at the end of the trip — there won't be dev time during/right after the trip. It's read-only aggregation over existing tables with no new tables and no economy impact, so it's safe to build now despite the 2-week runway. An end-of-trip auto-generated summary card per user (points earned, achievements, a fun stat-based "role"), in the spirit of Spotify Wrapped. All underlying data already exists (points, achievements, diary stars, casino history) — this is mostly an aggregation screen plus a shareable visual format.
     - Data draft (2026-06-21): pull from existing tables only, no new tracking needed — `economy_log` (points earned/spent), `casino_log` (case/prayer count, best drop), `user_achievements`, `diary_stars`/`diary_entries` (entries submitted, average stars), `shop_purchases` (spend + gifts), `raid_participants`+`raids` (raids joined/won), `contracts`, `daily_checks` (attendance %), `event_participants`/`event_actions` (Architect/WildAI participation, answer accuracy). `users` table has no `created_at`, so "trip duration" should be computed from the trip's known start/end dates, not per-user registration time. Can partially reuse the existing `/api/profile/{telegram_id}` aggregation logic. Suggested new endpoint: `/api/rewind/{telegram_id}` (read-only, joins existing tables, no new tables required).
     - Card content draft: title with trip date range; points earned/spent/final balance; case-opening highlights (best drop, e.g. "only one who pulled a legendary"); attendance % (framed as a compliment, not just a discipline metric); diary stats (entries + average star rating); event participation (times helped repel Architect/WildAI); a closing fun "role" generated from whichever stat is most pronounced for that user (e.g. biggest shop spender → "Шопоголик Протокола", most legendaries → "Любимец рандома", perfect attendance → "Образцовый оператор").
     - Visual design draft (2026-06-21): full-screen swipeable "story" slides (like Instagram/Spotify Wrapped stories), one stat per slide, large bold typography, not a single long stats page. Fixed brand palette independent of the user's currently active theme (NetWatch/Genshin/admin) — similar to how Wrapped has its own look regardless of device theme; reuse the existing Architect-event neon cyberpunk palette (green/red on black) since it already reads as "event-grade" in this app. Per-slide accent color driven by the existing casino rarity colors (gold = legendary, purple = epic, blue = common) so a "best drop" slide visually reads as rarity without inventing new color rules. Final slide = a condensed shareable summary card with the 3-4 best numbers plus the fun "role" — this is the one meant to be screenshotted and shared in the class chat. Cheap, high-impact technique: animate each big number counting up from 0 on slide entry.

