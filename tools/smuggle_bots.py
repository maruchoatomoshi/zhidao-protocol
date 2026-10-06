"""Боты для Контрабанды: играют за стол по HTTP, как настоящие телефоны.

Зачем. Чтобы один человек мог сыграть партию (минимум 3 игрока), проверить
оформление и баланс весов, не собирая живой стол. Приложение и правила игры не
меняются: боты -- обычные учётки оператора, которые ходят через тот же API.

Почему операторы. Персонал играет в комнатах без записи в составе сезона
(rooms.resolve_season), поэтому боты не попадают в рейтинг и списки участников.
Приза в ★ они не получают: награда требует членства в сезоне (smuggle.award).
Но партия с ботами считается за стол из четырёх -- человек, выигравший её,
получит 10★ (раз в день). Для проверок это нормально, фармить не стоит.

Две команды (только стандартная библиотека):

  provision  заводит учётки ботов (прямая запись в базу, одна короткая
             транзакция, как provision.py; запускать на сервере от www-data):
      sudo -u www-data /opt/zhidao-v4/.venv/bin/python /root/smuggle_bots.py \\
          provision --db /var/lib/zhidao-v4/zhidao.db --count 3 --out /root/bots.csv

  play       боты садятся за стол и играют до конца партии:
      sudo -u www-data python3 /tmp/smuggle_bots.py play --base http://127.0.0.1:8770 \
          --creds /var/lib/zhidao-v4/bots.csv --host
          боты сами открывают комнату, печатают её код и стартуют партию, когда
          за столом соберётся --start-when игроков (по умолчанию: боты + 1 человек);
      ... play --base ... --creds ... --code 1234
          боты входят в вашу комнату (партию запускаете вы, как ведущий).

Бот-таможенник читает накладную: расхождение веса -- вскрывает и отмечает карты,
которые не совпадают с заявленным; сошлось -- чаще пропускает (особенно за
взятку). Бот-купец то честен, то жульничает; жулик старается подобрать запрещёнку
так, чтобы вес сошёлся (но иногда ошибается). Способности ролей боты не
используют.
"""
from __future__ import annotations

import argparse
import csv
import http.cookiejar
import itertools
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

NAMES = ["Ли", "Чжан", "Ван", "Лю", "Чэнь", "Ян", "Чжао", "Хуан"]


# --- заведение учёток (прямая запись, как provision.py) ----------------------------------

def provision(args: argparse.Namespace) -> int:
    sys.path.insert(0, os.getcwd())  # запуск из /opt/zhidao-v4 -- так находится пакет zhidao_v4
    from zhidao_v4.auth import ProvisioningError, provision_local_account
    from zhidao_v4.db import connect_database, immediate_transaction
    from zhidao_v4.provision import generate_password

    out = Path(args.out)
    existing = {}
    if out.exists():
        with out.open(encoding="utf-8", newline="") as handle:
            existing = {row["username"]: row["password"] for row in csv.DictReader(handle)}
    conn = connect_database(args.db)
    created = []
    try:
        for index in range(1, args.count + 1):
            username = f"bot.smuggle.{index}"
            if username in existing:
                created.append((username, existing[username]))
                continue
            password = generate_password()
            try:
                with immediate_transaction(conn):
                    provision_local_account(conn, username=username, password=password,
                                            display_name=f"Бот · {NAMES[(index - 1) % len(NAMES)]}", role_code="operator")
            except ProvisioningError as exc:
                raise SystemExit(f"{username}: {exc}. Если учётка уже есть, а файла паролей нет -- "
                                 "сбросьте пароль: python -m zhidao_v4.passwd.") from None
            created.append((username, password))
    finally:
        conn.close()
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["username", "password"])
        writer.writerows(created)
    print(f"Готово: {len(created)} ботов, пароли в {out} (права 600).")
    return 0


# --- клиент API ----------------------------------------------------------------------------

class Bot:
    def __init__(self, base: str, username: str, password: str, label: str, rng: random.Random):
        self.base, self.username, self.password, self.label, self.rng = base.rstrip("/"), username, password, label, rng
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""
        self.account_id = 0
        self.last_error = ""

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return exc.code, {"detail": raw.decode("utf-8", "replace")[:200]}

    def login(self) -> None:
        status, body = self.call("POST", "/api/v4/auth/login", {"username": self.username, "password": self.password})
        if status != 200:
            raise SystemExit(f"{self.label}: вход не удался ({status}): {body.get('detail', body)}")
        self.csrf = body["csrf_token"]
        self.account_id = int(body["account"]["id"])

    def room(self) -> dict | None:
        status, body = self.call("GET", "/api/v4/games/rooms/current")
        return body if status == 200 and body.get("room") else None

    def act(self, code: str, action: str, body: dict | None = None) -> tuple[int, dict]:
        status, result = self.call("POST", f"/api/v4/games/rooms/{code}/smuggle/{action}", body)
        self.last_error = "" if status < 300 else str(result.get("detail", status))
        return status, result


