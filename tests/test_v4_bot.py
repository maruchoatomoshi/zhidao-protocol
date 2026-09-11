from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.bootstrap import bootstrap_system_admin
from zhidao_v4.bot.backend import V4Backend
from zhidao_v4.bot.commands import Bot, parse_update, split_command
from zhidao_v4.bot.max_api import MaxApiError, MaxBotApi
from zhidao_v4.db import connect_database, immediate_transaction


ADMIN_USERNAME = "architect"
ADMIN_PASSWORD = "correct horse battery staple"
BOT_USERNAME = "bot.service"
BOT_PASSWORD = "bot service secure passphrase"

OPERATOR_MAX_ID = 500500
PARTICIPANT_MAX_ID = 770077


def message_update(text: str, *, user_id: int, chat_type: str = "dialog",
                   mid: str = "mid.1") -> dict:
    """Событие MAX той формы, что описана в его схеме Bot API."""
    return {
        "update_type": "message_created",
        "timestamp": 1788800000000,
        "message": {
            "sender": {
                "user_id": user_id,
                "first_name": "Вожатый",
                "last_name": None,
                "username": None,
                "is_bot": False,
                "last_activity_time": 1788800000000,
            },
            "recipient": {"chat_id": 900 + user_id, "chat_type": chat_type, "user_id": user_id},
            "timestamp": 1788800000000,
            "body": {"mid": mid, "seq": 1, "text": text, "attachments": None},
        },
    }


class UpdateParsingTests(unittest.TestCase):
    def test_message_is_read_from_the_documented_nesting(self):
        incoming = parse_update(message_update("/help", user_id=42))
        assert incoming is not None
        self.assertEqual(incoming.user_id, 42)
        self.assertEqual(incoming.text, "/help")
        self.assertTrue(incoming.is_dialog)
        self.assertEqual(incoming.first_name, "Вожатый")

    def test_bot_started_is_treated_as_start(self):
        incoming = parse_update(
            {
                "update_type": "bot_started",
                "timestamp": 1788800000000,
                "chat_id": 777,
                "user": {
                    "user_id": 42,
                    "first_name": "Ася",
                    "last_name": None,
                    "username": None,
                    "is_bot": False,
                    "last_activity_time": 1,
                },
            }
        )
        assert incoming is not None
        self.assertEqual(incoming.text, "/start")
        self.assertEqual(incoming.first_name, "Ася")

    def test_messages_from_bots_are_ignored(self):
        update = message_update("/help", user_id=42)
        update["message"]["sender"]["is_bot"] = True
        self.assertIsNone(parse_update(update))

    def test_unknown_update_types_are_ignored(self):
        self.assertIsNone(parse_update({"update_type": "dialog_muted", "timestamp": 1}))

    def test_command_parsing_strips_the_bot_mention(self):
        # В групповом чате MAX дописывает к команде имя бота.
        self.assertEqual(split_command("/код@zhidao_bot Иванов"), ("код", "Иванов"))
        self.assertEqual(split_command("/help"), ("help", ""))
        self.assertEqual(split_command("  /Код  Иванов  "), ("код", "Иванов"))
        self.assertIsNone(split_command("просто текст"))


