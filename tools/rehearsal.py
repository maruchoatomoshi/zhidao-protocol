"""Репетиция сезона: заводит тестовых участников и вожатых, включает их в
сезон-черновик и заставляет их реально пользоваться приложением — через тот
же локальный API, что и настоящие телефоны, не прямой записью в базу.

Запуск: python -m tools.rehearsal --db /var/lib/zhidao-v4/zhidao.db \
    --season hainan-rehearsal --kids 60 --operators 6 --apply

Без --apply — только план (кого заведёт, что сделает), ничего не пишет и не
стучится в API. Учётные данные сохраняются в файл рядом (--credentials-out,
по умолчанию ./rehearsal-credentials.csv) с правами 600 — это настоящие,
рабочие пароли, пусть и от тестовых учёток.

ТОЛЬКО для одноразового сезона-репетиции. Скрипт отказывается работать с
кодом сезона "hainan-v4" — это боевой черновик, не полигон.

Часть «Заводим людей» — прямая запись в базу, как provision.py и
season_roster.py: короткие ручные транзакции, второй писатель разрешён
именно в таком виде (CLAUDE.md). Часть «Играем» идёт по HTTP на
127.0.0.1:8770 — тем самым локальным путём, который уже использует смок-тест
деплоя, — с ограниченной параллельностью (--concurrency, по умолчанию 4):
это репетиция обычной нагрузки, а не стресс-тест до отказа.
"""
from __future__ import annotations

import argparse
import csv
import http.cookiejar
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from zhidao_v4 import season_roster
from zhidao_v4.auth import ProvisioningError, provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.provision import generate_password

API_BASE = "http://127.0.0.1:8770"
FORBIDDEN_SEASON_CODES = {"hainan-v4"}
KID_ATTEMPTS = 3
ROOM_PAIRS = 4  # столько троек/четвёрок посадим играть в Шпиона


# --- заводим людей и включаем в сезон (прямая запись, как provision.py) ---

def find_system_admin(conn) -> int:
    row = conn.execute(
        """SELECT a.id FROM v4_accounts a JOIN v4_role_assignments r ON r.account_id = a.id
           WHERE r.role_code = 'system_admin' AND r.season_id IS NULL AND r.revoked_at IS NULL
             AND a.status = 'active' LIMIT 1"""
    ).fetchone()
    if row is None:
        raise SystemExit("Нет активного system_admin — нечем подписать создание учёток.")
    return int(row["id"])


def find_season(conn, code: str):
    return conn.execute("SELECT * FROM v4_seasons WHERE code = ?", (code,)).fetchone()


def provision_people(conn, actor_id: int, kids: int, operators: int) -> list[dict]:
    created = []
    plan = [(f"kid{i}", f"Тест-участник {i}", "participant") for i in range(1, kids + 1)]
    plan += [(f"op{i}", f"Тест-вожатый {i}", "operator") for i in range(1, operators + 1)]
    for username, display_name, role in plan:
        password = generate_password()
        try:
            account = provision_local_account(
                conn, username=username, password=password, display_name=display_name,
                role_code=role, actor_account_id=actor_id,
            )
        except ProvisioningError as exc:
            if "v4_external_identities" not in str(exc):
                raise
            print(f"  {username}: логин уже занят, пропускаю (учётка не тронута)")
            continue
        created.append({"username": username, "password": password, "role": role,
                        "account_id": int(account["id"]), "display_name": display_name})
    return created


def write_credentials(path: Path, people: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["username", "password", "role", "account_id", "display_name"])
        writer.writeheader()
        writer.writerows(people)
    os.chmod(path, 0o600)


def read_existing_credentials(path: Path) -> list[dict]:
    """Ростер из прошлого запуска: если все логины уже заняты, provision_people
    ничего не вернёт и играть будет некому -- подхватываем, кто уже заведён,
    вместо того чтобы остановиться и затереть файл с настоящими паролями."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [
            {"username": row["username"], "password": row["password"], "role": row["role"],
             "account_id": int(row["account_id"]), "display_name": row["display_name"]}
            for row in csv.DictReader(handle)
        ]


# --- играем: реальные HTTP-запросы на локальный API, как настоящий телефон ---

class _LocalCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Боевой ZHIDAO_V4_COOKIE_SECURE=1 ставит на сессионную и CSRF-куку флаг
    Secure. Это правильно для публичного адреса и трогать эту переменную
    нельзя, но локальный смок-порт 127.0.0.1:8770 обслуживается без TLS —
    стандартная политика http.cookiejar тогда молча перестаёт пересылать куку
    после логина, и каждый следующий запрос падает 401. Разрешаем это только
    для локального цикла этого скрипта."""

    def return_ok_secure(self, cookie, request):
        return True


