"use strict";

/* Дуэли Захвата кампуса (V4_GAMES.md §4.12, этап 2).

   Двое из разных фракций рядом: один жмёт «Вызвать» и показывает код, второй
   вводит его. Вид дуэли выбирает сервер: китайский поединок, реакция или
   攻守巧. Победа даёт фракции очки, а дуэль у точки — ход на этой точке.

   Всё решает сервер (zhidao_v4/duels.py): вопросы, время, чей раунд, итог.
   Правильные ответы и ход соперника в текущем раунде сюда не приходят.
   Панель живёт на экране карты рядом с табло Захвата (capture.js); оттуда же
   приходят фракции, окно и просьба «дуэль за эту точку». */

(function () {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 1500;
  const KINDS = { quiz: "Китайский поединок", reaction: "Реакция", tactics: "攻 · 守 · 巧" };
  const HELP = {
    quiz: "Пять одинаковых слов. Больше верных — победа, при равенстве побеждает быстрый",
    reaction: "Найдите иероглиф по переводу. Чем быстрее верный ответ, тем больше очков",
    tactics: "Тайный ход в каждом раунде: 攻 бьёт 巧, 巧 бьёт 守, 守 бьёт 攻. До двух побед",
  };
  const MOVES = [["attack", "攻", "Атака"], ["defend", "守", "Защита"], ["trick", "巧", "Хитрость"]];
  const MOVE_TEXT = Object.fromEntries(MOVES.map(([code, zh, ru]) => [code, `${zh} ${ru}`]));
  const POINT_TEXT = { capture: "точка захвачена", reinforce: "точка укреплена", attack: "защита точки пробита", flip: "точка перехвачена" };

  let session = window.ZhidaoSession || null;
  let cap = null;
  let data = null;
  let busy = false;
  let poll = null;
  let ticker = null;
  let code = "";
  let note = "";
  let leaveArmed = false;
  let offerDeadline = 0;
  let wasActive = false;
  const dismissed = new Set();

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
  const onMap = () => document.documentElement.dataset.currentScreen === "campus-map";
  const faction = (c) => (cap && cap.factions.find((f) => f.code === c)) || null;
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));

  function chip(factionCode, text) {
    const f = faction(factionCode);
    const span = node("b", "capture-you", text);
    span.style.setProperty("--faction", f ? f.color : "#8a9aa6");
    return span;
  }

  function countdown(deadlineMs) {
    const span = node("span", "capture-duel-left");
    span.dataset.deadline = String(deadlineMs);
    span.textContent = `${Math.max(0, Math.ceil((deadlineMs - Date.now()) / 1000))} с`;
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

  // --- экраны панели -----------------------------------------------------------------------

  function drawIdle() {
    const parts = [node("span", "capture-label", "⚔ Дуэли · 对决")];
    let reason = "";
    if (!cap.enabled) reason = "Захват выключен вожатым — дуэли тоже";
    else if (!cap.window.open) reason = "Дуэли идут в дневные окна Захвата";
    else if (data && data.duels_left === 0) reason = "Дуэли на сегодня закончились";
    const bonus = data && data.bonus ? data.bonus : 3;
    parts.push(node("p", "capture-meta",
      `Сразитесь с соперником из другой фракции: победа приносит фракции ${bonus} очка. Дуэль у точки решает её судьбу`));
    if (data && data.duels_left != null) parts.push(node("p", "capture-meta", `Сегодня осталось дуэлей: ${data.duels_left}`));
    if (reason) {
      parts.push(node("p", "capture-meta", reason));
      return parts;
    }
    const actions = node("div", "capture-actions");
    actions.append(button("btn btn-primary", "Вызвать на дуэль", () => makeOffer(null)));
    parts.push(actions);

    const form = node("form", "capture-duel-join");
    const input = node("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.maxLength = 6;
    input.placeholder = "000000";
    input.value = code;
    input.setAttribute("aria-label", "Код дуэли");
    input.addEventListener("input", () => { code = input.value.replace(/\D/g, "").slice(0, 6); input.value = code; });
    const accept = node("button", "btn btn-secondary", "Принять вызов");
    accept.type = "submit";
    accept.disabled = busy;
    form.append(input, accept);
    form.addEventListener("submit", (event) => { event.preventDefault(); joinDuel(); });
    parts.push(form);
    return parts;
  }

  function drawOffer(offer) {
    const parts = [node("span", "capture-label", "⚔ Ваш вызов")];
    parts.push(node("b", "capture-duel-code", `${offer.code.slice(0, 3)} ${offer.code.slice(3)}`));
    const line = node("p", "capture-meta", "Покажите код сопернику из другой фракции · код сгорит через ");
    line.append(countdown(offerDeadline));
    parts.push(line);
    if (offer.point) {
      const p = cap && cap.points.find((x) => x.code === offer.point);
      parts.push(node("p", "capture-owner", `Дуэль за точку: ${p ? p.name_ru : offer.point}`));
    }
    const actions = node("div", "capture-actions");
    actions.append(button("btn btn-secondary", "Отменить вызов", leaveDuel));
    parts.push(actions);
    return parts;
  }

  function drawHead(duel) {
    const head = node("div", "capture-hud-head");
    head.append(node("span", "capture-label", `⚔ ${KINDS[duel.kind]}`));
    const rival = faction(duel.rival.faction);
    head.append(chip(duel.rival.faction, `против ${duel.rival.name}${rival ? ` · ${rival.zh}` : ""}`));
    const parts = [head];
    if (duel.point) parts.push(node("p", "capture-owner", `За точку: ${duel.point.name_ru || duel.point.code}`));
    return parts;
  }

  function drawSheet(duel) {
    const s = duel.sheet;
    const parts = [node("p", "capture-meta", HELP[duel.kind])];
    const status = node("p", "capture-meta is-open",
      `${s.current ? `Вопрос ${s.answered + 1} из ${s.total}` : "Вы ответили на все"} · соперник ${s.rival_answered}/${s.total} · `);
    status.append(countdown(timeOf(s.deadline)));
    parts.push(status);
    if (!s.current) {
      parts.push(node("p", "capture-meta", "Ждём соперника…"));
      return parts;
    }
    const box = node("div", "capture-question");
    if (s.current.prompt.zh) {
      box.append(node("b", "capture-hanzi", s.current.prompt.zh), node("p", "capture-pinyin", s.current.prompt.pinyin));
    } else {
      box.append(node("b", "capture-duel-word", s.current.prompt.ru), node("p", "capture-meta", "Найдите иероглиф"));
    }
    const options = node("div", `capture-options${duel.kind === "reaction" ? " is-hanzi" : ""}`);
    s.current.options.forEach((text, index) => options.append(button("btn btn-secondary", text, () => sendAnswer(index))));
    box.append(options);
    parts.push(box);
    return parts;
  }

  function drawTactics(duel) {
    const t = duel.tactics;
    const parts = [node("p", "capture-meta", HELP.tactics)];
    const status = node("p", "capture-meta is-open", `Раунд ${t.round} · вы ${t.wins.you} : ${t.wins.rival} соперник · `);
    status.append(countdown(timeOf(t.round_deadline)));
    parts.push(status);
    if (t.last) {
      const verdict = t.last.winner === "tie" ? "ничья" : t.last.winner === "you" ? "раунд ваш" : "раунд соперника";
      parts.push(node("p", "capture-meta",
        `Прошлый раунд: вы ${t.last.you ? MOVE_TEXT[t.last.you] : "—"} · соперник ${t.last.rival ? MOVE_TEXT[t.last.rival] : "—"} → ${verdict}`));
    }
    if (t.your_move) {
      parts.push(node("p", "capture-owner", `Ваш ход: ${MOVE_TEXT[t.your_move]}`),
        node("p", "capture-meta", t.rival_moved ? "Соперник тоже сходил…" : "Ждём ход соперника…"));
      return parts;
    }
    const moves = node("div", "capture-duel-moves");
    MOVES.forEach(([move, zh, ru]) => {
      const b = button("btn btn-secondary capture-duel-move", "", () => sendMove(move));
      b.append(node("b", null, zh), node("small", null, ru));
      moves.append(b);
    });
    parts.push(moves);
    if (t.rival_moved) parts.push(node("p", "capture-meta", "Соперник уже сходил"));
    return parts;
  }

  function drawActive(duel) {
    const parts = [...drawHead(duel), ...(duel.sheet ? drawSheet(duel) : drawTactics(duel))];
    const actions = node("div", "capture-actions");
    actions.append(button("btn btn-secondary", leaveArmed ? "Точно сдаться?" : "Сдаться", () => {
      if (!leaveArmed) {
        leaveArmed = true;
        render();
        return;
      }
      leaveDuel();
    }));
    parts.push(actions);
    return parts;
  }

  function drawResult(duel) {
    const r = duel.result;
    const titles = { win: "Победа!", lose: "Поражение", draw: "Ничья", cancelled: "Дуэль отменена" };
    const parts = [...drawHead(duel), node("b", `capture-duel-result is-${r.result}`, titles[r.result] || "Дуэль окончена")];
    if (r.forfeit) parts.push(node("p", "capture-meta", r.forfeit === "you" ? "Вы сдались" : "Соперник сдался"));
    if (r.score) {
      if (duel.kind === "tactics") parts.push(node("p", "capture-meta", `Раунды ${r.score.you} : ${r.score.rival}`));
      else if (duel.kind === "quiz") parts.push(node("p", "capture-meta", `Верных ${r.score.you.correct} : ${r.score.rival.correct}`));
      else parts.push(node("p", "capture-meta", `Очки реакции ${r.score.you.points} : ${r.score.rival.points}`));
    }
    if (r.effect && r.effect.kind === "bonus") {
      const f = faction(r.effect.faction);
      parts.push(node("p", "capture-owner", `${f ? f.ru : "Фракция"} +${r.effect.points} очка`));
    } else if (r.effect && r.effect.kind === "point") {
      parts.push(node("p", "capture-owner", `${duel.point ? duel.point.name_ru : "Точка"}: ${POINT_TEXT[r.effect.action] || "без изменений"}`));
    }
    const actions = node("div", "capture-actions");
    actions.append(button("btn btn-primary", "Ещё дуэль", () => { dismissed.add(duel.id); render(); }));
    parts.push(actions);
    return parts;
  }

  function render() {
    const box = $("captureDuel");
    if (!signedIn() || !cap || !cap.you) {
      box.hidden = true;
      return;
    }
    const duel = data && data.duel;
    const offer = data && data.offer;
    let parts;
    if (duel && duel.status === "active") parts = drawActive(duel);
    else if (duel && !dismissed.has(duel.id)) parts = drawResult(duel);
    else if (offer) parts = drawOffer(offer);
    else parts = drawIdle();
    const focused = document.activeElement && box.contains(document.activeElement) && document.activeElement.tagName === "INPUT";
    box.replaceChildren(...parts, node("p", "case-message capture-duel-note", note));
    box.hidden = false;
    if (focused) box.querySelector("input")?.focus();
  }

  // --- запросы ---------------------------------------------------------------------------------

  function accept(body) {
    const active = Boolean(body.duel && body.duel.status === "active");
    if (wasActive && !active && body.duel) {
      window.dispatchEvent(new Event("zhidao:capture-refresh"));
      if (body.duel.result && body.duel.result.result === "win" && window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
    }
    if (active && !(data && data.duel && data.duel.id === body.duel.id)) leaveArmed = false;
    wasActive = active;
    if (body.offer && !(data && data.offer && data.offer.code === body.offer.code)) {
      offerDeadline = Date.now() + body.offer.expires_in * 1000;
    }
    data = body;
    if (active || body.offer) startPoll();
    else stopPoll();
    render();
  }

  async function refresh() {
    if (!signedIn()) {
      data = null;
      render();
      return;
    }
    try {
      accept(await api("/api/v4/capture/duel"));
    } catch (_) {
      /* панель подождёт следующего опроса */
    }
  }

  async function run(action) {
    if (busy) return;
    busy = true;
    note = "";
    render();
    try {
      await action();
    } catch (error) {
      note = error.message;
      if (error.status === 404 || error.status === 409) await refresh();
    } finally {
      busy = false;
      render();
    }
  }

  function makeOffer(point) {
    return run(async () => {
      const body = {};
      if (point) {
        note = "Ищем вас…";
        render();
        const coords = await position();
        Object.assign(body, { point, lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy });
      }
      const offer = await api("/api/v4/capture/duels/offer", { method: "POST", body });
      note = "";
      offerDeadline = Date.now() + offer.expires_in * 1000;
      accept({ ...(data || {}), duel: null, offer });
      $("captureDuel").scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  function joinDuel() {
    if (code.length !== 6) {
      note = "Введите шесть цифр кода";
      render();
      return undefined;
    }
    return run(async () => {
      accept(await api("/api/v4/capture/duels/join", { method: "POST", body: { code } }));
      code = "";
    });
  }

  const sendAnswer = (choice) => run(async () => accept(await api("/api/v4/capture/duel/answer", { method: "POST", body: { choice } })));
  const sendMove = (move) => run(async () => accept(await api("/api/v4/capture/duel/move", { method: "POST", body: { move } })));
  const leaveDuel = () => run(async () => {
    leaveArmed = false;
    accept(await api("/api/v4/capture/duel/leave", { method: "POST" }));
  });

  // --- часы --------------------------------------------------------------------------------------

  function tickCountdowns() {
    let expired = false;
    document.querySelectorAll("#captureDuel .capture-duel-left").forEach((span) => {
      const left = Math.ceil((Number(span.dataset.deadline) - Date.now()) / 1000);
      span.textContent = `${Math.max(0, left)} с`;
      if (left <= 0) expired = true;
    });
    if (expired && data && data.offer && !data.duel && Date.now() > offerDeadline) {
      data = { ...data, offer: null };
      stopPoll();
      render();
    }
  }

  function startPoll() {
    if (!poll) poll = setInterval(() => { if (!busy) refresh(); }, POLL_MS);
    if (!ticker) ticker = setInterval(tickCountdowns, 500);
  }

  function stopPoll() {
    clearInterval(poll);
    poll = null;
  }

  // --- подключение -----------------------------------------------------------------------------

  window.addEventListener("zhidao:capture-state", (event) => {
    const first = !cap;
    cap = event.detail;
    if (first) refresh();
    else render();
  });
  window.addEventListener("zhidao:duel-offer", (event) => makeOffer(event.detail));
  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    cap = null;
    data = null;
    wasActive = false;
    dismissed.clear();
    stopPoll();
    render();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "campus-map") refresh();
    else stopPoll();
  });
}());
