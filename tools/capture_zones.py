"""Кварталы Захвата кампуса: делит кампус на участки по настоящим дорогам.

Решение пользователя 2026-09-27: границы точек Захвата идут по дорогам —
кампус делится на кварталы, каждый квартал принадлежит ближайшей точке.
До этого карта резала кампус прямыми серединными линиями между точками
(взвешенная диаграмма Вороного в capture.js), и граница проходила сквозь
здания.

Геометрия здесь не выдумывается. Всё берётся из campus.geojson:
- граница кампуса — объект category=boundary;
- дороги — все объекты category=road (осевые линии OpenStreetMap), дорога
  вычитается из кампуса полосой шириной ROAD_WIDTH_M;
- точка Захвата — объект, на который она ссылается в capture.json.
Единственное правило, добавленное сверху: квартал отходит той точке, чей
объект (контур здания или площадки) к нему ближе всех. Точка подтверждается
вожатым по GPS и может сдвинуться на несколько метров — кварталы от этого
не прыгают, они привязаны к зданию, а не к отметке.

Кампус в campus.geojson всё ещё verified: false (CLAUDE.md, «Campus map»):
кварталы точны ровно настолько, насколько точны исходные дороги.

Запуск (нужен shapely, только для генерации; приложению и тестам он не нужен):

    python tools/capture_zones.py            # пересобрать файл
    python tools/capture_zones.py --check    # проверить, что файл актуален

Результат — zhidao_v4/static/app/assets/campus/capture-zones.json.
Руками этот файл не правят: перезапуск генератора сотрёт правки.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPUS = ROOT / "zhidao_v4/static/app/assets/maps/campus.geojson"
CAPTURE = ROOT / "zhidao_v4/static/app/assets/campus/capture.json"
TARGET = ROOT / "zhidao_v4/static/app/assets/campus/capture-zones.json"

ROAD_WIDTH_M = 8.0        # полоса, которую дорога вырезает из кварталов
MIN_BLOCK_M2 = 120.0      # обрезки меньше этого — щели между дорогами, не кварталы
SIMPLIFY_M = 0.6          # сглаживание контура: меньше точек, та же форма


def _projection(boundary_coords):
    lons = [p[0] for p in boundary_coords]
    lats = [p[1] for p in boundary_coords]
    lon0, lat0 = sum(lons) / len(lons), sum(lats) / len(lats)
    kx = math.cos(math.radians(lat0)) * 111_320.0
    ky = 110_540.0

    def to_m(lon, lat):
        return ((lon - lon0) * kx, (lat - lat0) * ky)

    def to_deg(x, y):
        return (round(lon0 + x / kx, 6), round(lat0 + y / ky, 6))

    return to_m, to_deg


def _split(block, anchors: dict) -> dict:
    """Делит квартал между объектами внутри него: точка квартала отходит
    ближайшему объекту. Считается диаграммой Вороного по точкам контуров
    объектов (через каждый метр), а не по их серединам: длинный корпус
    не должен проигрывать маленькой площадке из-за того, что его середина
    далеко."""
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import unary_union, voronoi_diagram

    seeds, owner = [], []
    for code, shape in anchors.items():
        # Объект-территория, внутри которой лежит другой объект (столовая
        # внутри «Жилой зоны 2»), борется за квартал своей серединой, а не
        # краем: иначе её край окружает вложенное здание со всех сторон и
        # тому не достаётся ничего.
        if any(other is not shape and shape.contains(other.centroid) for other in anchors.values()):
            seeds.append(shape.centroid)
            owner.append(code)
            continue
        boundary = shape.boundary
        steps = max(8, int(boundary.length))
        for i in range(steps):
            pt = boundary.interpolate(i / steps, normalized=True)
            seeds.append(pt)
            owner.append(code)
    cells = voronoi_diagram(MultiPoint(seeds), envelope=block.envelope.buffer(50))
    pieces: dict[str, list] = {code: [] for code in anchors}
    for cell in cells.geoms:
        # Какой затравке принадлежит ячейка — ищем затравку внутри неё.
        for i, seed in enumerate(seeds):
            if cell.contains(seed) or cell.touches(seed):
                piece = cell.intersection(block)
                if not piece.is_empty:
                    pieces[owner[i]].append(piece)
                break
    result = {}
    for code, parts in pieces.items():
        if parts:
            merged = unary_union(parts).buffer(0.01).buffer(-0.01)
            if merged.area >= MIN_BLOCK_M2 / 4:
                result[code] = merged
    return result


def build() -> dict:
    from shapely.geometry import LineString, MultiPolygon, Polygon
    from shapely.ops import unary_union

    campus = json.loads(CAMPUS.read_text(encoding="utf-8"))
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    features = {f["properties"]["id"]: f for f in campus["features"] if f.get("properties", {}).get("id")}
    boundary_feature = next(f for f in campus["features"] if f["properties"].get("category") == "boundary")
    ring = boundary_feature["geometry"]["coordinates"][0]
    to_m, to_deg = _projection(ring)

    def poly_m(coords):
        rings = [[to_m(*p) for p in r] for r in coords]
        return Polygon(rings[0], rings[1:])

    boundary = poly_m(boundary_feature["geometry"]["coordinates"]).buffer(0)
    roads = [LineString([to_m(*p) for p in f["geometry"]["coordinates"]])
             for f in campus["features"]
             if f["properties"].get("category") == "road" and f["geometry"]["type"] == "LineString"]
    cut = unary_union([r.buffer(ROAD_WIDTH_M / 2, cap_style="flat") for r in roads])
    pieces = boundary.difference(cut)
    blocks = [g for g in getattr(pieces, "geoms", [pieces]) if g.area >= MIN_BLOCK_M2]

    anchors = {}
    for point in capture["points"]:
        geometry = features[point["feature"]]["geometry"]
        if geometry["type"] == "Polygon":
            anchors[point["code"]] = poly_m(geometry["coordinates"]).buffer(0)
        elif geometry["type"] == "MultiPolygon":
            anchors[point["code"]] = unary_union([poly_m(c) for c in geometry["coordinates"]])
        else:
            raise SystemExit(f"{point['code']}: у объекта {point['feature']} нет контура")

    owned: dict[str, list] = {code: [] for code in anchors}
    for block in blocks:
        inside = [code for code, shape in anchors.items() if block.intersection(shape).area > 1.0]
        if len(inside) == 1:
            owned[inside[0]].append(block)
        elif len(inside) > 1:
            # В одном квартале несколько точек (библиотека рядом со
            # стадионом, столовая и площадки в жилой зоне): квартал делится
            # между ними — каждому участку достаётся ближайший объект.
            owned_parts = _split(block, {code: anchors[code] for code in inside})
            for code, part in owned_parts.items():
                owned[code].append(part)
        else:
            # Пустой квартал — ближайшему объекту; при равенстве тому,
            # чья середина ближе к середине квартала.
            code = min(anchors, key=lambda c: (round(block.distance(anchors[c]), 1),
                                               block.centroid.distance(anchors[c].centroid)))
            owned[code].append(block)

    zones = {}
    for code, parts in owned.items():
        if not parts:
            continue
        shape = unary_union(parts).simplify(SIMPLIFY_M, preserve_topology=True)
        polys = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
        zones[code] = [
            [[list(to_deg(x, y)) for x, y in poly.exterior.coords]]
            + [[list(to_deg(x, y)) for x, y in hole.coords] for hole in poly.interiors]
            for poly in polys
        ]
    return {
        "version": 1,
        "generated_by": "tools/capture_zones.py",
        "note_ru": "Кварталы Захвата: кампус, разрезанный настоящими дорогами из campus.geojson; "
                   "квартал принадлежит точке, чей объект ближе. Не править руками — перезапустить генератор.",
        "road_width_m": ROAD_WIDTH_M,
        "blocks": len(blocks),
        "zones": zones,
    }


def render(data: dict) -> str:
    # Одна зона — одна строка: файл читается глазами и даёт короткий diff.
    head = {k: v for k, v in data.items() if k != "zones"}
    lines = ["{"]
    for key, value in head.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    lines.append('  "zones": {')
    items = list(data["zones"].items())
    for i, (code, polys) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"    {json.dumps(code)}: {json.dumps(polys, separators=(',', ':'))}{comma}")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="только проверить, что файл актуален")
    args = parser.parse_args()
    text = render(build())
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print("capture-zones.json устарел: запустите python tools/capture_zones.py")
            return 1
        print("capture-zones.json актуален.")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    zones = json.loads(text)["zones"]
    print(f"записано {TARGET.relative_to(ROOT)}: {len(zones)} зон, "
          f"{sum(len(p) for p in zones.values())} участков")
    return 0


if __name__ == "__main__":
    sys.exit(main())