class Session:
    """Одна учётка — одна кука-сессия, как в браузере."""

    def __init__(self, base: str = API_BASE):
        self.jar = http.cookiejar.CookieJar(policy=_LocalCookiePolicy())
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.base = base

    def _cookie(self, name: str) -> str | None:
        for cookie in self.jar:
            if cookie.name == name:
                return urllib.parse.unquote(cookie.value)
        return None

    def call(self, method: str, path: str, body=None, expect=(200,)):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if method == "POST":
            token = self._cookie("zhidao_v4_csrf")
            if token:
                request.add_header("X-CSRF-Token", token)
            request.add_header("X-Idempotency-Key", secrets.token_hex(16))
        try:
            with self.opener.open(request, timeout=10) as response:
                status = response.status
                payload = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                payload = json.loads(exc.read() or b"{}")
            except json.JSONDecodeError:
                payload = {}
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, 0, {"detail": str(exc)}
        return status in expect, status, payload

    def login(self, username: str, password: str) -> bool:
        ok, _, _ = self.call("POST", "/api/v4/auth/login", {"username": username, "password": password})
        return ok


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, bool, int]] = []

    def add(self, who: str, action: str, ok: bool, status: int) -> None:
        self.rows.append((who, action, ok, status))

    def summary(self) -> str:
        total = len(self.rows)
        failed = [row for row in self.rows if not row[2]]
        lines = [f"Действий выполнено: {total}, из них неудачных: {len(failed)}"]
        for who, action, ok, status in failed[:30]:
            lines.append(f"  ОШИБКА {who}: {action} -> {status}")
        if len(failed) > 30:
            lines.append(f"  … и ещё {len(failed) - 30}")
        return "\n".join(lines)


def operator_setup(operators: list[dict], kid_ids: list[int], season_id: int, report: Report, api_base: str) -> None:
    """Один вожатый в начале дня выдаёт всем попытки — как это делают в жизни."""
    if not operators or not kid_ids:
        return
    operator = operators[0]
    session = Session(api_base)
    ok = session.login(operator["username"], operator["password"])
    report.add(operator["username"], "login", ok, 200 if ok else 0)
    if not ok:
        return
    ok, status, _ = session.call(
        "POST", f"/api/v4/seasons/{season_id}/cases/admin/grants",
        {"account_ids": kid_ids, "amount": KID_ATTEMPTS, "reason": "репетиция: попытки на разминку"},
        expect=(200,),
    )
    report.add(operator["username"], "cases.admin.grants", ok, status)

    # Заодно проверим сегодняшнюю ручную поправку ★/REP на паре участников.
    for kid_id in kid_ids[:2]:
        ok, status, _ = session.call(
            "POST", f"/api/v4/seasons/{season_id}/economy/grant",
            {"account_id": kid_id, "stars_delta": 10, "rep_delta": 5, "reason": "репетиция: бодрое утро"},
            expect=(200,),
        )
        report.add(operator["username"], f"economy.grant→{kid_id}", ok, status)


def play_kid(person: dict, season_id: int, report: Report, api_base: str) -> None:
    session = Session(api_base)
    ok = session.login(person["username"], person["password"])
    report.add(person["username"], "login", ok, 200 if ok else 0)
    if not ok:
        return
    ok, status, _ = session.call("GET", f"/api/v4/seasons/{season_id}/cases/state", expect=(200,))
    report.add(person["username"], "cases.state", ok, status)
    for _ in range(KID_ATTEMPTS):
        ok, status, _ = session.call(
            "POST", f"/api/v4/seasons/{season_id}/cases/open", {}, expect=(200, 409),
        )
        report.add(person["username"], "cases.open", ok, status)
    ok, status, _ = session.call("GET", f"/api/v4/seasons/{season_id}/shop", expect=(200,))
    report.add(person["username"], "shop", ok, status)
    ok, status, _ = session.call("GET", f"/api/v4/seasons/{season_id}/rep/board", expect=(200,))
    report.add(person["username"], "rep.board", ok, status)
    ok, status, _ = session.call("GET", f"/api/v4/seasons/{season_id}/diary/mine", expect=(200,))
    report.add(person["username"], "diary.mine", ok, status)


