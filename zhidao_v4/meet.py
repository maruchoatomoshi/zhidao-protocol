"""Рукопожатие двух телефонов и пазл встреч (V4_GAMES.md §3.2, §4.6).

Рукопожатие: один показывает код из шести цифр, второй вводит его. Код живёт
60 секунд, срабатывает один раз и привязан к сезону того, кто его показал.
Коды хранятся в памяти процесса (`Offers`): это секунды, а не данные.
QR появится позже — генератор QR в V4 пришлось бы писать или подключать, а
сторонние CDN из Китая не открываются; цифры работают в MAX и в браузере.

Пазл встреч по мотивам StreetPass: кусок картинки получают только от другого
человека, получают оба, никто ничего не отдаёт. Одна пара — один кусок в
сезон-день (день начинается в 07:00, как у витрины). Кто с кем встретился,
хранится только до конца дня.
"""
from __future__ import annotations

import json
import random
import secrets
import threading
import time
from functools import lru_cache
from pathlib import Path

from .cases import CaseError, authorize
from .shop import shop_day
from .virus import spread

STATIC_ROOT = Path(__file__).parent / "static"
PUZZLES_PATH = STATIC_ROOT / "app/assets/puzzles/puzzles.json"
OFFER_SECONDS = 60
_rng = random.SystemRandom()


def clock() -> float:
    """Часы кодов. Одна точка, чтобы тесты могли их подменить."""
    return time.monotonic()


@lru_cache(maxsize=1)
def puzzles() -> list[dict]:
    data = json.loads(PUZZLES_PATH.read_text(encoding="utf-8"))
    seen = set()
    for puzzle in data["puzzles"]:
        if puzzle["code"] in seen:
            raise ValueError(f"puzzles.json: повтор пазла {puzzle['code']}")
        seen.add(puzzle["code"])
        if puzzle["grid"] not in (3, 4):
            raise ValueError(f"puzzles.json: у {puzzle['code']} сетка 3×3 или 4×4")
        # Адрес картинки — от корня сайта (/app/… или /architect/…), а файлы
        # лежат в static/ под теми же именами папок.
        image = STATIC_ROOT / puzzle["image"].lstrip("/")
        if not image.exists():
            raise ValueError(f"puzzles.json: нет картинки {puzzle['image']}")
    if not data["puzzles"]:
        raise ValueError("puzzles.json: нет ни одного пазла")
    return data["puzzles"]


