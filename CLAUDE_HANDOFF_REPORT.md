# ZHIDAO Protocol: Handoff Report for Claude

This report summarizes the implementation work completed so far, the current state of the project, and the important caveats/context Claude should know before continuing.

## 1. Project Context

- Project: `ZHIDAO Protocol`
- Frontend: one large static `index.html`-based Telegram Mini App
- Backend: FastAPI + SQLite
- DB path on server: `/root/zhidao.db`
- Main backend file on server: `/root/zhidao_api.py`
- Bot file on server: `/root/zhidao_bot.py`
- Frontend file in workspace: `C:\projects\ZHIDAO protocol\index.html`

The user prefers manual, surgical edits over broad refactors. They often paste snippets and apply changes themselves. They do **not** want big unrelated rewrites.

## 2. Main Feature Implemented: Architect / Global Alert System

We built the first immersive "Architect" protocol layer in two parts:

1. Local client-side effect:
- haptic feedback
- local overlay popup
- local audio playback

2. Shared open-client alert system:
- admin triggers a backend global alert
- open clients poll the backend
- when they detect a new alert, they show the Architect popup

This means:
- users with the Mini App currently open can see the popup
- users with the Mini App closed will not see the popup
- audio on other clients depends on autoplay unlock and local sound state

## 3. Backend Changes in `/root/zhidao_api.py`

### 3.1 Earlier voice backend work

The following was added for system voice support:

- imports:
  - `asyncio`
  - `urllib.request`
  - `json as _json`
- `VOICE_REPLICAS`
- helper functions:
  - `get_all_active_telegram_ids()`
  - `send_system_voice_message(...)`
  - `broadcast_system_voice(...)`
- endpoint:
  - `POST /api/system-voice`

Current `admin_arrival` voice `file_id` used:

```python
AwACAgIAAxkBAAICG2nUBbqmiEIFwj2Tcc2VmHsPgKWKAAI9kQACsbehSpjYoALP2HuwOwQ
```

Important note:
- For the Architect effect, the app later shifted away from relying on mass voice broadcast and now primarily uses `global alert + local popup/audio`.
- The `/api/system-voice` machinery still exists and may still be useful for future events (`red_dragon`, `netwatch`, etc.).

### 3.2 Global alert storage

Added DB table in `init_db()`:

```python
c.execute('''CREATE TABLE IF NOT EXISTS global_alerts
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              alert_type TEXT NOT NULL,
              title TEXT NOT NULL,
              message TEXT NOT NULL,
              created_at TEXT NOT NULL,
              is_active INTEGER DEFAULT 1)''')
```

Purpose:
- store one current active broadcast-style in-app alert

### 3.3 Global alert helper functions

Added helper functions:

```python
def create_global_alert(alert_type: str, title: str, message: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE global_alerts SET is_active = 0 WHERE is_active = 1")
    c.execute(
        "INSERT INTO global_alerts (alert_type, title, message, created_at, is_active) VALUES (?, ?, ?, ?, 1)",
        (alert_type, title, message, datetime.utcnow().isoformat())
    )
    alert_id = c.lastrowid
    conn.commit()
    conn.close()
    return alert_id


def get_current_global_alert():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, alert_type, title, message, created_at, is_active
        FROM global_alerts
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "alert_type": row[1],
        "title": row[2],
        "message": row[3],
        "created_at": row[4],
        "is_active": bool(row[5]),
    }
```

### 3.4 Global alert endpoints

Added:

```python
@app.post("/api/global-alert")
async def create_global_alert_endpoint(data: dict):
    caller_id = data.get("telegram_id")
    alert_type = data.get("alert_type", "architect")
    title = data.get("title")
    message = data.get("message")

    if caller_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not title or not message:
        raise HTTPException(status_code=400, detail="Missing data")

    alert_id = create_global_alert(alert_type, title, message)
    return {
        "success": True,
        "alert_id": alert_id
    }


@app.get("/api/global-alert/current")
async def get_global_alert_current():
    alert = get_current_global_alert()
    return {
        "alert": alert
    }
```

Current intended use:
- create one global Architect alert
- clients poll `/api/global-alert/current`
- if a new alert appears, clients show a popup

## 4. Frontend Changes in `index.html`

### 4.1 Haptic + voice helpers

Added:

```js
function triggerHaptic(type) { ... }
async function triggerSystemVoice(eventType, targetId = 'all') { ... }
```

Patterns:
- `legendary`
- `admin`
- `attack`

### 4.2 Global alert frontend helpers

