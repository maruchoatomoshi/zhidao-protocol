# Handoff for Claude — ZHIDAO Hainan V4 and campus map

Date: 2026-09-03  
Working directory: `C:\projects\ZHIDAO protocol`

## 1. What the product is

ZHIDAO Protocol is a game-like participant system for educational travel
seasons. The older Beijing implementation is a Telegram Mini App with REP,
seasonal currency, ratings, missions, events/raids, collectible cards and
implants, a shop, diary scoring and administrator tools.

The active redesign is **ZHIDAO Hainan V4**. It keeps continuity with the
Beijing concept and mechanics but is being rebuilt as an independent web
application/PWA. Telegram is a possible external identity provider, not a
mandatory container. The expected Hainan scale is approximately 60
participants, 5–6 operators and one Architect role.

The intended product hierarchy is:

1. Daily route and useful information for a participant.
2. Seasonal REP rating.
3. Missions, events and raids.
4. Seasonal shop and consumables.
5. Collection of cards/implants and a Beijing archive for veterans.
6. Operator and Architect administration in a separate interface.

Do not assume that every legacy feature must be copied unchanged. V4 is an
additive rebuild with its own schema, roles and interface.

## 2. Which code is current

There are two frontends in this repository. Do not confuse them.

### Legacy Beijing application

- root `index.html`
- root `css/`
- root `js/`
- deployable legacy backend: `zhidao_api_ready.py`

This is the historical feature-rich Telegram application. It is a reference
for mechanics, terminology and visual continuity.

### Active Hainan V4 application

- participant app: `zhidao_v4/static/app/`
- Architect console: `zhidao_v4/static/architect/`
- backend: `zhidao_v4/api.py`
- database and migrations: `zhidao_v4/db.py`, `zhidao_v4/migrations.py`
- authentication/security: `zhidao_v4/auth.py`, `zhidao_v4/security.py`
- season logic: `zhidao_v4/seasons.py`

FastAPI mounts the participant preview at `/app/` and Architect console at
`/architect/`. The current API foundation contains health, login/logout,
current-user, season and Architect overview endpoints under `/api/v4/`.

V4 uses plain HTML, CSS and browser JavaScript. React has deliberately not
been introduced. Do not add a framework unless the user explicitly changes
that decision.

## 3. Current visual direction

The Hainan participant app is mobile-first. On a phone it fills the screen; on
desktop it appears as a portable personal device.

The visual language combines:

- bright Hainan water, sky and tropical landscape;
- translucent aqua/white glass surfaces;
- glossy early-2000s / Frutiger Aero details;
- small bilingual Russian/Chinese system labels;
- old mobile/game-like PNG icons inspired by the 2000s;
- typography and information hierarchy that should retain continuity with the
  Beijing version.

The user does not want a generic modern SaaS dashboard. The interface should
feel like a personal travel terminal from an optimistic PS2-era future. Avoid
flattening the design into plain cards or replacing its old-style icons with a
uniform contemporary outline icon set.

The participant shell currently contains six bottom-navigation sections:

- Сегодня
- REP
- Магазин
- Кейсы
- Задания
- Ещё

Most sections are still visual placeholders. They intentionally do not show
invented users, balances or events. The campus map is opened from `Ещё`.

## 4. Related PS2-style game work

Full game, Blender and Unity context is documented in
`CLAUDE_HANDOFF_GAME_BLENDER_2026-09-03.md`. Read that file before changing
anything under `game_assets/` or `C:\projects\ZHIDAO-Campus`.

The repository also contains experimental game assets under `game_assets/`.
These include a low-poly PS1/PS2-style Architect character, Blender source
versions, validation reports and Unity-oriented exports. The latest character
work reached approximately `architect-reference-v16.blend`.

This game experiment may later become a visual-novel/RPG companion experience
or an interactive presentation inside the Hainan product. It is **not yet a
required dependency of the web app**, and the current campus map task does not
require modifying Blender or Unity assets.