# --- мозги ---------------------------------------------------------------------------------

class Brain:
    def __init__(self, catalog: dict, rng: random.Random, cheat: float, clumsy: float):
        self.goods = {g["code"]: g for g in catalog["goods"]}
        self.by_zh = {g["zh"]: g["code"] for g in catalog["goods"]}
        self.max_bag, self.typhoon_bag, self.lantern_bribe = catalog["max_bag"], catalog["typhoon_bag"], catalog["lantern_bribe"]
        self.rng, self.cheat, self.clumsy = rng, cheat, clumsy

    def pack(self, game: dict) -> dict | None:
        you = game["you"]
        hand = you["hand"]
        limit = self.typhoon_bag if game.get("event") == "typhoon" else self.max_bag
        money = game["table"][str(self.me_id(game))]["money"] if "table" in game else 0
        legal = [i for i, card in enumerate(hand) if card["legal"]]
        if not legal:
            return None
        by_code: dict[str, list[int]] = {}
        for i in legal:
            by_code.setdefault(hand[i]["code"], []).append(i)
        best = max(by_code.values(), key=len)
        declared = hand[best[0]]["code"]
        take = min(len(best), limit, self.rng.randint(2, 4))
        honest = {"cards": best[:take], "declared": declared, "bribe": 0}
        bad = [i for i, card in enumerate(hand) if not card["legal"]]
        if not bad or self.rng.random() > self.cheat:
            return honest
        # Жулик: ищет набор с тем же весом, что у честной сумки, и хотя бы одной запрещёнкой.
        options = []
        for size in range(2, min(limit, len(hand)) + 1):
            for combo in itertools.combinations(range(len(hand)), size):
                if not any(i in bad for i in combo):
                    continue
                for code in {hand[i]["code"] for i in legal}:
                    if sum(hand[i]["weight"] for i in combo) == size * self.goods[code]["weight"]:
                        options.append((list(combo), code))
        if options:
            cards, code = self.rng.choice(options)
        elif self.rng.random() < self.clumsy:
            cards = self.rng.sample(bad, 1) + self.rng.sample(best, min(1, len(best)))
            code = declared
        else:
            return honest
        cap = self.lantern_bribe if game.get("event") == "lantern" else 4
        return {"cards": cards, "declared": code, "bribe": self.rng.randint(0, max(0, min(money, cap)))}

    @staticmethod
    def me_id(game: dict) -> int:
        return game["__me"]

    def inspect(self, game: dict, opened_budget: int) -> tuple[str, dict] | None:
        you = game["you"]
        decisions = game.get("decisions") or {}
        inspecting = you.get("inspecting") or {}
        for pid, cards in inspecting.items():
            if pid in decisions:
                continue
            declared_zh = self.goods[game["bags"][pid]["declared"]]["zh"]
            return "judge", {"merchant": int(pid), "marks": [i for i, card in enumerate(cards) if card.get("zh") != declared_zh]}
        for pid, bag in game["bags"].items():
            if pid in decisions or pid in (game.get("opened") or []):
                continue
            manifest = (you.get("manifest") or {}).get(pid)
            bribe = (you.get("bribes") or {}).get(pid, 0)
            if manifest and manifest["weight"] != manifest["expected"]:
                chance = 0.9
            else:
                chance = 0.15 if bribe >= 3 else 0.3
            if opened_budget > 0 and self.rng.random() < chance:
                return "open", {"merchant": int(pid)}
            return "pass", {"merchant": int(pid)}
        return None


# --- игра ----------------------------------------------------------------------------------

