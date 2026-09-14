"""«Сейчас в сезоне» на главной (дизайн-проход 2026-09-14, решение пользователя «Home screen content»).

Один лёгкий снимок того, что идёт прямо сейчас, вместо пяти опросов с главной.
Только чтение: догоняющие записи, итоги и чистки делают экраны самих игр.

Приватность: ни имён, ни чужих ролей, сторон и целей. Про тайного агента —
только «у вас есть миссия», без цели: главную видно через плечо.
"""
from __future__ import annotations

from . import agent, capture, market, royale, sabotage, shop, story, zombie


def utcnow():
    return shop.utcnow()


def _royale(conn, season_id: int) -> dict | None:
    game = royale._active(conn, season_id)
    if not game:
        return None
    if game["status"] == "lobby":
        players = conn.execute("SELECT COUNT(*) FROM v4_royale_players WHERE game_id=?", (game["id"],)).fetchone()[0]
        return {"key": "royale", "state": "lobby", "players": int(players)}
    alive = conn.execute("SELECT COUNT(*) FROM v4_royale_players WHERE game_id=? AND alive=1", (game["id"],)).fetchone()[0]
    return {"key": "royale", "state": "running", "alive": int(alive)}


def snapshot(conn, actor: int, season_id: int) -> dict:
    season = story.season_for(conn, actor, season_id)
    now = utcnow()
    items = []

    line = _royale(conn, season_id)
    if line:
        items.append(line)
    for key, module in (("zombie", zombie), ("sabotage", sabotage)):
        game = module._active(conn, season_id)
        if game:
            items.append({"key": key, "state": "lobby" if game["status"] == "lobby" else "running"})

    market_phase = market.phase(season, now)
    if market_phase != "closed":
        rules = market.config()
        joined = market._row(conn, season_id, market.today(season, now), actor) is not None
        items.append({"key": "market", "state": market_phase, "open": rules["open"], "close": rules["close"],
                      "joined": joined})

    if agent.running(conn, season_id):
        link = conn.execute("SELECT 1 FROM v4_agent_links WHERE season_id=? AND agent_account_id=? AND day=?",
                            (season_id, actor, agent.today(season, now))).fetchone()
        items.append({"key": "agent", "state": "running", "has_mission": bool(link) and agent.in_hours(season, now)})

    if capture.enabled(conn, season_id):
        window = capture.window_state(season, now)
        items.append({"key": "capture", "state": "open" if window["open"] else "waiting",
                      "until": window.get("closes_at") if window["open"] else window.get("opens_at")})

    if any(state == "open" for _, _, state in story.progress(conn, season)["states"]):
        items.append({"key": "story", "state": "open"})

    return {"season_id": season_id, "items": items}
