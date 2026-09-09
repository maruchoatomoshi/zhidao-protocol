"""Туман кампуса: исследованная область растёт от того, где люди побывали.

Карта уже умеет всё нужное. В `campus-map.js` есть слой тумана, признак
`is-unexplored` у объектов и «опорные точки» — список координат, каждая из
которых раздвигает исследованную область на радиус подложки. До сих пор
список был записан в данных и не менялся; здесь он становится живым.

Поэтому в модуле нет ни геометрии, ни рисования: он только решает, засчитать
ли точку, и отдаёт накопленные клетки в том виде, который карта уже понимает.

Чего здесь намеренно нет — привязки клетки к человеку. Механике нужно знать,
какие места открыты, а не кто где был. История перемещений шестидесяти
подростков — слишком дорогая вещь, чтобы заводить её ради тумана.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path


# Шаг сетки в градусах. 0,0004° — около 44 м по обеим осям на широте 18°N,
# то есть чуть меньше радиуса подложки (55 м): соседние клетки перекрываются,
# и открытая область получается сплошной, а не решетом.
GRID = 0.0004

# Точность геолокации, хуже которой точку не засчитываем. Телефон в здании
# легко отдаёт 200–500 м, и такая точка размазала бы карту по всему кампусу.
MAX_ACCURACY_M = 100.0

# Запас вокруг кампуса. Не косметика: актовый зал и жилая зона лежат снаружи
# OSM-контура на 61 и 110 м (см. комментарий в campus-map.js), и строгая
# проверка по контуру отвергала бы настоящие места.
MARGIN_DEGREES = 0.0025  # около 270 м

CAMPUS_GEOJSON = (
    Path(__file__).resolve().parent / "static" / "app" / "assets" / "maps" / "campus.geojson"
)


class CampusError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@lru_cache(maxsize=1)
def campus_box() -> tuple[float, float, float, float]:
    """Рамка кампуса с запасом: (min_lon, min_lat, max_lon, max_lat).

    Рамка, а не контур, и это честнее, чем кажется. Внутрь попадёт немного
    лишнего вокруг, но проверка существует не для того, чтобы отличить
    дорожку от газона, а чтобы карту нельзя было открыть из дома.
    """
    data = json.loads(CAMPUS_GEOJSON.read_text(encoding="utf-8"))
    lons: list[float] = []
    lats: list[float] = []

    def walk(coords) -> None:
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            lons.append(float(coords[0]))
            lats.append(float(coords[1]))
            return
        for item in coords:
            walk(item)

    for feature in data.get("features") or []:
        walk((feature.get("geometry") or {}).get("coordinates"))
    if not lons:
        raise CampusError("Campus geometry is missing", 500)
    return (
        min(lons) - MARGIN_DEGREES,
        min(lats) - MARGIN_DEGREES,
        max(lons) + MARGIN_DEGREES,
        max(lats) + MARGIN_DEGREES,
    )


def inside_campus(lon: float, lat: float) -> bool:
    min_lon, min_lat, max_lon, max_lat = campus_box()
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def snap(lon: float, lat: float) -> tuple[int, int]:
    """Координата → клетка сетки. Целыми, потому что это первичный ключ."""
    return (round(lon / GRID), round(lat / GRID))


def cell_centre(cell_lon: int, cell_lat: int) -> tuple[float, float]:
    return (round(cell_lon * GRID, 6), round(cell_lat * GRID, 6))


def active_season_id(conn: sqlite3.Connection, account_id: int) -> int | None:
    """Сезон, к которому относится человек прямо сейчас.

    Сначала активное членство, потом — служебная роль: у вожатого членства
    может не быть вовсе, а карта ему нужна та же самая.
    """
    row = conn.execute(
        """
        SELECT s.id FROM v4_seasons s
        JOIN v4_season_memberships m ON m.season_id = s.id
        WHERE s.status = 'active' AND m.account_id = ? AND m.status = 'active'
        ORDER BY s.id DESC LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    manages = conn.execute(
        """
        SELECT 1 FROM v4_role_assignments
        WHERE account_id = ? AND revoked_at IS NULL
          AND role_code IN ('operator', 'architect', 'system_admin')
        """,
        (account_id,),
    ).fetchone()
    if manages is None:
        return None
    row = conn.execute(
        "SELECT id FROM v4_seasons WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row is not None else None


def exploration(conn: sqlite3.Connection, season_id: int) -> dict:
    """Открытые клетки в том виде, в каком их понимает карта."""
    rows = conn.execute(
        "SELECT cell_lon, cell_lat FROM v4_campus_cells WHERE season_id = ?"
        " ORDER BY cell_lon, cell_lat",
        (season_id,),
    ).fetchall()
    points = []
    for row in rows:
        lon, lat = cell_centre(int(row["cell_lon"]), int(row["cell_lat"]))
        points.append(
            {"id": f"cell-{row['cell_lon']}-{row['cell_lat']}", "coordinates": [lon, lat]}
        )
    return {"season_id": season_id, "opened": len(points), "anchor_points": points}


def record_visit(
    conn: sqlite3.Connection,
    season_id: int,
    *,
    lon: float,
    lat: float,
    accuracy_m: float | None,
) -> dict:
    """Засчитывает точку. Возвращает, открылась ли новая клетка."""
    if accuracy_m is not None and accuracy_m > MAX_ACCURACY_M:
        raise CampusError(
            "Слишком неточное положение: подойдите ближе к открытому небу."
        )
    if not inside_campus(lon, lat):
        raise CampusError("Эта точка не на территории кампуса.")

    cell_lon, cell_lat = snap(lon, lat)
    cursor = conn.execute(
        """
        INSERT INTO v4_campus_cells(season_id, cell_lon, cell_lat)
        VALUES (?, ?, ?)
        ON CONFLICT(season_id, cell_lon, cell_lat)
        DO UPDATE SET visits = visits + 1
        """,
        (season_id, cell_lon, cell_lat),
    )
    # rowcount на UPSERT одинаков для вставки и обновления, поэтому «новая ли
    # клетка» спрашиваем у самой записи: у новой visits равен единице.
    row = conn.execute(
        "SELECT visits FROM v4_campus_cells WHERE season_id = ? AND cell_lon = ? AND cell_lat = ?",
        (season_id, cell_lon, cell_lat),
    ).fetchone()
    del cursor
    opened = int(row["visits"]) == 1
    total = conn.execute(
        "SELECT COUNT(*) FROM v4_campus_cells WHERE season_id = ?", (season_id,)
    ).fetchone()[0]
    return {"opened": opened, "cells": int(total)}
