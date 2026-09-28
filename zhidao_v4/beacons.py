"""Метки на кампусе: QR-табличка у каждой точки Захвата (V4_GAMES.md §3.7).

Решение пользователя 2026-09-28. У точки висит табличка с QR-кодом; игра
засчитывает присутствие, только если отсканирована настоящая табличка этой
точки **и** телефон рядом с ней по GPS. Без хорошего GPS — отказ с
подсказкой (тоже решение пользователя): иначе фото таблички, пересланное в
общежитие, работало бы.

Защита, по слоям:
- токен таблички — 10 случайных знаков, подделать новую точку нельзя;
- QR плюс GPS: фото и перевешенная табличка далеко от места не работают;
- перевыпуск: вожатый меняет токен, старая табличка перестаёт действовать;
- «две метки подряд слишком далеко»: нельзя отметиться у двух точек быстрее,
  чем до них дойти (память процесса, как коды встреч);
- счётчик далёких сканов: настоящую метку сканируют далеко от места —
  вожатые видят, что табличку, похоже, перевесили или сфотографировали.

Установка таблички и есть подтверждение точки: вожатый стоит у неё и
сканирует, координата — его телефона (v4_capture_points), а не с карты. Это
подтверждает **точку**, а не контуры зданий: campus.geojson остаётся
verified: false (CLAUDE.md, «Campus map»).

Хранится место, а не человек: кто сканировал, в базе нет.
"""
from __future__ import annotations

import math
import re
import secrets
import threading
import time

from . import campus, capture, rooms, story
from .cases import CaseError, authorize, encoded, replay

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"   # без 0/O и 1/I: код можно набрать руками
TOKEN_LEN = 10
ISSUE_OPERATION = "beacon.issue"
MAX_WALK_SPEED_MS = 7.0      # быстрее бега между двумя метками — это не ноги
TRAVEL_MEMORY_S = 900


def _token() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(TOKEN_LEN))


def pretty(token: str) -> str:
    """Как код напечатан под QR: две группы по пять."""
    return f"{token[:5]}-{token[5:]}"


def normalize(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(text or "").upper())


def parse(text: str) -> tuple[str | None, str]:
    """Что отсканировали или набрали: адрес с таблички, «точка.код» или код.

    Возвращает (точка или None, код). Точку по одному коду найдёт resolve()."""
    raw = str(text or "").strip()
    match = re.search(r"(?:[#?&]m=)?([a-z0-9_-]{1,40})\.([0-9A-Za-z-]{10,12})\s*$", raw)
    if match and len(normalize(match.group(2))) == TOKEN_LEN:
        return match.group(1), normalize(match.group(2))
    return None, normalize(raw)


def rows(conn, season_id: int) -> dict[str, dict]:
    return {r["point_code"]: dict(r) for r in conn.execute(
        "SELECT * FROM v4_beacons WHERE season_id = ?", (season_id,))}


def installed(conn, season_id: int, code: str) -> bool:
    row = conn.execute("SELECT installed_at FROM v4_beacons WHERE season_id = ? AND point_code = ?",
                       (season_id, code)).fetchone()
    return bool(row and row["installed_at"])


def resolve(conn, season_id: int, text: str) -> str:
    """Код таблички → точка. Ошибка — если это не метка или она перевыпущена."""
    point, token = parse(text)
    if len(token) != TOKEN_LEN or any(ch not in ALPHABET for ch in token):
        raise CaseError("Это не метка ZHIDAO. Наведите камеру на QR на табличке.")
    row = conn.execute("SELECT point_code FROM v4_beacons WHERE season_id = ? AND token = ?",
                       (season_id, token)).fetchone()
    if row is None or (point and point != row["point_code"]):
        raise CaseError("Эта метка больше не действует. Скажите вожатому — он повесит новую.", 410)
    return row["point_code"]


def _name(code: str) -> str:
    feature = capture.points().get(code, {}).get("feature")
    return story.feature_names().get(feature, {}).get("name_ru") or code


# --- нельзя быть в двух местах сразу ---------------------------------------------------------

class Travel:
    def __init__(self) -> None:
        self.last: dict[int, tuple[str, float, float, float]] = {}
        self.lock = threading.Lock()

    def check(self, account_id: int, code: str, lon: float, lat: float) -> None:
        now = time.monotonic()
        with self.lock:
            prev = self.last.get(account_id)
            if prev and prev[0] != code and now - prev[3] < TRAVEL_MEMORY_S:
                metres = capture.distance_m(lon, lat, prev[1], prev[2])
                seconds = max(now - prev[3], 1.0)
                if metres / seconds > MAX_WALK_SPEED_MS:
                    wait = math.ceil(metres / MAX_WALK_SPEED_MS - seconds)
                    raise CaseError(f"Вы только что были у другой метки в {round(metres)} м отсюда. "
                                    f"Попробуйте через {wait} с.", 429)
            self.last[account_id] = (code, lon, lat, now)