class Offers:
    """Живые коды встреч. Один код на человека: новый заменяет старый."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_code: dict[str, dict] = {}
        self._by_account: dict[int, str] = {}

    def _sweep(self, now: float) -> None:
        for code, offer in list(self._by_code.items()):
            # Использованный код держим ещё немного, чтобы показавший успел
            # увидеть результат при следующем опросе.
            if now - offer["created"] > OFFER_SECONDS + (30 if offer["result"] else 0):
                self._by_code.pop(code, None)
                if self._by_account.get(offer["account_id"]) == code:
                    self._by_account.pop(offer["account_id"], None)

    def create(self, account_id: int, season_id: int) -> dict:
        now = clock()
        with self._lock:
            self._sweep(now)
            old = self._by_account.pop(account_id, None)
            if old:
                self._by_code.pop(old, None)
            while True:
                code = f"{secrets.randbelow(1_000_000):06d}"
                if code not in self._by_code:
                    break
            self._by_code[code] = {"account_id": account_id, "season_id": season_id, "created": now, "result": None}
            self._by_account[account_id] = code
            return {"code": code, "expires_in": OFFER_SECONDS}

    def peek(self, code: str) -> dict | None:
        now = clock()
        with self._lock:
            self._sweep(now)
            offer = self._by_code.get(code)
            if offer is None:
                return None
            live = offer["result"] is None and now - offer["created"] <= OFFER_SECONDS
            return {**offer, "live": live, "expires_in": max(0, int(OFFER_SECONDS - (now - offer["created"])))}

    def claim(self, code: str) -> dict | None:
        """Забирает живой код; второй одновременный ввод его уже не получит."""
        now = clock()
        with self._lock:
            offer = self._by_code.get(code)
            if not offer or offer["result"] is not None or now - offer["created"] > OFFER_SECONDS:
                return None
            offer["result"] = {"state": "claimed"}
            return dict(offer)

    def release(self, code: str) -> None:
        with self._lock:
            offer = self._by_code.get(code)
            if offer and offer["result"] == {"state": "claimed"}:
                offer["result"] = None

    def finish(self, code: str, result: dict) -> None:
        with self._lock:
            if code in self._by_code:
                self._by_code[code]["result"] = result


# --- пазл -----------------------------------------------------------------------------


def _pieces(conn, season_id: int, account_id: int) -> dict[str, set[int]]:
    owned: dict[str, set[int]] = {}
    for row in conn.execute(
        "SELECT puzzle_code, piece FROM v4_puzzle_pieces WHERE season_id=? AND account_id=?",
        (season_id, account_id),
    ):
        owned.setdefault(row["puzzle_code"], set()).add(int(row["piece"]))
    return owned


def _purge_old_pairs(conn, season_id: int, today: str) -> None:
    conn.execute("DELETE FROM v4_meet_pairs WHERE season_id=? AND meet_day < ?", (season_id, today))


def state(conn, account_id: int, season_id: int) -> dict:
    season = authorize(conn, account_id, season_id)
    today = shop_day(season)
    if season["status"] == "active":
        _purge_old_pairs(conn, season_id, today)
    owned = _pieces(conn, season_id, account_id)
    items = []
    current = None
    for puzzle in puzzles():
        total = puzzle["grid"] ** 2
        have = sorted(owned.get(puzzle["code"], set()))
        complete = len(have) == total
        if not complete and current is None:
            current = puzzle["code"]
        items.append({**puzzle, "pieces": have, "total": total, "complete": complete})
    met_today = conn.execute(
        "SELECT COUNT(*) FROM v4_meet_pairs WHERE season_id=? AND meet_day=? AND (account_low=? OR account_high=?)",
        (season_id, today, account_id, account_id),
    ).fetchone()[0]
    return {"season_id": season_id, "season_status": season["status"], "day": today,
            "current": current, "puzzles": items, "met_today": int(met_today)}


def _grant_piece(conn, season_id: int, account_id: int) -> dict | None:
    owned = _pieces(conn, season_id, account_id)
    for puzzle in puzzles():
        total = puzzle["grid"] ** 2
        missing = sorted(set(range(total)) - owned.get(puzzle["code"], set()))
        if missing:
            piece = _rng.choice(missing)
            conn.execute(
                "INSERT INTO v4_puzzle_pieces(season_id, account_id, puzzle_code, piece) VALUES (?,?,?,?)",
                (season_id, account_id, puzzle["code"], piece),
            )
            return {"puzzle": puzzle["code"], "title_ru": puzzle["title_ru"], "piece": piece,
                    "have": total - len(missing) + 1, "total": total,
                    "complete": len(missing) == 1}
    return None  # все пазлы сезона собраны


def meet(conn, season_id: int, offerer: int, acceptor: int) -> dict:
    """Встреча двух людей. Вызывается внутри BEGIN IMMEDIATE."""
    if offerer == acceptor:
        raise CaseError("Это ваш собственный код. Покажите его другому человеку.", 409)
    season = authorize(conn, acceptor, season_id, write=True)
    authorize(conn, offerer, season_id, write=True)
    today = shop_day(season)
    _purge_old_pairs(conn, season_id, today)
    low, high = sorted((offerer, acceptor))
    if conn.execute(
        "SELECT 1 FROM v4_meet_pairs WHERE season_id=? AND meet_day=? AND account_low=? AND account_high=?",
        (season_id, today, low, high),
    ).fetchone():
        raise CaseError("Сегодня вы уже обменялись кусками. Завтра можно снова.", 409)
    conn.execute("INSERT INTO v4_meet_pairs(season_id, meet_day, account_low, account_high) VALUES (?,?,?,?)",
                 (season_id, today, low, high))
    names = {row["id"]: row["display_name"] for row in conn.execute(
        "SELECT id, display_name FROM v4_accounts WHERE id IN (?, ?)", (offerer, acceptor))}
    # Вирус Протокола передаётся и при встрече (V4_GAMES.md §4.7).
    caught = spread(conn, season_id, offerer, acceptor)
    return {
        offerer: {"state": "met", "partner": names[acceptor], "piece": _grant_piece(conn, season_id, offerer),
                  "virus": caught.get(offerer)},
        acceptor: {"state": "met", "partner": names[offerer], "piece": _grant_piece(conn, season_id, acceptor),
                   "virus": caught.get(acceptor)},
    }
