"use strict";

/* Вечерние игры. Сейчас здесь «Шпион Протокола» (V4_GAMES.md §4.9).

   Телефон здесь не судья. Кто шпион, какое место, сколько осталось и чем
   кончилось голосование, решает сервер; экран показывает только то, что
   сервер прислал именно этому игроку. Поэтому в файле нет проверок правил —
   только отрисовка и запросы. Кнопку можно подделать; исход нельзя.

   Опрос раз в две секунды, пока экран открыт. Свернули MAX, заблокировали
   телефон — опрос встаёт; вернулись — первым делом спрашиваем, что
   изменилось. Партия от этого не ломается: она живёт на сервере. */

(function () {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 2000;
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
    accused: "Стол единогласно поймал шпиона",
    framed: "Стол осудил невиновного",
    final_vote: "Время вышло — стол вычислил шпиона",
    survived: "Время вышло — шпион не раскрыт",
    spy_left: "Шпион вышел из комнаты — раунд не засчитан",
    too_few: "За столом осталось слишком мало людей — раунд не засчитан",
  };

  let session = window.ZhidaoSession || null;
  let view = null;
  let switches = {};
  let signature = "";
  let pollTimer = null;
  let clockTimer = null;
  let refreshing = false;
  let inFlight = false;
  let pick = null;          // "accuse" | "guess" | null — что сейчас выбирают касанием
  let armed = null;         // выбор, ждущий второго касания
  let armedLabel = "";
  let leaveArmed = false;
  let placesOpen = false;
  let holding = false;      // палец на карточке: перерисовку откладываем
  let pendingDraw = false;
  let timers = {};          // ключ → момент конца по performance.now()
  const zeroRefreshed = new Set();

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function button(className, text, onClick) {
    const b = node("button", className, text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function signedIn() { return Boolean(session && session.mode === "authenticated"); }
  function onScreen() { return document.documentElement.dataset.currentScreen === "games"; }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const init = {
      method: options.method || "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    };
    if (init.method === "POST") {
      const cookie = document.cookie.split("; ").find((v) => v.startsWith("zhidao_v4_csrf="));
      init.headers["X-CSRF-Token"] = cookie ? decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) : "";
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body || {});
    }
    try {
      const response = await fetch(path, init);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof data.detail === "string" ? data.detail : "Запрос отклонён.");
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Сервер не ответил. Проверьте связь.");
      if (error instanceof TypeError) throw new Error("Нет связи с сервером.");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function nameOf(id) {
    const player = view && view.players.find((p) => p.account_id === Number(id));
    return player ? player.display_name : "игрок вышел";
  }

  function setNote(text) {
    const target = view ? $("spyNote") : $("spyIntroStatus");
    if (target) target.textContent = text || "";
  }

  // --- время -------------------------------------------------------------------

  function format(seconds) {
    const s = Math.max(0, Math.ceil(seconds));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  /* Сервер присылает «осталось N секунд», а не момент на своих часах: часы
     телефона бывают сбиты на минуты. Локально отсчитываем от получения и
     подправляем, только если разошлись заметно — иначе цифры прыгают. */
  function setTimer(key, seconds) {
    if (seconds == null) return;
    const end = performance.now() + seconds * 1000;
    if (timers[key] == null || Math.abs(timers[key] - end) > 1500) timers[key] = end;
  }

  function tickClocks() {
    const now = performance.now();
    document.querySelectorAll("#spyRoom [data-timer]").forEach((el) => {
      const key = el.dataset.timer;
      if (timers[key] == null) return;
      const left = (timers[key] - now) / 1000;
      el.firstChild.textContent = format(left);
      el.classList.toggle("is-low", left <= 30);
      // Время вышло на экране — спрашиваем сервер сразу, не дожидаясь опроса.
      if (left <= 0 && !zeroRefreshed.has(key)) {
        zeroRefreshed.add(key);
        refresh();
      }
    });
  }

  function timerEl(key, seconds, caption) {
    const el = node("div", "spy-timer");
    el.dataset.timer = key;
    el.append(document.createTextNode(format(seconds || 0)));
    if (caption) el.append(node("small", null, caption));
    return el;
  }

  // --- опрос -------------------------------------------------------------------

  function startPolling() {
    if (!view || !onScreen() || document.hidden) return;
    if (!pollTimer) pollTimer = setInterval(() => { if (!inFlight) refresh(); }, POLL_MS);
    if (!clockTimer) clockTimer = setInterval(tickClocks, 250);
  }

  function stopPolling() {
    clearInterval(pollTimer);
    clearInterval(clockTimer);
    pollTimer = null;
    clockTimer = null;
  }

  async function refresh() {
    if (!signedIn()) { drawIntro(); return; }
    if (refreshing) return;
    refreshing = true;
    try {
      apply(await api("/api/v4/games/rooms/current"));
    } catch (error) {
      setNote(error.message);
    } finally {
      refreshing = false;
    }
  }

  function apply(data) {
    if (data && data.switches) switches = data.switches;
    if (!data || !data.room) {
      view = null;
      signature = "";
      pick = null;
      armed = null;
      timers = {};
      stopPolling();
      drawIntro();
      return;
    }
    const before = view && view.spy.round;
    const round = data.spy.round;
    if (!before || !round || before.phase !== round.phase || before.number !== round.number) {
      pick = null;
      armed = null;
      timers = {};
      zeroRefreshed.clear();
      // Подсказка прошлой фазы («нажмите ещё раз…») к новой не относится.
      if (before) $("spyNote").textContent = "";
    }
    view = data;
    if (round) {
      if (round.phase === "discussion") setTimer("round", round.seconds_left);
      if (round.vote) setTimer("vote", round.vote.seconds_left);
      if (round.final_vote) setTimer("final", round.final_vote.seconds_left);
    }
    const next = [
      data.room.revision,
      data.players.map((p) => `${p.account_id}:${p.present ? 1 : 0}`).join(","),
    ].join("|");
    if (next !== signature) {
      signature = next;
      draw();
    }
    startPolling();
  }

  // --- действия -------------------------------------------------------------------

  async function run(task) {
    if (inFlight) return;
    inFlight = true;
    setNote("");
    try {
      apply(await task());
    } catch (error) {
      setNote(error.message);
      if (error.status === 404) refresh();
    } finally {
      inFlight = false;
    }
  }

  const post = (suffix, body) =>
    api(`/api/v4/games/rooms/${view.room.code}${suffix}`, { method: "POST", body });

  function redraw() { signature = ""; apply(view); }

  function togglePick(kind) {
    pick = pick === kind ? null : kind;
    armed = null;
    if (kind === "guess") placesOpen = pick === "guess";
    redraw();
  }

  /* Обвинение, голос и названное место не отменить. Поэтому первое касание
     только выбирает, второе — подтверждает; промах пальцем в толпе за столом
     не должен решать раунд. */
  function confirmTwice(key, label, commit) {
    if (armed !== key) {
      armed = key;
      // Подсказка встаёт прямо над списком, где выбирают: строка внизу окна
      // на телефоне оказывалась под двадцатью четырьмя местами.
      armedLabel = label;
      redraw();
      return;
    }
    armed = null;
    pick = null;
    commit();
  }

  function choosePlayer(id) {
    const phase = view.spy.round && view.spy.round.phase;
    if (phase === "final_vote") {
      confirmTwice(`final:${id}`, `шпион — ${nameOf(id)}`,
        () => run(() => post("/spy/final-vote", { target_account_id: id })));
    } else {
      // «обвинение — Имя», а не «обвинить Имя»: склонять имена по падежам
      // код не умеет, и «обвинить Тимур» режет глаз.
      confirmTwice(`accuse:${id}`, `обвинение — ${nameOf(id)}`,
        () => run(() => post("/spy/accuse", { target_account_id: id })));
    }
  }

  function choosePlace(place) {
    confirmTwice(`place:${place.id}`, `место — ${place.zh}${place.ru ? ` (${place.ru})` : ""}`,
      () => run(() => post("/spy/guess", { location_id: place.id })));
  }

  function leave() {
    const round = view.spy.round;
    const live = round && round.phase !== "reveal";
    if (!leaveArmed) {
      leaveArmed = true;
      setNote(live
        ? "Нажмите × ещё раз, чтобы выйти. Если вы шпион, раунд не засчитается."
        : "Нажмите × ещё раз, чтобы выйти из комнаты.");
      setTimeout(() => { leaveArmed = false; }, 4000);
      return;
    }
    leaveArmed = false;
    run(() => post("/leave"));
  }

  // --- отрисовка -------------------------------------------------------------------

  function drawIntro() {
    $("spyIntro").hidden = false;
    $("spyRoom").hidden = true;
    const disabled = switches.spy === false;
    $("spyCreate").disabled = !signedIn() || disabled;
    $("spyJoinSubmit").disabled = !signedIn() || disabled;
    if (!signedIn()) $("spyIntroStatus").textContent = "Войдите, чтобы играть.";
    else if (disabled) $("spyIntroStatus").textContent = "Игра сейчас выключена организаторами.";
  }

  function draw() {
    if (holding) { pendingDraw = true; return; }
    pendingDraw = false;
    const { room } = view;
    const round = view.spy.round;
    $("spyIntro").hidden = true;
    $("spyRoom").hidden = false;
    $("spyRoomTitle").textContent = `Комната ${room.code}`;
    $("spyRoomPhase").textContent = PHASE_NAMES[round ? round.phase : "lobby"];

    const parts = [];
    if (!round || round.phase === "reveal") {
      if (round && round.result) parts.push(drawResult(round));
      parts.push(drawLobby(round));
    } else if (round.phase === "discussion") {
      parts.push(...drawDiscussion(round));
    } else if (round.phase === "vote") {
      parts.push(...drawVote(round));
    } else if (round.phase === "final_vote") {
      parts.push(...drawFinal(round));
    }
    parts.push(drawPlayers(round));
    if (round && round.phase !== "reveal") parts.push(drawPlaces(round));
    $("spyRoomBody").replaceChildren(...parts);
    tickClocks();
  }

  function drawLobby(round) {
    const { room } = view;
    const wrap = node("div", "spy-body-part spy-actions");
    const plate = node("div", "spy-code-plate");
    plate.append(node("span", "spy-label", "Код комнаты"), node("b", "spy-code", room.code),
      node("span", "spy-hint", "Продиктуйте его остальным"));
    wrap.append(plate);

    const { settings } = room;
    if (room.is_host) {
      const box = node("div", "spy-settings");
      box.append(node("span", "spy-label", "Режим"));
      const segmented = node("div", "spy-segmented");
      for (const mode of ["translated", "hanzi"]) {
        const b = button("btn btn-secondary", MODE_NAMES[mode],
          () => run(() => post("/settings", { mode, minutes: settings.minutes })));
        b.setAttribute("aria-pressed", String(settings.mode === mode));
        segmented.append(b);
      }
      box.append(segmented);
      const label = node("label", "spy-minutes", "Длина раунда");
      const select = document.createElement("select");
      for (let minutes = 5; minutes <= 12; minutes += 1) {
        const option = new Option(`${minutes} минут`, String(minutes));
        option.selected = minutes === settings.minutes;
        select.append(option);
      }
      select.addEventListener("change", () =>
        run(() => post("/settings", { mode: settings.mode, minutes: Number(select.value) })));
      label.append(select);
      box.append(label);
      wrap.append(box);
    } else {
      wrap.append(node("p", "spy-lead", `${MODE_NAMES[settings.mode]} · ${settings.minutes} минут. Раунд запускает ведущий.`));
    }
    if (settings.mode === "hanzi") {
      wrap.append(node("p", "spy-hint", "Место показывается только иероглифами. Не узнали слово — блефуйте, как шпион."));
    }

    const count = view.players.length;
    if (room.is_host) {
      const start = button("btn btn-primary", round ? "Следующий раунд" : "Начать раунд",
        () => run(() => post("/spy/start")));
      start.disabled = count < room.min_players;
      wrap.append(start);
    }
    if (count < room.min_players) {
      wrap.append(node("p", "spy-progress", `За столом ${count}, нужно минимум ${room.min_players}`));
    }
    return wrap;
  }

  function drawCard(you) {
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

    const show = () => {
      holding = true;
      cover.hidden = true;
      face.hidden = false;
      card.classList.add("is-open");
    };
    const hide = () => {
      if (!holding) return;
      holding = false;
      cover.hidden = false;
      face.hidden = true;
      card.classList.remove("is-open");
      if (pendingDraw) draw();
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

  function drawDiscussion(round) {
    const items = [timerEl("round", round.seconds_left, "ДО КОНЦА РАУНДА")];
    if (!round.you) {
      items.push(node("p", "spy-lead", "Вы подсели между раундами — сыграете в следующем."));
      return items;
    }
    items.push(drawCard(round.you));
    const actions = node("div", "spy-actions");
    if (round.can_accuse) {
      actions.append(button(pick === "accuse" ? "btn btn-primary" : "btn btn-secondary",
        pick === "accuse" ? "Отменить обвинение" : "Обвинить игрока", () => togglePick("accuse")));
    } else {
      actions.append(node("p", "spy-progress", "Своё обвинение в этом раунде вы уже использовали."));
    }
    if (round.you.spy) {
      actions.append(button(pick === "guess" ? "btn btn-primary" : "btn btn-action",
        pick === "guess" ? "Отмена" : "Я знаю место", () => togglePick("guess")));
    }
    if (pick === "accuse") actions.append(node("p", "spy-banner", "Выберите игрока в списке ниже. Голосуют все остальные: одно «нет» — и обвинение снято."));
    if (pick === "guess") actions.append(node("p", "spy-banner", "Выберите место в списке ниже. Ошибётесь — раунд за агентами."));
    items.push(actions);
    return items;
  }

  function drawVote(round) {
    const vote = round.vote;
    const paused = node("div", "spy-timer is-paused");
    paused.append(document.createTextNode(format(round.seconds_left)), node("small", null, "ТАЙМЕР НА ПАУЗЕ"));
    const items = [paused];
    items.push(node("p", "spy-banner", vote.target === view.you
      ? `${nameOf(vote.accuser)} обвиняет вас. Защищайтесь голосом.`
      : `${nameOf(vote.accuser)} обвиняет: ${nameOf(vote.target)}`));
    if (vote.can_vote && vote.your_vote == null) {
      const row = node("div", "spy-vote-buttons");
      row.append(
        button("btn btn-primary", "Да, это шпион", () => run(() => post("/spy/vote", { yes: true }))),
        button("btn btn-secondary", "Нет", () => run(() => post("/spy/vote", { yes: false }))),
      );
      items.push(row);
    } else if (vote.your_vote != null) {
      items.push(node("p", "spy-lead", `Ваш голос: ${vote.your_vote ? "да" : "нет"}.`));
    }
    const progress = node("p", "spy-progress", `За: ${vote.yes} из ${vote.required} · не успевших ждём `);
    const clock = node("span", null);
    clock.dataset.timer = "vote";
    clock.append(document.createTextNode(format(vote.seconds_left)));
    progress.append(clock);
    items.push(progress);
    return items;
  }

  function drawFinal(round) {
    const final = round.final_vote;
    const items = [timerEl("final", final.seconds_left, "ФИНАЛЬНОЕ ГОЛОСОВАНИЕ")];
    items.push(node("p", "spy-banner", "Время вышло. Кто шпион? Голосуют все, решает большинство."));
    if (round.you && final.your_vote == null) items.push(node("p", "spy-lead", "Выберите игрока в списке ниже."));
    else if (final.your_vote != null) items.push(node("p", "spy-lead", `Ваш голос: ${nameOf(final.your_vote)}.`));
    items.push(node("p", "spy-progress", `Проголосовали ${final.voted} из ${final.expected}`));
    return items;
  }

  function drawPlayers(round) {
    const wrap = node("div", "spy-actions");
    wrap.append(node("span", "spy-label", "За столом · очки вечера"));
    if (armed && !armed.startsWith("place:")) {
      wrap.append(node("p", "spy-banner", `Нажмите ещё раз, чтобы подтвердить: ${armedLabel}.`));
    }
    const list = node("div", "spy-players");
    const live = round && round.phase !== "reveal";
    const inRound = live ? new Set(round.participants) : null;
    const selecting = live && round.you && (
      (round.phase === "discussion" && pick === "accuse") ||
      (round.phase === "final_vote" && round.final_vote.your_vote == null));
    for (const player of view.players) {
      const eligible = selecting && player.account_id !== view.you && inRound.has(player.account_id);
      const row = node(eligible ? "button" : "div", "spy-player");
      if (eligible) {
        row.type = "button";
        const key = `${round.phase === "final_vote" ? "final" : "accuse"}:${player.account_id}`;
        if (armed === key) row.classList.add("is-armed");
        row.addEventListener("click", () => choosePlayer(player.account_id));
      }
      if (!player.present) row.classList.add("is-away");
      const dot = node("span", `spy-dot${player.present ? " is-on" : ""}`);
      dot.setAttribute("aria-hidden", "true");
      const name = node("span", "spy-player-name", player.display_name);
      const tags = [];
      if (player.account_id === view.room.host_account_id) tags.push("ведущий");
      if (player.account_id === view.you) tags.push("вы");
      if (live && !inRound.has(player.account_id)) tags.push("ждёт следующего раунда");
      if (!player.present) tags.push("нет на связи");
      if (tags.length) name.append(node("small", null, tags.join(" · ")));
      row.append(dot, name, node("span", "spy-score", String(player.score)));
      list.append(row);
    }
    wrap.append(list);
    return wrap;
  }

  function drawPlaces(round) {
    const places = view.spy.locations;
    const details = node("details", "spy-places");
    details.open = placesOpen || pick === "guess";
    details.addEventListener("toggle", () => { placesOpen = details.open; });
    details.append(node("summary", null, `Возможные места · ${places.length}`));
    if (armed && armed.startsWith("place:")) {
      const banner = node("p", "spy-banner spy-banner-inset", `Нажмите ещё раз, чтобы подтвердить: ${armedLabel}.`);
      details.append(banner);
    }
    const grid = node("div", "spy-place-grid");
    const guessing = pick === "guess" && round.phase === "discussion" && round.you && round.you.spy;
    for (const place of places) {
      const cell = node(guessing ? "button" : "div", "spy-place");
      if (guessing) {
        cell.type = "button";
        if (armed === `place:${place.id}`) cell.classList.add("is-armed");
        cell.addEventListener("click", () => choosePlace(place));
      }
      cell.append(node("b", null, place.zh));
      if (place.ru) cell.append(node("span", null, place.ru));
      grid.append(cell);
    }
    details.append(grid);
    return details;
  }

  function drawResult(round) {
    const result = round.result;
    const card = node("div", `spy-reveal${result.winner === "spy" ? " is-spy" : ""}`);
    card.append(node("span", "spy-label", `Раунд ${round.number}`), node("h3", null, REASONS[result.reason] || "Раунд окончен"));
    card.append(node("p", "spy-lead", `Шпион: ${nameOf(result.spy)}`));
    card.append(node("b", "spy-zh", result.location.zh), node("span", "spy-pinyin", result.location.pinyin),
      node("span", "spy-ru", result.location.ru));
    if (result.guessed) {
      card.append(node("p", "spy-progress", `Шпион назвал: ${result.guessed.zh} · ${result.guessed.ru}`));
    }
    const entries = Object.entries(result.points || {});
    if (entries.length) {
      const list = node("ul", "spy-points");
      for (const [id, amount] of entries) list.append(node("li", null, `+${amount} ${nameOf(id)}`));
      card.append(list);
    } else {
      card.append(node("p", "spy-progress", "Очков в этом раунде никто не получил."));
    }
    return card;
  }

  // --- подключение ---------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    view = null;
    signature = "";
    pick = null;
    armed = null;
    stopPolling();
    $("spyIntroStatus").textContent = "";
    drawIntro();
    if (onScreen() && signedIn()) refresh();
  });

  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "games") refresh();
    else stopPolling();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling();
    else if (onScreen()) refresh();
  });

  $("spyCreate").addEventListener("click", () =>
    run(() => api("/api/v4/games/rooms", { method: "POST", body: { game: "spy" } })));

  $("spyJoinCode").addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 4);
  });

  $("spyJoinForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const code = $("spyJoinCode").value.replace(/\D/g, "");
    if (code.length !== 4) {
      $("spyIntroStatus").textContent = "Код комнаты — четыре цифры.";
      return;
    }
    run(() => api("/api/v4/games/rooms/join", { method: "POST", body: { code } }));
  });

  $("spyLeave").addEventListener("click", leave);

  drawIntro();
}());
