"""Словарь команд бота и разбор событий MAX.

Что здесь есть и чего намеренно нет
-----------------------------------

Словарь взят у бота сезона 1 (`zhidao_bot_ready.py`): те же имена, те же
русские синонимы, тот же тон. Но сезон 1 писал в свою базу напрямую, а
здесь каждая команда обязана опираться на существующий эндпоинт API V4.
Систем начисления баллов, переклички, наград и магазина в V4 пока нет —
значит, и команд, которые ими управляют, тоже нет.

Молчать об этом было бы неверно: вожатый, работавший в Пекине, наберёт
`/баллы` и должен получить внятный ответ, а не «неизвестная команда».
Поэтому команды сезона 1 перечислены в `PENDING_COMMANDS` и отвечают тем,
чего именно ещё нет. Как появится система — команда переезжает из этого
списка в рабочие обработчики.

Права
-----

Выдавать коды сопряжения может только оператор. Список операторов — это
идентификаторы MAX в переменной окружения, а не роль из базы, и вот
почему: чтобы роль читалась из базы, MAX-аккаунт оператора должен быть уже
привязан, а привязка требует кода, который выдаёт оператор. Замкнутый
круг; список в окружении — это его размыкание. Операторов пять-шесть, так
что цена невелика. Когда первый оператор привязан, список можно будет
заменить проверкой роли — но не раньше.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from .backend import BackendError, V4Backend
from .max_api import MaxBotApi, open_app_button


LOG = logging.getLogger("zhidao.bot.commands")

UPDATE_TYPES = ("message_created", "bot_started")


@dataclass(frozen=True)
class Incoming:
    """Разобранное событие: кто написал, что и куда отвечать."""

    user_id: int
    chat_id: int | None
    is_dialog: bool
    text: str
    first_name: str
    update_type: str


def parse_update(update: dict) -> Incoming | None:
    """Разбирает Update из MAX. Формы полей — из схемы Bot API MAX."""
    kind = update.get("update_type")

    if kind == "bot_started":
        user = update.get("user") or {}
        user_id = user.get("user_id")
        if user_id is None:
            return None
        return Incoming(
            user_id=int(user_id),
            chat_id=update.get("chat_id"),
            is_dialog=True,
            # Кнопка «Начать» — это то же самое, что команда /start, и
            # обрабатывать её отдельной веткой незачем.
            text="/start",
            first_name=str(user.get("first_name") or "").strip(),
            update_type=kind,
        )

    if kind == "message_created":
        message = update.get("message") or {}
        sender = message.get("sender") or {}
        recipient = message.get("recipient") or {}
        body = message.get("body") or {}
        user_id = sender.get("user_id")
        if user_id is None or sender.get("is_bot"):
            return None
        chat_type = recipient.get("chat_type")
        return Incoming(
            user_id=int(user_id),
            chat_id=recipient.get("chat_id"),
            is_dialog=(chat_type == "dialog"),
            text=str(body.get("text") or "").strip(),
            first_name=str(sender.get("first_name") or "").strip(),
            update_type=kind,
        )

    return None


# Команда — первое слово, с косой чертой; в групповом чате MAX дописывает
# к ней имя бота через @, его надо отбросить.
COMMAND_RE = re.compile(r"^/([^\s@]+)(?:@\S+)?(?:\s+(.*))?$", re.DOTALL)


def split_command(text: str) -> tuple[str, str] | None:
    match = COMMAND_RE.match(text.strip())
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "").strip()


# Команды сезона 1, у которых в V4 пока нет системы. Значение — чего именно
# не хватает; человек должен понимать, ждать ему или звать Архитектора.
PENDING_COMMANDS: dict[str, str] = {
    "баллы": "экономики сезона (★ и REP) в V4 ещё нет",
    "points": "экономики сезона (★ и REP) в V4 ещё нет",
    "рейтинг": "рейтинга REP в V4 ещё нет",
    "leaderboard": "рейтинга REP в V4 ещё нет",
    "перекличка": "переклички в V4 ещё нет",
    "подъем": "утренней переклички в V4 ещё нет",
    "presence": "переклички в V4 ещё нет",
    "разбудить": "переклички в V4 ещё нет",
    "проснулся": "переклички в V4 ещё нет",
    "award": "начислений в V4 ещё нет",
    "penalize": "штрафов в V4 ещё нет",
    "зп": "выплат в V4 ещё нет",
    "подарить": "переводов между участниками в V4 ещё нет",
    "broadcast": "рассылки в V4 ещё нет",
    "рассылка": "рассылки в V4 ещё нет",
    "погода": "погоды в V4 ещё нет",
    "weather": "погоды в V4 ещё нет",
    "bug": "приёма сообщений об ошибках в V4 ещё нет",
    "ошибка": "приёма сообщений об ошибках в V4 ещё нет",
    "вопрос": "анонимных вопросов в V4 ещё нет",
    "напоминания": "напоминаний в V4 ещё нет",
}

# То, что показывается в меню бота в MAX.
MENU_COMMANDS: list[tuple[str, str]] = [
    ("start", "Начать и открыть приложение"),
    ("app", "Открыть приложение"),
    ("help", "Что умеет бот"),
    ("myid", "Показать мой идентификатор MAX"),
]


class Bot:
    def __init__(
        self,
        api: MaxBotApi,
        backend: V4Backend,
        *,
        operator_ids: frozenset[int] = frozenset(),
        web_app_name: str = "",
        app_url: str = "",
    ) -> None:
        self.api = api
        self.backend = backend
        self.operator_ids = operator_ids
        self.web_app_name = web_app_name
        self.app_url = app_url

    # --- отправка ---------------------------------------------------------

    def reply(self, incoming: Incoming, text: str, *, with_app_button: bool = False) -> None:
        buttons = None
        # Кнопку мини-аппа рисуем, только если бот знает своё публичное имя:
        # без него поле web_app обязательное и запрос отвалится.
        if with_app_button and self.web_app_name:
            buttons = [[open_app_button("Открыть ZHIDAO", self.web_app_name)]]
        # В диалоге отвечаем пользователю, в групповом чате — в чат, иначе
        # ответ уедет в личку и в чате повиснет тишина.
        if incoming.is_dialog or incoming.chat_id is None:
            self.api.send_message(user_id=incoming.user_id, text=text, buttons=buttons)
        else:
            self.api.send_message(chat_id=incoming.chat_id, text=text, buttons=buttons)

    def is_operator(self, user_id: int) -> bool:
        return user_id in self.operator_ids

    # --- обработка --------------------------------------------------------

    def handle(self, incoming: Incoming) -> None:
        parsed = split_command(incoming.text)
        if parsed is None:
            # Обычная реплика, а не команда. В групповом чате бот молчит:
            # иначе он будет отвечать на каждое сообщение подряд.
            if incoming.is_dialog:
                self.reply(
                    incoming,
                    "Я понимаю только команды. Наберите /help — покажу, что умею.",
                )
            return

        name, argument = parsed
        handler = self.HANDLERS.get(name)
        if handler is not None:
            handler(self, incoming, argument)
            return

        pending = PENDING_COMMANDS.get(name)
        if pending is not None:
            self.reply(
                incoming,
                f"Команда /{name} была в пекинском сезоне, но здесь пока не работает: "
                f"{pending}.\n\nКак система появится — команда включится, "
                f"и отдельно об этом сообщать не придётся.",
            )
            return

        self.reply(incoming, f"Не знаю команды /{name}. Наберите /help.")

    # --- команды, доступные всем ------------------------------------------

    def cmd_start(self, incoming: Incoming, argument: str) -> None:
        del argument
        greeting = f"Здравствуйте, {incoming.first_name}!" if incoming.first_name else "Здравствуйте!"
        self.reply(
            incoming,
            f"{greeting}\n\n"
            "Это ZHIDAO — система поездки. Расписание, задания, рейтинг и карта "
            "кампуса живут в приложении, а я нужен для мелочей рядом с ним.\n\n"
            "Чтобы войти, откройте приложение. Если оно попросит код сопряжения — "
            "его выдаёт вожатый: код из восьми цифр, живёт тридцать минут.\n\n"
            "/help — что я умею.",
            with_app_button=True,
        )

    def cmd_help(self, incoming: Incoming, argument: str) -> None:
        del argument
        lines = [
            "Что я умею:",
            "",
            "/app — открыть приложение",
            "/myid — показать ваш идентификатор MAX",
            "/help — этот список",
        ]
        if self.is_operator(incoming.user_id):
            lines += [
                "",
                "Для вожатых:",
                "/кто — весь ростер; /кто <имя> — поиск",
                "/код <имя или номер> — выдать код сопряжения",
                "/статус — состояние сервера",
            ]
        lines += [
            "",
            "Команды пекинского сезона (/баллы, /перекличка, /award и другие) "
            "я помню, но включу их, когда в V4 появятся сами системы.",
        ]
        self.reply(incoming, "\n".join(lines))

    def cmd_app(self, incoming: Incoming, argument: str) -> None:
        del argument
        text = "Приложение ZHIDAO:"
        if not self.web_app_name and self.app_url:
            # Запасной путь, пока публичное имя бота не прописано в
            # окружении: ссылкой, без кнопки мини-аппа.
            text = f"Приложение ZHIDAO: {self.app_url}"
        self.reply(incoming, text, with_app_button=True)

    def cmd_myid(self, incoming: Incoming, argument: str) -> None:
        del argument
        self.reply(
            incoming,
            f"Ваш идентификатор MAX: {incoming.user_id}\n\n"
            "Он нужен вожатому, если что-то пошло не так со входом. "
            "Это не код сопряжения — код выдаёт вожатый.",
        )

    # --- команды вожатого -------------------------------------------------

    def _require_operator(self, incoming: Incoming) -> bool:
        if self.is_operator(incoming.user_id):
            return True
        # Не «нет прав», а «это команда вожатых»: участник не сделал ничего
        # плохого, просто набрал не своё.
        self.reply(incoming, "Эта команда для вожатых.")
        return False

    # Сколько строк ростера показывать без запроса. Группа — около шестидесяти
    # человек, и вываливать всех в чат бессмысленно; но и переспрашивать «кого
    # искать», когда человек ещё не знает, что в базе вообще есть, — тоже.
    ROSTER_PREVIEW = 25

    def cmd_who(self, incoming: Incoming, argument: str) -> None:
        if not self._require_operator(incoming):
            return
        limit = 10 if argument else self.ROSTER_PREVIEW
        try:
            items = self.backend.find_accounts(argument, limit=limit)
        except BackendError as exc:
            LOG.warning("roster lookup failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
            return
        if not items:
            if argument:
                self.reply(
                    incoming,
                    f"По запросу «{argument}» никого нет.\n\n"
                    "Имя ищется по куску подряд и с учётом языка: «Ivan» не найдёт "
                    "«Иванова». Наберите /кто без слова — покажу, кто вообще есть.",
                )
            else:
                self.reply(incoming, "В ростере пока никого нет.")
            return
        head = f"Нашлось: {len(items)}" if argument else "Кто есть в ростере:"
        lines = [head, ""]
        for item in items:
            mark = "MAX привязан" if item["max_linked"] else "MAX не привязан"
            status = "" if item["status"] == "active" else f", {item['status']}"
            lines.append(f"#{item['id']} · {item['display_name']} — {mark}{status}")
        if not argument and len(items) == self.ROSTER_PREVIEW:
            # Ровно предел — почти наверняка список обрезан, и молчать об этом
            # нельзя: вожатый решит, что кого-то в базе нет.
            lines += ["", f"Показаны первые {self.ROSTER_PREVIEW}. Уточните: /кто <имя>"]
        self.reply(incoming, "\n".join(lines))

    def cmd_code(self, incoming: Incoming, argument: str) -> None:
        if not self._require_operator(incoming):
            return
        if not argument:
            self.reply(incoming, "Кому выдать код? Например: /код Иванов или /код 17")
            return

        account_id: int | None = None
        if argument.isdigit():
            account_id = int(argument)
        else:
            try:
                items = self.backend.find_accounts(argument, limit=10)
            except BackendError as exc:
                LOG.warning("roster lookup failed: %s", exc)
                self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
                return
            if not items:
                self.reply(incoming, f"По запросу «{argument}» никого нет.")
                return
            if len(items) > 1:
                # Не угадываем: выдать код не тому — значит отдать чужой
                # аккаунт постороннему.
                lines = ["Подходит несколько человек, уточните номером:", ""]
                lines += [f"#{i['id']} · {i['display_name']}" for i in items]
                self.reply(incoming, "\n".join(lines))
                return
            account_id = int(items[0]["id"])

        try:
            issued = self.backend.issue_link_code(account_id)
        except BackendError as exc:
            if exc.status_code == 404:
                self.reply(incoming, f"Аккаунта #{account_id} нет или он отключён.")
                return
            LOG.warning("link code issue failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Код не выдан.")
            return

        self.reply(
            incoming,
            f"Код для #{account_id}: {issued['code']}\n\n"
            f"Действует {issued.get('ttl_minutes', 30)} минут и только один раз. "
            "Если выдать новый — этот перестанет работать.",
        )

    def cmd_status(self, incoming: Incoming, argument: str) -> None:
        if not self._require_operator(incoming):
            return
        del argument
        try:
            health = self.backend.health()
        except BackendError as exc:
            LOG.warning("health check failed: %s", exc)
            self.reply(incoming, "Сервер не отвечает.")
            return
        self.reply(
            incoming,
            f"Сервер: {health.get('status')}\n"
            f"Режим: {health.get('mode')}\n"
            f"Схема базы: версия {health.get('schema_version')}",
        )

    HANDLERS: dict[str, Callable[["Bot", Incoming, str], None]] = {}


Bot.HANDLERS = {
    "start": Bot.cmd_start,
    "help": Bot.cmd_help,
    "помощь": Bot.cmd_help,
    "app": Bot.cmd_app,
    "приложение": Bot.cmd_app,
    "myid": Bot.cmd_myid,
    "мойid": Bot.cmd_myid,
    "кто": Bot.cmd_who,
    "who": Bot.cmd_who,
    "код": Bot.cmd_code,
    "code": Bot.cmd_code,
    "статус": Bot.cmd_status,
    "status": Bot.cmd_status,
}
