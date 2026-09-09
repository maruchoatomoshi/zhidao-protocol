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
import uuid
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
    # Идентификатор сообщения MAX. Нужен там, где команда что-то меняет:
    # из него строится ключ идемпотентности, и повторно прочитанное
    # обновление не выдаёт вторую порцию попыток.
    message_id: str | None = None


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
            message_id=(str(body.get("mid")) if body.get("mid") else None),
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
    ("сезон", "Состояние сезона"),
    ("шансы", "Что и с какой вероятностью выпадает"),
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
            "/сезон — состояние сезона",
            "/шансы — что и с какой вероятностью выпадает",
            "/help — этот список",
        ]
        if self.is_operator(incoming.user_id):
            lines += [
                "",
                "Для вожатых:",
                "/кто — весь ростер; /кто <имя> — поиск",
                "/код <имя или номер> — выдать код сопряжения",
                "/ростер — состав сезона и остаток попыток",
                "/выдать <кому> <сколько> <причина> — выдать попытки",
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


    # --- команды, доступные всем ------------------------------------------

    def cmd_season(self, incoming: Incoming, argument: str) -> None:
        del argument
        try:
            items = self.backend.seasons()
        except BackendError as exc:
            LOG.warning("seasons lookup failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
            return
        if not items:
            self.reply(incoming, "Сезонов пока нет.")
            return
        lines = ["Сезоны:", ""]
        for season in items:
            dates = " → ".join(
                str(season.get(key) or "—") for key in ("starts_on", "ends_on")
            )
            lines.append(
                f"{season.get('name')} — {season.get('status')}\n"
                f"даты: {dates}"
            )
        # Состояние draft — не поломка, а «ещё не начали». Говорим прямо,
        # иначе человек будет думать, что у него что-то сломалось.
        if all(season.get("status") == "draft" for season in items):
            lines += ["", "Черновик значит, что сезон ещё не запущен: "
                          "попытки не выдаются и кейсы не открываются."]
        self.reply(incoming, "\n\n".join(lines) if len(lines) > 2 else "\n".join(lines))

    def cmd_chances(self, incoming: Incoming, argument: str) -> None:
        del argument
        try:
            rules = self.backend.case_rules()
        except BackendError as exc:
            LOG.warning("case rules failed: %s", exc)
            self.reply(incoming, "Правила не загрузились. Попробуйте ещё раз.")
            return
        tiers = rules.get("tiers") or []
        if not tiers:
            self.reply(incoming, "Правила кейсов пока не заданы.")
            return
        # Проценты считаются из весов здесь же, а не берутся готовыми: ровно
        # по той причине, по которой их считает приложение — записанное число
        # однажды разойдётся с правилами, и заметить это будет нечем.
        total = sum(int(tier.get("weight") or 0) for tier in tiers) or 1
        lines = ["Что выпадает за одно сканирование:", ""]
        for tier in tiers:
            share = int(tier.get("weight") or 0) / total
            lines.append(f"{tier.get('name_ru')} — {self.percent(share)}")
        black = next((t for t in tiers if t.get("code") == "black"), None)
        if black and black.get("prizes"):
            inner = sum(int(p.get("weight") or 0) for p in black["prizes"]) or 1
            share = int(black.get("weight") or 0) / total
            lines += ["", f"Внутри «{black.get('name_ru')}» (и шанс за попытку):"]
            for prize in black["prizes"]:
                part = int(prize.get("weight") or 0) / inner
                lines.append(
                    f"· {prize.get('name_ru')} — {self.percent(part)} "
                    f"({self.percent(part * share)} за попытку)"
                )
        lines += ["", "Полная таблица — в приложении, раздел «Кейсы»."]
        self.reply(incoming, "\n".join(lines), with_app_button=True)

    @staticmethod
    def percent(value: float) -> str:
        """Округление по величине: 0,2% нельзя показать как 0%."""
        share = value * 100
        digits = 0 if share >= 10 else 1 if share >= 1 else 2
        return f"{share:.{digits}f}".replace(".", ",") + "%"

    # --- команды оператора, связанные с сезоном ---------------------------

    def manageable_season(self, incoming: Incoming) -> dict | None:
        """Сезон, в котором бот вправе распоряжаться. Молчать не даёт."""
        try:
            seasons = self.backend.case_context()
        except BackendError as exc:
            LOG.warning("case context failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
            return None
        manageable = [s for s in seasons if s.get("can_manage")]
        active = [s for s in manageable if s.get("status") == "active"]
        if active:
            return active[0]
        if manageable:
            names = ", ".join(f"{s.get('name')} ({s.get('status')})" for s in manageable)
            self.reply(
                incoming,
                f"Активного сезона нет: {names}.\n\n"
                "Пока сезон не запущен, попытки не выдаются и состава ещё нет.",
            )
            return None
        self.reply(
            incoming,
            "У служебной учётки бота нет сезона, которым она распоряжается. "
            "Это настраивает Архитектор.",
        )
        return None

    def cmd_roster(self, incoming: Incoming, argument: str) -> None:
        del argument
        if not self._require_operator(incoming):
            return
        season = self.manageable_season(incoming)
        if season is None:
            return
        try:
            roster = self.backend.case_roster(int(season["id"]))
        except BackendError as exc:
            LOG.warning("season roster failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
            return
        members = roster.get("members") or []
        if not members:
            self.reply(
                incoming,
                f"В сезоне «{season.get('name')}» пока нет участников. "
                "Состав задаёт Архитектор.",
            )
            return
        lines = [f"Состав «{season.get('name')}» — {len(members)}:", ""]
        for member in members[: self.ROSTER_PREVIEW]:
            lines.append(
                f"#{member['id']} · {member['display_name']} — "
                f"{member.get('scans', 0)}/7 попыток"
            )
        if len(members) > self.ROSTER_PREVIEW:
            lines += ["", f"Показаны первые {self.ROSTER_PREVIEW} из {len(members)}."]
        self.reply(incoming, "\n".join(lines))

    def cmd_grant(self, incoming: Incoming, argument: str) -> None:
        if not self._require_operator(incoming):
            return
        parsed = self.parse_grant(argument)
        if parsed is None:
            self.reply(
                incoming,
                "Формат: /выдать <кому> <сколько> <причина>\n\n"
                "Например:\n"
                "/выдать 17 2 участие во встрече\n"
                "/выдать Иванов Пётр 2 участие во встрече\n\n"
                "«Кому» — номер из /кто или имя целиком, можно из нескольких "
                "слов. Причина обязательна: она попадает в журнал и объясняет "
                "выдачу через месяц, когда никто уже не помнит.",
            )
            return
        target, amount, reason = parsed
        if not 1 <= amount <= 7:
            self.reply(incoming, "Сколько попыток? Число от 1 до 7.")
            return

        account = self.resolve_account(incoming, target)
        if account is None:
            return
        season = self.manageable_season(incoming)
        if season is None:
            return

        # Ключ из идентификатора сообщения: то же сообщение, прочитанное
        # дважды, даёт ту же выдачу, а не двойную.
        key = f"bot-grant-{incoming.message_id or uuid.uuid4().hex}"
        try:
            result = self.backend.grant_scans(
                int(season["id"]),
                account_ids=[int(account["id"])],
                amount=amount,
                reason=reason,
                idempotency_key=key,
            )
        except BackendError as exc:
            if exc.status_code in (400, 403, 404, 409, 422):
                LOG.info("grant rejected: %s", exc)
                self.reply(
                    incoming,
                    "Сервер отклонил выдачу. Чаще всего это значит, что человек "
                    "не входит в состав сезона или сезон уже не активен.",
                )
                return
            LOG.warning("grant failed: %s", exc)
            self.reply(
                incoming,
                "Нет подтверждения от сервера. Повторите ту же команду: "
                "выдача защищена от удвоения.",
            )
            return

        rows = result.get("results") or []
        if not rows:
            self.reply(incoming, "Сервер ответил, но ничего не выдал. Позовите Архитектора.")
            return
        lines = [f"Выдано. Причина: {reason}", ""]
        for row in rows:
            granted, requested = row.get("granted", 0), row.get("requested", amount)
            tail = "" if granted == requested else f" (просили {requested}, упёрлись в предел)"
            lines.append(
                f"#{row.get('account_id')} · {account['display_name']}: "
                f"+{granted}{tail}, запас {row.get('scans')}/7"
            )
        self.reply(incoming, "\n".join(lines))

    @staticmethod
    def parse_grant(argument: str) -> tuple[str, int, str] | None:
        """Разбирает «кому сколько причина», где имя бывает из нескольких слов.

        Правило объяснимое: если команда начинается с числа, это номер из
        /кто, и следующее число — количество. Иначе количество — первое
        число после имени, а всё до него имя. «Иванов Пётр 2 встреча»
        разбирается так же надёжно, как «17 2 встреча».

        Первый вариант разбора требовал одного слова в имени, и это выяснил
        тест: вожатый пишет имя целиком, а не одно слово из него.
        """
        words = argument.split()
        if len(words) < 3:
            return None
        first = words[0].lstrip("#")
        if first.isdigit():
            if not words[1].isdigit():
                return None
            return first, int(words[1]), " ".join(words[2:]).strip()
        for index in range(1, len(words) - 1):
            if words[index].isdigit():
                name = " ".join(words[:index]).strip()
                reason = " ".join(words[index + 1:]).strip()
                if not name or not reason:
                    return None
                return name, int(words[index]), reason
        return None

    def resolve_account(self, incoming: Incoming, target: str) -> dict | None:
        """Один человек по номеру или куску имени. Не угадывает при неоднозначности."""
        clean = target.lstrip("#")
        try:
            items = self.backend.find_accounts("" if clean.isdigit() else target, limit=25)
        except BackendError as exc:
            LOG.warning("roster lookup failed: %s", exc)
            self.reply(incoming, "Сервер не ответил. Попробуйте ещё раз через минуту.")
            return None
        if clean.isdigit():
            found = [i for i in items if int(i["id"]) == int(clean)]
            if not found:
                self.reply(incoming, f"Аккаунта #{clean} нет или он отключён.")
                return None
            return found[0]
        if not items:
            self.reply(incoming, f"По запросу «{target}» никого нет.")
            return None
        if len(items) > 1:
            lines = ["Подходит несколько человек, уточните номером:", ""]
            lines += [f"#{i['id']} · {i['display_name']}" for i in items[:10]]
            self.reply(incoming, "\n".join(lines))
            return None
        return items[0]

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
    "сезон": Bot.cmd_season,
    "season": Bot.cmd_season,
    "шансы": Bot.cmd_chances,
    "chances": Bot.cmd_chances,
    "ростер": Bot.cmd_roster,
    "roster": Bot.cmd_roster,
    "выдать": Bot.cmd_grant,
    "grant": Bot.cmd_grant,
}