def read_creds(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [(row["username"], row["password"]) for row in csv.DictReader(handle)]


def fetch_catalog(base: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + "/app/assets/games/smuggle.json", timeout=20) as response:
        return json.loads(response.read())


def play(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed)
    creds = read_creds(args.creds)[: args.bots] if args.bots else read_creds(args.creds)
    if not creds:
        raise SystemExit("В файле нет ни одного бота.")
    catalog = fetch_catalog(args.base)
    brain = Brain(catalog, rng, args.cheat, args.clumsy)
    bots = [Bot(args.base, user, password, f"бот {i}", rng) for i, (user, password) in enumerate(creds, start=1)]
    for bot in bots:
        bot.login()
        time.sleep(0.4)
    code = args.code
    host = bots[0]
    start_when = args.start_when or len(bots) + 1
    if args.host:
        status, body = host.call("POST", "/api/v4/games/rooms", {"game": "smuggle"})
        if status != 200:
            raise SystemExit(f"Не удалось открыть комнату: {body.get('detail', body)}")
        code = body["room"]["code"]
        print(f"\n=== КОД КОМНАТЫ: {code} === Заходите в «Ивенты» → «Контрабанда» → «Войти по коду».", flush=True)
    if not code:
        raise SystemExit("Нужен --host или --code.")
    for bot in bots[1:] if args.host else bots:
        status, body = bot.call("POST", "/api/v4/games/rooms/join", {"code": code})
        if status != 200:
            raise SystemExit(f"{bot.label}: не вошёл в комнату {code}: {body.get('detail', body)}")
    print(f"Боты за столом: {len(bots)}. Жду игроков (старт при {start_when}), Ctrl+C -- остановить.", flush=True)

    started, last_round, finished = False, None, False
    opens = {}
    while not finished:
        time.sleep(args.pace)
        for bot in bots:
            snapshot = bot.room()
            if snapshot is None:
                continue
            game = snapshot.get("game") or {}
            room = snapshot["room"]
            if args.host and bot is host and not started and room["status"] == "lobby":
                seated = len(snapshot.get("players") or [])
                if seated >= start_when:
                    status, _ = host.act(code, "start")
                    started = status < 300
                    print("Партия началась." if started else f"Старт не удался: {host.last_error}", flush=True)
                continue
            phase = game.get("phase")
            if phase in (None, "lobby"):
                continue
            started = True
            game["__me"] = snapshot["you"]
            if phase == "over":
                if game.get("result"):
                    print_result(game, [b.label for b in bots])
                finished = True
                break
            round_key = (game.get("game"), game.get("round"))
            if round_key != last_round:
                last_round = round_key
                opens = {}
                print(f"-- Раунд {game['round']} из {game['rounds']}, событие: {game.get('event')}, тара {game.get('tare', 0)}", flush=True)
            you = game.get("you")
            if not you:
                continue
            time.sleep(rng.uniform(*args.think))
            if phase == "pack" and not you["officer"] and "bag" not in you:
                move = brain.pack(game)
                if move:
                    bot.act(code, "pack", move)
            elif phase == "inspect" and you["officer"]:
                budget = 1 - opens.get("n", 0) if game.get("event") == "dutyfree" else 99
                choice = brain.inspect(game, budget)
                if choice:
                    action, body = choice
                    status, _ = bot.act(code, action, body)
                    if status >= 300 and action == "open":
                        bot.act(code, "pass", body)
                    elif status < 300 and action == "open":
                        opens["n"] = opens.get("n", 0) + 1
    return 0


def print_result(game: dict, labels: list[str]) -> None:
    result = game["result"]
    print("\n=== Итог партии ===")
    if result["reason"] != "done":
        print("Партия не засчитана:", result["reason"])
        return
    for pid, row in sorted(result["scores"].items(), key=lambda item: -item[1]["total"]):
        crown = "  <- победа" if int(pid) in result["winners"] else ""
        print(f"игрок {pid}: {row['total']} (юани {row['money']}, товары {row['goods']}, короли {row['king']}, наборы {row['sets']}){crown}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("provision", help="завести учётки ботов (на сервере)")
    p.add_argument("--db", required=True)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--out", default="bots.csv")
    p.set_defaults(handler=provision)
    q = sub.add_parser("play", help="посадить ботов за стол и играть")
    q.add_argument("--base", default="http://127.0.0.1:8770")
    q.add_argument("--creds", default="bots.csv")
    q.add_argument("--bots", type=int, default=0, help="сколько ботов взять из файла (0 -- все)")
    q.add_argument("--host", action="store_true", help="первый бот открывает комнату и печатает код")
    q.add_argument("--code", help="код уже открытой комнаты (если вы ведущий)")
    q.add_argument("--start-when", type=int, default=0, help="стартовать, когда за столом столько игроков")
    q.add_argument("--cheat", type=float, default=0.45, help="вероятность, что бот-купец жульничает")
    q.add_argument("--clumsy", type=float, default=0.3, help="вероятность неуклюжего жульничества (вес не сойдётся)")
    q.add_argument("--pace", type=float, default=1.5, help="пауза между опросами, с")
    q.add_argument("--think", type=float, nargs=2, default=[0.8, 2.5], metavar=("MIN", "MAX"))
    q.add_argument("--seed", type=int, default=None)
    q.set_defaults(handler=play)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except KeyboardInterrupt:
        print("\nОстановлено.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
