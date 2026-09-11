"use strict";

/* Шпион Протокола — экран партии (V4_GAMES.md §4.9). Каркас комнаты, опрос
   и подтверждения — в games.js; здесь только то, что видно за столом. */

(function () {
  const MODE_NAMES = { translated: "С переводом", hanzi: "Только иероглифы" };
  const PHASE_NAMES = {
    lobby: "ЛОББИ",
    discussion: "ОБСУЖДЕНИЕ",
    vote: "ГОЛОСОВАНИЕ",
    final_vote: "ФИНАЛЬНОЕ ГОЛОСОВАНИЕ",
    reveal: "РАСКРЫТИЕ",
  };
  const REASONS = {
    guessed: "Шпион назвал место — и угадал",
    wrong_guess: "Шпион назвал место — и ошибся",
    accused: "Стол поймал шпиона",
    framed: "Стол осудил невиновного",
    final_vote: "Время вышло — стол вычислил шпиона",
    survived: "Время вышло — шпион не раскрыт",
    spy_left: "Шпион вышел из комнаты — раунд не засчитан",
    too_few: "За столом осталось слишком мало людей — раунд не засчитан",
  };

  function phaseKey(game) {
    const round = game.round;
    return round ? `${round.number}:${round.phase}` : "lobby";
  }

  function phaseName(game) {
    return PHASE_NAMES[game.round ? game.round.phase : "lobby"];
  }

  function sync(c) {
    const round = c.game.round;
    if (!round) return;
    if (round.phase === "discussion") c.setTimer("round", round.seconds_left);
    if (round.vote) c.setTimer("vote", round.vote.seconds_left);
    if (round.final_vote) c.setTimer("final", round.final_vote.seconds_left);
  }

  function drawLobby(c, round) {
    const { node, button, room } = c;
    const wrap = node("div", "spy-actions");
    wrap.append(c.codePlate());
    const { settings } = room;
    if (room.is_host) {
      const box = node("div", "spy-settings");
      box.append(node("span", "spy-label", "Режим"));
      box.append(c.segmented(Object.entries(MODE_NAMES), settings.mode,
        (mode) => c.settings({ mode, minutes: settings.minutes })));
      const label = node("label", "spy-minutes", "Длина раунда");
      const select = document.createElement("select");
      for (let minutes = 5; minutes <= 12; minutes += 1) {
        const option = new Option(`${minutes} минут`, String(minutes));
        option.selected = minutes === settings.minutes;
        select.append(option);
      }
      select.addEventListener("change", () => c.settings({ mode: settings.mode, minutes: Number(select.value) }));
      label.append(select);
      box.append(label);
      wrap.append(box);
    } else {
      wrap.append(node("p", "spy-lead", `${MODE_NAMES[settings.mode]} · ${settings.minutes} минут. Раунд запускает ведущий.`));
    }
    if (settings.mode === "hanzi") {
      wrap.append(node("p", "spy-hint", "Место показывается только иероглифами. Не узнали слово — блефуйте, как шпион."));
    }
    const count = c.view.players.length;
    if (room.is_host) {
      const start = button("btn btn-primary", round ? "Следующий раунд" : "Начать раунд", () => c.act("start"));
      start.disabled = count < room.min_players;
      wrap.append(start);
    }
    if (count < room.min_players) {
      wrap.append(node("p", "spy-progress", `За столом ${count}, нужно минимум ${room.min_players}`));
    }
    return wrap;
  }

  /* Карточка видна, только пока держишь палец. Пока держишь, опрос не
     перерисовывает экран — иначе карточка захлопнулась бы посреди чтения. */
  function drawCard(c, you) {
    const { node } = c;
    const card = node("button", "spy-card");
    card.type = "button";
    const cover = node("span", "spy-card-cover", "Удерживайте, чтобы увидеть свою карточку");
    const face = node("span", "spy-card-face");
    face.hidden = true;
    if (you.spy) {
      face.append(node("b", "spy-verdict", "ВЫ ШПИОН"),
        node("span", "spy-role", "Места вы не знаете. Слушайте вопросы, не выдайте себя и попробуйте угадать, где все."));
    } else {
      face.append(node("b", "spy-zh", you.location.zh));
      if (you.location.pinyin) face.append(node("span", "spy-pinyin", you.location.pinyin));
      if (you.location.ru) face.append(node("span", "spy-ru", you.location.ru));
      face.append(node("span", "spy-role", `Ваша роль: ${you.role}`));
    }
    card.append(cover, face);

    let open = false;
    const show = () => {
      open = true;
      c.setHolding(true);
      cover.hidden = true;
      face.hidden = false;
      card.classList.add("is-open");
    };
    const hide = () => {
      if (!open) return;
      open = false;
      cover.hidden = false;
      face.hidden = true;
      card.classList.remove("is-open");
      c.setHolding(false);
    };
    card.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      if (card.setPointerCapture) card.setPointerCapture(event.pointerId);
      show();
    });
    ["pointerup", "pointercancel", "lostpointercapture", "blur"].forEach((type) => card.addEventListener(type, hide));
    card.addEventListener("keydown", (event) => {
      if ((event.key === " " || event.key === "Enter") && !event.repeat) {
        event.preventDefault();
        show();
      }
    });
    card.addEventListener("keyup", (event) => {
      if (event.key === " " || event.key === "Enter") hide();
    });
    card.addEventListener("contextmenu", (event) => event.preventDefault());
    return card;
  }

  function togglePick(c, kind) {
    c.local.pick = c.local.pick === kind ? null : kind;
    c.disarm();
    if (kind === "guess") c.local.placesOpen = c.local.pick === "guess";
    c.redraw();
  }

  function drawDiscussion(c, round) {
    const { node, button, local } = c;
    const items = [c.timerEl("round", round.seconds_left, "ДО КОНЦА РАУНДА")];
    if (!round.you) {
      items.push(node("p", "spy-lead", "Вы подсели между раундами — сыграете в следующем."));
      return items;
    }
    items.push(drawCard(c, round.you));
    const actions = node("div", "spy-actions");
    if (round.can_accuse) {
      actions.append(button(local.pick === "accuse" ? "btn btn-primary" : "btn btn-secondary",
        local.pick === "accuse" ? "Отменить обвинение" : "Обвинить игрока", () => togglePick(c, "accuse")));
    } else {
      actions.append(node("p", "spy-progress", "Своё обвинение в этом раунде вы уже использовали."));
    }
    if (round.you.spy) {
      actions.append(button(local.pick === "guess" ? "btn btn-primary" : "btn btn-action",
        local.pick === "guess" ? "Отмена" : "Я знаю место", () => togglePick(c, "guess")));
    }
    if (local.pick === "accuse") actions.append(c.banner("Выберите игрока в списке ниже. Голосуют все остальные: одно «нет» — и обвинение снято."));
    if (local.pick === "guess") actions.append(c.banner("Выберите место в списке ниже. Ошибётесь — раунд за агентами."));
    items.push(actions);
    return items;
  }

  function drawVote(c, round) {
    const { node, button } = c;
    const vote = round.vote;
    const paused = node("div", "spy-timer is-paused");
    paused.append(document.createTextNode(c.format(round.seconds_left)), node("small", null, "ТАЙМЕР НА ПАУЗЕ"));
    const items = [paused];
    items.push(c.banner(vote.target === c.you
      ? `${c.nameOf(vote.accuser)} обвиняет вас. Защищайтесь голосом.`
      : `${c.nameOf(vote.accuser)} обвиняет: ${c.nameOf(vote.target)}`));
    if (vote.can_vote && vote.your_vote == null) {
      const row = node("div", "spy-vote-buttons");
      row.append(
        button("btn btn-primary", "Да, это шпион", () => c.act("vote", { yes: true })),
        button("btn btn-secondary", "Нет", () => c.act("vote", { yes: false })),
      );
      items.push(row);
    } else if (vote.your_vote != null) {
      items.push(node("p", "spy-lead", `Ваш голос: ${vote.your_vote ? "да" : "нет"}.`));
    }
    const progress = node("p", "spy-progress", `За: ${vote.yes} из ${vote.required} · не успевших ждём `);
    const clock = node("span", null);
    clock.dataset.timer = "vote";
    clock.append(document.createTextNode(c.format(vote.seconds_left)));
    progress.append(clock);
    items.push(progress);
    return items;
  }

  function drawFinal(c, round) {
    const { node } = c;
    const final = round.final_vote;
    const items = [c.timerEl("final", final.seconds_left, "ФИНАЛЬНОЕ ГОЛОСОВАНИЕ")];
    items.push(c.banner("Время вышло. Кто шпион? Голосуют все, решает большинство стола."));
    if (round.you && final.your_vote == null) items.push(node("p", "spy-lead", "Выберите игрока в списке ниже."));
    else if (final.your_vote != null) items.push(node("p", "spy-lead", `Ваш голос: ${c.nameOf(final.your_vote)}.`));
    items.push(node("p", "spy-progress", `Проголосовали ${final.voted} из ${final.expected}`));
    return items;
  }

  function choosePlayer(c, round, id) {
    if (round.phase === "final_vote") {
      c.confirmTwice(`final:${id}`, `шпион — ${c.nameOf(id)}`,
        () => c.act("final-vote", { target_account_id: id }));
    } else {
      // «обвинение — Имя», а не «обвинить Имя»: склонять имена по падежам
      // код не умеет, и «обвинить Тимур» режет глаз.
      c.confirmTwice(`accuse:${id}`, `обвинение — ${c.nameOf(id)}`, () => {
        c.local.pick = null;
        c.act("accuse", { target_account_id: id });
      });
    }
  }

  function drawPlayers(c, round) {
    const live = round && round.phase !== "reveal";
    const inRound = live ? new Set(round.participants) : new Set();
    const selecting = Boolean(live && round.you && (
      (round.phase === "discussion" && c.local.pick === "accuse") ||
      (round.phase === "final_vote" && round.final_vote.your_vote == null)));
    const prefix = round && round.phase === "final_vote" ? "final:" : "accuse:";
    return c.playersList({
      armedPrefix: selecting ? prefix : null,
      selectable: (p) => selecting && p.account_id !== c.you && inRound.has(p.account_id),
      keyFor: (p) => `${prefix}${p.account_id}`,
      onPick: (p) => choosePlayer(c, round, p.account_id),
      tags: (p) => (live && !inRound.has(p.account_id) ? ["ждёт следующего раунда"] : []),
    });
  }

  function drawPlaces(c, round) {
    const { node } = c;
    const places = c.game.locations;
    const details = node("details", "spy-places");
    details.open = Boolean(c.local.placesOpen || c.local.pick === "guess");
    details.addEventListener("toggle", () => { c.local.placesOpen = details.open; });
    details.append(node("summary", null, `Возможные места · ${places.length}`));
    const banner = c.armedBanner("place:");
    if (banner) {
      banner.classList.add("spy-banner-inset");
      details.append(banner);
    }
    const grid = node("div", "spy-place-grid");
    const guessing = c.local.pick === "guess" && round.phase === "discussion" && round.you && round.you.spy;
    for (const place of places) {
      const cell = node(guessing ? "button" : "div", "spy-place");
      if (guessing) {
        cell.type = "button";
        if (c.armed() === `place:${place.id}`) cell.classList.add("is-armed");
        cell.addEventListener("click", () =>
          c.confirmTwice(`place:${place.id}`, `место — ${place.zh}${place.ru ? ` (${place.ru})` : ""}`, () => {
            c.local.pick = null;
            c.act("guess", { location_id: place.id });
          }));
      }
      cell.append(node("b", null, place.zh));
      if (place.ru) cell.append(node("span", null, place.ru));
      grid.append(cell);
    }
    details.append(grid);
    return details;
  }

  function drawResult(c, round) {
    const { node } = c;
    const result = round.result;
    const card = node("div", `spy-reveal${result.winner === "spy" ? " is-spy" : ""}`);
    card.append(node("span", "spy-label", `Раунд ${round.number}`), node("h3", null, REASONS[result.reason] || "Раунд окончен"));
    card.append(node("p", "spy-lead", `Шпион: ${c.nameOf(result.spy)}`));
    card.append(node("b", "spy-zh", result.location.zh), node("span", "spy-pinyin", result.location.pinyin),
      node("span", "spy-ru", result.location.ru));
    if (result.guessed) {
      card.append(node("p", "spy-progress", `Шпион назвал: ${result.guessed.zh} · ${result.guessed.ru}`));
    }
    const entries = Object.entries(result.points || {});
    if (entries.length) {
      const list = node("ul", "spy-points");
      for (const [id, amount] of entries) list.append(node("li", null, `+${amount} ${c.nameOf(id)}`));
      card.append(list);
    } else {
      card.append(node("p", "spy-progress", "Очков в этом раунде никто не получил."));
    }
    return card;
  }

  function draw(c) {
    const round = c.game.round;
    const parts = [];
    if (!round || round.phase === "reveal") {
      if (round && round.result) parts.push(drawResult(c, round));
      parts.push(drawLobby(c, round));
    } else if (round.phase === "discussion") {
      parts.push(...drawDiscussion(c, round));
    } else if (round.phase === "vote") {
      parts.push(...drawVote(c, round));
    } else if (round.phase === "final_vote") {
      parts.push(...drawFinal(c, round));
    }
    parts.push(drawPlayers(c, round));
    if (round && round.phase !== "reveal") parts.push(drawPlaces(c, round));
    return parts;
  }

  const finished = (game) => Boolean(game.round && game.round.result);
  window.ZhidaoGames.register("spy", { phaseKey, phaseName, sync, draw, finished });
}());
