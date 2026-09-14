"use strict";

/* Зомби-протокол — вечерний раунд, скрещённый с Вирусом (V4_GAMES.md §4.12).

   Вожатый открывает лобби и называет зону. Люди уходят шагом, зомби касаются
   плеча и вводят шестизначный код с телефона жертвы. Зомби может один раз
   вернуться в люди у станции: подтверждённой точки кампуса и китайского
   вопроса. Всё решает сервер (zhidao_v4/zombie.py); свой код видит только
   хозяин. Панель перерисовывается, только когда ответ сервера изменился, а
   отсчёты меняют одну цифру, — чтобы набранный код не стирался при опросе. */

(function () {
  const $ = (id) => document.getElementById(id);
  const LEAD = "Зомби касаются плеча и вводят код с телефона жертвы. Люди держатся до конца раунда. Зомби может один раз вернуться в люди у станции-вакцины";
  const SAFETY = "Только шагом. Касаемся только плеча. Не выходим из зоны, которую назвал вожатый";

  let session = window.ZhidaoSession || null;
  let data = null;
  let signature = "";
  let busy = false;
  let note = "";
  let armed = null;
  let codeDraft = "";
  let question = null;
  let poll = null;
  let pollMs = 0;
  let ticker = null;

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

  function armedButton(kind, className, label, confirmLabel, action) {
    return button(className, armed === kind ? confirmLabel : label, () => {
      if (armed !== kind) {
        armed = kind;
        draw();
        return;
      }
      armed = null;
      action();
    });
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onGames = () => document.documentElement.dataset.currentScreen === "games";
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));
  const leftText = (ms) => {
    const total = Math.max(0, Math.ceil(ms / 1000));
    return total >= 60 ? `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}` : `${total} с`;
  };

  function countdown(iso) {
    const span = node("span", "zombie-left");
    span.dataset.until = String(timeOf(iso));
    span.textContent = leftText(timeOf(iso) - Date.now());
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
      init.body = JSON.stringify(options.body || {});
    }
    try {
      const response = await fetch(path, init);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const detail = Array.isArray(body.detail) ? "Проверьте, что введено." : body.detail;
        throw new Error(typeof detail === "string" ? detail : "Запрос отклонён.");
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

  function position() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("GPS недоступен на этом устройстве."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => reject(new Error(err.code === err.PERMISSION_DENIED ? "Доступ к геопозиции закрыт." : "Не удалось определить позицию.")),
        { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
    });
  }

  // --- куски панели ------------------------------------------------------------------------

  function rulesLine() {
    const r = data.rules;
    if (!r) return null;
    return node("p", "zombie-meta",
      `Раунд ${r.round_minutes} мин. Выжившие и лучший зомби — по ${r.prize.survivor_stars}★ (в раундах от ${r.prize_min_players} человек, одна награда в день)`);
  }

  function drawHuman(me, parts) {
    const box = node("section", "zombie-card is-human");
    box.append(node("span", "capture-label", "Вы человек · ваш код"));
    const code = String(me.code || "");
    box.append(node("b", "zombie-code", `${code.slice(0, 3)} ${code.slice(3)}`));
    box.append(node("p", "zombie-meta", "Зомби коснулся вашего плеча — покажите ему этот код. Прятать и спорить нельзя"));
    if (me.immune_until) {
      const line = node("p", "zombie-meta is-ok", "Иммунитет после вакцины ещё ");
      line.append(countdown(me.immune_until));
      box.append(line);
    }
    parts.push(box);
  }

  function drawTagForm(me, box) {
    if (me.rest_until) {
      const line = node("p", "zombie-meta", "Зомби приходит в себя: ");
      line.append(countdown(me.rest_until));
      box.append(line);
    }
    const form = node("form", "zombie-tag");
    const input = node("input", "zombie-input");
    input.id = "zombieCode";
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.maxLength = 7;
    input.placeholder = "000 000";
    input.setAttribute("aria-label", "Код с телефона жертвы");
    input.value = codeDraft;
    input.disabled = busy;
    input.addEventListener("input", () => { codeDraft = input.value; });
    const submit = node("button", "btn btn-primary", "Заразить");
    submit.type = "submit";
    submit.disabled = busy;
    form.append(input, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const digits = codeDraft.replace(/\D/g, "");
      if (digits.length !== 6) {
        note = "Код — шесть цифр с телефона человека";
        draw();
        return;
      }
      act("tag", { code: digits });
    });
    box.append(form);
  }

  function drawVaccine(me, box) {
    if (me.vaccinated) {
      box.append(node("p", "zombie-meta", "Вакцина в этом раунде уже использована"));
      return;
    }
    box.append(node("span", "capture-label", "Вакцина: дойдите до станции и ответьте на вопрос"));
    if (question) {
      const q = node("div", "zombie-question");
      q.append(node("b", "zombie-hanzi", question.zh), node("p", "zombie-meta", question.pinyin));
      const options = node("div", "zombie-options");
      question.options.forEach((text, index) => options.append(button("btn btn-secondary", text, () => answerVaccine(index))));
      q.append(options);
      box.append(q);
      return;
    }
    const stations = data.stations || [];
    if (!stations.length) {
      box.append(node("p", "zombie-meta", "Станций пока нет: вожатый ещё не подтвердил точки кампуса"));
      return;
    }
    const list = node("div", "zombie-stations");
    stations.forEach((s) => list.append(button("btn btn-secondary", `Я у станции: ${s.name_ru || s.code}`, () => challenge(s.code))));
    box.append(list);
  }

  function drawZombie(me, parts) {
    const box = node("section", "zombie-card is-zombie");
    box.append(node("span", "capture-label", me.starter ? "Вы первый зомби" : "Вы зомби"),
      node("p", "zombie-meta", `Заражений: ${me.tags}`));
    drawTagForm(me, box);
    drawVaccine(me, box);
    parts.push(box);
  }

  function drawResults(game, parts) {
    if (game.cancelled) {
      parts.push(node("p", "zombie-meta", "Раунд остановил вожатый. Без наград"));
      return;
    }
    const r = game.results || {};
    parts.push(node("p", "zombie-headline", r.reason === "all_turned" ? "Людей не осталось — победили зомби" : `Время вышло · выжило ${r.humans}`));
    const withPrize = (row) => (row.prize ? ` · +${row.prize}★` : row.limited ? " · награда сегодня уже была" : "");
    if ((r.survivors || []).length) {
      parts.push(node("span", "capture-label", "Выжившие"));
      const list = node("ul", "zombie-list");
      r.survivors.forEach((row) => list.append(node("li", null, `${row.name}${withPrize(row)}`)));
      parts.push(list);
    }
    if ((r.best_zombies || []).length) {
      parts.push(node("span", "capture-label", "Лучший зомби"));
      const list = node("ul", "zombie-list");
      r.best_zombies.forEach((row) => list.append(node("li", null, `${row.name} · заражений ${row.tags}${withPrize(row)}`)));
      parts.push(list);
    }
    if (!r.prizes) parts.push(node("p", "zombie-meta", "Раунд был меньше, чем нужно для наград"));
    const me = game.me;
    if (me && me.survived) parts.push(node("p", "zombie-meta is-ok", "Вы выжили!"));
    else if (me && me.best_zombie) parts.push(node("p", "zombie-meta is-ok", "Вы — лучший зомби раунда!"));
  }

  function drawStaff(game, parts) {
    const actions = node("div", "capture-actions");
    if (!game || game.status === "over") {
      actions.append(button("btn btn-primary", "Открыть лобби", () => act("create")));
    } else if (game.status === "lobby") {
      const go = button("btn btn-primary", `Начать раунд (${game.players})`, () => act("start"));
      go.disabled = busy || game.players < data.rules.min_players;
      actions.append(go);
    }
    if (game && game.status !== "over") {
      actions.append(armedButton("cancel", "btn btn-secondary", "Остановить", "Точно остановить?", () => act("cancel")));
    }
    parts.push(node("span", "capture-label", "Вожатому"), actions);
    if (game && game.grid && game.grid.length) {
      const grid = node("div", "zombie-grid");
      game.grid.forEach((p) => {
        const chip = node("span", `zombie-chip is-${p.side}`, p.side === "zombie" ? `${p.name} · ${p.tags}` : p.name);
        grid.append(chip);
      });
      parts.push(grid);
    }
  }

  function draw() {
    const body = $("zombieBody");
    const status = $("zombieStatus");
    if (!body) return;
    if (!signedIn() || !data) {
      body.replaceChildren(node("p", "spy-lead", LEAD), node("p", "zombie-meta", signedIn() ? "Загружаем…" : "Войдите, чтобы играть"));
      status.textContent = "—";
      return;
    }
    const focused = document.activeElement && document.activeElement.id === "zombieCode";
    const game = data.game;
    const parts = [node("p", "spy-lead", LEAD), node("p", "zombie-safety", SAFETY)];
    if (!game) {
      const rules = rulesLine();
      if (rules) parts.push(rules);
      parts.push(node("p", "zombie-meta", data.can_host ? "Откройте лобби, когда все соберутся в зоне" : "Раунд открывает вожатый — ждите объявления"));
      status.textContent = "ЖДЁМ ВОЖАТОГО";
    } else if (game.status === "lobby") {
      const rules = rulesLine();
      if (rules) parts.push(rules);
      parts.push(node("b", "zombie-count", `В лобби: ${game.players}`));
      if (data.can_play) {
        parts.push(game.me
          ? button("btn btn-secondary", "Выйти из лобби", () => act("leave"))
          : button("btn btn-primary", "Войти в раунд", () => act("join")));
      }
      status.textContent = "ЛОББИ";
    } else if (game.status === "running") {
      const head = node("p", "zombie-headline", `Людей ${game.humans} · зомби ${game.zombies} · до конца `);
      head.append(countdown(game.ends_at));
      parts.push(head);
      if (!game.me) parts.push(node("p", "zombie-meta", "Раунд идёт — вы смотрите со стороны"));
      else if (game.me.side === "human") drawHuman(game.me, parts);
      else drawZombie(game.me, parts);
      status.textContent = "РАУНД ИДЁТ";
    } else {
      drawResults(game, parts);
      status.textContent = "ИТОГИ";
    }
    if (data.can_host) drawStaff(game, parts);
    parts.push(node("p", "case-message", note));
    body.replaceChildren(...parts);
    if (focused && $("zombieCode")) {
      const input = $("zombieCode");
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  // --- данные ------------------------------------------------------------------------------------

  let quietRefresh = true;
  let refreshing = false;
  function accept(body) {
    const before = !quietRefresh && !document.hidden && onGames() ? (data && data.game && data.game.me) : null;
    quietRefresh = false;
    data = body;
    const after = data.game && data.game.me;
    if (before && after && before.side === "human" && after.side === "zombie") {
      window.showToast?.("Вас заразили! Теперь вы зомби");
      window.ZhidaoSounds?.play("buy");
      question = null;
    }
    if (!after || after.side !== "zombie") question = null;
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      draw();
      if (before && after && before.side !== after.side) window.ZhidaoRetro?.reveal(document.getElementById("zombieBody"));
    }
    schedule();
  }

  async function refresh() {
    if (!signedIn()) {
      data = null;
      signature = "";
      draw();
      return;
    }
    if (refreshing) return;
    refreshing = true;
    const account = session?.account?.id;
    try {
      const response = await api("/api/v4/zombie");
      if (account !== session?.account?.id) return;
      accept(response);
    } catch (_) {
      quietRefresh = true;
      const status = document.getElementById("zombieStatus");
      if (status) status.textContent = "Нет связи · повторяем автоматически";
    } finally {
      refreshing = false;
      schedule();
    }
  }

  async function act(action, body) {
    if (busy) return;
    busy = true;
    note = "";
    draw();
    try {
      const result = await api(`/api/v4/zombie/${action}`, { method: "POST", body });
      if (action === "tag") {
        codeDraft = "";
        if (result.tagged) window.showToast?.(`${result.tagged} теперь зомби`);
      }
      accept(result);
    } catch (error) {
      note = error.message;
      await refresh();
    } finally {
      busy = false;
      signature = "";
      draw();
    }
  }

  async function challenge(point) {
    if (busy) return;
    busy = true;
    note = "Ищем вас…";
    draw();
    try {
      const coords = await position();
      const result = await api("/api/v4/zombie/vaccine/challenge", {
        method: "POST", body: { point, lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy },
      });
      if (result.question) {
        question = { ...result.question };
        note = `Ответьте за ${result.seconds} с`;
      } else {
        accept(result);
        note = "";
      }
    } catch (error) {
      note = error.message;
    } finally {
      busy = false;
      signature = "";
      draw();
    }
  }

  async function answerVaccine(choice) {
    if (busy) return;
    busy = true;
    draw();
    try {
      const result = await api("/api/v4/zombie/vaccine/answer", { method: "POST", body: { choice } });
      question = null;
      note = result.vaccine && result.vaccine.correct ? "Вакцина сработала — вы снова человек!" : "Неверно. Станция примет вас через минуту";
      accept(result);
    } catch (error) {
      question = null;
      note = error.message;
    } finally {
      busy = false;
      signature = "";
      draw();
    }
  }

  function schedule() {
    const status = data && data.game ? data.game.status : null;
    const want = status === "running" ? 3000 : status === "lobby" ? 5000 : 20000;
    if (!signedIn() || !onGames() || document.hidden) {
      clearInterval(poll);
      clearInterval(ticker);
      poll = null;
      ticker = null;
      pollMs = 0;
      return;
    }
    if (!ticker) {
      ticker = setInterval(() => {
        document.querySelectorAll(".zombie-left").forEach((span) => {
          span.textContent = leftText(Number(span.dataset.until) - Date.now());
        });
      }, 500);
    }
    if (poll && pollMs === want) return;
    clearInterval(poll);
    pollMs = want;
    poll = setInterval(() => { if (!busy) refresh(); }, want);
  }

  // --- подключение -------------------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    quietRefresh = true;
    session = event.detail;
    data = null;
    signature = "";
    armed = null;
    note = "";
    codeDraft = "";
    question = null;
    draw();
    if (onGames()) refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    quietRefresh = true;
    if (event.detail === "games") refresh();
    else schedule();
  });
  document.addEventListener("visibilitychange", () => {
    quietRefresh = true;
    schedule();
    if (!document.hidden && onGames() && !busy) refresh();
  });
  window.addEventListener("online", () => {
    quietRefresh = true;
    if (!document.hidden && onGames() && !busy) refresh();
  });
  draw();
}());