Added:

```js
async function triggerGlobalAlert(alertType, title, message) { ... }
async function checkGlobalAlert() { ... }
function startGlobalAlertPolling() { ... }
```

Current behavior:
- admin creates alert through `triggerGlobalAlert(...)`
- clients poll `/api/global-alert/current` every 4 seconds
- if alert is new and active, they show Architect popup
- last seen alert ID is stored in `localStorage` (`last_global_alert_id`)

### 4.3 Polling bootstrap

Added startup hook:

```js
window.addEventListener('load', startGlobalAlertPolling);
```

### 4.4 Local Architect audio

Added local audio element near the bottom of the document:

```html
<audio id="architectVoiceLocal" preload="auto">
  <source src="https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architect-arrival.ogg" type="audio/ogg">
</audio>
```

This raw GitHub URL is currently used for local playback.

### 4.5 Audio unlock logic

Because Telegram WebView / browser autoplay restrictions block audio without user interaction, we added an unlock phase:

```js
let architectAudioUnlocked = false;

function unlockArchitectAudio() {
  if (architectAudioUnlocked) return;

  const audio = document.getElementById('architectVoiceLocal');
  if (!audio) return;

  audio.volume = 0;
  audio.play()
    .then(() => {
      audio.pause();
      audio.currentTime = 0;
      audio.volume = 1;
      architectAudioUnlocked = true;
    })
    .catch(() => {});
}
```

And this hook:

```js
document.addEventListener('click', unlockArchitectAudio, { passive: true });
```

Important behavior:
- for sound to autoplay later on a client, that client typically needs at least one user interaction in the current session

### 4.6 Local sound toggle logic

We attempted a local sound enable/disable toggle. Current intended implementation:

```js
let protocolSoundEnabled = localStorage.getItem('protocol_sound_enabled') !== '0';

function isProtocolSoundEnabled() {
  return protocolSoundEnabled;
}

function updateProtocolSoundStatus() {
  const onBtn = document.getElementById('protocolSoundOnBtn');
  const offBtn = document.getElementById('protocolSoundOffBtn');
  if (!onBtn || !offBtn) return;

  if (protocolSoundEnabled) {
    onBtn.style.background = 'rgba(212,175,55,0.10)';
    onBtn.style.border = '1px solid rgba(212,175,55,0.28)';
    onBtn.style.color = 'var(--gold)';

    offBtn.style.background = 'rgba(255,255,255,0.04)';
    offBtn.style.border = '1px solid rgba(255,255,255,0.10)';
    offBtn.style.color = 'var(--text2)';
  } else {
    offBtn.style.background = 'rgba(212,175,55,0.10)';
    offBtn.style.border = '1px solid rgba(212,175,55,0.28)';
    offBtn.style.color = 'var(--gold)';

    onBtn.style.background = 'rgba(255,255,255,0.04)';
    onBtn.style.border = '1px solid rgba(255,255,255,0.10)';
    onBtn.style.color = 'var(--text2)';
  }
}

function setProtocolSoundEnabled(enabled) {
  protocolSoundEnabled = !!enabled;
  localStorage.setItem('protocol_sound_enabled', protocolSoundEnabled ? '1' : '0');

  const audio = document.getElementById('architectVoiceLocal');
  if (audio) {
    audio.pause();
    audio.currentTime = 0;
    audio.muted = !protocolSoundEnabled;
  }

  updateProtocolSoundStatus();
}
```

And on load:

```js
window.addEventListener('load', updateProtocolSoundStatus);
```

Known caveat:
- this area caused confusion and some instability during iteration
- the intended final behavior is local-only sound control, not global
- if it behaves inconsistently, Claude should simplify rather than over-engineer

### 4.7 Local Architect playback

Intended current function:

```js
function playArchitectVoiceLocal() {
  try {
    const audio = document.getElementById('architectVoiceLocal');
    if (!audio || !protocolSoundEnabled) return;

    audio.muted = false;
    audio.pause();
    audio.currentTime = 0;
    audio.play().catch(() => {});
  } catch (e) {}
}
```

### 4.8 Architect overlay popup

`showArchitectOverlay()` was upgraded into a more dramatic cyberpunk/Blackwall-style sequence:

- dark red radial background
- scanlines
- moving scan beam
- red flash
- `CRITICAL_OVERRIDE`
- animated glitch title
- system flavor labels like:
  - `BLACKWALL//OVERRIDE`
  - `NODE:ZHIDAO-PRIME`
  - `PRIORITY:ABSOLUTE`
  - `WATCHING...`
