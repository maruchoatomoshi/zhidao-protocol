# CLAUDE.md

Context and working rules for Claude / Claude Code in the `ZHIDAO Protocol` repository.

Last restructured: 2026-09-03.

## What this repository is now

ZHIDAO Protocol is a game-like participant system for educational travel seasons:
REP rating, seasonal currency, missions, events/raids, collectible cards and
implants, a shop, diary scoring and administrator tools.

The repository currently holds **three separate bodies of work**. Do not confuse
them, and do not mix edits across them without an explicit request.

| Body of work | Location | Status |
|---|---|---|
| Season 1 — Beijing Telegram Mini App | root `index.html`, `css/`, `js/`, `zhidao_api_ready.py`, `zhidao_bot_ready.py` | **Archive.** Finished, frozen, not deployable — see `SEASON1_BEIJING_ARCHIVE.md` |
| Season 2 — Hainan V4 web app/PWA | `zhidao_v4/`, `migrations/v4/`, `tests/` | **Active development line** |
| PS2-style game experiment | `game_assets/` (untracked here) + separate Unity project | Experimental companion, not a dependency of the web app |

Learning MVP (`zhidao_web.py`, `web/`) is a **frozen experiment**, kept as a
baseline. It is not the foundation of the Hainan V4 interface.

## Current state — read this before planning anything

**The Beijing production server is dead.** `hk.marucho.icu` (API on 8443, media
on 8444) is gone, and so is the production database. Confirmed by the user
2026-09-03.

Consequences that override every older instruction in this repository:

- There is **no live backend to compare against, diff, restart or deploy to**.
  Any instruction of the form `diff /root/zhidao_api.py …`, `systemctl restart
  zhidao_api.service`, or "check current server state first" is historical.
  Do not follow it and do not ask the user to run it.
- Beijing balances, REP, cards, implants and logs are **not recoverable** from
  this repository. A Beijing archive shown to veterans is a memorial season
  archive, not a restoration of personal progress.
- Bringing up a new server and porting the backend is a **known future task and
  explicitly not a current priority**. Do not start it, and do not block other
  work on it.
- Until a test server exists, all work is **local only, on temporary
  databases**. Production deploy is forbidden (`V4_DECISIONS.md` §2).

The old Telegram Mini App is additionally feature-frozen in code:
`js/config.js` has `APP_FEATURE_FREEZE_ENABLED = true` since `2026-07-26`, with
casino, shop, map, laundry and contracts closed and trip-end copy shown.

## Branches and tags

- `main` — the V4 (Hainan) development line. It contains the full season-1
  history plus the V4 packages; `codex/v4-hainan` was merged into it on
  2026-09-03 and is now redundant.
- `season1-beijing` (tag, at `550ff15`) — the frozen season-1 tree, including
  the original season-1 `CLAUDE.md` verbatim.
- Older `codex/*` branches are historical.

## Where to read before touching something

Do not start work from this file alone. Read the document that owns the area:

| Working on | Read first |
|---|---|
| Any V4 scope/product decision | `V4_DECISIONS.md` |
| V4 login, roles, sessions, CSRF | `V4_AUTH.md` |
| V4 schema, migrations | `V4_SCHEMA.md` |
| Hainan visual language | `V4_DESIGN.md` |
| Hainan app + campus map, in detail | `CLAUDE_HANDOFF_HAINAN_V4_2026-09-03.md` |
| Blender characters, Unity game | `CLAUDE_HANDOFF_GAME_BLENDER_2026-09-03.md` |
| Rewards, prices, limits, currency | `ECONOMY_PASSPORT.md` |
| Season-1 mechanics, history, МЮ backlog, lore | `SEASON1_BEIJING_ARCHIVE.md` |
| Learning MVP experiment | `WEB_MVP.md`, `COURSE_CONTENT.md` |
| Running legacy code locally | `TRAVEL_LOCAL.md` |

## Hainan V4 — the active line

Independent web app/PWA. Telegram is a possible external identity provider, not
a required container. Expected scale: ~60 participants, 5–6 operators, one
Architect.

Layout:

- `zhidao_v4/api.py` — FastAPI app; mounts the participant app at `/app/` and
  the Architect console at `/architect/`; endpoints under `/api/v4/`.
- `zhidao_v4/auth.py`, `security.py` — local accounts, scrypt password hashing,
  session/CSRF token hashes, lockout, rate limiting.
- `zhidao_v4/seasons.py`, `db.py`, `migrations.py` — seasons, storage,
  versioned additive migrations (`migrations/v4/`).