def play_spy_table(players: list[dict], report: Report, api_base: str) -> None:
    """Небольшая группа садится за Шпиона: комната создана и заполнена — партию
    саму репетиция не разыгрывает, это уже интерактив за столом."""
    if len(players) < 3:
        return
    host, guests = players[0], players[1:]
    session = Session(api_base)
    if not session.login(host["username"], host["password"]):
        report.add(host["username"], "spy.login", False, 0)
        return
    ok, status, body = session.call("POST", "/api/v4/games/rooms", {"game": "spy"}, expect=(200,))
    report.add(host["username"], "games.rooms.create", ok, status)
    if not ok:
        return
    code = body.get("room", {}).get("code")
    for guest in guests:
        guest_session = Session(api_base)
        if not guest_session.login(guest["username"], guest["password"]):
            report.add(guest["username"], "spy.login", False, 0)
            continue
        ok, status, _ = guest_session.call("POST", "/api/v4/games/rooms/join", {"code": code}, expect=(200,))
        report.add(guest["username"], "games.rooms.join", ok, status)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, help="Путь к боевой SQLite базе")
    parser.add_argument("--season", required=True, help="Код сезона-репетиции (не hainan-v4)")
    parser.add_argument("--kids", type=int, default=60)
    parser.add_argument("--operators", type=int, default=6)
    parser.add_argument("--concurrency", type=int, default=4, help="Сколько участников играют одновременно")
    parser.add_argument("--credentials-out", default="rehearsal-credentials.csv")
    parser.add_argument("--api-base", default=API_BASE, help="Локальный API (127.0.0.1, не публичный адрес)")
    parser.add_argument("--apply", action="store_true", help="Без этого — только план, без записи и без сети")
    args = parser.parse_args()

    if args.season in FORBIDDEN_SEASON_CODES:
        raise SystemExit(f"Отказ: {args.season!r} — боевой сезон, не полигон для репетиции.")

    api_base = args.api_base

    conn = connect_database(args.db)
    try:
        with immediate_transaction(conn):
            actor_id = find_system_admin(conn)
            season = find_season(conn, args.season)
            if season is None:
                raise SystemExit(f"Сезона с кодом {args.season!r} нет. Создайте его сначала в админке.")
            print(f"Сезон #{season['id']} «{season['name']}», статус {season['status']}.")
            print(f"План: {args.kids} участников (kid1..kid{args.kids}), "
                  f"{args.operators} вожатых (op1..op{args.operators}).")
            if not args.apply:
                print("Это был просмотр плана (--apply не передан). Ничего не создано и не отправлено.")
                return 0

            report_path = Path(args.credentials_out)
            roster_by_name = {p["username"]: p for p in read_existing_credentials(report_path)}
            new_people = provision_people(conn, actor_id, args.kids, args.operators)
            for person in new_people:
                roster_by_name[person["username"]] = person
            people = list(roster_by_name.values())
            kids = [p for p in people if p["role"] == "participant"]
            operators = [p for p in people if p["role"] == "operator"]
            print(f"Заведено новых: {len(new_people)}. Всего в ростере: "
                  f"{len(kids)} участников, {len(operators)} вожатых.")

            write_credentials(report_path, people)
            print(f"Логины и пароли — {report_path.resolve()} (права 600, это настоящие рабочие пароли).")

            roster = season_roster.configure(
                conn, season_code=args.season, actor_id=actor_id,
                account_ids=[p["account_id"] for p in kids], activate=True, apply=True,
            )
            print(f"Включено в сезон и переведено в active: {len(roster['accounts'])} участников.")
            season = find_season(conn, args.season)
    finally:
        conn.close()

    if not kids:
        print("Некого пускать играть — все учётки уже существовали. Остановился на этом.")
        return 0

    report = Report()

    print(f"\nИграем через {api_base} (локальный порт, не публичный адрес)…")
    operator_setup(operators, [p["account_id"] for p in kids], season["id"], report, api_base)

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(play_kid, kid, season["id"], report, api_base) for kid in kids]
        for future in as_completed(futures):
            future.result()

    for start in range(0, len(kids), 4):
        table = kids[start:start + 4]
        if len(table) >= 3:
            play_spy_table(table, report, api_base)
        if (start // 4) + 1 >= ROOM_PAIRS:
            break

    print("\n" + report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
