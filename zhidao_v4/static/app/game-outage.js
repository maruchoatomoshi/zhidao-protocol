"use strict";

/* Сбой системы — экран партии (V4_GAMES.md §4.11). Каркас комнаты, опрос и
   подтверждения — в games.js.

   У техника на экране модули, у экспертов — инструкция. Что кому рисовать,
   решает не этот файл, а ответ сервера: у техника в нём нет инструкции, у
   экспертов нет модулей. Здесь только отрисовка того, что пришло. */

(function () {
  const PHASES = { lobby: "ЛОББИ", defuse: "СБОЙ", over: "ИТОГ" };
  const DIFFICULTY = [["easy", "Лёгкий"], ["normal", "Обычный"], ["hard", "Сложный"]];
  const DIFFICULTY_HINT = { easy: "2 модуля · 5 минут", normal: "3 модуля · 5 минут", hard: "4 модуля · 4 минуты" };
  const TYPE_NAMES = { wires: "Провода", keypad: "Замок", compass: "Навигация", number: "Счётчик" };
  const ARROWS = { up: "↑", down: "↓", left: "←", right: "→" };
  const ARROW_NAMES = { up: "вверх", down: "вниз", left: "влево", right: "вправо" };
  const ORDINALS = ["первый", "второй", "третий", "четвёртый", "пятый", "шестой"];
  const REASONS = {
    defused: "Система восстановлена",
    strikes: "Три ошибки — система легла",
    time: "Время вышло — система легла",
    technician_left: "Техник вышел — раунд не засчитан",
    too_few: "За столом меньше двух человек — раунд не засчитан",
  };

  function phaseKey(game) { return `${game.round || 0}:${game.phase || "lobby"}`; }
  function phaseName(game) { return PHASES[game.phase || "lobby"]; }
  function sync(c) { if (c.game.phase === "defuse") c.setTimer("outage", c.game.seconds_left); }

  function strikes(c) {
    const { node, game } = c;
    const row = node("div", "outage-strikes");
    row.setAttribute("aria-label", `Ошибок ${game.strikes} из ${game.max_strikes}`);
    for (let i = 0; i < game.max_strikes; i += 1) {
      const lamp = node("span", `outage-lamp${i < game.strikes ? " is-on" : ""}`, "✕");
      lamp.setAttribute("aria-hidden", "true");
      row.append(lamp);
    }
    return row;
  }

  function moduleShell(c, module, index) {
    const { node } = c;
    const box = node("section", `outage-module${module.solved ? " is-solved" : ""}`);
    const head = node("div", "outage-module-head");
    head.append(node("b", null, `${String(index + 1).padStart(2, "0")} · ${TYPE_NAMES[module.type]}`),
      node("span", null, module.solved ? "ИСПРАВЛЕН" : "СБОЙ"));
    box.append(head);
    return box;
  }

  // --- модули техника -------------------------------------------------------------

  function drawWires(c, module, index, live) {
    const { node } = c;
    const box = moduleShell(c, module, index);
    const banner = live ? c.armedBanner(`cut:${index}:`) : null;
    if (banner) box.append(banner);
    const list = node("div", "outage-wires");
    module.wires.forEach((wire, i) => {
      const interactive = live && !module.solved && !wire.cut;
      const row = node(interactive ? "button" : "div", `outage-wire${wire.cut ? " is-cut" : ""}`);
      const key = `cut:${index}:${i}`;
      if (interactive) {
        row.type = "button";
        if (c.armed() === key) row.classList.add("is-armed");
        row.addEventListener("click", () =>
          c.confirmTwice(key, `перерезать ${ORDINALS[i]} провод`, () => c.act("cut", { module: index, wire: i })));
      }
      if (module.answer === i) row.classList.add("is-answer");
      row.setAttribute("aria-label", `${ORDINALS[i]} провод, ${wire.zh}${wire.cut ? ", перерезан" : ""}`);
      row.append(node("span", "outage-wire-no", String(i + 1)), node("span", "outage-wire-line"), node("b", null, wire.zh));
      list.append(row);
    });
    box.append(list);
    if (module.answer != null) box.append(node("p", "spy-hint", `Ответ: ${ORDINALS[module.answer]} провод.`));
    return box;
  }

  function drawKeypad(c, module, index, live) {
    const { node, button } = c;
    const box = moduleShell(c, module, index);
    const grid = node("div", "outage-keypad");
    module.symbols.forEach((symbol, i) => {
      const b = button(`outage-key${symbol.pressed ? " is-pressed" : ""}`, symbol.zh,
        () => c.act("press", { module: index, symbol: i }));
      b.disabled = !live || module.solved || symbol.pressed;
      grid.append(b);
    });
    box.append(grid);
    if (module.answer) box.append(node("p", "spy-hint", `Ответ: ${module.answer.join(" → ")}`));
    return box;
  }

  function drawCompass(c, module, index, live) {
    const { node, button } = c;
    const box = moduleShell(c, module, index);
    const sequence = node("div", "outage-sequence");
    module.sequence.forEach((zh, i) => sequence.append(node("b", i < module.progress ? "is-done" : null, zh)));
    box.append(sequence);
    const pad = node("div", "outage-arrows");
    for (const direction of ["up", "left", "right", "down"]) {
      const b = button(`outage-arrow is-${direction}`, ARROWS[direction],
        () => c.act("direction", { module: index, direction }));
      b.setAttribute("aria-label", ARROW_NAMES[direction]);
      b.disabled = !live || module.solved;
      pad.append(b);
    }
    box.append(pad);
    if (module.answer) box.append(node("p", "spy-hint", `Ответ: ${module.answer.map((d) => ARROWS[d]).join(" ")}`));
    return box;
  }

  function drawNumber(c, module, index, live) {
    const { node, button, local } = c;
    const box = moduleShell(c, module, index);
    box.append(node("b", "outage-number", module.zh));
    if (live && !module.solved) {
      const form = node("div", "outage-number-form");
      const input = node("input");
      input.type = "text";
      input.inputMode = "numeric";
      input.maxLength = 3;
      input.placeholder = "00";
      input.setAttribute("aria-label", "Число цифрами");
      input.value = local[`number${index}`] || "";
      input.addEventListener("input", () => {
        input.value = input.value.replace(/\D/g, "").slice(0, 3);
        local[`number${index}`] = input.value;
      });
      const submit = button("btn btn-primary", "Ввести", () => {
        if (!input.value) return;
        const value = Number(input.value);
        local[`number${index}`] = "";
        c.act("number", { module: index, value });
      });
      form.append(input, submit);
      box.append(form);
    }
    if (module.answer != null) box.append(node("p", "spy-hint", `Ответ: ${module.answer}`));
    return box;
  }

  const DRAWERS = { wires: drawWires, keypad: drawKeypad, compass: drawCompass, number: drawNumber };

  function drawModules(c, live) {
    const { node, game } = c;
    const wrap = node("div", "outage-modules");
    game.modules.forEach((module, index) => wrap.append(DRAWERS[module.type](c, module, index, live)));
    return wrap;
  }

  // --- инструкция экспертов ----------------------------------------------------------

  function manualSection(c, title, open) {
    const details = c.node("details", "spy-places outage-manual");
    details.open = open;
    details.append(c.node("summary", null, title));
    return details;
  }

  function glossary(c, rows) {
    const { node } = c;
    const table = node("div", "outage-glossary");
    for (const row of rows) {
      const cell = node("div", "outage-gloss");
      cell.append(node("b", null, row.zh), node("small", null, row.pinyin), node("span", null, row.ru));
      table.append(cell);
    }
    return table;
  }

  function drawManual(c) {
    const { node, game } = c;
    const wrap = node("div", "spy-actions");
    const manual = game.manual || {};
    if (manual.wires) {
      const s = manualSection(c, "Провода", true);
      s.append(node("p", "outage-manual-intro", manual.wires.intro), glossary(c, manual.wires.colors));
      for (const [count, rules] of Object.entries(manual.wires.rules)) {
        s.append(node("b", "outage-rule-head", `${count} ${Number(count) >= 5 ? "проводов" : "провода"}`));
        const list = node("ol", "outage-rules");
        rules.forEach((rule) => list.append(node("li", null, rule)));
        s.append(list);
      }
      wrap.append(s);
    }
    if (manual.keypad) {
      const s = manualSection(c, "Замок", true);
      s.append(node("p", "outage-manual-intro", manual.keypad.intro));
      const columns = node("div", "outage-columns");
      manual.keypad.columns.forEach((column, i) => {
        const col = node("div", "outage-column");
        col.append(node("span", "spy-label", String.fromCharCode(1040 + i)));
        column.forEach((cell) => {
          const item = node("div", "outage-column-cell");
          item.append(node("b", null, cell.zh), node("small", null, cell.pinyin));
          item.title = cell.ru;
          col.append(item);
        });
        columns.append(col);
      });
      s.append(columns);
      wrap.append(s);
    }
    if (manual.compass) {
      const s = manualSection(c, "Навигация", true);
      s.append(node("p", "outage-manual-intro", manual.compass.intro));
      s.append(glossary(c, manual.compass.table.map((row) => ({ zh: row.zh, pinyin: row.pinyin, ru: `${ARROWS[row.direction]} ${row.ru}` }))));
      wrap.append(s);
    }
    if (manual.number) {
      const s = manualSection(c, "Счётчик", true);
      s.append(node("p", "outage-manual-intro", manual.number.intro));
      s.append(glossary(c, manual.number.digits.map((row) => ({ zh: row.zh, pinyin: row.pinyin, ru: String(row.value) }))));
      wrap.append(s);
    }
    return wrap;
  }

  function drawSummary(c) {
    const { node, game } = c;
    const row = node("div", "outage-summary");
    game.summary.forEach((item) => {
      row.append(node("span", `outage-chip${item.solved ? " is-solved" : ""}`,
        `${String(item.index + 1).padStart(2, "0")} ${TYPE_NAMES[item.type]}${item.solved ? " ✓" : ""}`));
    });
    return row;
  }

  // --- лобби и итог -------------------------------------------------------------------

  function drawLobby(c) {
    const { node, button, room, game } = c;
    const wrap = node("div", "spy-actions");
    wrap.append(c.codePlate());
    if (room.is_host) {
      wrap.append(node("span", "spy-label", "Сложность"));
      wrap.append(c.segmented(DIFFICULTY, room.settings.difficulty, (difficulty) => c.settings({ difficulty })));
    }
    wrap.append(node("p", "spy-hint", `${DIFFICULTY.find(([v]) => v === room.settings.difficulty)[1]}: ${DIFFICULTY_HINT[room.settings.difficulty]}, три ошибки — сбой.`));
    wrap.append(node("p", "spy-lead", "Техник видит модули, но не знает, как их чинить. У остальных — инструкция. Держите телефоны так, чтобы техник не видел ваш экран, а вы — его."));
    if (room.is_host) {
      wrap.append(node("p", "spy-hint", "Коснитесь игрока ниже, чтобы сделать его техником. Не выберете — техник сменится по кругу."));
      const start = button("btn btn-primary", game.phase === "over" ? "Следующий раунд" : "Начать раунд", () => c.act("start"));
      start.disabled = c.view.players.length < room.min_players;
      wrap.append(start);
    }
    if (c.view.players.length < room.min_players) {
      wrap.append(node("p", "spy-progress", `За столом ${c.view.players.length}, нужно минимум ${room.min_players}`));
    }
    return wrap;
  }

  function drawResult(c) {
    const { node, game } = c;
    const result = game.result;
    const box = node("div", `spy-reveal${result.success === false ? " is-spy" : ""}`);
    box.append(node("span", "spy-label", `Раунд ${game.round}`), node("h3", null, REASONS[result.reason] || "Раунд окончен"));
    box.append(node("p", "spy-lead", `Техник: ${c.nameOf(game.technician)} · ошибок ${game.strikes} из ${game.max_strikes}`));
    const entries = Object.entries(result.points || {});
    if (entries.length) {
      const list = node("ul", "spy-points");
      for (const [id, amount] of entries) list.append(node("li", null, `+${amount} ${c.nameOf(id)}`));
      box.append(list);
    }
    box.append(node("p", "spy-hint", "Модули и ответы открыты ниже."));
    return box;
  }

  function draw(c) {
    const { node, game, room } = c;
    const parts = [];
    if (game.phase === "defuse") {
      parts.push(c.timerEl("outage", game.seconds_left, "ДО СБОЯ"), strikes(c));
      if (game.you_technician) {
        parts.push(c.banner("Вы техник. Описывайте экспертам, что видите на модулях, и делайте, что они скажут."));
        parts.push(drawModules(c, true));
      } else {
        parts.push(c.banner(`Техник: ${c.nameOf(game.technician)}. Модулей вы не видите — спрашивайте, что на них, и ищите ответ в инструкции.`));
        parts.push(drawSummary(c), drawManual(c));
      }
    } else {
      if (game.phase === "over" && game.result) parts.push(drawResult(c));
      parts.push(drawLobby(c));
      if (game.phase === "over" && game.modules) parts.push(drawModules(c, false));
    }
    const selecting = game.phase !== "defuse" && room.is_host;
    parts.push(c.playersList({
      selectable: () => selecting,
      onPick: (p) => c.act("technician", { account_id: p.account_id }),
      tags: (p) => {
        if (game.phase === "defuse") return p.account_id === game.technician ? ["техник"] : ["эксперт"];
        return p.account_id === game.technician_choice ? ["следующий техник"] : [];
      },
    }));
    return parts;
  }

  window.ZhidaoGames.register("outage", { phaseKey, phaseName, sync, draw });
}());