- `zhidao_v4/static/app/` — participant app (Сегодня / REP / Магазин / Кейсы /
  Задания / Ещё). Most sections are deliberate placeholders — they must not
  display invented users, balances or events.
- `zhidao_v4/static/architect/` — Architect console.
- `tests/` — the first automated tests in this repository. Keep them passing.

Identity model: an internal `account_id` independent of any messenger, with
`ExternalIdentity` rows (`local` | `telegram` | `max`). A Beijing Telegram ID
identifies a veteran and unlocks their archive; it is not the internal V4 ID.

Season economy: REP is the seasonal rating and stays in the season archive; ★ is
the spendable seasonal currency; at season rollover 30% of the closing ★ balance
carries over (rounded down) and 70% burns, written as two journalled operations
sharing one `rollover_id` and protected by an idempotency key. Rollover is the
**last** thing to implement, after economy, rewards, shop and archive stabilize.

Stack decisions, already made — do not relitigate them without the user:

- Python, FastAPI and SQLite stay until measurements prove otherwise.
- **React is deliberately not introduced.** V4 is plain HTML, CSS and browser
  JavaScript. Do not add a framework, DI container, or async/networking package.
- The new schema is additive and versioned; it does not destroy season-1 data
  structures.
- Permissions are enforced server-side. Hiding a button is not access control.
- Critical POST requests take an idempotency key; economy, purchases, review and
  admin corrections go to a shared operation journal and AuditLog.

### Campus map — the current active task

Digitize the real Lingshui Li'an campus inside the participant app. The
governing rule, from the user:

> First make the geography true; then make it look like ZHIDAO.

An earlier pass drew an attractive invented schematic and was rejected. **Do not
invent campus geometry.** Every outline, road, path and marker must come from a
georeferenced source or be traced against the supplied satellite reference.
AMap/GCJ-02 is the primary provider; never place Baidu BD-09 coordinates onto an
AMap layer. Never fill an unknown coordinate with a guess — leave
`verified: false`. Provider keys must not be committed. Details, POI ids and the
step order live in `CLAUDE_HANDOFF_HAINAN_V4_2026-09-03.md` §5–§11.

## PS2-style game — summary only

A visual novel with light RPG/exploration elements, deliberately PS1/PS2-era
stylized, not photorealism and not AAA. It shares design, story and assets with
the web app but **no runtime state**: there is no WebGL build in `/app/`, no API
auth from Unity, no REP synchronization, no shared save.

What exists: Blender sources under `game_assets/` (Architect character through
`architect-reference-v16.blend`, Hainan campus `hainan-campus-ps2-v02.blend`),
and a real Unity project at `C:\projects\ZHIDAO-Campus` (Unity 6000.3.23f1,
Built-in RP) with an imported campus, first-person controller, the static
Architect v16 NPC, a first-meeting dialogue episode and Windows builds. Do not
say Unity has not been started or the campus has not been imported.

Architect v16 is a finished **static appearance model**: no armature, no skin
weights, no facial rig, no animation clips, no LODs, no tested deformation or
retargeting. Numerical validation of a static mesh proves consistency, not
rigging quality or artistic likeness. The campus level is artistically
condensed and is **not** survey-accurate — never use it as authoritative
geography, and never claim it matches the real campus map.

Everything else about the game — module lists, texture atlas contract, rigging
strategy, per-character workflow, QA reports — is in
`CLAUDE_HANDOFF_GAME_BLENDER_2026-09-03.md`. **Read that file before changing
anything under `game_assets/` or in the Unity project.**

`game_assets/` (~210 MB) and the Unity project are not versioned in this
repository. Planned: a separate `zhidao-game` repository with Git LFS.

## Hard rules

### Generated files

Several assets are produced by generator scripts, and rerunning a generator
silently destroys manual edits. Before editing by hand, find out whether the
file is generated:

- Blender scripts under `game_assets/architect/blender/`
  (`architect_finish_v16.py`, `architect_hair_v16.py`, `export_*`, …).
  Diagnostic and render scripts must read and render only — they must not save
  over a source model.
- Unity Editor builders under `Assets/Campus/Editor`
  (`CampusFirstMeetingBuilder.AssembleAndBuild`, `CampusSceneBuilder`)
  regenerate scenes and prefabs from a preserved baseline.

If manual work matters, save it to a new path or update the builder as the
source of truth. Never rerun a builder that will erase it.

### Asset and version safety

- Never overwrite an approved `.blend`, `.unity`, prefab or build. Make a new
  numbered version instead; v01–v16 exist as history for a reason.
