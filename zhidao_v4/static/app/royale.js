"use strict";

/* Протокол 60 — королевская битва на всю смену (V4_GAMES.md §4.12).

   Вожатый открывает лобби и выводит «Большой экран» на ноутбук у телевизора.
   Участники входят со своих телефонов в «Ивентах». Все одновременно отвечают на
   китайское слово; ошибся или не успел — выбыл. Между раундами выбывшие
   голосуют за сюрприз выжившим и могут один раз воскреснуть за звёзды.

   Всё решает сервер (zhidao_v4/royale.py): время, кто выбыл, места и призы.
   Правильный вариант сюда приходит только в разборе раунда, первое слово — только
   после заставки. Панель перерисовывается, только когда ответ сервера изменился,
   а отсчёт меняет одну цифру — чтобы нажатие на вариант не терялось.

   Шоу (доработка по оценке пользователя 2026-09-13): логотип и бегущая строка в
   лобби, заставка 3-2-1, появление вопроса, горячий таймер на последних трёх
   секундах, волна гаснущих аватарок и тряска экрана при массовом выбывании,
   прокрутка счётчика «выбыло», вспышка правильного ответа, экран «вы выбыли»,
   конфетти и пьедестал в финале. Движение живёт только при data-motion="full";
   звуки — через ZhidaoSounds и молчат без купленного набора. */

