"use strict";

/* Саботаж — Among Us вживую на кампусе (V4_GAMES.md §4.12).

   Экипаж ходит по станциям (подтверждённым точкам кампуса) и отвечает на
   китайские вопросы. Тайные саботажники касаются плеча и вводят код с
   телефона жертвы. Капитаны созывают собрание: все идут к капитану, спорят
   вслух и голосуют здесь. Всё решает сервер (zhidao_v4/sabotage.py): роль,
   код и задания видит только их хозяин. Панель перерисовывается, только когда
   ответ сервера изменился, — чтобы набранный код не стирался при опросе. */

(function () {
  const $ = (id) => document.getElementById(id);
  const LEAD = "Экипаж выполняет задания у станций кампуса. Среди вас прячутся саботажники. Капитаны созывают собрание — и все вместе решают, кого выгнать";
  const SAFETY = "Только шагом. Касаемся только плеча. Выведенные молчат до конца игры";
  const REASONS = {
    ejected: "Экипаж выгнал всех саботажников",
    tasks: "Экипаж выполнил все задания",
    parity: "Саботажники сравнялись с экипажем",
    time: "Время вышло — экипаж не успел",
  };

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
  let doneTasks = new Set();

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
    const span = node("span", "sabotage-left");
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

  function drawRole(game, me, parts) {
    const box = node("section", `sabotage-card is-${me.alive ? me.role : "ghost"}`);
    if (!me.alive) {
      box.append(node("b", "sabotage-role", me.ejected ? "Вас выгнали на собрании" : "Вас вывели"),
        node("p", "sabotage-meta", "Молчите до конца игры. Задания можно доделывать — они всё ещё помогают"));
    } else if (me.role === "saboteur") {
      box.append(node("b", "sabotage-role", "Вы саботажник"));
      box.append(node("p", "sabotage-meta", me.allies && me.allies.length ? `Союзники: ${me.allies.join(", ")}` : "Вы действуете в одиночку"));
      if (game.status === "running") drawEliminate(me, box);
    } else {
      box.append(node("b", "sabotage-role", me.captain ? "Вы капитан экипажа" : "Вы в экипаже"));
    }
    if (me.alive && me.code) {
      const code = String(me.code);
      box.append(node("span", "capture-label", "Ваш код"), node("b", "sabotage-code", `${code.slice(0, 3)} ${code.slice(3)}`),
        node("p", "sabotage-meta", "Саботажник коснулся плеча — покажите ему код. Прятать и спорить нельзя"));
    }
    if (me.alive && me.captain && game.status === "running") {
      if (me.meetings_left > 0) {
        box.append(armedButton("meeting", "btn btn-primary", `Созвать собрание (осталось ${me.meetings_left})`,
          "Точно созвать? Все пойдут к вам", () => act("meeting")));
      } else {
        box.append(node("p", "sabotage-meta", "Свои собрания вы уже созвали"));
      }
    }
    parts.push(box);
  }

  function drawEliminate(me, box) {
    if (me.rest_until) {
      const line = node("p", "sabotage-meta", "Выждать ещё ");
      line.append(countdown(me.rest_until));
      box.append(line);
    }
    const form = node("form", "sabotage-form");
    const input = node("input", "sabotage-input");
    input.id = "sabotageCode";
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.maxLength = 7;
    input.placeholder = "000 000";
    input.setAttribute("aria-label", "Код с телефона игрока");
    input.value = codeDraft;
    input.disabled = busy;
    input.addEventListener("input", () => { codeDraft = input.value; });
    const submit = node("button", "btn btn-primary", "Вывести");
    submit.type = "submit";
    submit.disabled = busy;
    form.append(input, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const digits = codeDraft.replace(/\D/g, "");
      if (digits.length !== 6) {
        note = "Код — шесть цифр с телефона игрока";
        draw();
        return;
      }
      act("eliminate", { code: digits });
    });
    box.append(form);
  }

  function drawTasks(game, me, parts) {
    if (game.status !== "running" || !(me.tasks || []).length) return;
    const box = node("section", "sabotage-card is-tasks");
    box.append(node("span", "capture-label", "Ваши задания: дойдите до станции и ответьте на вопрос"));
    if (question) {
      const q = node("div", "sabotage-question");
      q.append(node("b", "sabotage-hanzi", question.zh), node("p", "sabotage-meta", question.pinyin));
      const options = node("div", "sabotage-options");
      question.options.forEach((text, index) => options.append(button("btn btn-secondary", text, () => answerTask(index))));
      q.append(options);
      box.append(q);
    }
    const list = node("div", "sabotage-tasks");
    me.tasks.forEach((t) => {
      if (t.done) {
        const fresh = !doneTasks.has(t.code);
        doneTasks.add(t.code);
        list.append(node("p", `sabotage-done${fresh ? " is-fresh" : ""}`, `✓ ${t.name_ru || t.code}`));
      } else {
        list.append(button("btn btn-secondary", `Я у станции: ${t.name_ru || t.code}`, () => challenge(t.code)));
      }
    });
    box.append(list);
    if (me.task_wait) box.append(node("p", "sabotage-meta", `После ошибки станция ждёт ${me.task_wait} с`));
    parts.push(box);
  }

  function drawMeeting(game, parts) {
    const m = game.meeting;
    const box = node("section", "sabotage-card is-meeting");
    const head = node("b", "sabotage-role", `Собрание! Созвал капитан ${m.caller} — все к нему. Голосование ещё `);
    head.append(countdown(m.until));
    box.append(head, node("p", "sabotage-meta", `Проголосовали ${m.voted} из ${m.voters}. Обсуждайте вслух, голосуйте здесь`));
    const me = game.me;
    if (me && me.alive) {
      const list = node("div", "sabotage-votes");
      m.candidates.forEach((c) => {
        const b = button("btn btn-secondary", c.name, () => act("vote", { choice: c.account_id }));
        b.setAttribute("aria-pressed", String(me.vote === c.account_id));
        list.append(b);
      });
      const skip = button("btn btn-secondary", "Пропустить", () => act("vote", { choice: 0 }));
      skip.setAttribute("aria-pressed", String(me.vote === 0));
      list.append(skip);
      box.append(list);
    } else if (me) {
      box.append(node("p", "sabotage-meta", "Выведенные не голосуют"));
    }
    parts.push(box);
  }

  function drawHistory(game, parts) {
    const history = game.history || (game.results && game.results.history) || [];
    if (!history.length) return;
    const list = node("ul", "sabotage-history");
    history.forEach((h) => {
      const text = h.ejected
        ? `Собрание ${h.meeting}: выгнали ${h.ejected} — ${h.was_saboteur ? "это был саботажник!" : "это был член экипажа"}`
        : `Собрание ${h.meeting}: никого не выгнали`;
      list.append(node("li", null, text));
    });
    parts.push(list);
  }

  function drawResults(game, parts) {
    if (game.cancelled) {
      parts.push(node("p", "sabotage-meta", "Игру остановил вожатый. Без наград"));
      return;
    }
    const r = game.results || {};
    parts.push(node("p", "sabotage-headline", `${r.winner === "crew" ? "Победил экипаж" : "Победили саботажники"}. ${REASONS[r.reason] || ""}`));
    parts.push(node("p", "sabotage-meta", `Саботажники: ${(r.saboteurs || []).join(", ")} · задания экипажа ${r.bar}%`));
    const list = node("ul", "sabotage-history");
    (r.winners || []).forEach((w) => {
      const prize = w.prize ? ` · +${w.prize}★` : w.limited ? " · награда сегодня уже была" : "";
      list.append(node("li", null, `${w.name}${prize}`));
    });
    parts.push(node("span", "capture-label", "Победители"), list);
    if (!r.prizes) parts.push(node("p", "sabotage-meta", "Игра была меньше, чем нужно для наград"));
    if (game.me && game.me.won) parts.push(node("p", "sabotage-meta is-ok", "Вы победили!"));
    drawHistory(game, parts);
  }

  function drawStaff(game, parts) {
    const actions = node("div", "capture-actions");
    if (!game || game.status === "over") {
      actions.append(button("btn btn-primary", "Открыть лобби", () => act("create")));
    } else if (game.status === "lobby") {
      const go = button("btn btn-primary", `Начать игру (${game.players})`, () => act("start"));
      go.disabled = busy || game.players < data.rules.min_players || !data.stations;
      actions.append(go);
    }
    if (game && game.status !== "over") {
      actions.append(armedButton("cancel", "btn btn-secondary", "Остановить", "Точно остановить?", () => act("cancel")));
    }
    parts.push(node("span", "capture-label", "Вожатому"), actions);
    if (!data.stations) parts.push(node("p", "sabotage-meta", "Станций нет: подтвердите точки Захвата на месте"));
    if (game && game.grid && game.grid.length) {
      const grid = node("div", "sabotage-grid");
      game.grid.forEach((p) => {
        const label = `${p.role === "saboteur" ? "☠ " : ""}${p.name}${p.captain ? " ★" : ""} · ${p.done}/${p.total}`;
        grid.append(node("span", `sabotage-chip is-${p.role}${p.alive ? "" : " is-out"}`, label));
      });
      parts.push(grid);
    }
  }

  function draw() {
    const body = $("sabotageBody");
    const status = $("sabotageStatus");
    if (!body) return;
    if (!signedIn() || !data) {
      body.replaceChildren(node("p", "spy-lead", LEAD), node("p", "sabotage-meta", signedIn() ? "Загружаем…" : "Войдите, чтобы играть"));
      status.textContent = "—";
      return;
    }
    const focused = document.activeElement && document.activeElement.id === "sabotageCode";
    const game = data.game;
    const rules = data.rules || {};
    const parts = [node("p", "spy-lead", LEAD), node("p", "sabotage-safety", SAFETY)];
    if (!game || game.status === "lobby") {
      if (rules.prize) {
        parts.push(node("p", "sabotage-meta",
          `Игра до ${rules.round_minutes} мин. Победители — по ${rules.prize.winner_stars}★ (в играх от ${rules.prize_min_players} человек, одна награда в день)`));
      }
    }
    if (!game) {
      parts.push(node("p", "sabotage-meta", data.can_host ? "Откройте лобби, когда все соберутся" : "Игру открывает вожатый — ждите объявления"));
      status.textContent = "ЖДЁМ ВОЖАТОГО";
    } else if (game.status === "lobby") {
      parts.push(node("b", "sabotage-count", `В лобби: ${game.players}`));
      if (data.can_play) {
        parts.push(game.me
          ? button("btn btn-secondary", "Выйти из лобби", () => act("leave"))
          : button("btn btn-primary", "Войти в игру", () => act("join")));
      }
      status.textContent = "ЛОББИ";
    } else if (game.status === "running" || game.status === "meeting") {
      const head = node("p", "sabotage-headline", `Задания экипажа: ${game.bar}% · в игре ${game.alive} из ${game.players} · до конца `);
      head.append(countdown(game.ends_at));
      parts.push(head);
      const bar = node("div", `sabotage-bar${game.bar >= 90 ? " is-near" : ""}`);
      const fill = node("span");
      fill.style.width = `${game.bar}%`;
      bar.append(fill);
      parts.push(bar, node("p", "sabotage-meta", `Полоса обновляется на собраниях. Капитаны: ${game.captains.join(", ")}`));
      if (game.status === "meeting") drawMeeting(game, parts);
      if (game.me) {
        drawRole(game, game.me, parts);
        drawTasks(game, game.me, parts);
      } else {
        parts.push(node("p", "sabotage-meta", "Игра идёт — вы смотрите со стороны"));
      }
      drawHistory(game, parts);
      status.textContent = game.status === "meeting" ? "СОБРАНИЕ" : "ИГРА ИДЁТ";
    } else {
      drawResults(game, parts);
      status.textContent = "ИТОГИ";
    }
    if (data.can_host) drawStaff(game, parts);
    parts.push(node("p", "case-message", note));
    body.replaceChildren(...parts);
    if (focused && $("sabotageCode")) {
      const input = $("sabotageCode");
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  // --- данные ------------------------------------------------------------------------------------

  let quietRefresh = true;
  let refreshing = false;
  function accept(body) {
    const before = !quietRefresh && !document.hidden && onGames() ? (data && data.game) : null;
    quietRefresh = false;
    data = body;
    const after = data.game;
    if (before && after && before.me && after.me && before.me.alive && after.me.alive === false) {
      window.showToast?.(after.me.ejected ? "Вас выгнали на собрании" : "Вас вывели! Молчите — вы призрак");
      window.ZhidaoSounds?.play("buy");
    }
    if (before && after && before.status === "running" && after.status === "meeting") {
      window.showToast?.(`Собрание! Все к капитану ${after.meeting.caller}`);
      window.ZhidaoSounds?.play("rare");
    }
    if (!after || after.status !== "running") question = null;
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      draw();
      if (before && after && (before.status !== after.status || before.me?.alive !== after.me?.alive)) window.ZhidaoRetro?.reveal(document.getElementById("sabotageBody"));
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
      const response = await api("/api/v4/sabotage");
      if (account !== session?.account?.id) return;
      accept(response);
    } catch (_) {
      quietRefresh = true;
      const status = document.getElementById("sabotageStatus");
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
      const result = await api(`/api/v4/sabotage/${action}`, { method: "POST", body });
      if (action === "eliminate") {
        codeDraft = "";
        if (result.eliminated) window.showToast?.(`${result.eliminated} выведен`);
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
      const result = await api("/api/v4/sabotage/task/challenge", {
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

  async function answerTask(choice) {
    if (busy) return;
    busy = true;
    draw();
    try {
      const result = await api("/api/v4/sabotage/task/answer", { method: "POST", body: { choice } });
      question = null;
      note = result.task && result.task.correct ? "Задание выполнено" : "Неверно. Станция примет вас через минуту";
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
    const want = status === "running" || status === "meeting" ? 3000 : status === "lobby" ? 5000 : 20000;
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
        document.querySelectorAll(".sabotage-left").forEach((span) => {
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
    doneTasks = new Set();
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
