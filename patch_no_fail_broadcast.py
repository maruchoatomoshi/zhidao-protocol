#!/usr/bin/env python3
"""One-shot patch: do not send the bot broadcast when a WILD AI BREACH event
is FAILED. Manual admin activation of breach mode keeps the broadcast.

Run on the server:
    python3 /root/patch_no_fail_broadcast.py
"""
import sys

PATH = "/root/zhidao_api.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

replacements = [
    (
        '''def activate_wildai_breach(c, admin_id: Optional[int] = None, reason: str = 'Wild AI Breach auto-triggered (system integrity restoration failed)'):''',
        '''def activate_wildai_breach(c, admin_id: Optional[int] = None, reason: str = 'Wild AI Breach auto-triggered (system integrity restoration failed)', send_broadcast: bool = True):''',
    ),
    (
        '''    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_broadcast_pending', '1')")''',
        '''    if send_broadcast:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('breach_broadcast_pending', '1')")''',
    ),
    (
        '''                add_event_log(c, event_row["id"], "system", f"WILD AI BREACH: операция провалена — {reason}. Дикий ИИ закрепился в системе.")
                activate_wildai_breach(c)''',
        '''                add_event_log(c, event_row["id"], "system", f"WILD AI BREACH: операция провалена — {reason}. Дикий ИИ закрепился в системе.")
                activate_wildai_breach(c, send_broadcast=False)''',
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

print("OK: patch applied successfully")