## 5. Active task: faithful campus digitization

The current task is to build a useful digital map of the Lingshui Li'an
International Education Innovation Pilot Zone campus inside the participant
application.

### Intended area

Digitize the real territory bounded by:

- west side: `立德路`;
- east side: the next unnamed road to the east;
- north side: `博学大道`.

The useful area must include at least:

1. `海南陵水黎安国际教育创新试验区体育中心`
2. `陵水黎安国际教育创新试验区图书馆`
3. `陵水黎安国际教育创新实验区公共教学楼`
4. `陵水黎安国际教育创新试验区-1号食堂`

The user previously supplied two dormitory references as orientation points:

- AMap `B0IR1DTQ8A` — stale/unavailable in one desktop check; associated with
  the student living zone 2 / building 4 commercial courtyard.
- AMap `B0LRFH6LH5` — confirmed as
  `海南陵水黎安国际教育创新试验区学生生活1区`.

These dormitories are context, not the center or entire scope of the requested
map.

### Critical user feedback

An early pass drew an attractive but invented schematic. The user rejected it
because the roads, buildings and distances did not resemble the real campus.

**Do not invent campus geometry again.** Visual style is secondary to spatial
fidelity. Every building outline, road, path and marker must come from a
georeferenced source or be traced against the supplied satellite reference.

Also keep these distinct:

- `公共实验楼` — public experimental building visible on some map labels;
- `公共教学楼` — the public teaching building requested by the user.

They are different places. AMap identified the requested teaching building as
POI `B0IR1ZT9R2`. The canteen search resolved to POI `B0J13ULQUA`.

## 6. Current campus-map implementation

Uncommitted work currently changes:

- `zhidao_v4/static/app/index.html`
- `zhidao_v4/static/app/app.css`
- `zhidao_v4/static/app/app.js`
- `zhidao_v4/static/app/assets/maps/campus-satellite-reference.png`

The map screen currently provides:

- navigation from `Ещё → Карта кампуса`;
- a satellite screenshot supplied by the user as the visual base;
- four clickable point markers;
- a selected-place information card;
- links that open searches in AMap and Baidu Maps;
- a highlighted draft boundary for the area being digitized.

`campusPoints` in `app.js` is the current small client-side location registry.
The screen-switching logic uses `data-open-screen`; markers use
`data-map-point`.

The current satellite-backed pass is substantially more faithful than the
discarded schematic, but it is still a **prototype**, not a completed digital
map:

- the screenshot is a temporary reference layer, not final distributable map
  data;
- the blue boundary is approximate;
- marker positions were visually aligned and still need coordinate-level
  verification;
- building and path polygons have not yet been traced;
- there is no pan, zoom, routing or live geolocation;
- the image includes Baidu-derived imagery and must not silently become a
  permanent production asset without checking applicable map licensing.

Do not claim this pass is an accurate vector map or navigation-ready.

## 7. Correct implementation direction

**Superseded 2026-09-04.** This section originally called for AMap as the live
basemap. The user decided against it, and the decision stands: obtaining an
AMap key requires Chinese real-name verification (`实名认证`), which a foreign
individual cannot complete alone. The only route was to ask a Chinese
colleague to put their identity documents behind our key, and the user
declined to ask that of anyone. That reasoning is not a technical detail — do
not reopen it by proposing "just get a key".

The architecture is now a **self-contained vector map**:

1. Geometry is project-owned GeoJSON at
   `zhidao_v4/static/app/assets/maps/campus.geojson`, currently seeded from
   OpenStreetMap (ODbL, attribution required and present in the file).
2. **All coordinates are WGS-84.** This is deliberate: device GPS returns
   WGS-84, so a WGS-84 map means positions land where they belong with no
   conversion step and no class of offset bugs.
3. No runtime provider dependency: no key, nothing to block from mainland
   China, works offline in the PWA, and the whole dataset is tens of KB rather
   than a tile stream.
