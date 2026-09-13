"use strict";

/* Захват кампуса (V4_GAMES.md §4.12).

   Три фракции воюют за настоящие точки кампуса. У точки нажимают «Захватить»,
   телефон отдаёт позицию, сервер проверяет, что человек рядом и окно открыто,
   и присылает китайское слово с тремя переводами. Правильный ответ захватывает
   ничью точку, укрепляет свою или пробивает чужую.

   Всё решает сервер (zhidao_v4/capture.py): чья точка, какой ход, верен ли
   ответ, сколько очков. Правильный вариант сюда не приходит. Этот файл рисует
   слой поверх карты, табло фракций и карточку точки; геометрию карты не
   трогает — проекцию отдаёт window.ZhidaoCampus. */

(function () {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const REFRESH_MS = 30000;
  const SIZE = 1.15;          // ромб 10 единиц → примерно 11 px на экране
  const NEUTRAL = "#8a9aa6";
  const ACTIONS = { capture: "Захватить", reinforce: "Укрепить", attack: "Пробить защиту" };
  const RESULTS = {
    capture: "Точка захвачена!",
    reinforce: "Точка укреплена",
    attack: "Защита пробита — ещё немного",
    flip: "Точка перехвачена!",
  };

  let session = window.ZhidaoSession || null;
  let state = null;
  let ui = null;
  let scale = 1;
  let selected = null;
  let busy = false;
  let question = null;
  let noteText = "";
  let switchArmed = false;
  let poll = null;
  let ticker = null;
  const cooldownUntil = new Map();

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

  function svg(tag, attrs) {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onMap = () => document.documentElement.dataset.currentScreen === "campus-map";
  const faction = (code) => (state && state.factions.find((f) => f.code === code)) || null;
  const clock = (iso) => String(iso || "").slice(11, 16);
  const cooldownLeft = (code) => Math.max(0, Math.ceil(((cooldownUntil.get(code) || 0) - Date.now()) / 1000));
  const pips = (level, max) => "◆".repeat(level) + "◇".repeat(Math.max(0, max - level));

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
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

  // --- слой на карте -------------------------------------------------------------------

  function unitsPerPixel() {
    if (!ui || !ui.svg) return 1;
    const rect = ui.svg.getBoundingClientRect();
    return rect.width ? ui.svg.viewBox.baseVal.width / rect.width : 1.5;
  }

  function resize() {
    if (!ui || !ui.layer) return;
    const k = (unitsPerPixel() / scale) * SIZE;
    ui.layer.querySelectorAll(".capture-shape").forEach((shape) => shape.setAttribute("transform", `scale(${k.toFixed(3)})`));
  }

  function draw() {
    if (!ui || !ui.layer) return;
    ui.layer.querySelector(".capture-points")?.remove();
    if (!state || !state.points.length || !window.ZhidaoCampus) return;
    const group = svg("g", { class: "capture-points" });
    for (const p of state.points) {
      if (!p.coordinates) continue;
      const at = window.ZhidaoCampus.project(p.coordinates[0], p.coordinates[1]);
      if (!at) continue;
      const owner = faction(p.owner);
      const mine = Boolean(owner && state.you && state.you.faction === owner.code);
      const item = svg("g", {
        class: `capture-point${p.confirmed ? "" : " is-draft"}${mine ? " is-mine" : ""}${p.code === selected ? " is-selected" : ""}`,
        transform: `translate(${at.x.toFixed(1)} ${at.y.toFixed(1)})`,
        tabindex: "0",
        role: "button",
        "aria-label": `${p.name_ru || "Точка"}: ${owner ? `${owner.ru}, защита ${p.level}` : p.confirmed ? "ничья" : "не подтверждена"}`,
      });
      item.dataset.point = p.code;
      item.style.setProperty("--faction", owner ? owner.color : NEUTRAL);
      const shape = svg("g", { class: "capture-shape" });
      shape.append(
        svg("path", { class: "capture-glow", d: "M0 -17 L17 0 L0 17 L-17 0Z" }),
        svg("path", { class: "capture-core", d: "M0 -10 L10 0 L0 10 L-10 0Z" }));
      if (p.level) {
        const text = svg("text", { class: "capture-level", y: "3.6", "text-anchor": "middle" });
        text.textContent = String(p.level);
        shape.append(text);
      }
      item.append(shape);
      group.append(item);
    }
    const before = ui.layer.querySelector(".campus-marks") || (ui.me && ui.me.parentNode === ui.layer ? ui.me : null);
    if (before) ui.layer.insertBefore(group, before);
    else ui.layer.append(group);
    resize();
  }

  // --- табло -----------------------------------------------------------------------------

  function drawHud() {
    const hud = $("captureHud");
    if (!state || !state.season_id || (!state.you && !state.can_manage)) {
      hud.hidden = true;
      return;
    }
    const parts = [];
    const head = node("div", "capture-hud-head");
    head.append(node("span", "capture-label", "Захват кампуса · 占领"));
    const mine = state.you && faction(state.you.faction);
    if (mine) {
      const badge = node("b", "capture-you", `Вы — ${mine.ru} ${mine.zh}`);
      badge.style.setProperty("--faction", mine.color);
      head.append(badge);
    }
    parts.push(head);

    const top = Math.max(1, ...state.factions.map((f) => f.score));
    const board = node("div", "capture-board");
    state.factions.forEach((f) => {
      const row = node("div", `capture-score${mine && mine.code === f.code ? " is-mine" : ""}`);
      row.style.setProperty("--faction", f.color);
      const track = node("span", "capture-track");
      const bar = node("span", "capture-bar");
      bar.style.width = `${Math.round((f.score / top) * 100)}%`;
      track.append(bar);
      row.append(node("b", null, f.ru), track, node("span", "capture-score-value", `${f.score} · ⌂${f.points}`));
      board.append(row);
    });
    parts.push(board);

    let status;
    if (!state.enabled) status = "Захват выключен вожатым";
    else if (state.window.open) status = `Захват открыт до ${clock(state.window.closes_at)}`;
    else status = state.window.opens_at ? `Захват откроется в ${clock(state.window.opens_at)}` : "Захват закрыт";
    parts.push(node("p", `capture-meta${state.enabled && state.window.open ? " is-open" : ""}`, status));

    if (state.can_manage) {
      const label = switchArmed ? (state.enabled ? "Точно выключить?" : "Точно включить?")
        : (state.enabled ? "Выключить захват" : "Включить захват");
      const toggle = button("btn btn-secondary", label, toggleSwitch);
      toggle.disabled = busy;
      const unconfirmed = state.points.filter((p) => !p.confirmed).length;
      parts.push(toggle, node("p", "capture-meta", unconfirmed
        ? `Не подтверждено точек: ${unconfirmed}. Нажмите на серый ромб у объекта и подтвердите, стоя рядом`
        : "Все точки подтверждены"));
    }
    hud.replaceChildren(...parts);
    hud.hidden = false;
  }

  async function toggleSwitch() {
    if (busy || !state) return;
    if (!switchArmed) {
      switchArmed = true;
      drawHud();
      return;
    }
    switchArmed = false;
    busy = true;
    try {
      const result = await api("/api/v4/capture/switch", { method: "POST", body: { enabled: !state.enabled } });
      window.showToast?.(result.enabled ? "Захват включён" : "Захват выключен, очки замерли");
      await refresh();
    } catch (error) {
      window.showToast?.(error.message);
    } finally {
      busy = false;
      drawHud();
    }
  }

  // --- карточка точки ---------------------------------------------------------------------

  function drawQuestion() {
    const box = node("div", "capture-question");
    const left = Math.max(0, Math.ceil((question.deadline - Date.now()) / 1000));
    box.append(
      node("span", "capture-label", `${ACTIONS[question.action] || "Ход"} · ${left} с`),
      node("b", "capture-hanzi", question.zh),
      node("p", "capture-pinyin", question.pinyin),
      node("p", "capture-meta", "Что это значит?"));
    const options = node("div", "capture-options");
    question.options.forEach((text, index) => {
      const b = button("btn btn-secondary", text, () => sendAnswer(index));
      b.disabled = busy;
      options.append(b);
    });
    box.append(options);
    return box;
  }

  function showCard(code) {
    const card = $("capturePointCard");
    const p = state && state.points.find((x) => x.code === code);
    if (!p) {
      card.hidden = true;
      selected = null;
      return;
    }
    if (selected !== code) noteText = "";
    selected = code;
    ui?.layer?.querySelectorAll(".capture-point").forEach((g) => g.classList.toggle("is-selected", g.dataset.point === code));
    const owner = faction(p.owner);
    card.style.setProperty("--faction", owner ? owner.color : NEUTRAL);
    const parts = [
      node("span", "capture-label", p.confirmed ? "Точка захвата" : "Точка не подтверждена"),
      node("b", "capture-title", p.name_ru || "Точка кампуса"),
    ];
    if (p.name_zh) parts.push(node("p", "capture-zh", p.name_zh));
    if (p.confirmed) {
      parts.push(node("p", "capture-owner", owner
        ? `${owner.ru} ${owner.zh} · защита ${pips(p.level, p.max_level)}`
        : "Ничья — захватите первыми"));
    }

    if (question && question.code === code) {
      parts.push(drawQuestion());
    } else {
      const actions = node("div", "capture-actions");
      if (p.confirmed && state.you) {
        const wait = cooldownLeft(code);
        let reason = "";
        if (!state.enabled) reason = "Захват выключен вожатым";
        else if (!state.window.open) reason = state.window.opens_at ? `Захват откроется в ${clock(state.window.opens_at)}` : "Захват закрыт";
        else if (!p.action) reason = "Точка вашей фракции укреплена до предела";
        else if (wait) reason = `Точка ждёт вас через ${wait} с`;
        const go = button("btn btn-primary", ACTIONS[p.action] || "Ход недоступен", () => startChallenge(p));
        go.disabled = busy || Boolean(reason);
        actions.append(go);
        parts.push(node("p", "capture-meta", reason || `Встаньте у точки (до ${state.radius_m} м) и ответьте на вопрос`));
      }
      if (state.can_manage) {
        actions.append(button("btn btn-secondary", p.confirmed ? "Уточнить точку здесь" : "Подтвердить точку здесь", () => confirmPoint(p)));
      }
      if (actions.childElementCount) parts.push(actions);
    }
    parts.push(node("p", "case-message capture-note", noteText));
    card.replaceChildren(...parts);
    card.hidden = false;
  }

  function setNote(text) {
    noteText = text || "";
    const note = $("capturePointCard").querySelector(".capture-note");
    if (note) note.textContent = noteText;
  }

  async function startChallenge(p) {
    if (busy) return;
    busy = true;
    showCard(p.code);
    setNote("Ищем вас…");
    try {
      const coords = await position();
      const result = await api(`/api/v4/capture/points/${p.code}/challenge`, {
        method: "POST", body: { lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy },
      });
      question = { code: p.code, action: result.action, ...result.question, deadline: Date.now() + result.seconds * 1000 };
      noteText = "";
      window.ZhidaoCampus?.reload();   // ход у точки открывает туман
    } catch (error) {
      noteText = error.message;
      if (error.status === 429 || error.status === 409) refresh();
    } finally {
      busy = false;
      showCard(p.code);
    }
  }

  async function sendAnswer(choice) {
    if (busy || !question) return;
    busy = true;
    const code = question.code;
    try {
      const result = await api(`/api/v4/capture/points/${code}/answer`, { method: "POST", body: { choice } });
      question = null;
      cooldownUntil.set(code, Date.now() + (result.point.cooldown_seconds || 0) * 1000);
      if (result.correct) {
        noteText = RESULTS[result.action] || "Ход засчитан";
        window.showToast?.(noteText);
        if (window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
      } else {
        noteText = "Неверно. Точка подождёт вас пару минут";
      }
      await refresh();
    } catch (error) {
      question = null;
      noteText = error.message;
    } finally {
      busy = false;
      showCard(code);
    }
  }

  async function confirmPoint(p) {
    if (busy) return;
    busy = true;
    setNote("Ищем вас… для подтверждения нужна точность до 30 м");
    try {
      const coords = await position();
      const result = await api(`/api/v4/capture/points/${p.code}/confirm`, {
        method: "POST", body: { lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy },
      });
      noteText = `Точка подтверждена · ${result.offset_m} м от объекта на карте`;
      await refresh();
    } catch (error) {
      noteText = error.message;
    } finally {
      busy = false;
      showCard(p.code);
    }
  }

  // --- данные и часы ---------------------------------------------------------------------------

  async function refresh() {
    if (!signedIn()) {
      state = null;
    } else {
      try {
        state = await api("/api/v4/capture");
      } catch (_) {
        /* табло подождёт следующего опроса */
      }
    }
    (state ? state.points : []).forEach((p) => {
      if (p.cooldown_seconds) cooldownUntil.set(p.code, Date.now() + p.cooldown_seconds * 1000);
    });
    draw();
    drawHud();
    if (selected) showCard(selected);
  }

  function tick() {
    if (!selected) return;
    if (question && Date.now() >= question.deadline) {
      question = null;
      noteText = "Время на ответ вышло";
      showCard(selected);
    } else if (question || cooldownLeft(selected) > 0) {
      showCard(selected);
    }
  }

  function start() {
    refresh();
    if (!poll) poll = setInterval(() => { if (!busy && !question) refresh(); }, REFRESH_MS);
    if (!ticker) ticker = setInterval(tick, 1000);
  }

  function stop() {
    clearInterval(poll);
    clearInterval(ticker);
    poll = null;
    ticker = null;
  }

  // --- подключение -------------------------------------------------------------------------------

  window.addEventListener("zhidao:campus-drawn", (event) => {
    ui = event.detail;
    draw();
  });
  window.addEventListener("zhidao:campus-view", (event) => {
    if (event.detail === scale) return;
    scale = event.detail;
    resize();
  });
  window.addEventListener("zhidao:capture-point", (event) => showCard(event.detail));
  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    state = null;
    selected = null;
    question = null;
    cooldownUntil.clear();
    $("capturePointCard").hidden = true;
    if (onMap()) start();
    else drawHud();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "campus-map") start();
    else stop();
  });
  window.addEventListener("resize", resize);
}());