- Never use `git clean`, destructive resets or bulk deletion around untracked
  `game_assets/` and uncommitted map work.
- Keep a character FBX and its baked atlas from the same export together.
  Never mix a new FBX with an old atlas.
- Preserve axis, metre scale and ground plane across Blender and Unity.
- Fix geometry in normal 3D coordinates; never deform a model to flatter a
  camera angle.

### SQLite and backend

These were learned from a real outage on 2026-06-09 that caused 27–1463 second
stalls on every write endpoint. V4 is still FastAPI + SQLite, so they still
apply.

- **Never run `wal_checkpoint(RESTART)` or `wal_checkpoint(TRUNCATE)` in a live
  background loop.** Use `PASSIVE` only, accept that the WAL will not shrink,
  and control size with `wal_autocheckpoint`.
- **Never `await` a startup checkpoint inside a startup event handler.** It
  blocked uvicorn from finishing startup and made the port unreachable. Run it
  fire-and-forget after the server is up.
- **A second writer process starves the first.** In season 1 the bot was a
  second writer: any change that lengthened its write-lock hold time (e.g.
  Telegram sends before commit) stalled the API. A writer must commit and close
  before any `await`. If V4 ever grows a bot or worker, this is the failure mode
  to design against — prefer routing its writes through the API.
- **Do not add an extra writer executor or thread-pool layer** on top of a write
  lock without benchmarking; it only adds latency.

### Code

- **Season-1 code only:** many functions are called from inline `onclick=`
  handlers. Do not rename a public function without updating every caller. Do
  not introduce ES modules. Scripts load classically with cache-busting `?v=`
  query tags — bump the tag when you change a file.
- Do not change economy values — rewards, prices, limits, drop probabilities —
  casually. Read `ECONOMY_PASSPORT.md` first and discuss with the user. Backend
  is the source of truth; the frontend visualizes outcomes, it does not decide
  rewards.
- Be careful with encoding. Some files show mojibake in PowerShell output. Do
  not "fix" encoding globally; use UTF-8-safe edits and check visually.
- Keep changes targeted and mechanical unless the user asks for a redesign.
- Do not add secrets or provider keys to git.

## Validation

CI (`.github/workflows/ci.yml`) runs syntax checks only — it does not prove
behaviour. Run the checks that match what you touched.

Season-1 code:

```powershell
python -m py_compile zhidao_api_ready.py zhidao_bot_ready.py
node --check js\<changed>.js
git diff --check
```

V4 frontend:

```powershell
node --check zhidao_v4\static\app\app.js
```

V4 backend, locally, on a temporary database:

```powershell
$env:ZHIDAO_V4_DB_PATH = "C:\path\to\temporary-preview.sqlite3"
$env:ZHIDAO_V4_COOKIE_SECURE = "false"
.\.venv-web\Scripts\python.exe -m uvicorn zhidao_v4.api:create_app --factory --host 127.0.0.1 --port 8770
```

Then check `/app/` visually: bottom navigation works; `Ещё → Карта кампуса`
opens and Back returns; markers are click- and keyboard-accessible; Chinese
names stay valid UTF-8; nothing is clipped at narrow mobile widths; the app does
not imply GPS accuracy while the map is a prototype.

Validate saved and reopened files, not only an in-memory scene. Compare renders
at equal scale and lighting — never judge likeness from differently framed
images.

## Git workflow

The user often asks to push directly. Before committing, run the checks above,
plus `git status --short` to confirm you are not sweeping up unrelated
untracked work.

```powershell
git add <changed files>
git commit -m "Short clear message"
git push origin main
```

Do not amend commits unless explicitly requested. Do not use destructive git
commands — the user frequently has active uncommitted work, and `game_assets/`
plus in-progress map changes are untracked.

## Things to avoid

- Do not treat the dead Beijing server as if it were alive.
- Do not plan work around restoring Beijing production data.
- Do not introduce React or another framework into V4.
- Do not introduce ES modules into the season-1 app.
- Do not rename inline-handler functions.
- Do not change economy values casually.
- Do not globally "fix" mojibake from terminal output.
- Do not remove old systems unless the user explicitly says to delete them.
- Do not claim static mesh validation proves rigging quality.
- Do not claim the artistic campus level is geographically accurate.
- Do not expand the game into an open world; keep it small, finishable episodes.
- Do not connect the game to the V4 API before authentication, anti-replay and
  the reward question are decided.

## Core principle

> Build a small, honest, finishable thing with reusable parts. Do not turn a
> deliberate stylistic experiment into an unfinished modern AAA project, and do
> not describe prototypes as finished systems.
