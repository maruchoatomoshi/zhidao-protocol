from __future__ import annotations

import json
import math
import unittest
from pathlib import Path


GEOJSON = (
    Path(__file__).resolve().parents[1]
    / "zhidao_v4" / "static" / "app" / "assets" / "maps" / "campus.geojson"
)
MAP_JS = (
    Path(__file__).resolve().parents[1]
    / "zhidao_v4" / "static" / "app" / "campus-map.js"
)

# Кампус Лиань, Линшуй. Рамка нарочно широкая — она ловит не мелкую ошибку в
# координате, а подмену системы: GCJ-02 уводит точку на сотни метров, BD-09
# ещё дальше, и такая правка выглядит правдоподобно ровно до этой проверки.
HAINAN_BBOX = (109.95, 18.35, 110.09, 18.46)


class CampusMapDataTests(unittest.TestCase):
    """Проверки данных карты.

    До этого файла у карты не было ни одной: дубликат `id` в кампусе нашёлся
    случайно, когда скрипт напечатал одну и ту же строку дважды. Здесь
    проверяется то, что делает данные пригодными к отрисовке и к доверию, —
    не красота карты, а её непротиворечивость.
    """

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(GEOJSON.read_text(encoding="utf-8"))
        cls.features = cls.data["features"]
        cls.map_js = MAP_JS.read_text(encoding="utf-8")

    def test_ids_are_unique(self):
        seen: dict[str, int] = {}
        for feature in self.features:
            fid = feature["properties"]["id"]
            seen[fid] = seen.get(fid, 0) + 1
        duplicates = {fid: n for fid, n in seen.items() if n > 1}
        self.assertEqual(duplicates, {}, f"повторяющиеся id: {duplicates}")

    def test_only_geometry_the_renderer_can_draw(self):
        # campus-map.js разбирает Polygon и LineString и ничего больше;
        # MultiPolygon отрисовался бы пустым местом, молча.
        allowed = {"Polygon", "LineString"}
        for feature in self.features:
            with self.subTest(feature["properties"]["id"]):
                self.assertIn(feature["geometry"]["type"], allowed)

    def test_polygons_are_closed_rings(self):
        for feature in self.features:
            if feature["geometry"]["type"] != "Polygon":
                continue
            for ring in feature["geometry"]["coordinates"]:
                with self.subTest(feature["properties"]["id"]):
                    self.assertGreaterEqual(len(ring), 4)
                    self.assertEqual(ring[0], ring[-1], "кольцо не замкнуто")

    def test_every_feature_carries_the_fields_the_renderer_reads(self):
        for feature in self.features:
            props = feature["properties"]
            with self.subTest(props.get("id")):
                for field in ("id", "name_ru", "name_zh", "category", "named", "source"):
                    self.assertIn(field, props)
                self.assertIn("verified", props)

    def test_nothing_has_drifted_into_another_coordinate_system(self):
        lonmin, latmin, lonmax, latmax = HAINAN_BBOX
        for feature in self.features:
            coords = feature["geometry"]["coordinates"]
            while isinstance(coords[0][0], list):
                coords = coords[0]
            for lon, lat in coords:
                with self.subTest(feature["properties"]["id"]):
                    self.assertTrue(
                        lonmin <= lon <= lonmax and latmin <= lat <= latmax,
                        f"{lon},{lat} вне Хайнаня — похоже на GCJ-02 или BD-09",
                    )

    def test_osm_sourced_features_name_the_object_they_came_from(self):
        for feature in self.features:
            props = feature["properties"]
            if props.get("source") == "openstreetmap":
                with self.subTest(props["id"]):
                    self.assertIn("osm_id", props)

    def test_features_not_from_osm_say_where_they_came_from(self):
        # «Обвёл по снимку» — законный источник, «взялось откуда-то» — нет.
        for feature in self.features:
            props = feature["properties"]
            if props.get("source") == "openstreetmap":
                continue
            with self.subTest(props["id"]):
                self.assertTrue(
                    props.get("identified_from") or props.get("accuracy_note")
                    or props.get("identification_note"),
                    "объект не из OSM обязан объяснять своё происхождение",
                )

    def test_nothing_claims_to_be_surveyed(self):
        # verified=true означало бы замер на месте. Его не было ни разу.
        for feature in self.features:
            with self.subTest(feature["properties"]["id"]):
                self.assertFalse(feature["properties"]["verified"])
        self.assertIn("verified=false", self.data["verified_note"])

    def test_attribution_covers_both_sources_actually_used(self):
        sources = {f["properties"].get("source", "") for f in self.features}
        attribution = self.data["attribution"]
        self.assertIn("OpenStreetMap", attribution)
        if any("Esri" in s for s in sources):
            self.assertIn("Esri", attribution)

    def test_categories_are_ones_the_map_knows(self):
        # Незнакомая категория не упадёт, а тихо отрисуется цветом по умолчанию
        # и не попадёт в легенду — то есть исчезнет для человека.
        used = {f["properties"]["category"] for f in self.features}
        for category in used:
            with self.subTest(category):
                self.assertIn(f'"{category}"', self.map_js)

    def test_sport_features_do_not_claim_a_sport_they_cannot_prove(self):
        # Площадки у общежитий опознаны по снимку 0,55 м/пиксель. Размер не
        # позволяет отличить волейбол от бадминтона, поэтому в подписи не
        # должно стоять конкретного вида спорта, пока его не проверили.
        for feature in self.features:
            props = feature["properties"]
            if not props.get("sport_unconfirmed"):
                continue
            with self.subTest(props["id"]):
                for word in ("Теннис", "теннис", "Волейбол", "волейбол", "Баскетбол"):
                    self.assertNotIn(word, props["name_ru"])
                self.assertIn("НЕ ОПРЕДЕЛЁН", props["identification_note"])

    def test_the_exploration_sector_still_points_at_a_feature_that_exists(self):
        exploration = self.data["exploration"]
        ids = {f["properties"]["id"] for f in self.features}
        for core_id in exploration["core_feature_ids"]:
            with self.subTest(core_id):
                self.assertIn(core_id, ids)

    def test_landmark_groups_reference_existing_features(self):
        ids = {f["properties"]["id"] for f in self.features}
        for group in self.data.get("landmark_groups", []):
            for member in group.get("feature_ids", []):
                with self.subTest(member):
                    self.assertIn(member, ids)

    def test_polygon_areas_are_plausible_for_a_campus(self):
        # Ловит перепутанные местами долготу и широту и лишний ноль: такая
        # ошибка рисуется как гигантское пятно поверх всей карты.
        for feature in self.features:
            if feature["geometry"]["type"] != "Polygon":
                continue
            ring = feature["geometry"]["coordinates"][0][:-1]
            lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
            pts = [(p[0] * 111_320 * math.cos(lat0), p[1] * 110_540) for p in ring]
            total = 0.0
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                total += x1 * y2 - x2 * y1
            area = abs(total) / 2
            with self.subTest(feature["properties"]["id"]):
                self.assertGreater(area, 20, "меньше 20 м² — это не объект кампуса")
                self.assertLess(area, 2_000_000, "больше 2 км² — что-то не так")


if __name__ == "__main__":
    unittest.main()