class FakeMaxApi:
    """Записывает отправленное вместо похода в сеть."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send_message(self, *, user_id=None, chat_id=None, text, buttons=None, notify=True):
        self.sent.append(
            {"user_id": user_id, "chat_id": chat_id, "text": text, "buttons": buttons}
        )
        return {}

    @property
    def last_text(self) -> str:
        return self.sent[-1]["text"]


class BotCommandTests(unittest.TestCase):
    """Бот поверх настоящего API V4 — фальшивый только мессенджер.

    Смысл именно в этом: команда `/код` должна пройти по-настоящему через
    проверку роли, CSRF и журнал, иначе тест доказывал бы только то, что
    подделка отвечает так, как её научили.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        self.bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Architect",
        )
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                provision_local_account(
                    conn,
                    username=BOT_USERNAME,
                    password=BOT_PASSWORD,
                    display_name="Служебная учётка бота",
                    role_code="operator",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
                self.participant = provision_local_account(
                    conn,
                    username="kid1",
                    password="participant secure passphrase",
                    display_name="Иванов Пётр",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
                self.namesake = provision_local_account(
                    conn,
                    username="kid2",
                    password="another secure passphrase",
                    display_name="Иванова Мария",
                    role_code="participant",
                    actor_account_id=self.bootstrap["account"]["id"],
                )
        finally:
            conn.close()

        app = create_app(self.db_path, cookie_secure=False, session_hours=1)
        self.client = TestClient(app)
        # Клиент бота ходит в приложение через настоящий стек httpx: те же
        # заголовки, те же куки, тот же разбор ответа — только без сокета.
        # Отдельный TestClient, а не общий с тестом: у бота своя сессия и
        # свой CSRF, и путать их с чужими не стоит.
        self.bot_client = TestClient(app)
        self.backend = V4Backend(
            "http://testserver",
            username=BOT_USERNAME,
            password=BOT_PASSWORD,
            client=self.bot_client,
        )
        self.backend.login()
        self.max = FakeMaxApi()
        self.bot = Bot(
            self.max,
            self.backend,
            operator_ids=frozenset({OPERATOR_MAX_ID}),
            web_app_name="zhidao_bot",
        )

    def tearDown(self):
        self.backend.close()
        self.client.close()
        self.temp_dir.cleanup()

    def send(self, text: str, *, user_id: int = OPERATOR_MAX_ID, chat_type: str = "dialog",
             mid: str = "mid.1"):
        incoming = parse_update(
            message_update(text, user_id=user_id, chat_type=chat_type, mid=mid)
        )
        assert incoming is not None
        self.bot.handle(incoming)
        return self.max.sent[-1] if self.max.sent else None

    # --- всем ------------------------------------------------------------

    def test_start_offers_the_mini_app(self):
        sent = self.send("/start", user_id=PARTICIPANT_MAX_ID)
        self.assertIn("ZHIDAO", sent["text"])
        self.assertEqual(sent["buttons"][0][0]["type"], "open_app")
        self.assertEqual(sent["buttons"][0][0]["web_app"], "zhidao_bot")

    def test_myid_reports_the_max_identifier(self):
        sent = self.send("/myid", user_id=PARTICIPANT_MAX_ID)
        self.assertIn(str(PARTICIPANT_MAX_ID), sent["text"])

    def test_help_hides_operator_commands_from_participants(self):
        participant = self.send("/help", user_id=PARTICIPANT_MAX_ID)
        self.assertNotIn("/код", participant["text"])
        operator = self.send("/help", user_id=OPERATOR_MAX_ID)
        self.assertIn("/код", operator["text"])

    def test_season_one_commands_answer_with_what_is_missing(self):
        # Вожатый из Пекина наберёт /баллы. Ответ должен объяснять, а не
        # притворяться, что такой команды никогда не было.
        sent = self.send("/баллы", user_id=PARTICIPANT_MAX_ID)
        self.assertIn("экономики сезона", sent["text"])
        self.assertNotIn("Не знаю команды", sent["text"])

    def test_bot_stays_silent_on_plain_text_in_a_group_chat(self):
        before = len(self.max.sent)
        incoming = parse_update(
            message_update("просто болтовня", user_id=OPERATOR_MAX_ID, chat_type="chat")
        )
        assert incoming is not None
        self.bot.handle(incoming)
        self.assertEqual(len(self.max.sent), before)

    def test_group_chat_replies_go_to_the_chat_not_the_author(self):
        sent = self.send("/help", user_id=OPERATOR_MAX_ID, chat_type="chat")
        self.assertIsNone(sent["user_id"])
        self.assertEqual(sent["chat_id"], 900 + OPERATOR_MAX_ID)

    # --- вожатому --------------------------------------------------------

    def test_participants_cannot_issue_pairing_codes(self):
        sent = self.send("/код Иванов Пётр", user_id=PARTICIPANT_MAX_ID)
        self.assertIn("для вожатых", sent["text"])
        # И самое важное: код не выдан.
        self.assertNotRegex(sent["text"], r"\d{8}")

    def test_roster_search_shows_who_is_linked(self):
        sent = self.send("/кто Иванов")
        self.assertIn("Иванов Пётр", sent["text"])
        self.assertIn("Иванова Мария", sent["text"])
        self.assertIn("MAX не привязан", sent["text"])

    def test_who_without_a_name_lists_the_roster(self):
        # Ровно тот случай, ради которого это и сделано: вожатый не знает,
        # что в базе есть, и «кого искать?» ему не помогает.
        sent = self.send("/кто")
        self.assertIn("Кто есть в ростере", sent["text"])
        self.assertIn("Иванов Пётр", sent["text"])
        self.assertIn("Служебная учётка бота", sent["text"])

    def test_a_search_that_finds_nothing_explains_why(self):
        # Настоящий случай с сервера: искали «Архитектор», а учётка звалась
        # «Architect». Ответ должен подсказывать выход, а не только отказ.
        sent = self.send("/кто Архитектор")
        self.assertIn("никого нет", sent["text"])
        self.assertIn("/кто без слова", sent["text"])

    def test_ambiguous_name_is_not_guessed(self):
        sent = self.send("/код Иванов")
        self.assertIn("уточните", sent["text"])
        self.assertNotRegex(sent["text"], r"\b\d{8}\b")

    def test_code_is_issued_by_exact_name_and_by_number(self):
        by_name = self.send("/код Иванов Пётр")
        self.assertRegex(by_name["text"], r"\b\d{8}\b")

        account_id = int(self.participant["id"])
        by_number = self.send(f"/код {account_id}")
        self.assertRegex(by_number["text"], r"\b\d{8}\b")

        # Второй код подряд — тот самый случай, который до миграции 0005
        # падал. Здесь он проходит через весь HTTP-путь.
        self.assertNotEqual(by_name["text"], by_number["text"])

    def test_code_for_a_missing_account_says_so(self):
        sent = self.send("/код 9999")
        self.assertIn("нет или он отключён", sent["text"])

    # --- сезон, шансы, выдача --------------------------------------------

    def open_season(self):
        """Запускает сезон и вводит в него участника — как это сделает Архитектор."""
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                conn.execute("UPDATE v4_seasons SET status='active' WHERE id=1")
                conn.execute(
                    "INSERT INTO v4_season_memberships(season_id, account_id, status)"
                    " VALUES (1, ?, 'active')",
                    (self.participant["id"],),
                )
        finally:
            conn.close()

    def scans(self) -> int:
        conn = connect_database(self.db_path)
        try:
            row = conn.execute(
                "SELECT scans FROM v4_case_wallets WHERE season_id=1 AND account_id=?",
                (self.participant["id"],),
            ).fetchone()
        finally:
            conn.close()
        return int(row["scans"]) if row else 0

    def test_season_says_plainly_that_a_draft_has_not_started(self):
        # Чаще всего человек пишет /сезон именно потому, что ничего не
        # работает. Ответ должен объяснять, а не сообщать слово «draft».
        sent = self.send("/сезон", user_id=PARTICIPANT_MAX_ID)
        self.assertIn("draft", sent["text"])
        self.assertIn("ещё не запущен", sent["text"])

    def test_chances_are_computed_from_the_weights_the_server_serves(self):
        sent = self.send("/шансы", user_id=PARTICIPANT_MAX_ID)
        text = sent["text"]
        self.assertIn("%", text)
        # Шанс за попытку и шанс внутри кейса — разные числа, и путать их
        # нечестно: об этом же говорит таблица в приложении.
        self.assertIn("за попытку", text)

    def test_grant_refuses_while_no_season_is_active(self):
        sent = self.send("/выдать 3 2 участие во встрече")
        self.assertIn("Активного сезона нет", sent["text"])
        self.assertEqual(self.scans(), 0)

    def test_grant_checks_its_arguments_before_touching_the_server(self):
        self.assertIn("Формат", self.send("/выдать")["text"])
        self.assertIn("Формат", self.send("/выдать 3 2")["text"])
        self.assertIn("от 1 до 7", self.send("/выдать 3 9 причина")["text"])
        self.assertEqual(self.scans(), 0)

    def test_participants_cannot_grant_or_read_the_season_roster(self):
        for command in ("/выдать 3 1 просто так", "/ростер"):
            sent = self.send(command, user_id=PARTICIPANT_MAX_ID)
            self.assertNotIn("Выдано", sent["text"])
            self.assertNotIn("Состав", sent["text"])
        self.assertEqual(self.scans(), 0)

    def test_grant_gives_attempts_and_the_same_message_never_gives_twice(self):
        # Длинный опрос перечитывает обновления после перезапуска — это не
        # теоретический случай. Ключ идемпотентности берётся из mid, поэтому
        # то же сообщение обязано вернуть тот же результат, а не вторую порцию.
        self.open_season()
        first = self.send("/выдать Иванов Пётр 2 встреча", mid="mid.grant")
        self.assertIn("Выдано", first["text"])
        self.assertEqual(self.scans(), 2)

        again = self.send("/выдать Иванов Пётр 2 встреча", mid="mid.grant")
        self.assertIn("Выдано", again["text"])
        self.assertEqual(self.scans(), 2)

        # Другое сообщение — другое намерение, и оно выдаёт по-настоящему.
        self.send("/выдать Иванов Пётр 1 ещё одна встреча", mid="mid.grant.2")
        self.assertEqual(self.scans(), 3)

    def test_grant_says_who_got_it_and_names_the_reason(self):
        self.open_season()
        sent = self.send("/выдать Пётр 3 дневник", mid="mid.grant.3")
        self.assertIn("дневник", sent["text"])
        self.assertIn("Иванов Пётр", sent["text"])
        self.assertIn("3/7", sent["text"])

    def test_roster_shows_who_is_in_the_season_and_what_is_left(self):
        self.open_season()
        sent = self.send("/ростер")
        self.assertIn("Иванов Пётр", sent["text"])
        self.assertIn("0/7", sent["text"])
        # Мария в сезон не введена — её здесь быть не должно.
        self.assertNotIn("Иванова Мария", sent["text"])

    def test_status_reports_the_live_schema_version(self):
        sent = self.send("/статус")
        self.assertIn("ok", sent["text"])
        self.assertIn("версия 11", sent["text"])


class SecureCookieBackendTests(unittest.TestCase):
    """Бот обязан работать при `ZHIDAO_V4_COOKIE_SECURE=1` поверх http.

    Именно так стоит боевой сервер: кука сессии помечена `Secure`, а бот
    ходит в API на `http://127.0.0.1:8770`. Банка кук httpx такую куку
    принимает, но по обычному HTTP не отдаёт — логин отвечал 200, а
    следующий запрос 401, и клиент уходил в бесконечный перелогин. Тест
    ставит ровно эту конфигурацию: TestClient работает по http, а
    приложение создано с `cookie_secure=True`.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "zhidao.db"
        bootstrap = bootstrap_system_admin(
            self.db_path,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
            display_name="Architect",
        )
        conn = connect_database(self.db_path)
        try:
            with immediate_transaction(conn):
                provision_local_account(
                    conn,
                    username=BOT_USERNAME,
                    password=BOT_PASSWORD,
                    display_name="Служебная учётка бота",
                    role_code="operator",
                    actor_account_id=bootstrap["account"]["id"],
                )
        finally:
            conn.close()
        self.app = create_app(self.db_path, cookie_secure=True, session_hours=1)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def test_session_survives_a_secure_cookie_over_plain_http(self):
        backend = V4Backend(
            "http://testserver",
            username=BOT_USERNAME,
            password=BOT_PASSWORD,
            client=self.client,
        )
        backend.login()

        # Кука действительно помечена Secure — иначе тест ничего не проверяет.
        stored = self.client.cookies.jar
        session_cookie = next(c for c in stored if c.name == "zhidao_v4_session")
        self.assertTrue(session_cookie.secure)

        who = backend.whoami()
        self.assertEqual(who["account"]["display_name"], "Служебная учётка бота")

        # И запись тоже: там ещё и CSRF, который сверяется с кукой.
        roster = backend.find_accounts("Служебная")
        self.assertEqual(len(roster), 1)
        issued = backend.issue_link_code(int(roster[0]["id"]))
        self.assertRegex(issued["code"], r"^\d{8}$")


class MaxApiClientTests(unittest.TestCase):
    def test_token_goes_in_the_authorization_header(self):
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"user_id": 1, "name": "ZHIDAO"})

        api = MaxBotApi(
            "secret-token",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        api.get_me()
        # Голый токен, без Bearer, и не в строке запроса: официальный
        # клиент MAX делает именно так, а query-параметр больше не работает.
        self.assertEqual(seen["auth"], "secret-token")
        self.assertNotIn("secret-token", str(seen["url"]))

    def test_marker_is_omitted_rather_than_sent_as_null(self):
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"updates": [], "marker": 17})

        api = MaxBotApi(
            "t", client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        _, marker = api.get_updates(marker=None)
        self.assertNotIn("marker", seen[0])
        self.assertEqual(marker, 17)

        api.get_updates(marker=marker)
        self.assertIn("marker=17", seen[1])

    def test_api_errors_carry_the_status_code(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="invalid token")

        api = MaxBotApi(
            "t", client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with self.assertRaises(MaxApiError) as caught:
            api.get_me()
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
