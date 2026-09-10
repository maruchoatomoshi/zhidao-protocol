"use strict";

/* Шифровальщики — экран партии (V4_GAMES.md §4.10). Каркас комнаты, опрос и
   подтверждения — в games.js.

   Подсказка звучит голосом за столом, а в приложение капитан вводит только
   число. Поля для текста здесь нет намеренно: всё, что видят другие дети,
   собирается из готовых кусков, и модерировать нечего.

   Цвет закрытой карточки приходит с сервера только капитану. Рисуем мы то,
   что пришло; если цвета нет в ответе, его нет и на экране. */

(function () {
  const TEAMS = ["blue", "red"];
  const TEAM = { blue: "Синие", red: "Красные" };
  const TEAM_TO = { blue: "К синим", red: "К красным" };
  const TEAM_ZH = { blue: "蓝队", red: "红队" };
  const KEY_NAMES = { blue: "синяя", red: "красная", neutral: "пустая", virus: "вирус" };
  const MODE_NAMES = { translated: "С переводом", pinyin: "С пиньинем", hanzi: "Иероглифы" };
  const PHASES = { lobby: "ЛОББИ", clue: "ПОДСКАЗКА", guess: "ОТГАДЫВАНИЕ", over: "ИТОГ" };

  const inGame = (game) => game.phase === "clue" || game.phase === "guess";

  function phaseKey(game) {
    return `${game.round || 0}:${game.phase || "lobby"}:${game.turn ? game.turn.team : ""}`;
  }

  function phaseName(game) {
    return PHASES[game.phase || "lobby"];
  }

  function teamOf(game, id) {
    return TEAMS.find((team) => game.teams[team].members.includes(id)) || null;
  }

  function drawTeams(c) {
    const { node, button, game } = c;
    const grid = node("div", "cipher-teams");
    for (const team of TEAMS) {
      const info = game.teams[team];
      const box = node("div", `cipher-team is-${team}`);
      const head = node("div", "cipher-team-head");
      head.append(node("b", null, TEAM[team]), node("span", null, TEAM_ZH[team]));
      box.append(head);
      const list = node("ul", "cipher-team-list");
      if (!info.members.length) list.append(node("li", "is-empty", "пока никого"));
      for (const id of info.members) {
        const item = node("li", null, c.nameOf(id));
        if (id === info.captain) item.append(node("small", null, "капитан"));
        list.append(item);
      }
      box.append(list);
      if (game.you.team !== team) {
        box.append(button("btn btn-secondary", TEAM_TO[team], () => c.act("team", { team })));
      } else if (!game.you.captain) {
        box.append(button("btn btn-secondary", "Стать капитаном", () => c.act("captain")));
      }
      grid.append(box);
    }
    return grid;
  }

  function drawLobby(c) {
    const { node, button, room, game } = c;
    const wrap = node("div", "spy-actions");
    wrap.append(c.codePlate());
    if (room.is_host) {
      wrap.append(node("span", "spy-label", "Что видят отгадчики"));
      wrap.append(c.segmented(Object.entries(MODE_NAMES), room.settings.mode, (mode) => c.settings({ mode })));
    } else {
      wrap.append(node("p", "spy-lead", `Режим: ${MODE_NAMES[room.settings.mode].toLowerCase()}. Партию запускает ведущий.`));
    }
    wrap.append(node("p", "spy-hint", "Капитан всегда видит слово целиком: подсказку он даёт по-русски. Режим меняет только то, что видят отгадчики."));
    wrap.append(drawTeams(c));
    if (game.unassigned.length) {
      wrap.append(node("p", "spy-hint", `Без команды: ${game.unassigned.map((id) => c.nameOf(id)).join(", ")}. При старте рассадим поровну.`));
    }
    const count = c.view.players.length;
    if (room.is_host) {
      const row = node("div", "spy-vote-buttons");
      row.append(button("btn btn-secondary", "Перемешать", () => c.act("shuffle")));
      const start = button("btn btn-primary", game.phase === "over" ? "Новая партия" : "Начать партию", () => c.act("start"));
      start.disabled = count < room.min_players;
      row.append(start);
      wrap.append(row);
    }
    if (count < room.min_players) {
      wrap.append(node("p", "spy-progress", `За столом ${count}, нужно минимум ${room.min_players}`));
    }
    return wrap;
  }

  function drawScore(c) {
    const { node, game } = c;
    const row = node("div", "cipher-score");
    for (const team of TEAMS) {
      const chip = node("div", `cipher-chip is-${team}${game.turn.team === team ? " is-turn" : ""}`);
      chip.append(node("span", null, TEAM[team]), node("b", null, String(game.remaining[team])));
      chip.setAttribute("aria-label", `${TEAM[team]}: осталось слов ${game.remaining[team]}${game.turn.team === team ? ", сейчас их ход" : ""}`);
      row.append(chip);
    }
    return row;
  }

  function drawTurn(c) {
    const { node, button, game, local } = c;
    const turn = game.turn;
    const mine = game.you.team === turn.team;
    const wrap = node("div", "spy-actions");
    if (game.phase === "clue") {
      if (mine && game.you.captain) {
        wrap.append(c.banner("Ваш ход, капитан. Скажите команде вслух одно слово и число, потом отметьте это число здесь."));
        const grid = node("div", "cipher-count");
        for (let n = 1; n <= 9; n += 1) {
          const b = button("btn btn-secondary", String(n), () => { local.count = n; c.redraw(); });
          b.setAttribute("aria-pressed", String(local.count === n));
          grid.append(b);
        }
        wrap.append(grid);
        const send = button("btn btn-primary", local.count ? `Подсказка на ${local.count}` : "Выберите число",
          () => c.act("clue", { count: local.count }));
        send.disabled = !local.count;
        wrap.append(send);
      } else {
        wrap.append(c.banner(`Ход: ${TEAM[turn.team]}. Капитан придумывает подсказку.`));
      }
    } else {
      wrap.append(c.banner(`Ход: ${TEAM[turn.team]} · подсказка на ${turn.clue} · попыток осталось ${turn.guesses_left}`));
      if (mine && !game.you.captain) {
        wrap.append(node("p", "spy-hint", "Коснитесь карточки дважды, чтобы открыть её."));
        if (turn.guesses_made >= 1) wrap.append(button("btn btn-secondary", "Закончить ход", () => c.act("end-turn")));
      } else if (mine) {
        wrap.append(node("p", "spy-hint", "Капитан молчит, пока команда отгадывает."));
      }
    }
    if (game.last) {
      const card = game.board[game.last.index];
      wrap.append(node("p", "spy-progress", `Последней открыта: ${card.word.zh} — ${KEY_NAMES[game.last.key]}`));
    }
    return wrap;
  }

  function drawBoard(c, live) {
    const { node, game } = c;
    const wrap = node("div", "spy-actions");
    const banner = c.armedBanner("card:");
    if (banner) wrap.append(banner);
    const grid = node("div", "cipher-board");
    grid.setAttribute("role", "list");
    const guessing = live && game.phase === "guess" && game.you.team === game.turn.team && !game.you.captain;
    for (const card of game.board) {
      const openable = guessing && !card.revealed;
      const el = node(openable ? "button" : "div", "cipher-card");
      if (!openable) el.setAttribute("role", "listitem");
      if (card.key) el.classList.add(`is-${card.key}`);
      el.classList.add(card.revealed ? "is-revealed" : card.key ? "is-hint" : "is-closed");
      el.append(node("b", null, card.word.zh));
      if (card.word.pinyin) el.append(node("small", null, card.word.pinyin));
      if (card.word.ru) el.append(node("small", "cipher-ru", card.word.ru));
      el.setAttribute("aria-label", [card.word.zh, card.word.pinyin, card.word.ru,
        card.key ? KEY_NAMES[card.key] : null, card.revealed ? "открыта" : null].filter(Boolean).join(", "));
      if (openable) {
        el.type = "button";
        const key = `card:${card.index}`;
        if (c.armed() === key) el.classList.add("is-armed");
        el.addEventListener("click", () =>
          c.confirmTwice(key, `открыть ${card.word.zh}`, () => c.act("guess", { index: card.index })));
      }
      grid.append(el);
    }
    wrap.append(grid);
    return wrap;
  }

  function drawResult(c) {
    const { node, game } = c;
    const result = game.result;
    const box = node("div", `spy-reveal${result.winner ? ` cipher-win is-${result.winner}` : ""}`);
    box.append(node("span", "spy-label", `Партия ${game.round}`));
    let title = "В команде осталось меньше двух человек — партия не засчитана";
    if (result.reason === "virus") title = `Открыт вирус. Победа: ${TEAM[result.winner].toLowerCase()}`;
    if (result.reason === "all_found") title = `${TEAM[result.winner]} нашли все свои слова`;
    box.append(node("h3", null, title));
    const entries = Object.entries(result.points || {});
    if (entries.length) {
      const list = node("ul", "spy-points");
      for (const [id, amount] of entries) list.append(node("li", null, `+${amount} ${c.nameOf(id)}`));
      box.append(list);
    } else {
      box.append(node("p", "spy-progress", "Очков никто не получил."));
    }
    box.append(node("p", "spy-hint", "Раскладка открыта ниже: посмотрите, какие слова были чьими."));
    return box;
  }

  function draw(c) {
    const game = c.game;
    const parts = [];
    if (inGame(game)) {
      parts.push(drawScore(c), drawTurn(c), drawBoard(c, true));
    } else {
      if (game.phase === "over" && game.result) parts.push(drawResult(c));
      parts.push(drawLobby(c));
      if (game.board) parts.push(drawBoard(c, false));
    }
    parts.push(c.playersList({
      tags: (p) => {
        const team = teamOf(game, p.account_id);
        if (!team) return [];
        return [game.teams[team].captain === p.account_id ? `${TEAM[team]}, капитан` : TEAM[team]];
      },
    }));
    return parts;
  }

  window.ZhidaoGames.register("cipher", { phaseKey, phaseName, draw });
}());
