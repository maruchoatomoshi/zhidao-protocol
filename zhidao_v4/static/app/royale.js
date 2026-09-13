"use strict";

/* Протокол 60 — королевская битва на всю смену (V4_GAMES.md §4.12).

   Вожатый открывает лобби и выводит «Большой экран» на ноутбук у телевизора.
   Участники входят со своих телефонов в «Ивентах». Все одновременно отвечают на
   китайское слово; ошибся или не успел — выбыл. Между раундами выбывшие
   голосуют за сюрприз выжившим и могут один раз воскреснуть за звёзды.

   Всё решает сервер (zhidao_v4/royale.py): время, кто выбыл, места и призы.
   Правильный вариант сюда приходит только в разборе раунда. Панель
   перерисовывается, только когда ответ сервера изменился, а отсчёт меняет одну
   цифру — чтобы нажатие на вариант не терялось при перерисовке. */

(function () {
  const $ = (id) => document.getElementById(id);
  const SURPRISE = { fast: "−3 секунды", hanzi: "Без пиньиня", more: "+1 вариант" };
  const LEAD = "Вся смена одновременно отвечает на китайские слова. Ошибся или не успел — выбыл. Последний выживший забирает главный приз";

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
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));
  const newKey = () => `royale-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
  const initial = (name) => (String(name || "?").trim()[0] || "?").toUpperCase();

  function countdown(iso) {
    const span = node("span", "royale-left");
    span.dataset.until = String(timeOf(iso));
    span.textContent = `${Math.max(0, Math.ceil((timeOf(iso) - Date.now()) / 1000))} с`;
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

  // --- куски панели ------------------------------------------------------------------------

  function prompt(question, big) {
    const box = node("div", `royale-question${big ? " is-big" : ""}`);
    if (question.prompt.zh) {
      box.append(node("b", "royale-hanzi", question.prompt.zh));
      if (question.prompt.pinyin) box.append(node("p", "royale-pinyin", question.prompt.pinyin));
    } else {
      box.append(node("b", "royale-word", question.prompt.ru), node("p", "royale-pinyin", "Найдите иероглиф"));
    }
    if (question.surprise) box.append(node("span", "royale-surprise", `Сюрприз раунда: ${SURPRISE[question.surprise]}`));
    return box;
  }

  function optionsReveal(game) {
    const list = node("div", `royale-options is-reveal${game.question.direction === "ru" ? " is-hanzi" : ""}`);
    game.question.options.forEach((text, index) => {
      const item = node("div", "royale-option", text);
      if (index === game.reveal.answer) item.classList.add("is-right");
      if (game.me && game.me.choice === index && index !== game.reveal.answer) item.classList.add("is-wrong");
      list.append(item);
    });
    return list;
  }

  function drawIdle() {
    const parts = [node("p", "spy-lead", LEAD)];
    const prizes = data.prizes || [];
    if (prizes.length) {
      parts.push(node("p", "royale-meta",
        `Призы: ${prizes.map((p, i) => `${i + 1} место — ${p.stars}★ и ${p.rep} REP`).join(" · ")} (в играх от ${data.prize_min_players} человек, один приз в день)`));
    }
    parts.push(node("p", "royale-meta", data.can_host ? "Откройте лобби, когда смена соберётся" : "Игру открывает вожатый — ждите объявления"));
    return parts;
  }

  function drawLobby(game) {
    const parts = [node("p", "spy-lead", LEAD), node("b", "royale-count", `В лобби: ${game.players}`)];
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

  function drawQuestion(game) {
    const parts = [];
    const head = node("p", "royale-meta", `Раунд ${game.round} · живых ${game.alive} из ${game.starters} · ответили ${game.answered} · `);
    head.append(countdown(game.question.deadline));
    parts.push(head, prompt(game.question, false));
    const me = game.me;
    if (me && me.alive && !me.answered) {
      const options = node("div", `royale-options${game.question.direction === "ru" ? " is-hanzi" : ""}`);
      game.question.options.forEach((text, index) => options.append(button("btn btn-secondary", text, () => act("answer", { choice: index }))));
      parts.push(options);
    } else if (me && me.alive) {
      parts.push(node("p", "royale-meta is-ok", "Ответ принят. Ждём остальных…"));
    } else if (me) {
      parts.push(node("p", "royale-meta", `Вы выбыли в раунде ${me.out_round}. Следите за битвой`));
    } else {
      parts.push(node("p", "royale-meta", "Вы смотрите битву со стороны"));
    }
    return parts;
  }

  function drawReveal(game) {
    const parts = [];
    const head = node("p", "royale-meta", `Выбыло ${game.reveal.eliminated} · осталось ${game.alive} · следующий раунд через `);
    head.append(countdown(game.reveal.until));
    parts.push(head, prompt(game.question, false), optionsReveal(game));
    const me = game.me;
    if (me && me.alive) {
      parts.push(node("p", "royale-meta is-ok", me.choice === game.reveal.answer ? "Верно! Вы в игре" : "Вы в игре"));
    } else if (me) {
      parts.push(node("p", "royale-meta", "Вы выбыли"));
      if (me.can_revive) {
        parts.push(button("btn btn-primary", `Воскреснуть за ${game.revive_price}★`, revive));
      }
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
    const list = node("ol", "royale-results");
    game.results.forEach((r) => {
      const item = node("li", r.place <= 3 ? `is-top is-place-${r.place}` : "");
      item.append(node("b", null, r.name));
      if (r.prize) item.append(node("span", null, `+${r.prize.stars}★ · +${r.prize.rep} REP`));
      else if (r.limited) item.append(node("span", null, "приз сегодня уже был"));
      list.append(item);
    });
    parts.push(list);
    if (game.me && game.me.place) parts.push(node("p", "royale-meta is-ok", `Ваше место: ${game.me.place}`));
    return parts;
  }

  function staffControls(game) {
    const actions = node("div", "capture-actions");
    const armedButton = (kind, label, confirmLabel, action) => button("btn btn-secondary", armed === kind ? confirmLabel : label, () => {
      if (armed !== kind) {
        armed = kind;
        render(true);
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

  function renderPanel() {
    const body = $("royaleBody");
    const status = $("royaleStatus");
    if (!signedIn() || !data) {
      body.replaceChildren(node("p", "spy-lead", LEAD), node("p", "royale-meta", signedIn() ? "Загружаем…" : "Войдите, чтобы играть"));
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
    } else if (game.status === "question") {
      parts = drawQuestion(game);
      status.textContent = `РАУНД ${game.round}`;
    } else if (game.status === "reveal") {
      parts = drawReveal(game);
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

  function grid(game) {
    const box = node("div", "royale-grid");
    (game.grid || []).forEach((p) => {
      const cell = node("span", "royale-avatar", initial(p.name));
      cell.title = p.name;
      if (!p.alive) cell.classList.add("is-out");
      if (p.answered) cell.classList.add("is-answered");
      if (p.revived && p.alive) cell.classList.add("is-revived");
      if (p.frame) cell.dataset.frame = p.frame;
      box.append(cell);
    });
    return box;
  }

  function renderStage() {
    const stage = $("royaleStage");
    const game = data && data.game;
    const bar = node("div", "royale-stage-bar");
    bar.append(node("b", null, "ПРОТОКОЛ 60 · 大逃杀"), button("royale-stage-close", "×", closeStage));
    const parts = [bar];
    if (!game) {
      parts.push(node("p", "royale-stage-title", "Ждём лобби"));
    } else if (game.status === "lobby") {
      parts.push(node("p", "royale-stage-title", "Заходите: Ивенты → Протокол 60"), node("p", "royale-stage-count", String(game.players)), grid(game));
    } else if (game.status === "question" || game.status === "reveal") {
      const head = node("p", "royale-stage-head", `Раунд ${game.round} · живых ${game.alive} из ${game.starters} · `);
      head.append(countdown(game.status === "question" ? game.question.deadline : game.reveal.until));
      parts.push(head, prompt(game.question, true));
      if (game.status === "reveal") {
        parts.push(optionsReveal(game), node("p", "royale-stage-head", `Выбыло: ${game.reveal.eliminated}`));
      } else {
        const options = node("div", `royale-options is-big${game.question.direction === "ru" ? " is-hanzi" : ""}`);
        game.question.options.forEach((text) => options.append(node("div", "royale-option", text)));
        parts.push(options);
      }
      parts.push(grid(game));
    } else if (game.cancelled) {
      parts.push(node("p", "royale-stage-title", "Игра остановлена"));
    } else {
      const podium = node("div", "royale-podium");
      game.results.slice(0, 3).forEach((r) => {
        const place = node("div", `royale-podium-place is-place-${r.place}`);
        place.append(node("span", null, String(r.place)), node("b", null, r.name));
        podium.append(place);
      });
      parts.push(node("p", "royale-stage-title", "Победители"), podium);
    }
    stage.replaceChildren(...parts);
  }

  function openStage() {
    stageOpen = true;
    $("royaleStage").hidden = false;
    renderStage();
    $("royaleStage").requestFullscreen?.().catch(() => { /* полноэкранный режим не обязателен */ });
    schedule();
  }

  function closeStage() {
    stageOpen = false;
    $("royaleStage").hidden = true;
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    schedule();
  }

  // --- данные ------------------------------------------------------------------------------------

  function render(force) {
    renderPanel();
    if (stageOpen) renderStage();
    if (force) signature = JSON.stringify(data);
  }

  function accept(body) {
    const before = data && data.game && data.game.me;
    data = body;
    const after = data.game && data.game.me;
    if (before && after && before.alive && !after.alive && window.ZhidaoSounds) window.ZhidaoSounds.play("buy");
    if (after && after.place === 1 && !(before && before.place === 1) && window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      renderPanel();
      if (stageOpen) renderStage();
    }
    schedule();
  }

  async function refresh() {
    if (!signedIn()) {
      data = null;
      signature = "";
      renderPanel();
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
    render(true);
    try {
      accept(await api(`/api/v4/royale/${action}`, { method: "POST", body }));
    } catch (error) {
      note = error.message;
      await refresh();
    } finally {
      busy = false;
      render(true);
    }
  }

  async function revive() {
    if (busy) return;
    busy = true;
    reviveKey = reviveKey || newKey();
    render(true);
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
      render(true);
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
    if (!ticker) {
      ticker = setInterval(() => {
        document.querySelectorAll(".royale-left").forEach((span) => {
          span.textContent = `${Math.max(0, Math.ceil((Number(span.dataset.until) - Date.now()) / 1000))} с`;
        });
      }, 250);
    }
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
    renderPanel();
    if (onGames()) refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "games") refresh();
    else schedule();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && stageOpen) closeStage();
  });
  renderPanel();
}());
