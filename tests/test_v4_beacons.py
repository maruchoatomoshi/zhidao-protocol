from __future__ import annotations

import unittest

from zhidao_v4 import beacons, capture, story

import test_v4_capture as base

CENTRE, north = base.CENTRE, base.north

LIBRARY = story.feature_centres()[capture.points()["library"]["feature"]]


class BeaconTests(unittest.TestCase):
    """Метки на кампусе (V4_GAMES.md §3.7, решение пользователя 2026-09-28).

    Обещания: таблички выпускает и печатает только вожатый; установка метки и
    есть подтверждение точки, и координата — телефона у таблички; пока метка
    не висит, игры работают по GPS, как раньше; когда висит — ход только со
    сканом именно этой таблички и только рядом с ней: фото из общежития,
    чужая табличка, выключенный GPS и перевыпущенная табличка не проходят;
    далёкие сканы видит вожатый; две метки подряд быстрее ног не засчитываются;
    кто сканировал, не хранится.
    """

    setUp = base.CaptureTests.setUp
    tearDown = base.CaptureTests.tearDown
    sql = base.CaptureTests.sql
    post = base.CaptureTests.post
    view = base.CaptureTests.view
    switch = base.CaptureTests.switch

    def issue(self, points=("stadium",), who="architect"):
        return self.clients[who].post("/api/v4/beacons/issue", json={"points": list(points)},
                                      headers={"X-CSRF-Token": self.tokens[who], "X-Idempotency-Key": f"issue-{len(points)}-{points[0]}-{self._issued}"})

    def label(self, point="stadium"):
        labels = self.clients["architect"].get("/api/v4/beacons/labels").json()["labels"]
        return next(l for l in labels if l["point"] == point)

    def install(self, point="stadium", at=CENTRE, accuracy=8.0):
        return self.post("architect", "/api/v4/beacons/install",
                         {"text": self.label(point)["url"], "lon": at[0], "lat": at[1], "accuracy_m": accuracy})

    def challenge(self, who="kid1", point="stadium", at=None, accuracy=10.0, beacon=None):
        lon, lat = at or north(20)
        body = {"lon": lon, "lat": lat, "accuracy_m": accuracy}
        if beacon is not None:
            body["beacon"] = beacon
        return self.post(who, f"/api/v4/capture/points/{point}/challenge", body)

    def ready(self, points=("stadium",)):
        self._issued += 1
        self.assertEqual(self.issue(points).status_code, 200)
        for point in points:
            at = CENTRE if point == "stadium" else LIBRARY
            response = self.install(point, at=at)
            self.assertEqual(response.status_code, 200, response.text)
        self.switch(True)

    _issued = 0

    def setUpClassState(self):
        beacons.travel = beacons.Travel()
        beacons.far = beacons.FarScans()

    def test_only_staff_issue_and_print(self):
        self.setUpClassState()
        self._issued += 1
        self.assertEqual(self.issue(who="kid1").status_code, 403)
        self.assertEqual(self.clients["kid1"].get("/api/v4/beacons/labels").status_code, 403)
        self.assertEqual(self.issue().status_code, 200)
        label = self.label()
        self.assertIn("#m=stadium.", label["url"])
        self.assertRegex(label["code"], r"^[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}$")
        self.assertEqual(len(label["qr"]), len(label["qr"][0]))
        self.assertGreaterEqual(len(label["qr"]), 21)

    def test_installing_confirms_the_point_where_the_label_hangs(self):
        self.setUpClassState()
        self._issued += 1
        self.issue()
        # С выпущенной меткой прежнее подтверждение по GPS не проходит.
        plain = self.post("architect", "/api/v4/capture/points/stadium/confirm",
                          {"lon": CENTRE[0], "lat": CENTRE[1], "accuracy_m": 8.0})
        self.assertEqual(plain.status_code, 409)
        self.assertEqual(self.install(accuracy=60.0).status_code, 400)   # грубый GPS — не ставим
        spot = north(12)
        self.assertEqual(self.install(at=spot).status_code, 200)
        row = self.sql("SELECT lon, lat FROM v4_capture_points WHERE point_code='stadium'")[0]
        self.assertAlmostEqual(row["lat"], spot[1], places=5)
        point = next(p for p in self.view()["points"] if p["code"] == "stadium")
        self.assertTrue(point["beacon"])

    def test_scan_must_be_this_label_and_near_it(self):
        self.setUpClassState()
        self.ready(("stadium", "library"))
        stadium, library = self.label("stadium"), self.label("library")
        self.assertEqual(self.challenge().status_code, 428)                               # без скана
        self.assertEqual(self.challenge(beacon="просто текст").status_code, 400)           # не метка
        self.assertEqual(self.challenge(beacon=library["url"]).status_code, 409)           # чужая табличка
        self.assertEqual(self.challenge(beacon=stadium["url"], accuracy=500).status_code, 400)  # без GPS
        # Фото таблички, отсканированное в полукилометре: не засчитано, вожатый видит сигнал.
        self.assertEqual(self.challenge(beacon=stadium["url"], at=north(500)).status_code, 400)
        status = self.clients["architect"].get("/api/v4/beacons").json()
        self.assertEqual(next(p for p in status["points"] if p["point"] == "stadium")["far_scans"], 1)
        # Код, набранный руками с таблички, — то же, что скан.
        self.assertEqual(self.challenge(beacon=stadium["code"]).status_code, 200)

    def test_reissued_label_stops_working(self):
        self.setUpClassState()
        self.ready()
        old = self.label()["url"]
        self._issued += 1
        self.assertEqual(self.issue().status_code, 200)
        self.assertNotEqual(self.label()["url"], old)
        self.assertEqual(self.post("kid1", "/api/v4/beacons/scan",
                                   {"text": old, "lon": north(10)[0], "lat": north(10)[1], "accuracy_m": 10}).status_code, 410)

    def test_two_labels_faster_than_legs_do_not_count(self):
        self.setUpClassState()
        self.ready(("stadium", "library"))
        near = lambda at: {"lon": at[0], "lat": at[1] + 10 / 111320, "accuracy_m": 10}  # noqa: E731
        first = self.post("kid1", "/api/v4/beacons/scan", {"text": self.label("stadium")["url"], **near(CENTRE)})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["point"], "stadium")
        second = self.post("kid1", "/api/v4/beacons/scan", {"text": self.label("library")["url"], **near(LIBRARY)})
        self.assertEqual(second.status_code, 429)

    def test_until_a_label_hangs_gps_still_works(self):
        self.setUpClassState()
        confirm = self.post("architect", "/api/v4/capture/points/stadium/confirm",
                            {"lon": CENTRE[0], "lat": CENTRE[1], "accuracy_m": 8.0})
        self.assertEqual(confirm.status_code, 200)
        self.switch(True)
        self.assertEqual(self.challenge().status_code, 200)

    def test_no_one_is_stored(self):
        columns = {row["name"] for row in self.sql("PRAGMA table_info(v4_beacons)")}
        self.assertFalse({c for c in columns if "account" in c})


if __name__ == "__main__":
    unittest.main()
