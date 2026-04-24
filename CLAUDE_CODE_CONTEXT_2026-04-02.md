# ZHIDAO Protocol — Context Report for Claude Code

Date: 2026-04-02
Workspace: `C:\projects\ZHIDAO protocol`

## Main decision

We are staying on the single-file HTML version for now.

Do not start a full React rewrite at this stage.

Reason:
- the HTML app is already launched, tested, and close to production use
- stability before the 2026 trip is more important than a risky rewrite
- React can exist later as a parallel experimental branch, but current production should remain HTML-first

## Current main files

- Main deploy file: `index.html`
- Synced working copies: `index(4).html`, `index_new.html`, `index(4)-fixed.html`
- Backup file: `index_old_backup.html`
- Backend helper files: `zhidao_api_raid_patch.txt`, `zhidao_api_ready.py`, `backend-raid-upgrade.md`

## What was done today

### 1. HTML cleanup and stabilization

The single-file frontend was cleaned up and normalized.

Done:
- removed duplicate JS functions
- removed duplicate HTML ids that could cause DOM conflicts
- cleaned up conflicting admin/news/schedule blocks
- unified raid logic into one real API-based implementation
- made the frontend structure more consistent for further edits

### 2. Raid system alignment

Frontend and backend prep were adjusted around the updated raid rules:
- raid entry cost: `50★`
- raid success chance: `40%`
- reward on success: `150★` to each participant
- minimum participants: `3`
- base daily limit for regular players: `3`
- shop item plan/implementation support: `extra_raid_attempt` for `80★`
- admins can raid solo and without normal user restrictions

### 3. Backend prep

Prepared backend support files from the provided `zhidao_api.py`:
- `zhidao_api_raid_patch.txt` — patch-style text instructions
- `zhidao_api_ready.py` — ready combined backend file with raid changes

Backend-side notes included:
- `extra_raids` support in `user_status`
- updated raid status/join handling
- shop support for extra raid attempts
- duplicate `POST /api/shop/use/{purchase_id}` removed in ready version
- Genshin gender restriction removed in ready version

### 4. Raid visuals upgraded in HTML

The raid overlay was made more cinematic.

Done:
- added a 5-second raid intro animation before status loading
- improved boss display so the avatar is shown more fully and is not hard-cut by a circular crop
- upgraded the raid panel with:
  - top protocol kicker
  - threat chips
  - state badge
  - enhanced progress bar
  - live percent label
  - progress hint text
- improved button styling and overall raid atmosphere

### 5. Current raid frontend behavior

When the raid panel opens now:
- the overlay starts with a staged initialization animation
- progress moves through several phases like neural link, scan, wall bypass, route lock, ready
- after the intro, the real raid status is loaded from the API
- on join, the panel shows a more dramatic “breach/link” state
- on success/failure, the progress panel switches to a victory/fail visual state

### 6. Diary prototype added into HTML app

A first near-production prototype of the travel diary was added directly into the HTML app.

Source reference used:
- `C:\Users\mrpra\Downloads\Дневник практики.pdf`

Current diary implementation in `index.html`:
- new `Дневник / 旅遊日记` entry point added in `More`
- separate `page-diary` screen added
- fields preserved by meaning from the PDF:
  - date
  - weekday
  - weather
  - vocabulary table with 15 rows
  - “today how are you” rating
  - discussion person
  - discussion topic
  - Chinese daily text block
  - lesson score
  - diary score
- data currently saves per user and per date in `localStorage`
- saved days can be reopened from chips inside the page
- autosave is enabled
- visual design follows current app themes, including Genshin-compatible styling

Important:
- this diary version is front-end demo/prototype level but intentionally built close to production UX
- it is not yet connected to backend tables/API
- role separation for student / counselor / teacher grading is still undecided
- for now the score fields remain editable in the prototype so the full flow can be demonstrated

### 7. Diary backend prepared in ready API file

`zhidao_api_ready.py` was expanded with diary backend support.

Added database tables:
- `diary_entries`
- `diary_words`
- `diary_scores`

Added helper logic:
- normalized 15-row vocabulary handling
- per-date entry payload builder
- staff helper checks

Added endpoints:
- `GET /api/diary/admin/overview`
- `GET /api/diary/{telegram_id}`
- `GET /api/diary/{telegram_id}/{entry_date}`
- `POST /api/diary/save`
- `POST /api/diary/submit`
- `POST /api/diary/score`
- `POST /api/diary/lock`

Current backend approach:
- student content is stored separately from adult scoring
- this was chosen so future permissions can be separated cleanly
- lock/review workflow is already supported at API level

### 8. Bot command proposal for diary

Created:
- `zhidao_bot_diary_commands.md`

Current recommendation:
- keep the diary itself in the Mini App
- use bot only for admin shortcuts:
  - status overview
  - quick scoring
  - lock
  - unlock

## Important guidance for future work

### Keep using HTML as production

For the next iteration, continue improving the HTML app instead of rewriting the whole frontend.

Priority order:
1. stability
2. visual polish
3. API consistency
4. quality-of-life features
5. only then optional modularization or future React migration

### Good next steps

- continue polishing raid UX
- continue polishing the diary UX and then move it to backend persistence
- add more raid-specific shop bonuses if needed
- refine animations and particle effects carefully without breaking stability
- keep reducing duplicated logic inside the single HTML file
- if modularization starts, first split CSS and JS out of the monolith before considering a full React migration

### What not to do now

- do not begin a big-bang rewrite to React
- do not replace the production HTML flow right now
- do not break working API integration for the sake of refactoring

## Verification done today

- `index.html` was updated and then synced into:
  - `index(4).html`
  - `index_new.html`
  - `index(4)-fixed.html`
- extracted JavaScript from `index.html` passed `node --check`

## Final note for Claude Code

Assume the HTML version is the active production branch.

If you continue work from here, treat `index.html` as the canonical current frontend file.