travel = Travel()


# --- далёкие сканы ----------------------------------------------------------------------------
# Отказ откатывает транзакцию, поэтому счётчик не пишется в момент отказа:
# он копится здесь и сбрасывается в базу при следующей удачной записи меток.
# Перезапуск процесса теряет только ещё не записанное — это сигнал, не учёт.

class FarScans:
    def __init__(self) -> None:
        self.pending: dict[tuple[int, str], tuple[int, str]] = {}
        self.lock = threading.Lock()

    def note(self, season_id: int, code: str) -> None:
        with self.lock:
            count, _ = self.pending.get((season_id, code), (0, ""))
            self.pending[(season_id, code)] = (count + 1, rooms.iso(capture.utcnow()))

    def peek(self, season_id: int, code: str) -> tuple[int, str | None]:
        with self.lock:
            return self.pending.get((season_id, code), (0, None))

    def flush(self, conn) -> None:
        with self.lock:
            pending, self.pending = self.pending, {}
        for (season_id, code), (count, at) in pending.items():
            conn.execute(
                """UPDATE v4_beacons SET far_scans = far_scans + ?, far_last_at = ?
                   WHERE season_id = ? AND point_code = ?""", (count, at, season_id, code))


far = FarScans()


# --- проверка присутствия (для всех игр со станциями) ----------------------------------------

def check(conn, season_id: int, actor: int, code: str, row: dict, *, beacon: str | None,
          lon: float, lat: float, accuracy_m: float) -> None:
    """Игрок у точки? Если на точке висит метка — нужен её скан, и рядом.

    Пока метки нет, работает прежняя проверка по GPS: игры не ломаются до
    того, как вожатые развесят таблички."""
    far.flush(conn)
    if not installed(conn, season_id, code):
        capture._present(row, lon, lat, accuracy_m)
        return
    if not beacon:
        raise CaseError(f"Отсканируйте метку на точке «{_name(code)}».", 428)
    scanned = resolve(conn, season_id, beacon)
    if scanned != code:
        raise CaseError(f"Это метка другой точки — «{_name(scanned)}».", 409)
    if accuracy_m is None or accuracy_m > campus.MAX_ACCURACY_M:
        raise CaseError("Метка засчитывается вместе с геопозицией. Включите геолокацию "
                        "и выйдите под открытое небо, потом сканируйте ещё раз.")
    radius = capture.config()["radius_m"]
    if capture.distance_m(lon, lat, row["lon"], row["lat"]) > radius:
        far.note(season_id, code)
        raise CaseError(f"Метка засчитывается только рядом с ней (в {radius} м). Подойдите к табличке.")
    travel.check(actor, code, lon, lat)


