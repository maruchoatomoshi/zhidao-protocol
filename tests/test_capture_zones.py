"""Кварталы Захвата (assets/campus/capture-zones.json) — генерируемый файл.

Сам генератор (tools/capture_zones.py) требует shapely и в CI не
запускается; здесь проверяется то, что без него проверить можно: у каждой
точки Захвата есть зона, контуры замкнуты и лежат внутри кампуса, файл
действительно сделан генератором, а не нарисован руками.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "zhidao_v4/static/app/assets"


class CaptureZonesTests(unittest.TestCase):
    def setUp(self):
        self.zones_file = json.loads((ASSETS / "campus/capture-zones.json").read_text(encoding="utf-8"))
        self.capture = json.loads((ASSETS / "campus/capture.json").read_text(encoding="utf-8"))
        campus = json.loads((ASSETS / "maps/campus.geojson").read_text(encoding="utf-8"))
        ring = next(f for f in campus["features"] if f["properties"].get("category") == "boundary")["geometry"]["coordinates"][0]
        self.bbox = (min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring))

    def test_made_by_the_generator(self):
        self.assertEqual(self.zones_file["generated_by"], "tools/capture_zones.py")

    def test_every_capture_point_has_a_zone(self):
        codes = {p["code"] for p in self.capture["points"]}
        self.assertEqual(set(self.zones_file["zones"]), codes)

    def test_rings_are_closed_and_inside_the_campus(self):
        west, south, east, north = self.bbox
        slack = 0.0002  # около 20 м: контур упрощён и может чуть выйти за точку границы
        for code, polygons in self.zones_file["zones"].items():
            self.assertTrue(polygons, code)
            for rings in polygons:
                for ring in rings:
                    self.assertGreaterEqual(len(ring), 4, code)
                    self.assertEqual(ring[0], ring[-1], f"{code}: контур не замкнут")
                    for lon, lat in ring:
                        self.assertTrue(west - slack <= lon <= east + slack and south - slack <= lat <= north + slack,
                                        f"{code}: точка {lon},{lat} вне кампуса")


if __name__ == "__main__":
    unittest.main()
