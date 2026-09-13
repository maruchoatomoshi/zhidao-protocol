"use strict";

/* Контрабанда — экран партии (V4_GAMES.md §4.12). Каркас комнаты, опрос и
   подтверждения — в games.js.

   Порт Хайнаня, таможня BlueJoy. Купец тайно собирает сумку и заявляет один
   разрешённый товар, таможенник пропускает или вскрывает. Торг идёт голосом за
   столом: в приложении — только выбор карт, товар из списка и число юаней.

   Чужая рука, содержимое сумок и провезённая запрещёнка приходят с сервера
   только тем, кому положены. В режиме «Иероглифы» во вскрытой сумке у
   таможенника есть только знаки — перевода в ответе сервера нет вовсе.
   Названия товаров, ролей и событий берём из assets/games/smuggle.json. */

(function () {
  const PHASES = { lobby: "ЛОББИ", pack: "СБОРКА СУМОК", inspect: "ДОСМОТР", over: "ИТОГ" };
  const MODES = [["hanzi", "Иероглифы у таможни"], ["translated", "С переводом"]];
  const MODE_NAMES = Object.fromEntries(MODES);
  const MERCHANT_TRICKS = { virtuoso: "compartment", hacker: "hack" };
  let catalog = null;

  const inRound = (game) => game.phase === "pack" || game.phase === "inspect";
  const phaseKey = (game) => `${game.game || 0}:${game.round || 0}:${game.phase || "lobby"}`;
  const phaseName = (game) => PHASES[game.phase || "lobby"];
  const good = (code) => (catalog ? catalog.goods.find((g) => g.code === code) : null);
  const roleOf = (code) => (catalog ? catalog.roles.find((r) => r.code === code) : null);
  const eventOf = (code) => (catalog ? catalog.events.find((e) => e.code === code) : null);
  const goodName = (code) => {
    const g = good(code);
    return g ? `${g.zh} ${g.ru}` : code;
  };

  function cardEl(c, card, opts = {}) {
    const classes = ["smuggle-card"];
    if (card.legal === true) classes.push("is-legal");
    if (card.legal === false) classes.push("is-contraband");
    if (opts.picked) classes.push("is-picked");
    if (opts.marked) classes.push("is-marked");
    const el = c.node(opts.onClick ? "button" : "div", classes.join(" "));
    if (opts.onClick) {
      el.type = "button";
      el.setAttribute("aria-pressed", String(Boolean(opts.picked || opts.marked)));
      el.addEventListener("click", opts.onClick);
    }
    el.append(c.node("b", null, card.zh));
    if (card.pinyin) el.append(c.node("small", null, card.pinyin));
    if (card.ru) el.append(c.node("small", "smuggle-ru", card.ru));
    if (card.value) el.append(c.node("span", "smuggle-price", `${card.value} 元 · штраф ${card.penalty}`));
    return el;
  }

  function decisionText(d) {
    if (d.kind === "hacked") return "Сканер взломан — сумка прошла без досмотра";
    if (d.kind === "pass") return d.bribe ? `Пропущено · взятка ${d.bribe} 元` : "Пропущено";
    if (d.honest) return `Вскрыто: всё честно · таможня заплатила ${d.officer_paid} 元`;
    let text = `Вскрыто: конфисковано ${d.confiscated.length ? d.confiscated.map(goodName).join(", ") : "ничего"} · штраф ${d.fine} 元`;
    if (d.officer_paid) text += ` · за ложные отметки таможня заплатила ${d.officer_paid} 元`;
    if (d.slipped) text += ` · проскользнуло: ${d.slipped}`;
    return text;
  }

  // --- лобби и итоги ---------------------------------------------------------------------

  function drawLobby(c) {
    const { node, button, room, game } = c;
    const wrap = node("div", "spy-actions");
    wrap.append(c.codePlate());
    if (room.is_host) {
      wrap.append(node("span", "spy-label", "Что видит таможенник во вскрытой сумке"));
      wrap.append(c.segmented(MODES, room.settings.mode, (mode) => c.settings({ mode })));
    } else {
      wrap.append(node("p", "spy-lead", `Режим: ${(MODE_NAMES[room.settings.mode] || "").toLowerCase()}. Партию запускает ведущий.`));
    }
    wrap.append(node("p", "spy-hint",
      "Купцы тайно собирают сумки и заявляют разрешённый товар. Таможенник пропускает за взятку или вскрывает. Юани — только на эту партию; победитель партии от 4 игроков получает 10★ раз в день"));
    const count = c.view.players.length;
    if (room.is_host) {
      const start = button("btn btn-primary", game.phase === "over" ? "Новая партия" : "Начать партию", () => c.act("start"));
      start.disabled = count < room.min_players;
      wrap.append(start);
    }
    if (count < room.min_players) wrap.append(node("p", "spy-progress", `За столом ${count}, нужно минимум ${room.min_players}`));
    return wrap;
  }

  function drawResult(c) {
    const { node, game } = c;
    const result = game.result;
    const box = node("div", "spy-reveal smuggle-result");
    box.append(node("span", "spy-label", `Партия ${game.game}`));
    if (result.reason !== "done") {
      box.append(node("h3", null, "За столом осталось меньше трёх — партия не засчитана"));
      return box;
    }
    box.append(node("h3", null, `Победа: ${result.winners.map((id) => c.nameOf(id)).join(", ")}`));
    const list = node("ol", "smuggle-scores");
    Object.entries(result.scores).sort((a, b) => b[1].total - a[1].total).forEach(([pid, s]) => {
      const item = node("li");
      item.append(node("b", null, `${c.nameOf(pid)} — ${s.total}`),
        node("small", null, `юани ${s.money} · товары ${s.goods} · короли рынка ${s.king} · наборы ${s.sets} · запрещёнки ${s.contraband}`));
      if (result.prizes[pid] === "granted") item.append(node("span", "smuggle-prize", "+10★"));
      else if (result.prizes[pid] === "limited") item.append(node("span", "spy-hint", "приз сегодня уже был"));
      list.append(item);
    });
    box.append(list);
    return box;
  }

  // --- раунд ---------------------------------------------------------------------------------

  function drawHeader(c) {
    const { node, game } = c;
    const wrap = node("div", "spy-actions");
    wrap.append(c.banner(`Раунд ${game.round} из ${game.rounds} · таможенник: ${c.nameOf(game.officer)}`));
    const event = eventOf(game.event);
    if (event) {
      const card = node("div", `smuggle-event is-${event.code}`);
      card.append(node("b", null, `${event.zh} ${event.ru}`), node("span", null, event.note_ru));
      wrap.append(card);
    }
    const you = game.you;
    const role = you && roleOf(you.role);
    if (role) {
      wrap.append(node("p", "spy-hint", `Ваша роль: ${role.zh} ${role.ru} — ${role.note_ru}${you.role_used ? " Уже использована." : ""}`));
    }
    return wrap;
  }

  function drawTable(c) {
    const { node, game } = c;
    const wrap = node("div", "smuggle-table");
    for (const id of game.order) {
      const info = game.table[String(id)];
      const seat = node("div", `smuggle-seat${id === game.officer ? " is-officer" : ""}`);
      const head = node("div", "smuggle-seat-head");
      head.append(node("b", null, c.nameOf(id)), node("span", "smuggle-money", `${info.money} 元`));
      if (id === game.officer) head.append(node("small", "smuggle-badge", "таможня"));
      seat.append(head);
      const stall = node("div", "smuggle-stall");
      Object.entries(info.legal).forEach(([code, n]) => {
        const g = good(code);
        stall.append(node("span", "smuggle-chip", `${g ? g.zh : code} ×${n}`));
      });
      if (info.hidden) stall.append(node("span", "smuggle-chip is-hidden", `🎁 ×${info.hidden}`));
      if (!stall.childElementCount) stall.append(node("span", "smuggle-chip is-empty", "прилавок пуст"));
      seat.append(stall);
      const bag = game.bags && game.bags[String(id)];
      if (bag) seat.append(node("p", "spy-hint", `Заявил: ${bag.count} × ${goodName(bag.declared)}`));
      const decision = game.decisions && game.decisions[String(id)];
      if (decision) seat.append(node("p", "spy-progress", decisionText(decision)));
      wrap.append(seat);
    }
    return wrap;
  }

  function drawPack(c) {
    const { node, button, game, local } = c;
    const you = game.you;
    const wrap = node("div", "spy-actions");
    if (you.bag) {
      wrap.append(node("span", "spy-label", "Ваша сумка"));
      const grid = node("div", "smuggle-hand");
      you.bag.cards.forEach((card) => grid.append(cardEl(c, card)));
      wrap.append(grid);
      const extras = [you.bag.hack ? "сканер взломан" : null, you.bag.compartment ? "двойное дно" : null].filter(Boolean);
      wrap.append(node("p", "spy-hint",
        `Заявлено: ${you.bag.cards.length} × ${goodName(you.bag.declared)} · взятка ${you.bag.bribe} 元${extras.length ? ` · ${extras.join(" · ")}` : ""}`));
      if (game.phase === "pack") {
        wrap.append(button("btn btn-secondary", "Разобрать сумку", () => {
          local.pick = [];
          c.act("unpack");
        }));
      } else {
        wrap.append(node("p", "spy-progress", "Сумка на таможне. Смотрите таможеннику в глаза"));
      }
      return wrap;
    }
    if (game.phase !== "pack") return wrap;
    const limit = game.event === "typhoon" ? (catalog ? catalog.typhoon_bag : 3) : (catalog ? catalog.max_bag : 5);
    local.pick = local.pick || [];
    wrap.append(node("span", "spy-label", `Соберите сумку: от 1 до ${limit} товаров`));
    const grid = node("div", "smuggle-hand");
    you.hand.forEach((card, index) => {
      const picked = local.pick.includes(index);
      grid.append(cardEl(c, card, {
        picked,
        onClick: () => {
          if (picked) local.pick = local.pick.filter((i) => i !== index);
          else if (local.pick.length < limit) local.pick = [...local.pick, index];
          c.redraw();
        },
      }));
    });
    wrap.append(grid);

    wrap.append(node("span", "spy-label", "Что заявляете вслух"));
    const legal = catalog ? catalog.goods.filter((g) => g.legal) : [];
    wrap.append(c.segmented(legal.map((g) => [g.code, `${g.zh} ${g.ru}`]), local.declared, (code) => {
      local.declared = code;
      c.redraw();
    }));

    const money = game.table[String(c.you)] ? game.table[String(c.you)].money : 0;
    const cap = game.event === "lantern" ? Math.min(money, catalog ? catalog.lantern_bribe : 5) : money;
    local.bribe = Math.min(local.bribe || 0, cap);
    const bribe = node("div", "smuggle-bribe");
    bribe.append(
      button("btn btn-secondary", "−", () => { local.bribe = Math.max(0, local.bribe - 1); c.redraw(); }),
      node("b", null, `Взятка ${local.bribe} 元`),
      button("btn btn-secondary", "+", () => { local.bribe = Math.min(cap, local.bribe + 1); c.redraw(); }));
    wrap.append(bribe);

    const trick = MERCHANT_TRICKS[you.role];
    if (trick && !you.role_used) {
      const role = roleOf(you.role);
      const toggle = button("btn btn-secondary", `${local.trick ? "✓ " : ""}${role ? role.ru : "Способность роли"}: применить к этой сумке`,
        () => { local.trick = !local.trick; c.redraw(); });
      toggle.setAttribute("aria-pressed", String(Boolean(local.trick)));
      wrap.append(toggle);
    }

    const send = button("btn btn-primary",
      local.pick.length ? `Отдать сумку: ${local.pick.length} × ${local.declared ? goodName(local.declared) : "…"}` : "Выберите товары",
      () => {
        const body = { cards: local.pick, declared: local.declared, bribe: local.bribe };
        if (local.trick && trick) body.trick = trick;
        c.act("pack", body);
      });
    send.disabled = !local.pick.length || !local.declared;
    wrap.append(send);
    wrap.append(node("p", "spy-hint", "Число товаров в заявлении всегда честное, а тип — как решите. Торгуйтесь голосом"));
    return wrap;
  }

  function drawInspect(c) {
    const { node, button, game, local } = c;
    const you = game.you;
    const wrap = node("div", "spy-actions");
    if (game.phase === "pack") {
      const waiting = game.waiting.map((id) => c.nameOf(id)).join(", ");
      wrap.append(node("p", "spy-progress", `Вы таможенник. Ждём сумки: ${waiting || "все готовы"}`));
      return wrap;
    }
    const banner = c.armedBanner("smuggle:");
    if (banner) wrap.append(banner);
    local.marks = local.marks || {};
    for (const [pid, bag] of Object.entries(game.bags)) {
      const box = node("div", "smuggle-bag");
      const head = node("div", "smuggle-seat-head");
      head.append(node("b", null, `${c.nameOf(pid)}: ${bag.count} × ${goodName(bag.declared)}`),
        node("span", "smuggle-money", `взятка ${(you.bribes && you.bribes[pid]) || 0} 元`));
      box.append(head);
      const decision = game.decisions[pid];
      if (decision) {
        box.append(node("p", "spy-progress", decisionText(decision)));
        wrap.append(box);
        continue;
      }
      if (you.double && you.double.includes(Number(pid))) box.append(node("p", "spy-hint", "Инспектор NetWatch: штрафы с этого купца вдвое"));
      const peek = you.peek && you.peek[pid];
      if (peek) box.append(node("p", "spy-hint", `Осведомитель: карта №${peek.index + 1} — ${peek.card.zh}${peek.card.ru ? ` (${peek.card.ru})` : ""}`));
      const opened = you.inspecting && you.inspecting[pid];
      if (opened) {
        const marks = local.marks[pid] || [];
        box.append(node("p", "spy-hint", "Отметьте карты, которые НЕ совпадают с заявленным. Ложная отметка стоит таможне штрафа"));
        const grid = node("div", "smuggle-hand");
        opened.forEach((card, index) => grid.append(cardEl(c, card, {
          marked: marks.includes(index),
          onClick: () => {
            local.marks[pid] = marks.includes(index) ? marks.filter((i) => i !== index) : [...marks, index];
            c.redraw();
          },
        })));
        box.append(grid);
        box.append(button("btn btn-primary", `Вынести решение · отмечено ${marks.length}`,
          () => c.confirmTwice(`smuggle:judge:${pid}`, `решение по сумке ${c.nameOf(pid)}`,
            () => c.act("judge", { merchant: Number(pid), marks }))));
      } else {
        const row = node("div", "spy-vote-buttons");
        row.append(
          button("btn btn-secondary", "Пропустить", () => c.confirmTwice(`smuggle:pass:${pid}`, `пропустить сумку ${c.nameOf(pid)}`,
            () => c.act("pass", { merchant: Number(pid) }))),
          button("btn btn-primary", "Вскрыть", () => c.act("open", { merchant: Number(pid) })));
        box.append(row);
        if (!you.role_used && you.role === "informant" && !peek) {
          box.append(button("btn btn-secondary", "👁 Подсмотреть одну карту", () => c.act("peek", { merchant: Number(pid) })));
        }
        if (!you.role_used && you.role === "inspector") {
          box.append(button("btn btn-secondary", "×2 штрафы с этого купца", () => c.act("double", { merchant: Number(pid) })));
        }
      }
      wrap.append(box);
    }
    return wrap;
  }

  function drawLastRound(c) {
    const { node, game } = c;
    const last = game.last_round;
    if (!last || !inRound(game)) return null;
    const details = node("details", "spy-places");
    details.append(node("summary", null, `Итоги раунда ${last.round}`));
    for (const [pid, decision] of Object.entries(last.decisions)) {
      const declared = last.declared[pid];
      details.append(node("p", "spy-hint",
        `${c.nameOf(pid)}: ${declared ? `${declared.count} × ${goodName(declared.declared)} — ` : ""}${decisionText(decision)}`));
    }
    return details;
  }

  function draw(c) {
    const game = c.game;
    const parts = [];
    if (inRound(game)) {
      parts.push(drawHeader(c));
      if (game.you) parts.push(game.you.officer ? drawInspect(c) : drawPack(c));
      else parts.push(c.node("p", "spy-progress", "Партия уже идёт — вы смотрите со стороны"));
      parts.push(drawTable(c), drawLastRound(c));
    } else {
      if (game.result) parts.push(drawResult(c));
      parts.push(drawLobby(c));
    }
    parts.push(c.playersList({ tags: (p) => (inRound(game) && p.account_id === game.officer ? ["таможенник"] : []) }));
    return parts;
  }

  const finished = (game) => Boolean(game.result);
  const renderer = { phaseKey, phaseName, draw, finished };
  window.ZhidaoGames.register("smuggle", renderer);
  fetch("./assets/games/smuggle.json", { cache: "no-cache" })
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (!data) return;
      catalog = data;
      window.ZhidaoGames.register("smuggle", renderer);   // перерисовать с названиями товаров
    })
    .catch(() => { /* без справочника покажем коды — партия всё равно играется */ });
}());