def scan(conn, actor: int, season_id: int, *, text: str, lon: float, lat: float, accuracy_m: float) -> dict:
    """Просто скан метки вне игры: отметиться у места. Открывает туман там
    (а с ним и сюжетные места рядом) и говорит, во что тут можно играть."""
    authorize(conn, actor, season_id, write=True, staff_may_play=True)
    code = resolve(conn, season_id, text)
    row = capture._point_rows(conn, season_id).get(code)
    if row is None or not installed(conn, season_id, code):
        raise CaseError("Эту метку ещё не установили. Скажите вожатому.", 409)
    check(conn, season_id, actor, code, row, beacon=text, lon=lon, lat=lat, accuracy_m=accuracy_m)
    campus.record_visit(conn, season_id, lon=lon, lat=lat, accuracy_m=accuracy_m)
    feature = capture.points()[code]["feature"]
    names = story.feature_names().get(feature, {})
    return {"point": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh")}


# --- вожатый ----------------------------------------------------------------------------------

def status(conn, actor: int, season_id: int) -> dict:
    authorize(conn, actor, season_id, manage=True)
    have = rows(conn, season_id)
    confirmed = capture._point_rows(conn, season_id)
    items = []
    for code, point in capture.points().items():
        names = story.feature_names().get(point["feature"], {})
        b = have.get(code)
        extra, extra_at = far.peek(season_id, code)
        items.append({
            "point": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh"),
            "issued": b is not None, "installed": bool(b and b["installed_at"]),
            "installed_at": b["installed_at"] if b else None, "confirmed": code in confirmed,
            "far_scans": (b["far_scans"] if b else 0) + (extra if b else 0),
            "far_last_at": (extra_at or b["far_last_at"]) if b else None,
        })
    return {"season_id": season_id, "radius_m": capture.config()["radius_m"],
            "install_accuracy_m": capture.config()["confirm_accuracy_m"], "points": items}


def issue(conn, actor: int, season_id: int, points: list[str], key: str, request_id=None):
    """Новые таблички: для точки без метки — первая, для точки с меткой —
    перевыпуск (старая табличка сразу перестаёт действовать, место остаётся
    неподтверждённым до установки новой)."""
    authorize(conn, actor, season_id, manage=True)
    points = sorted(set(points))
    key, digest, old = replay(conn, actor, ISSUE_OPERATION, key, {"season_id": season_id, "points": points})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, manage=True, write=True)
    far.flush(conn)
    unknown = [p for p in points if p not in capture.points()]
    if not points or unknown:
        raise CaseError("Выберите точки Захвата." if not points else f"Нет такой точки: {unknown[0]}.")
    now = rooms.iso(capture.utcnow())
    for code in points:
        conn.execute(
            """INSERT INTO v4_beacons(season_id, point_code, token, issued_at) VALUES (?,?,?,?)
               ON CONFLICT(season_id, point_code) DO UPDATE SET token = excluded.token,
                   issued_at = excluded.issued_at, installed_at = NULL, installed_lon = NULL,
                   installed_lat = NULL, far_scans = 0, far_last_at = NULL""",
            (season_id, code, _token(), now))
    response = {"season_id": season_id, "issued": points}
    conn.execute(
        """INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key, request_hash,
               response_status, response_json) VALUES (?,?,?,?,200,?)""",
        (actor, ISSUE_OPERATION, key, digest, encoded(response)))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id,
               request_id, after_json) VALUES (?, ?, ?, 'beacon', ?, ?, ?)""",
        (actor, season_id, ISSUE_OPERATION, ",".join(points), request_id, encoded({"points": points})))
    return response, False


def labels(conn, actor: int, season_id: int, base_url: str) -> dict:
    """Таблички на печать: адрес для QR, код для ручного ввода, названия.

    Сам QR рисует страница печати по матрице отсюда: генератор — проверенная
    библиотека (vendor/qrcodegen.py), а не самодельный."""
    from .vendor.qrcodegen import QrCode

    authorize(conn, actor, season_id, manage=True)
    have = rows(conn, season_id)
    items = []
    for code, point in capture.points().items():
        b = have.get(code)
        if b is None:
            continue
        url = f"{base_url.rstrip('/')}/app/#m={code}.{b['token']}"
        qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
        matrix = ["".join("1" if qr.get_module(x, y) else "0" for x in range(qr.get_size()))
                  for y in range(qr.get_size())]
        names = story.feature_names().get(point["feature"], {})
        items.append({"point": code, "name_ru": names.get("name_ru"), "name_zh": names.get("name_zh"),
                      "url": url, "code": pretty(b["token"]), "installed": bool(b["installed_at"]),
                      "qr": matrix})
    return {"season_id": season_id, "labels": items}


def install(conn, actor: int, season_id: int, *, text: str, lon: float, lat: float, accuracy_m: float) -> dict:
    """Вожатый у таблички сканирует её: метка установлена, точка подтверждена
    координатой его телефона. Правила точности — те же, что у подтверждения
    точки в Захвате (confirm_accuracy_m, не дальше confirm_max_offset_m от
    объекта на карте)."""
    authorize(conn, actor, season_id, manage=True, write=True)
    far.flush(conn)
    code = resolve(conn, season_id, text)
    result = capture.confirm(conn, actor, season_id, code, lon=lon, lat=lat, accuracy_m=accuracy_m,
                             via_beacon=True)
    now = rooms.iso(capture.utcnow())
    conn.execute(
        """UPDATE v4_beacons SET installed_at = ?, installed_lon = ?, installed_lat = ?,
               far_scans = 0, far_last_at = NULL WHERE season_id = ? AND point_code = ?""",
        (now, round(lon, 6), round(lat, 6), season_id, code))
    conn.execute(
        """INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type, entity_id, after_json)
           VALUES (?, ?, 'beacon.install', 'beacon', ?, ?)""",
        (actor, season_id, code, encoded({"accuracy_m": round(accuracy_m), "offset_m": result["offset_m"]})))
    return {**result, "point": code, "name_ru": _name(code), "installed": True}
