"""«Сейчас в сезоне» на главной (дизайн-проход 2026-09-14, решение пользователя «Home screen content»).

Один лёгкий снимок того, что идёт прямо сейчас, вместо пяти опросов с главной.
Только чтение: догоняющие записи, итоги и чистки делают экраны самих игр.

Приватность: ни имён, ни чужих ролей, сторон и целей. Про тайного агента —
только «у вас есть миссия», без цели: главную видно через плечо.
"""
from __future__ import annotations

from datetime import timedelta, timezone

from . import agent, capture, market, royale, sabotage, shop, story, zombie

# «Что нового» (главная без дублей, 2026-09-15): только то, что с человеком
# сделали другие или игра, — не его собственные покупки и открытия. Строки
# журнала без имён: кто оценил дневник или с кем был обмен, сюда не попадает.
FEED_KINDS = {
    "diary.rate": "diary",
    "case.grant": "scans",
    "trade.swap": "trade",
    "story.finale": "story",
    "royale.prize": "prize",
    "zombie.prize": "prize",
    "sabotage.prize": "prize",
    "smuggle.prize": "prize",
    "market.prize": "prize",
}
FEED_HOURS = 48
FEED_LIMIT = 5


def utcnow():
    return shop.utcnow()


def feed(conn, actor: int, season_id: int, now) -> list[dict]:
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    since = (moment - timedelta(hours=FEED_HOURS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    marks = ",".join("?" * len(FEED_KINDS))
    rows = conn.execute(
        f"""SELECT id, operation, stars_delta, scans_delta, rep_delta, created_at FROM v4_economy_operations
            WHERE season_id=? AND account_id=? AND operation IN ({marks}) AND created_at >= ?
            ORDER BY id DESC LIMIT ?""",
        (season_id, actor, *FEED_KINDS, since, FEED_LIMIT),
    ).fetchall()
    items = []
    for row in rows:
        kind = FEED_KINDS[row["operation"]]
        item = {"id": row["id"], "kind": kind, "stars": row["stars_delta"], "scans": row["scans_delta"],
                "rep": row["rep_delta"], "at": row["created_at"]}
        if kind == "prize":
            item["game"] = row["operation"].split(".", 1)[0]
        items.append(item)
    return items


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

    # Без даты старта первый заход в историю сам записывает день начала. Главная
    # только читает: до этого первого захода ей объявлять нечего, а попытка
    # записи посреди чтения ловила «database is locked» рядом с экраном истории.
    started = season["starts_on"] or conn.execute(
        "SELECT 1 FROM v4_story_state WHERE season_id=?", (season_id,)).fetchone()
    if started and any(state == "open" for _, _, state in story.progress(conn, season)["states"]):
        items.append({"key": "story", "state": "open"})

    return {"season_id": season_id, "items": items, "feed": feed(conn, actor, season_id, now)}
