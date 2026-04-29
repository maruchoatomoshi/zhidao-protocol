# CLAUDE.md

Context and working rules for Claude / Claude Code in the `ZHIDAO Protocol` repository.

This project is a Telegram Mini App plus a FastAPI backend file used for deployment. The app is intentionally game-like: cyberpunk / NetWatch / Genshin themes, points economy, cases, raids, diary scoring, Architect Protocol event, profile cards, inventory, and admin tools.

## Current Priority

The latest visible bug reported by the user:

- The diary stars page shows `Ошибка загрузки`.
- The diary leaderboard/rating tab shows nobody.
- This likely means the deployed backend is not serving the new diary stars endpoints correctly, or the frontend is receiving a non-OK response from:
  - `GET /api/diary/stars/overview?entry_date=YYYY-MM-DD`
  - `GET /api/diary/stars/leaderboard`
  - `POST /api/diary/stars/rate`

Start there before doing visual polish.

Recommended diagnostic commands on the server:

```bash
grep -n "/api/diary/stars" /root/zhidao_api.py
python3 -m py_compile /root/zhidao_api.py
systemctl status zhidao_api.service --no-pager
journalctl -u zhidao_api.service -n 120 --no-pager
curl -k "https://127.0.0.1:8443/api/diary/stars/overview?entry_date=2026-04-29" -H "X-Admin-Id: 389741116"
curl -k "https://127.0.0.1:8443/api/diary/stars/leaderboard" -H "X-Admin-Id: 389741116"
```

Frontend diagnostics:

- Check `js/diary.js`, function `loadDiaryStarsList()`.
- Check `js/leaderboard.js`, function `loadDiaryStarsLeaderboardRating()`.
- If the backend returns 404, the deployed `/root/zhidao_api.py` is stale.
- If the backend returns 500, inspect journal logs. Common causes are missing DB columns/tables after a migration, malformed SQL, or an older deployed file.

Backend update command used in this project:

```bash
cp /root/zhidao_api.py /root/zhidao_api.backup.py
curl -L https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/zhidao_api_ready.py -o /root/zhidao_api.py
grep -n "/api/diary/stars" /root/zhidao_api.py
python3 -m py_compile /root/zhidao_api.py
systemctl restart zhidao_api.service
sleep 3
systemctl status zhidao_api.service --no-pager
```

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
curl -k "https://127.0.0.1:8443/api/diary/stars/overview?entry_date=2026-04-29" -H "X-Admin-Id: 389741116"
curl -k "https://127.0.0.1:8443/api/diary/stars/leaderboard" -H "X-Admin-Id: 389741116"
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

## Recommended Next Steps

1. Fix the diary stars load error and diary leaderboard empty state.
2. Confirm server has `/api/diary/stars/*` routes deployed.
3. If backend works, improve frontend error display so it shows the actual `detail` from API instead of generic `Ошибка загрузки`.
4. Continue profile polish after diary is stable.
5. Then return to Architect result screens, music crossfade, and iPhone battle layout polish.

