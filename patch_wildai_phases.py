#!/usr/bin/env python3
"""One-shot patch: add 3-phase progression to WILD AI BREACH events
(reuses ARCHITECT_PHASE2_THRESHOLD / ARCHITECT_PHASE3_THRESHOLD), mirroring
Architect Protocol's phase 2/3 transitions.

Run on the server:
    python3 /root/patch_wildai_phases.py
"""
import sys

PATH = "/root/zhidao_api.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

old = '''            time_expired = started and (now - started).total_seconds() > WILD_AI_BREACH_TIME_LIMIT_SECONDS
            infection_critical = event_row["overload_pressure"] >= WILD_AI_BREACH_INFECTION_THRESHOLD

            if event_row["current_hp"] > 0 and (time_expired or infection_critical):'''

new = '''            time_expired = started and (now - started).total_seconds() > WILD_AI_BREACH_TIME_LIMIT_SECONDS
            infection_critical = event_row["overload_pressure"] >= WILD_AI_BREACH_INFECTION_THRESHOLD

            hp_ratio = event_row["current_hp"] / event_row["max_hp"] if event_row["max_hp"] else 0

            if event_row["phase"] == 1 and hp_ratio <= ARCHITECT_PHASE2_THRESHOLD:
                event_row["phase"] = 2
                c.execute("UPDATE events SET phase=2 WHERE id=?", (event_row["id"],))
                add_event_log(c, event_row["id"], "boss", "WILD AI BREACH: вторичный периметр пробит. Дикий ИИ усиливает атаку.")

            if event_row["phase"] == 2 and hp_ratio <= ARCHITECT_PHASE3_THRESHOLD:
                event_row["phase"] = 3
                c.execute("UPDATE events SET phase=3 WHERE id=?", (event_row["id"],))
                add_event_log(c, event_row["id"], "boss", "WILD AI BREACH: критическая зона. Дикий ИИ обходит последние защиты.")

            if event_row["current_hp"] > 0 and (time_expired or infection_critical):'''

count = src.count(old)
if count != 1:
    print(f"ERROR: expected 1 match, found {count}")
    sys.exit(1)

src = src.replace(old, new, 1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("OK: patch applied successfully")