4. **Never draw these coordinates on an AMap or Baidu tile layer** without
   converting WGS-84 -> GCJ-02 first. The old warning about mixing datums
   applies with the sides swapped, and it is now the likelier mistake.
5. Baidu and AMap remain external deep links only.
6. Every feature carries `verified: false` until checked against the ground or
   a second source. Do not fill an unknown coordinate with a guess; leave it
   out and record it under `missing`.

Known trade-off, recorded honestly: publishing maps of China is regulated and
a licensed Chinese provider would settle that question, which OSM-derived
geometry does not. For an internal tool used by roughly sixty participants the
practical exposure is small, but the question exists and was weighed rather
than overlooked.

If a key ever does arrive, the swap is cheap by construction: coordinates stay
WGS-84 in storage and conversion happens once at render time.

A safe data model for each campus object should include:

```json
{
  "id": "public-teaching-building",
  "name_ru": "Общий учебный корпус",
  "name_zh": "陵水黎安国际教育创新实验区公共教学楼",
  "category": "academic",
  "position_gcj02": [null, null],
  "outline": null,
  "entrances": [],
  "source": "amap-poi-and-user-verification",
  "verified": false
}
```

Do not fill unknown coordinates with guesses. Keep `verified: false` until the
user or a reliable provider coordinate confirms them.

## 8. Recommended next work, in order

1. Preserve the current screenshot-backed screen as a comparison/reference.
2. Acquire/configure the AMap Web JS key and security code.
3. Load the real AMap basemap centered on the requested quarter.
4. Resolve coordinate-level positions for the four named POIs.
5. Ask the user only for ambiguous entrances or buildings that providers do
   not distinguish; do not ask them to re-identify already supplied names.
6. Trace and review the actual area boundary, building footprints and useful
   pedestrian paths.
7. Add categories and selection states: study, food, sport and residence.
8. Add route display only after the geometry and entrances are verified.
9. Test at mobile widths and inside Telegram/PWA safe areas if that container
   is reintroduced.
10. Replace or remove the temporary Baidu screenshot before a production
    release if licensing does not permit bundling it.

## 9. Validation expectations

For the participant frontend:

```powershell
node --check zhidao_v4\static\app\app.js
git diff --check
```

Run the local V4 app with a temporary database, then inspect `/app/` visually:

```powershell
$env:ZHIDAO_V4_DB_PATH = "C:\path\to\temporary-preview.sqlite3"
$env:ZHIDAO_V4_COOKIE_SECURE = "false"
.\.venv-web\Scripts\python.exe -m uvicorn zhidao_v4.api:create_app --factory --host 127.0.0.1 --port 8770
```

Check:

- bottom navigation still works;
- `Ещё → Карта кампуса` opens and Back returns correctly;
- all map markers are keyboard/click accessible;
- selecting a marker changes its card and provider links;
- Chinese names remain UTF-8 and are not corrupted;
- no marker or label is clipped at narrow mobile widths;
- the app does not imply GPS/navigation accuracy while the map is a prototype.

## 10. Repository safety

- Current map changes and `game_assets/` are uncommitted/untracked in the
  working tree. Do not delete, reset or overwrite them.
- Do not perform broad cleanup of legacy files while working on V4.
- Do not deploy to production merely because the local preview works.
- Do not add secrets or provider keys to git.
- Preserve the user's existing Hainan visual design and old-2000s icon
  direction unless explicitly asked to redesign it.
- Prefer targeted edits and visual verification over framework migration or a
  broad refactor.

## 11. Product definition of done for the map

The map is useful when a participant can recognize the actual campus at a
glance, select a real destination, understand where it is relative to roads and
other buildings, and eventually build a sensible walking route to an entrance.

It is not done merely because the screen is attractive. The governing rule for
this feature is:

> First make the geography true; then make it look like ZHIDAO.
