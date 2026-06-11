#!/usr/bin/env python3
"""One-shot patch: add a separate 'wildai_event' visibility setting
(seed, /api/settings field, POST /api/admin/wildai-event endpoint),
mirroring the existing 'architect_event' toggle.

Run on the server:
    python3 /root/patch_wildai_event_toggle.py
"""
import sys

PATH = "/root/zhidao_api.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

replacements = [
    (
        '''    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('architect_event', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('breach_until', '')")''',
        '''    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('architect_event', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wildai_event', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('breach_until', '')")''',
    ),
    (
        '''    c.execute("SELECT value FROM settings WHERE key='architect_event'")
    architect_event = c.fetchone()
    breach = get_wild_ai_breach_state(c)
    conn.commit()
    conn.close()
    return {
        "blackwall": blackwall[0] == '1' if blackwall else False,
        "architect_event": architect_event[0] == '1' if architect_event else False,
        **breach,
    }''',
        '''    c.execute("SELECT value FROM settings WHERE key='architect_event'")
    architect_event = c.fetchone()
    c.execute("SELECT value FROM settings WHERE key='wildai_event'")
    wildai_event = c.fetchone()
    breach = get_wild_ai_breach_state(c)
    conn.commit()
    conn.close()
    return {
        "blackwall": blackwall[0] == '1' if blackwall else False,
        "architect_event": architect_event[0] == '1' if architect_event else False,
        "wildai_event": wildai_event[0] == '1' if wildai_event else False,
        **breach,
    }''',
    ),
    (
        '''        conn.commit()
        conn.close()
        return {"success": True, "architect_event": enabled}
    return await db_write(_run)''',
        '''        conn.commit()
        conn.close()
        return {"success": True, "architect_event": enabled}
    return await db_write(_run)


@app.post("/api/admin/wildai-event")
async def toggle_wildai_event(data: dict, x_admin_id: Optional[int] = Header(None)):
    def _run():
        if x_admin_id not in ADMIN_IDS:
            raise HTTPException(status_code=403, detail="Forbidden")
        enabled = bool(data.get("enabled", False))
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('wildai_event', ?)", ('1' if enabled else '0',))
        c.execute(
            \'\'\'INSERT INTO admin_action_logs
               (admin_id, target_id, action_type, points_delta, reason, created_at)
               VALUES (?, NULL, 'wildai_event', 0, ?, ?)\'\'\',
            (x_admin_id, 'Wild AI event enabled' if enabled else 'Wild AI event disabled', now_iso()),
        )
        conn.commit()
        conn.close()
        return {"success": True, "wildai_event": enabled}
    return await db_write(_run)''',
    ),
]

for old, new in replacements:
    count = src.count(old)
    if count != 1:
        print(f"ERROR: expected 1 match, found {count} for block starting:\n{old[:80]!r}")
        sys.exit(1)
    src = src.replace(old, new, 1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

# Seed the setting immediately so /api/settings returns it without waiting
# for the next init_db() run.
import sqlite3
conn = sqlite3.connect("/root/zhidao.db")
conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wildai_event', '0')")
conn.commit()
conn.close()

print("OK: patch applied successfully")
