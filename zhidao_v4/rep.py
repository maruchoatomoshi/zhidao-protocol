"""REP сезона на экране рейтинга (решение пользователя 2026-09-15).

Всей таблицы из шестидесяти человек нет: участник видит тройку лидеров, своё
место и соседей рядом с собой. Последние места не видны всем.

Только чтение: REP лежит в кошельке сезона и меняется там, где его начисляют
(дневник, призы игр). Места — по REP, при равенстве — по имени, чтобы порядок
не прыгал между запросами.
"""
from __future__ import annotations

from .cases import authorize, can_manage
from .shop import frames_for

LEADERS = 3
NEIGHBOURS = 2


def board(conn, actor: int, season_id: int) -> dict:
    member = conn.execute("SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?",
                          (season_id, actor)).fetchone()
    is_member = bool(member and member["status"] in ("active", "completed"))
    # Участник смотрит как участник; организатор без участия — как организатор.
    authorize(conn, actor, season_id, manage=not is_member and can_manage(conn, actor, season_id))
    rows = conn.execute(
        """SELECT a.id AS account_id, a.display_name, COALESCE(w.rep, 0) AS rep
           FROM v4_season_memberships m
           JOIN v4_accounts a ON a.id = m.account_id
           LEFT JOIN v4_case_wallets w ON w.season_id = m.season_id AND w.account_id = m.account_id
           WHERE m.season_id = ? AND m.status IN ('active', 'completed') AND a.status = 'active'
             -- Штат может играть наравне со всеми (участие выдаёт им
             -- членство при первой же игре), но не соревнуется за REP.
             AND NOT EXISTS (SELECT 1 FROM v4_role_assignments ra WHERE ra.account_id = a.id
                              AND ra.role_code IN ('operator', 'architect', 'system_admin')
                              AND ra.revoked_at IS NULL)
           ORDER BY rep DESC, a.display_name, a.id""",
        (season_id,),
    ).fetchall()
    ranked = [{"rank": index + 1, "account_id": row["account_id"], "display_name": row["display_name"],
               "rep": row["rep"]} for index, row in enumerate(rows)]
    mine = next((index for index, row in enumerate(ranked) if row["account_id"] == actor), None)
    leaders = ranked[:LEADERS]
    around = ranked[max(LEADERS, mine - NEIGHBOURS): mine + NEIGHBOURS + 1] if mine is not None else []
    frames = frames_for(conn, [row["account_id"] for row in leaders + around])

    def public(row):
        return {"rank": row["rank"], "display_name": row["display_name"], "rep": row["rep"],
                "is_you": row["account_id"] == actor, "frame": frames.get(row["account_id"])}

    me = None
    if mine is not None:
        ahead = ranked[mine - 1] if mine > 0 else None
        me = {"rank": ranked[mine]["rank"], "rep": ranked[mine]["rep"], "next_rep": ahead["rep"] if ahead else None}
    return {"season_id": season_id, "total": len(ranked), "me": me,
            "leaders": [public(row) for row in leaders], "around": [public(row) for row in around]}