- body glitch effect
- RGB title shift effect
- fade-out removal

Key message shown:

```text
你正在被主协议注视。
Главный протокол наблюдает за тобой.
```

### 4.9 Architect activation function

Current intended Architect activation flow:

```js
async function activateMasterProtocol(targetId = 'all') {
  triggerHaptic('admin');
  showArchitectOverlay();
  playArchitectVoiceLocal();

  await triggerGlobalAlert(
    'architect',
    'АРХИТЕКТОР В СЕТИ',
    '你正在被主协议注视。\\nГлавный протокол наблюдает за тобой.'
  );
}
```

Important note:
- `targetId` is now basically vestigial here; the action is driven by the global alert
- local user sees it immediately
- open clients see it via polling

## 5. Admin UI Changes

In the admin `BlackWall` section, we added:

- `INIT MASTER PROTOCOL`
- sound buttons:
  - `🔊 ЗВУК ВКЛ`
  - `🔇 ЗВУК ВЫКЛ`

The Architect trigger button eventually moved to:

```html
onclick="activateMasterProtocol('all')"
```

There was a period where it used a hardcoded personal Telegram ID for safe testing. Final intended shared mode is `'all'`.

## 6. Current Runtime Behavior

### Architect event now behaves like this

1. Admin presses `INIT MASTER PROTOCOL`
2. On admin client:
- haptic feedback
- Architect popup
- local audio (if unlocked + enabled)

3. Backend creates a `global_alert`
4. Open clients poll and receive the new Architect alert
5. On open clients:
- popup appears
- haptic may occur
- local sound may play if:
  - app is open
  - user has interacted with app before in this session
  - sound is locally enabled

### Important limitation

Users with the Mini App closed will **not** see the popup.

This system is intentionally scoped to open clients only.

## 7. Known Caveats / Warnings

1. The project is a very large monolithic `index.html`.
- edits should be surgical
- avoid broad refactors

2. The sound toggle feature was the shakiest part of the Architect work.
- if Claude sees inconsistent behavior, the best fallback is to simplify
- e.g. temporarily remove sound toggles and keep sound always on locally

3. Audio playback on secondary clients depends on autoplay unlock.
- this is not just app logic
- it is a platform/WebView limitation

4. The user is sensitive to breaking layout and navigation.
- they already had a case where missing closing `</div>` tags caused the nav to disappear
- preserve HTML structure carefully

## 8. Other Frontend Fixes Done During This Session

These were not the primary goal, but they were implemented/fixed:

### 8.1 Announcements multiline fix

In announcements rendering:

```js
<div class="announcement-text" style="white-space:pre-wrap;">${item.text}</div>
```

This preserves line breaks from textarea input.

### 8.2 Implant light-theme text fixes

Several implant catalog cards were corrected from hardcoded:
- `#fff`
- `#ccc`

to:
- `var(--text)`
- `var(--text2)`
- `var(--text3)`

Notably `ГУАНЬСИ` and `ТЕРРАКОТА` were corrected.

### 8.3 NetWatch Light roulette and prize overlay improvements

Work was done on:
- light theme roulette look
- prize overlay in light themes
- corrected overlay mounting and closure behavior
- fixed a missing function brace issue during overlay edits

## 9. Event Engine Idea Was Discussed But Not Implemented Yet

A future event system skeleton was agreed conceptually, but not implemented yet.

Desired lifecycle:

```text
create event
-> ACTIVE
-> players send actions
-> damage reduces HP
-> logs are written
-> when HP reaches 0
-> FINISHED
```

Planned backend pieces:
- `events`
- `event_actions`
- `event_logs`

But this is still a future task and should not be assumed complete.

## 10. Recommended Next Steps for Claude

Best next moves, in order:

1. Stabilize the Architect sound toggle if needed
- only if current behavior is still inconsistent
- otherwise do not churn it further

2. Add global alert auto-expire
- alerts currently may remain active until replaced
- a simple expire mechanism or timed deactivation would help

3. Add second themed alert type
- e.g. `netwatch`
- reuse the same architecture

4. Build the first event-engine MVP
- now that global alerts work, they can become a reusable delivery layer for weekly events

## 11. What Claude Should Preserve

- do not rewrite unrelated app sections
- do not refactor the giant `index.html` unless explicitly asked
- preserve the current vibe: cyberpunk / Blackwall / protocol intrusion
- prefer small, testable additions
- user prefers snippets and highly controlled changes

