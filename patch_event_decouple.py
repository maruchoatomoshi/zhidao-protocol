#!/usr/bin/env python3
"""One-shot patch: decouple Architect Protocol and WildAI Breach event slots
on /root/zhidao_api.py (minimal patch, no implant/card bonus system).

Run on the server:
    python3 /root/patch_event_decouple.py
"""
import re
import sys

PATH = "/root/zhidao_api.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

orig = src

replacements = [
    (
        '''def get_current_or_latest_event_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    row = None
    for candidate in rows:
        event_row = fetch_event_row(c, candidate[0])
        event_row = refresh_event_state(c, event_row)
        if event_row and event_row["state"] in ("REGISTRATION", "ACTIVE"):
            row = candidate
            break
    conn.commit()
    if row:
        conn.close()
        return row[0]
    # No live event: keep showing the latest finished/failed one for a while
    # so participants see the result screen instead of the standby lobby.
    c.execute(
        "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') ORDER BY id DESC LIMIT 1"
    )
    terminal = c.fetchone()''',
        '''def get_current_or_latest_event_id(event_code: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    if event_code:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? ORDER BY id DESC", (event_code,))
    else:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    row = None
    for candidate in rows:
        event_row = fetch_event_row(c, candidate[0])
        event_row = refresh_event_state(c, event_row)
        if event_row and event_row["state"] in ("REGISTRATION", "ACTIVE"):
            row = candidate
            break
    conn.commit()
    if row:
        conn.close()
        return row[0]
    # No live event: keep showing the latest finished/failed one for a while
    # so participants see the result screen instead of the standby lobby.
    if event_code:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') AND code=? ORDER BY id DESC LIMIT 1",
            (event_code,)
        )
    else:
        c.execute(
            "SELECT id, ended_at FROM events WHERE state IN ('FINISHED', 'FAILED') ORDER BY id DESC LIMIT 1"
        )
    terminal = c.fetchone()''',
    ),
    (
        '''def get_blocking_event_id():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    blocking_id = None''',
        '''def get_blocking_event_id(event_code: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    if event_code:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') AND code=? ORDER BY id DESC", (event_code,))
    else:
        c.execute("SELECT id FROM events WHERE state IN ('REGISTRATION', 'ACTIVE') ORDER BY id DESC")
    rows = c.fetchall()
    blocking_id = None''',
    ),
    (
        '''        blocking_event_id = get_blocking_event_id()
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="Another event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "ARCHITECT PROTOCOL"''',
        '''        blocking_event_id = get_blocking_event_id('architect')
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="Another Architect Protocol event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "ARCHITECT PROTOCOL"''',
    ),
    (
        '''        blocking_event_id = get_blocking_event_id()
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="Another event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "WILD AI BREACH"''',
        '''        blocking_event_id = get_blocking_event_id('wildai_breach')
        if blocking_event_id:
            raise HTTPException(status_code=409, detail="A WILD AI BREACH event is already active")

        conn = get_conn()
        c = conn.cursor()

        title = data.get("title") or "WILD AI BREACH"''',
    ),
    (
        '''@app.get("/api/events/current")
async def get_current_event():
    event_id = get_current_or_latest_event_id()
    return {"event": get_event_snapshot(event_id) if event_id else None}''',
        '''@app.get("/api/events/current")
async def get_current_event(code: Optional[str] = None):
    event_id = get_current_or_latest_event_id(code)
    return {"event": get_event_snapshot(event_id) if event_id else None}''',
    ),
]

for old, new in replacements:
    count = src.count(old)
    if count != 1:
        print(f"ERROR: expected 1 match, found {count} for block starting:\n{old[:80]!r}")
        sys.exit(1)
    src = src.replace(old, new, 1)

if src == orig:
    print("ERROR: no changes applied")
    sys.exit(1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("OK: patch applied successfully")