(function () {
  const $ = (id) => document.getElementById(id);
  const SURPRISE = { fast: "−3 секунды", hanzi: "Без пиньиня", more: "+1 вариант", mirror: "Зеркальный иероглиф", shuffle: "Варианты бегают" };
  const LEAD = "Вся смена одновременно отвечает на китайские слова. Ошибся или не успел — выбыл. Последний выживший забирает главный приз";
  const MARQUEE = "ЗАХОДИТЕ: ИВЕНТЫ → ПРОТОКОЛ 60 · 大逃杀 · ОДНА ОШИБКА — И ВЫ ВЫБЫЛИ · ПОСЛЕДНИЙ ВЫЖИВШИЙ ЗАБИРАЕТ ГЛАВНЫЙ ПРИЗ · ";
  const CONFETTI = ["#ffd54a", "#ff7ab8", "#7dffb0", "#6ec3ff", "#b58cff"];

  let session = window.ZhidaoSession || null;
  let data = null;
  let signature = "";
  let busy = false;
  let note = "";
  let armed = null;
  let poll = null;
  let pollMs = 0;
  let ticker = null;
  let stageOpen = false;
  let reviveKey = null;
  let seenRound = null;         // вопрос, чьё появление уже проиграно
  let seenReveal = null;        // разбор, чьи вспышка и счётчик уже проиграны
  let celebrated = null;        // игра, чей финал уже отпраздновали
  let stageAlive = new Map();   // кто был жив на прошлой отрисовке большого экрана
  let stageSeen = new Set();    // кого большой экран уже показал в лобби
  let tickSecond = null;
  let introTimer = null;
  let justOut = 0;
  let fx = null;
  let shuffledAt = 0;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function button(className, text, onClick) {
    const b = node("button", className, text);
    b.type = "button";
    b.disabled = busy;
    b.addEventListener("click", onClick);
    return b;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onGames = () => document.documentElement.dataset.currentScreen === "games";
  const moving = () => document.documentElement.dataset.motion === "full";
  const sound = (event) => window.ZhidaoSounds?.play(event);
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));
  const newKey = () => `royale-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
  const initial = (name) => (String(name || "?").trim()[0] || "?").toUpperCase();
  const secondsLeft = (until) => Math.max(0, Math.ceil((Number(until) - Date.now()) / 1000));

  function countdown(iso, hot) {
    const span = node("span", "royale-left");
    span.dataset.until = String(timeOf(iso));
    if (hot) span.dataset.hot = "1";
    span.textContent = `${secondsLeft(span.dataset.until)} с`;
    return span;
  }

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
      if (options.key) init.headers["X-Idempotency-Key"] = options.key;
      init.body = JSON.stringify(options.body || {});
    }
    try {
      const response = await fetch(path, init);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof body.detail === "string" ? body.detail : "Запрос отклонён.");
        error.status = response.status;
        throw error;
      }
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Сервер не ответил. Проверьте связь.");
      if (error instanceof TypeError) throw new Error("Нет связи с сервером.");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  // --- шоу ----------------------------------------------------------------------------------

  function logo(big) {
    const box = node("div", `royale-logo${big ? " is-big" : ""}`);
    box.setAttribute("role", "img");
    box.setAttribute("aria-label", "Протокол 60");
    box.append(node("b", null, "ПРОТОКОЛ"), node("span", null, "60"), node("i", null, "大逃杀"));
    return box;
  }

  function marquee() {
    const box = node("div", "royale-marquee");
    const track = node("div", "royale-marquee-track");
    const copy = node("span", null, MARQUEE);
    copy.setAttribute("aria-hidden", "true");
    track.append(node("span", null, MARQUEE), copy);
    box.append(track);
    return box;
  }

  function intro(iso, big) {
    const box = node("div", `royale-intro${big ? " is-big" : ""}`);
    const count = node("b", "royale-intro-count");
    count.dataset.until = String(timeOf(iso));
    count.textContent = String(Math.max(1, secondsLeft(count.dataset.until)));
    box.append(node("p", "royale-intro-label", "Битва начинается"), count);
    return box;
  }

  function roll(value, animate) {
    const span = node("b", "royale-roll", String(value));
    if (animate && moving() && value > 0) {
      span.textContent = "0";
      const started = performance.now();
      const step = (moment) => {
        const k = Math.min(1, (moment - started) / 700);
        span.textContent = String(Math.round(value * k));
        if (k < 1 && span.isConnected) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    return span;
  }

  function confetti() {
    if (!moving()) return;
    if (!fx) {
      fx = node("div", "royale-fx");
      fx.setAttribute("aria-hidden", "true");
      document.body.append(fx);
    }
    const layer = node("div");
    for (let i = 0; i < 56; i += 1) {
      const bit = node("i");
      bit.style.left = `${Math.random() * 100}%`;
      bit.style.background = CONFETTI[i % CONFETTI.length];
      bit.style.animationDelay = `${(Math.random() * 1.4).toFixed(2)}s`;
      bit.style.setProperty("--drift", `${Math.round(Math.random() * 200 - 100)}px`);
      layer.append(bit);
    }
    fx.append(layer);
    setTimeout(() => layer.remove(), 5000);
  }

  function shake(game) {
    const lost = game.reveal.eliminated;
    if (!moving() || lost < 3 || lost * 3 < game.alive + lost) return;
    const stage = $("royaleStage");
    stage.classList.remove("is-shake");
    void stage.offsetWidth;
    stage.classList.add("is-shake");
    setTimeout(() => stage.classList.remove("is-shake"), 700);
  }

  // --- куски панели ------------------------------------------------------------------------

  // Классы вариантов по типу раунда: иероглифы, пиньинь с тонами, числа.
  function kindClass(question) {
    const kind = question.kind || "word";
    return `${question.direction === "ru" ? " is-hanzi" : ""}${kind === "tone" ? " is-pinyin" : ""}${kind === "number" ? " is-number" : ""}`;
  }

  function prompt(question, big, fresh) {
    const box = node("div", `royale-question${big ? " is-big" : ""}${fresh ? " is-new" : ""}`);
    const kind = question.kind || "word";
    if (question.final) box.append(node("span", "royale-final", "ФИНАЛЬНАЯ ДУЭЛЬ"));
    if (question.prompt.zh) {
      box.append(node("b", `royale-hanzi${question.surprise === "mirror" ? " is-mirror" : ""}`, question.prompt.zh));
      if (kind === "tone") box.append(node("p", "royale-pinyin", "Как это читается? Угадайте тон"));
      else if (kind === "number") box.append(node("p", "royale-pinyin", "Какое это число?"));
      else if (question.prompt.pinyin) box.append(node("p", "royale-pinyin", question.prompt.pinyin));
    } else {
      box.append(node("b", "royale-word", question.prompt.ru), node("p", "royale-pinyin", "Найдите иероглиф"));
    }
    if (question.surprise) box.append(node("span", "royale-surprise", `Сюрприз раунда: ${SURPRISE[question.surprise]}`));
    return box;
  }

  function optionsReveal(game, fresh) {
    const list = node("div", `royale-options is-reveal${kindClass(game.question)}`);
    game.question.options.forEach((text, index) => {
      const item = node("div", "royale-option", text);
      if (index === game.reveal.answer) item.classList.add("is-right");
      if (index === game.reveal.answer && fresh) item.classList.add("is-flash");
      if (game.me && game.me.choice === index && index !== game.reveal.answer) item.classList.add("is-wrong");
      list.append(item);
    });
    return list;
  }

  function outCard(me, game) {
    const card = node("section", `royale-out${Date.now() < justOut ? " is-just-out" : ""}`);
    card.append(node("b", null, "ВЫ ВЫБЫЛИ"),
      node("p", null, `Раунд ${me.out_round}. В игре ${game.alive} из ${game.starters} — следите за битвой`));
    return card;
  }

  function drawIdle() {
    const parts = [logo(false), node("p", "spy-lead", LEAD)];
    const prizes = data.prizes || [];
    if (prizes.length) {
      parts.push(node("p", "royale-meta",
        `Призы: ${prizes.map((p, i) => `${i + 1} место — ${p.stars}★ и ${p.rep} REP`).join(" · ")} (в играх от ${data.prize_min_players} человек, один приз в день)`));
    }
    parts.push(node("p", "royale-meta", data.can_host ? "Откройте лобби, когда смена соберётся" : "Игру открывает вожатый — ждите объявления"));
    return parts;
  }

  function drawLobby(game) {
    const parts = [logo(false), marquee(), node("b", "royale-count", `В лобби: ${game.players}`)];
    if (data.can_play) {
      const actions = node("div", "capture-actions");
      if (game.me) {
        parts.push(node("p", "royale-meta is-ok", "Вы в игре. Ждём старта"));
        actions.append(button("btn btn-secondary", "Выйти из лобби", () => act("leave")));
      } else {
        actions.append(button("btn btn-primary", "Войти в игру", () => act("join")));
      }
      parts.push(actions);
    }
    return parts;
  }

  function drawIntro(game) {
    const parts = [logo(false), intro(game.intro_until, false)];
    parts.push(node("p", "royale-meta", game.me ? "Приготовьтесь: одна ошибка — и вы выбыли" : "Битва начинается — смотрите со стороны"));
    return parts;
  }

  function drawQuestion(game, fresh) {
    const parts = [];
    const me = game.me;
    if (me && !me.alive) parts.push(outCard(me, game));
    const head = node("p", "royale-meta", `Раунд ${game.round} · живых ${game.alive} из ${game.starters} · ответили ${game.answered} · `);
    head.append(countdown(game.question.deadline, true));
    parts.push(head, prompt(game.question, false, fresh));
    if (me && me.alive && !me.answered) {
      const options = node("div", `royale-options${kindClass(game.question)}${fresh ? " is-new" : ""}`);
      if (game.question.surprise === "shuffle") options.dataset.shuffle = "1";
      game.question.options.forEach((text, index) => options.append(button("btn btn-secondary", text, () => act("answer", { choice: index }))));
      parts.push(options);
    } else if (me && me.alive) {
      parts.push(node("p", "royale-meta is-ok", "Ответ принят. Ждём остальных…"));
    } else if (!me) {
      parts.push(node("p", "royale-meta", "Вы смотрите битву со стороны"));
    }
    return parts;
  }

  function drawReveal(game, fresh) {
    const parts = [];
    const me = game.me;
    if (me && !me.alive) parts.push(outCard(me, game));
    const head = node("p", "royale-meta", "Выбыло ");
    head.append(roll(game.reveal.eliminated, fresh), ` · осталось ${game.alive} · следующий раунд через `, countdown(game.reveal.until));
    parts.push(head, prompt(game.question, false, false), optionsReveal(game, fresh));
    if (me && me.alive) {
      parts.push(node("p", "royale-meta is-ok", me.choice === game.reveal.answer ? "Верно! Вы в игре" : "Вы в игре"));
    } else if (me) {
      if (me.can_revive) parts.push(button("btn btn-primary", `Воскреснуть за ${game.revive_price}★`, revive));
      parts.push(node("span", "capture-label", "Сюрприз выжившим в следующем раунде"));
      const votes = node("div", "royale-votes");
      Object.entries(SURPRISE).forEach(([code, label]) => {
        const b = button("btn btn-secondary", `${label} · ${game.reveal.votes[code]}`, () => act("vote", { surprise: code }));
        b.setAttribute("aria-pressed", String(me.vote === code));
        votes.append(b);
      });
      parts.push(votes);
    }
    return parts;
  }

  function drawResults(game) {
    const parts = [];
    if (game.cancelled) {
      parts.push(node("p", "royale-meta", "Игру остановил вожатый. Оплаченные воскрешения вернулись"));
      return parts;
    }
    const place = game.me && game.me.place;
    if (place === 1) {
      const win = node("section", "royale-win");
      win.append(node("b", null, "ПОБЕДА!"), node("p", null, "Вы — последний выживший смены"));
      parts.push(win);
    } else if (place && place <= 3) {
      parts.push(node("p", "royale-meta is-ok", `Вы в тройке лучших: ${place} место`));
    }
    const list = node("ol", "royale-results");
    game.results.forEach((r) => {
      const item = node("li", r.place <= 3 ? `is-top is-place-${r.place}` : "");
      item.append(node("b", null, r.name));
      if (r.prize) item.append(node("span", null, `+${r.prize.stars}★ · +${r.prize.rep} REP`));
      else if (r.limited) item.append(node("span", null, "приз сегодня уже был"));
      list.append(item);
    });
    parts.push(list);
    if (place && place > 3) parts.push(node("p", "royale-meta", `Ваше место: ${place}`));
    return parts;
  }

  function staffControls(game) {
    const actions = node("div", "capture-actions");
    const armedButton = (kind, label, confirmLabel, action) => button("btn btn-secondary", armed === kind ? confirmLabel : label, () => {
      if (armed !== kind) {
        armed = kind;
        draw();
        return;
      }
      armed = null;
      action();
    });
    if (!game || game.status === "over") {
      actions.append(button("btn btn-primary", "Открыть лобби", () => act("create")));
    } else if (game.status === "lobby") {
      const go = button("btn btn-primary", `Начать битву (${game.players})`, () => act("start"));
      go.disabled = busy || game.players < 2;
      actions.append(go);
    }
    actions.append(button("btn btn-secondary", "Большой экран", openStage));
    if (game && game.status !== "over") actions.append(armedButton("cancel", "Остановить", "Точно остановить?", () => act("cancel")));
    return actions;
  }

  function renderPanel(freshRound, freshReveal) {
    const body = $("royaleBody");
    const status = $("royaleStatus");
    if (!signedIn() || !data) {
      body.replaceChildren(logo(false), node("p", "spy-lead", LEAD), node("p", "royale-meta", signedIn() ? "Загружаем…" : "Войдите, чтобы играть"));
      status.textContent = "—";
      return;
    }
    const game = data.game;
    let parts;
    if (!game) {
      parts = drawIdle();
      status.textContent = "ЖДЁМ ВОЖАТОГО";
    } else if (game.status === "lobby") {
      parts = drawLobby(game);
      status.textContent = "ЛОББИ";
    } else if (game.status === "question" && game.intro_until) {
      parts = drawIntro(game);
      status.textContent = "ОТСЧЁТ";
    } else if (game.status === "question") {
      parts = drawQuestion(game, freshRound);
      status.textContent = `РАУНД ${game.round}`;
    } else if (game.status === "reveal") {
      parts = drawReveal(game, freshReveal);
      status.textContent = `РАЗБОР РАУНДА ${game.round}`;
    } else {
      parts = drawResults(game);
      status.textContent = game.cancelled ? "ОСТАНОВЛЕНА" : "ИТОГИ";
    }
    if (data.can_host) parts.push(staffControls(game));
    parts.push(node("p", "case-message royale-note", note));
    body.replaceChildren(...parts);
  }

  // --- большой экран -------------------------------------------------------------------------

  function grid(game, mode) {
    const box = node("div", "royale-grid");
    let falling = 0;
    (game.grid || []).forEach((p) => {
      const cell = node("span", "royale-avatar", initial(p.name));
      cell.title = p.name;
      if (p.color) cell.style.setProperty("--faction", p.color);
      if (p.frame) cell.dataset.frame = p.frame;
      if (!p.alive) cell.classList.add("is-out");
      if (p.answered) cell.classList.add("is-answered");
      if (p.revived && p.alive) cell.classList.add("is-revived");
      if (mode === "lobby" && !stageSeen.has(p.name)) cell.classList.add("is-joining");
      if (mode === "play" && stageAlive.get(p.name) === true && !p.alive) {
        cell.classList.add("is-falling");
        cell.style.animationDelay = `${falling * 70}ms`;
        falling += 1;
      }
      box.append(cell);
    });
    stageAlive = new Map((game.grid || []).map((p) => [p.name, p.alive]));
    stageSeen = new Set((game.grid || []).map((p) => p.name));
    return box;
  }

  function renderStage(freshRound, freshReveal) {
    const stage = $("royaleStage");
    const game = data && data.game;
    const bar = node("div", "royale-stage-bar");
    bar.append(logo(false), button("royale-stage-close", "×", closeStage));
    const parts = [bar];
    if (!game) {
      parts.push(logo(true), node("p", "royale-stage-title", "Ждём лобби"));
    } else if (game.status === "lobby") {
      parts.push(logo(true), marquee(), node("p", "royale-stage-title", "Заходите: Ивенты → Протокол 60"),
        node("p", "royale-stage-count", String(game.players)), grid(game, "lobby"));
    } else if (game.status === "question" && game.intro_until) {
      parts.push(intro(game.intro_until, true), grid(game, "play"));
    } else if (game.status === "question" || game.status === "reveal") {
      const label = game.question.final ? "ФИНАЛ" : `Раунд ${game.round}`;
      const head = node("p", "royale-stage-head", `${label} · живых ${game.alive} из ${game.starters} · `);
      head.append(countdown(game.status === "question" ? game.question.deadline : game.reveal.until, game.status === "question"));
      parts.push(head, prompt(game.question, true, freshRound));
      if (game.status === "reveal") {
        const lost = node("p", "royale-stage-head", "Выбыло: ");
        lost.append(roll(game.reveal.eliminated, freshReveal));
        parts.push(optionsReveal(game, freshReveal), lost);
      } else {
        const options = node("div", `royale-options is-big${kindClass(game.question)}${freshRound ? " is-new" : ""}`);
        if (game.question.surprise === "shuffle") options.dataset.shuffle = "1";
        game.question.options.forEach((text) => options.append(node("div", "royale-option", text)));
        parts.push(options);
      }
      parts.push(grid(game, "play"));
    } else if (game.cancelled) {
      parts.push(node("p", "royale-stage-title", "Игра остановлена"));
    } else {
      const podium = node("div", "royale-podium");
      game.results.slice(0, 3).forEach((r) => {
        const place = node("div", `royale-podium-place is-place-${r.place}`);
        place.append(node("span", null, String(r.place)), node("b", null, r.name));
        podium.append(place);
      });
      const rest = node("ol", "royale-stage-rest");
      rest.start = 4;
      game.results.slice(3).forEach((r) => rest.append(node("li", null, r.name)));
      parts.push(logo(true), node("p", "royale-stage-title", "Победители"), podium, rest);
    }
    stage.replaceChildren(...parts);
  }

  function openStage() {
    stageOpen = true;
    stageAlive = new Map();
    stageSeen = new Set();
    $("royaleStage").hidden = false;
    draw();
    $("royaleStage").requestFullscreen?.().catch(() => { /* полноэкранный режим не обязателен */ });
    schedule();
  }

  function closeStage() {
    stageOpen = false;
    $("royaleStage").hidden = true;
    if (fx) fx.replaceChildren();
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    schedule();
  }

  // --- данные ------------------------------------------------------------------------------------

  function draw() {
    const game = data && data.game;
    const roundKey = game && game.status === "question" && game.question ? `${game.id}:${game.round}` : null;
    const revealKey = game && game.status === "reveal" ? `${game.id}:${game.round}` : null;
    const freshRound = Boolean(roundKey && roundKey !== seenRound);
    const freshReveal = Boolean(revealKey && revealKey !== seenReveal);
    renderPanel(freshRound, freshReveal);
    if (stageOpen) renderStage(freshRound, freshReveal);
    if (freshRound) {
      seenRound = roundKey;
      sound("join");
    }
    if (freshReveal) {
      seenReveal = revealKey;
      if (stageOpen) shake(game);
    }
    if (game && game.status === "over" && !game.cancelled && celebrated !== game.id) {
      celebrated = game.id;
      if (stageOpen) confetti();
      if (stageOpen || (game.me && game.me.place === 1)) sound("win");
    }
    clearTimeout(introTimer);
    if (game && game.intro_until) {
      introTimer = setTimeout(() => { if (!busy) refresh(); }, Math.max(0, timeOf(game.intro_until) - Date.now()) + 120);
    }
  }

  function accept(body) {
    const before = data && data.game;
    const first = !data;
    data = body;
    const after = data.game;
    // Уже законченную игру, открытую позже, не празднуем заново.
    if (first && after && after.status === "over") celebrated = after.id;
    const wasMe = before && before.me;
    const nowMe = after && after.me;
    if (wasMe && nowMe && wasMe.alive && nowMe.alive === false) {
      justOut = Date.now() + 1800;
      sound("buy");
    }
    if (wasMe && nowMe && wasMe.alive === false && nowMe.alive && nowMe.revived) sound("rare");
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      draw();
    }
    schedule();
  }

  async function refresh() {
    if (!signedIn()) {
      data = null;
      signature = "";
      renderPanel(false, false);
      return;
    }
    try {
      accept(await api("/api/v4/royale"));
    } catch (_) {
      /* панель подождёт следующего опроса */
    }
  }

  async function act(action, body) {
    if (busy) return;
    busy = true;
    note = "";
    draw();
    try {
      accept(await api(`/api/v4/royale/${action}`, { method: "POST", body }));
    } catch (error) {
      note = error.message;
      await refresh();
    } finally {
      busy = false;
      signature = JSON.stringify(data);
      draw();
    }
  }

  async function revive() {
    if (busy) return;
    busy = true;
    reviveKey = reviveKey || newKey();
    draw();
    try {
      const result = await api("/api/v4/royale/revive", { method: "POST", key: reviveKey });
      reviveKey = null;
      note = "";
      window.showToast?.(`Вы снова в игре · −${result.price}★`);
      await refresh();
    } catch (error) {
      if (error.status) reviveKey = null;
      note = error.status ? error.message : "Нет связи. Нажмите ещё раз — звёзды не спишутся дважды.";
    } finally {
      busy = false;
      draw();
    }
  }

  function tick() {
    // Сюрприз «варианты бегают»: кнопки меняются местами, номер варианта остаётся прежним.
    if (Date.now() - shuffledAt > 1400) {
      shuffledAt = Date.now();
      document.querySelectorAll(".royale-options[data-shuffle]").forEach((list) => {
        const order = [...list.children].map((_, i) => i).sort(() => Math.random() - 0.5);
        [...list.children].forEach((child, i) => { child.style.order = String(order[i]); });
      });
    }
    document.querySelectorAll(".royale-left").forEach((span) => {
      const left = secondsLeft(span.dataset.until);
      span.textContent = `${left} с`;
      span.classList.toggle("is-hot", Boolean(span.dataset.hot) && left > 0 && left <= 3);
    });
    document.querySelectorAll(".royale-intro-count").forEach((count) => {
      count.textContent = String(Math.max(1, secondsLeft(count.dataset.until)));
    });
    const game = data && data.game;
    if (game && game.status === "question" && game.question) {
      const left = secondsLeft(timeOf(game.question.deadline));
      if (left >= 1 && left <= 3 && left !== tickSecond) {
        tickSecond = left;
        if (stageOpen || (game.me && game.me.alive && !game.me.answered)) sound("tick");
      }
    }
  }

  function schedule() {
    const status = data && data.game ? data.game.status : null;
    const want = status === "question" || status === "reveal" ? 1000 : status === "lobby" ? 3000 : 15000;
    if (!signedIn() || !(onGames() || stageOpen)) {
      clearInterval(poll);
      clearInterval(ticker);
      poll = null;
      ticker = null;
      pollMs = 0;
      return;
    }
    if (!ticker) ticker = setInterval(tick, 250);
    if (poll && pollMs === want) return;
    clearInterval(poll);
    pollMs = want;
    poll = setInterval(() => { if (!busy) refresh(); }, want);
  }

  // --- подключение -------------------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    data = null;
    signature = "";
    armed = null;
    note = "";
    if (stageOpen) closeStage();
    renderPanel(false, false);
    if (onGames()) refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "games") refresh();
    else schedule();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && stageOpen) closeStage();
  });
  renderPanel(false, false);
}());
