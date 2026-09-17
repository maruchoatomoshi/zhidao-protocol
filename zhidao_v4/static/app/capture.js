"use strict";

/* Захват кампуса (V4_GAMES.md §4.12).

   Три фракции воюют за настоящие точки кампуса. У точки нажимают «Захватить»,
   телефон отдаёт позицию, сервер проверяет, что человек рядом и окно открыто,
   и присылает китайское слово с тремя переводами. Правильный ответ захватывает
   ничью точку, укрепляет свою или пробивает чужую.

   Этап 3: способности складчиной фракции (щит, туман, двойные очки, разведка),
   лидер дня и итоги войны с кубком.

   Всё решает сервер (zhidao_v4/capture.py): чья точка, какой ход, верен ли
   ответ, сколько очков, когда включилась способность. Правильный вариант сюда
   не приходит. Этот файл рисует слой поверх карты, табло фракций и карточку
   точки; геометрию карты не трогает — проекцию отдаёт window.ZhidaoCampus. */

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
    shielded: "Щит отбил атаку",
  };
  const ABILITY = {
    shield: { icon: "🛡", name: "Щит", note: "Чужие не пробьют точку" },
    fog: { icon: "🌫", name: "Туман", note: "Соперники не видят уровни защиты ваших точек" },
    double: { icon: "×2", name: "Двойные очки", note: "Точка приносит вдвое больше очков" },
    scout: { icon: "🔍", name: "Разведка", note: "Видно, сколько ходов сегодня было у точки" },
  };

  let session = window.ZhidaoSession || null;
  let state = null;
  let ui = null;
  let scale = 1;
  let selected = null;
  let busy = false;
  let question = null;
  let noteText = "";
  let hudNote = "";
  let armed = null;
  let poll = null;
  let ticker = null;
  let refreshVersion = 0;
  const cooldownUntil = new Map();
  const poolKeys = new Map();

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
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));
  const minutesLeft = (iso) => Math.max(1, Math.ceil((timeOf(iso) - Date.now()) / 60000));
  const cooldownLeft = (code) => Math.max(0, Math.ceil(((cooldownUntil.get(code) || 0) - Date.now()) / 1000));
  const pips = (level, max) => "◆".repeat(level) + "◇".repeat(Math.max(0, max - level));
  const newKey = () => `pool-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

  // Живой отсчёт: меняется только цифра, кнопки рядом не пересоздаются.
  function countdown(untilMs, suffix = " с") {
    const span = node("span", "capture-countdown");
    span.dataset.until = String(untilMs);
    span.dataset.suffix = suffix;
    span.textContent = `${Math.max(0, Math.ceil((untilMs - Date.now()) / 1000))}${suffix}`;
    return span;
  }

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

  // Штриховка боя рисуется одним <pattern> в <defs> самой карты и переиспользуется
  // всеми зонами -- не заводим свою на каждую точку.
  function ensureContestPattern() {
    if (!ui || !ui.svg || ui.svg.querySelector("#capture-contest-hatch")) return;
    let defs = ui.svg.querySelector("defs");
    if (!defs) {
      defs = svg("defs", {});
      ui.svg.insertBefore(defs, ui.svg.firstChild);
    }
    const pattern = svg("pattern", {
      id: "capture-contest-hatch", width: "6", height: "6",
      patternTransform: "rotate(45)", patternUnits: "userSpaceOnUse",
    });
    pattern.append(svg("rect", { width: "6", height: "6", fill: "#ff4a3d", "fill-opacity": ".18" }));
    pattern.append(svg("rect", { width: "3", height: "6", fill: "#ff4a3d", "fill-opacity": ".55" }));
    defs.append(pattern);
  }

  // --- разбиение всей карты между точками (взвешенная диаграмма Вороного) -------------
  //
  // Игроки просили не пятно вокруг здания, а настоящую границу: карта делится
  // между всеми точками захвата целиком, без дыр и нахлёстов, граница одной
  // упирается ровно в границу соседней. Это степенная (Лагеррова) диаграмма
  // Вороного, отсечённая по контуру подготовленного сектора (та же граница,
  // которой уже проверяют "вы на территории кампуса" в campus-map.js) --
  // ничего не выдумываем, просто честно делим настоящую площадь между
  // настоящими точками. Вес у "Общий учебный корпус" больше остальных --
  // её участок нарочно крупнее (решение пользователя 2026-09-17).
  const ZONE_WEIGHTS = { teaching: 46000 };

  // Sutherland-Hodgman: оставляет часть poly по одну сторону прямой,
  // заданной точкой (px,py) и внешней нормалью (nx,ny).
  function clipHalfPlane(poly, px, py, nx, ny) {
    if (!poly.length) return poly;
    const out = [];
    const side = (pt) => (pt.x - px) * nx + (pt.y - py) * ny;
    for (let i = 0; i < poly.length; i += 1) {
      const cur = poly[i];
      const prev = poly[(i + poly.length - 1) % poly.length];
      const curSide = side(cur);
      const prevSide = side(prev);
      if (curSide >= 0) {
        if (prevSide < 0) {
          const t = prevSide / (prevSide - curSide);
          out.push({ x: prev.x + (cur.x - prev.x) * t, y: prev.y + (cur.y - prev.y) * t });
        }
        out.push(cur);
      } else if (prevSide >= 0) {
        const t = prevSide / (prevSide - curSide);
        out.push({ x: prev.x + (cur.x - prev.x) * t, y: prev.y + (cur.y - prev.y) * t });
      }
    }
    return out;
  }

  // Граница между взвешенными точками -- та же прямая, что у обычного
  // серединного перпендикуляра, но сдвинутая к более лёгкой точке на
  // (wSite-wOther)/(2|PQ|) вдоль (other-site): тяжелее точка -- дальше от
  // неё уезжает граница, больше её участок. Нормаль (site-other) указывает
  // на саму site -- её и оставляем при отсечке половиной плоскости.
  function voronoiCell(site, others, boundary) {
    let poly = boundary;
    for (const other of others) {
      if (other === site) continue;
      const dx = other.x - site.x;
      const dy = other.y - site.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 1e-6) continue;
      const nx = -dx / dist;
      const ny = -dy / dist;
      const shift = ((site.w || 0) - (other.w || 0)) / (2 * dist);
      const mx = (site.x + other.x) / 2 - shift * nx;
      const my = (site.y + other.y) / 2 - shift * ny;
      poly = clipHalfPlane(poly, mx, my, nx, ny);
      if (!poly.length) break;
    }
    return poly;
  }

  function computeZones(points) {
    const cells = new Map();
    const boundaryRing = window.ZhidaoCampus.boundary();
    if (!boundaryRing) return cells;
    const boundary = boundaryRing.map(([lon, lat]) => window.ZhidaoCampus.project(lon, lat)).filter(Boolean);
    if (boundary.length < 3) return cells;
    const sites = [];
    for (const p of points) {
      if (!p.coordinates) continue;
      const at = window.ZhidaoCampus.project(p.coordinates[0], p.coordinates[1]);
      if (at) sites.push({ code: p.code, x: at.x, y: at.y, w: ZONE_WEIGHTS[p.code] || 0 });
    }
    for (const site of sites) cells.set(site.code, voronoiCell(site, sites, boundary));
    return cells;
  }

  function drawZone(cellPts, p, owner, mine, contested) {
    if (!cellPts || cellPts.length < 3) return null;
    const classes = ["capture-zone"];
    if (!p.confirmed) classes.push("is-draft");
    if (mine) classes.push("is-mine");
    if (contested) classes.push("is-contested");
    const zone = svg("polygon", {
      class: classes.join(" "),
      points: cellPts.map((pt) => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" "),
    });
    zone.dataset.point = p.code;
    zone.style.setProperty("--faction", owner ? owner.color : NEUTRAL);
    return zone;
  }

  function draw() {
    if (!ui || !ui.layer) return;
    ui.layer.querySelector(".capture-points")?.remove();
    ui.layer.querySelector(".capture-zones")?.remove();
    if (!state || !state.points.length || !window.ZhidaoCampus) return;
    ensureContestPattern();
    const zoneCells = computeZones(state.points);
    const zones = svg("g", { class: "capture-zones" });
    const group = svg("g", { class: "capture-points" });
    for (const p of state.points) {
      if (!p.coordinates) continue;
      const at = window.ZhidaoCampus.project(p.coordinates[0], p.coordinates[1]);
      if (!at) continue;
      const owner = faction(p.owner);
      const mine = Boolean(owner && state.you && state.you.faction === owner.code);
      const contested = Boolean(question && question.code === p.code);
      const zone = drawZone(zoneCells.get(p.code), p, owner, mine, contested);
      if (zone) zones.append(zone);
      const classes = ["capture-point"];
      if (!p.confirmed) classes.push("is-draft");
      if (mine) classes.push("is-mine");
      if (p.shield_until) classes.push("is-shielded");
      if (p.double_until) classes.push("is-double");
      if (p.code === selected) classes.push("is-selected");
      if (contested) classes.push("is-contested");
      const item = svg("g", {
        class: classes.join(" "),
        transform: `translate(${at.x.toFixed(1)} ${at.y.toFixed(1)})`,
        tabindex: "0",
        role: "button",
        "aria-label": `${p.name_ru || "Точка"}: ${owner ? `${owner.ru}, защита ${p.hidden ? "скрыта" : p.level}` : p.confirmed ? "ничья" : "не подтверждена"}`,
      });
      item.dataset.point = p.code;
      item.style.setProperty("--faction", owner ? owner.color : NEUTRAL);
      const shape = svg("g", { class: "capture-shape" });
      shape.append(svg("path", { class: "capture-glow", d: "M0 -17 L17 0 L0 17 L-17 0Z" }));
      if (p.shield_until) shape.append(svg("path", { class: "capture-ring", d: "M0 -14 L14 0 L0 14 L-14 0Z" }));
      shape.append(svg("path", { class: "capture-core", d: "M0 -10 L10 0 L0 10 L-10 0Z" }));
      if (p.owner) {
        const text = svg("text", { class: "capture-level", y: "3.6", "text-anchor": "middle" });
        text.textContent = p.hidden ? "?" : String(p.level);
        shape.append(text);
      }
      item.append(shape);
      group.append(item);
    }
    const before = ui.layer.querySelector(".campus-marks") || (ui.me && ui.me.parentNode === ui.layer ? ui.me : null);
    if (before) {
      ui.layer.insertBefore(zones, before);
      ui.layer.insertBefore(group, before);
    } else {
      ui.layer.append(zones);
      ui.layer.append(group);
    }
    resize();
  }

  // --- способности ---------------------------------------------------------------------------

  function abilityBlock(ability, target) {
    const spec = state.abilities[ability];
    const info = ABILITY[ability];
    const box = node("div", "capture-ability");
    box.append(node("b", "capture-ability-title", `${info.icon} ${info.name} · ${spec.price}★ · ${spec.minutes} мин`),
      node("small", null, info.note));
    const effect = state.effects.find((e) => e.ability === ability && (e.target || null) === (target || null));
    if (effect) {
      box.classList.add("is-active");
      box.append(node("p", "capture-meta is-open", `Действует ещё ${minutesLeft(effect.until)} мин`));
      return box;
    }
    const pool = state.pools.find((p) => p.ability === ability && (p.target || null) === (target || null));
    const collected = pool ? pool.collected : 0;
    const track = node("span", "capture-track");
    const bar = node("span", "capture-bar");
    bar.style.width = `${Math.round((collected / spec.price) * 100)}%`;
    track.append(bar);
    const row = node("div", "capture-pool");
    row.append(track, node("span", "capture-score-value", `${collected}/${spec.price}★`));
    box.append(row);
    const remaining = spec.price - collected;
    const open = state.enabled && state.window.open && !state.war.finished;
    const chips = node("div", "capture-actions");
    [...new Set([1, 5, remaining].filter((n) => n > 0 && n <= remaining))].forEach((amount) => {
      const chip = button("btn btn-secondary capture-chip", amount === remaining ? `Весь остаток ${amount}★` : `+${amount}★`,
        () => contribute(ability, target, amount));
      chip.disabled = busy || !open;
      chips.append(chip);
    });
    box.append(chips);
    if (!open) box.append(node("p", "capture-meta", "Взносы принимаются, пока идёт Захват"));
    return box;
  }

  async function contribute(ability, target, amount) {
    if (busy) return;
    const slot = `${ability}:${target || ""}:${amount}`;
    const key = poolKeys.get(slot) || newKey();
    poolKeys.set(slot, key);
    busy = true;
    rerender();
    try {
      const result = await api("/api/v4/capture/pool", { method: "POST", key, body: { ability, target: target || undefined, amount } });
      poolKeys.delete(slot);
      const text = result.activated
        ? `${ABILITY[ability].icon} ${ABILITY[ability].name} включён!`
        : `Взнос ${result.paid}★ · собрано ${result.collected}/${result.price}★`;
      window.showToast?.(text);
      if (result.activated && window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
      if (target) noteText = text;
      else hudNote = text;
      await refresh();
    } catch (error) {
      if (error.status) poolKeys.delete(slot);
      const text = error.status || !poolKeys.has(slot) ? error.message : "Нет связи. Нажмите ещё раз — звёзды не спишутся дважды.";
      if (target) noteText = text;
      else hudNote = text;
    } finally {
      busy = false;
      rerender();
    }
  }

  // --- табло -----------------------------------------------------------------------------

  function staffButton(kind, label, confirmLabel, action) {
    const b = button("btn btn-secondary", armed === kind ? confirmLabel : label, () => {
      if (armed !== kind) {
        armed = kind;
        drawHud();
        return;
      }
      armed = null;
      action();
    });
    b.disabled = busy;
    return b;
  }

  function drawHud() {
    const hud = $("captureHud");
    if (!state || !state.season_id || (!state.you && !state.can_manage)) {
      hud.hidden = true;
      return;
    }
    const parts = [];
    const head = node("div", "capture-hud-head");
    head.append(node("span", "capture-label", `Захват кампуса · 占领 · война №${state.war.number}`));
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

    if (state.war.finished) {
      const last = state.wars[state.wars.length - 1];
      const names = last && last.winners.length ? last.winners.map((c) => faction(c)?.ru || c).join(", ") : "никто";
      parts.push(node("p", "capture-cup", `🏆 Война №${state.war.number} окончена · победили: ${names}`));
    } else {
      const today = state.factions.map((f) => `${f.ru} ${f.today}`).join(" · ");
      const reward = state.daily_reward;
      parts.push(node("p", "capture-meta", `Сегодня: ${today}. Лидер дня получит +${reward.stars}★ и +${reward.rep} REP — тем, кто сегодня играл`));
      let status;
      if (!state.enabled) status = "Захват выключен вожатым";
      else if (state.window.open) status = `Захват открыт до ${clock(state.window.closes_at)}`;
      else status = state.window.opens_at ? `Захват откроется в ${clock(state.window.opens_at)}` : "Захват закрыт";
      parts.push(node("p", `capture-meta${state.enabled && state.window.open ? " is-open" : ""}`, status));
    }
    const cups = state.wars.filter((w) => !state.war.finished || w.number !== state.war.number);
    if (cups.length) {
      parts.push(node("p", "capture-meta", cups.map((w) => `🏆 №${w.number}: ${w.winners.map((c) => faction(c)?.ru || c).join(", ") || "ничья"}`).join(" · ")));
    }

    if (mine && !state.war.finished) parts.push(abilityBlock("fog", null));

    if (state.can_manage) {
      const actions = node("div", "capture-actions");
      if (state.war.finished) {
        actions.append(staffButton("new", "Начать новую войну", "Точно начать заново?", () => staffAction("/api/v4/capture/new-war", "Новая война: карта ничья. Включите захват, когда будете готовы")));
      } else {
        actions.append(staffButton("switch", state.enabled ? "Выключить захват" : "Включить захват",
          state.enabled ? "Точно выключить?" : "Точно включить?",
          () => staffAction("/api/v4/capture/switch", state.enabled ? "Захват выключен, очки замерли" : "Захват включён", { enabled: !state.enabled })));
        actions.append(staffButton("finish", "Подвести итоги", "Точно завершить войну?", () => staffAction("/api/v4/capture/finish", "Итоги подведены — победитель получил кубок")));
      }
      parts.push(actions);
      const unconfirmed = state.points.filter((p) => !p.confirmed).length;
      parts.push(node("p", "capture-meta", unconfirmed
        ? `Не подтверждено точек: ${unconfirmed}. Нажмите на серый ромб у объекта и подтвердите, стоя рядом`
        : "Все точки подтверждены"));
    }
    parts.push(node("p", "case-message capture-hud-note", hudNote));
    hud.replaceChildren(...parts);
    hud.hidden = false;
  }

  async function staffAction(path, success, body) {
    if (busy) return;
    busy = true;
    drawHud();
    try {
      await api(path, { method: "POST", body });
      hudNote = success;
      window.showToast?.(success);
      await refresh();
    } catch (error) {
      hudNote = error.message;
    } finally {
      busy = false;
      drawHud();
    }
  }

  // --- карточка точки ---------------------------------------------------------------------

  function drawQuestion() {
    const box = node("div", "capture-question");
    const label = node("span", "capture-label", `${ACTIONS[question.action] || "Ход"} · `);
    label.append(countdown(question.deadline));
    box.append(label, node("b", "capture-hanzi", question.zh), node("p", "capture-pinyin", question.pinyin),
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
    // Каждый вызов идёт сразу после того, как question мог смениться (начали
    // бой, ответили, истекло время) -- перерисовываем зоны, чтобы штриховка
    // боя на карте не отставала от карточки точки.
    draw();
    ui?.layer?.querySelectorAll(".capture-point").forEach((g) => g.classList.toggle("is-selected", g.dataset.point === code));
    const owner = faction(p.owner);
    const mine = Boolean(owner && state.you && state.you.faction === owner.code);
    card.style.setProperty("--faction", owner ? owner.color : NEUTRAL);
    const parts = [
      node("span", "capture-label", p.confirmed ? "Точка захвата" : "Точка не подтверждена"),
      node("b", "capture-title", p.name_ru || "Точка кампуса"),
    ];
    if (p.name_zh) parts.push(node("p", "capture-zh", p.name_zh));
    if (p.confirmed) {
      let ownerText = "Ничья — захватите первыми";
      if (owner) ownerText = `${owner.ru} ${owner.zh} · ${p.hidden ? "защита скрыта туманом" : `защита ${pips(p.level, p.max_level)}`}`;
      parts.push(node("p", "capture-owner", ownerText));
      const badges = node("div", "capture-badges");
      if (p.shield_until) badges.append(node("span", "capture-badge", `🛡 щит ещё ${minutesLeft(p.shield_until)} мин`));
      if (p.double_until) badges.append(node("span", "capture-badge", `×2 ещё ${minutesLeft(p.double_until)} мин`));
      if (p.scouted) badges.append(node("span", "capture-badge", `🔍 ходов сегодня: ${p.scouted.moves_today}`));
      if (badges.childElementCount) parts.push(badges);
    }

    if (question && question.code === code) {
      parts.push(drawQuestion());
    } else {
      const actions = node("div", "capture-actions");
      if (p.confirmed && state.you) {
        const wait = cooldownLeft(code);
        let reason = null;
        if (state.war.finished) reason = "Война окончена — ждём новую";
        else if (!state.enabled) reason = "Захват выключен вожатым";
        else if (!state.window.open) reason = state.window.opens_at ? `Захват откроется в ${clock(state.window.opens_at)}` : "Захват закрыт";
        else if (!p.action) reason = "Точка вашей фракции укреплена до предела";
        else if (p.action === "attack" && p.shield_until) reason = "Точка под щитом";
        else if (wait) {
          reason = node("p", "capture-meta", "Точка ждёт вас через ");
          reason.append(countdown(cooldownUntil.get(code)));
        }
        const go = button("btn btn-primary", ACTIONS[p.action] || "Ход недоступен", () => startChallenge(p));
        go.disabled = busy || Boolean(reason);
        actions.append(go);
        if (!state.war.finished && state.enabled && state.window.open) {
          actions.append(button("btn btn-secondary", "⚔ Дуэль за точку",
            () => window.dispatchEvent(new CustomEvent("zhidao:duel-offer", { detail: p.code }))));
        }
        if (reason instanceof Node) parts.push(reason);
        else parts.push(node("p", "capture-meta", reason || `Встаньте у точки (до ${state.radius_m} м) и ответьте на вопрос`));
      }
      if (state.can_manage) {
        actions.append(button("btn btn-secondary", p.confirmed ? "Уточнить точку здесь" : "Подтвердить точку здесь", () => confirmPoint(p)));
      }
      if (actions.childElementCount) parts.push(actions);
      if (p.confirmed && state.you && !state.war.finished) {
        const abilities = node("div", "capture-abilities");
        if (mine) abilities.append(abilityBlock("shield", code), abilityBlock("double", code));
        else if (p.owner) abilities.append(abilityBlock("scout", code));
        if (abilities.childElementCount) parts.push(node("span", "capture-label", "Способности фракции · складчина"), abilities);
      }
    }
    parts.push(node("p", "case-message capture-note", noteText));
    card.replaceChildren(...parts);
    card.hidden = false;
  }

  function rerender() {
    drawHud();
    if (selected) showCard(selected);
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
        if (window.ZhidaoSounds && result.action !== "shielded") window.ZhidaoSounds.play("rare");
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
    const version = ++refreshVersion;
    if (!signedIn()) {
      state = null;
    } else {
      try {
        const response = await api("/api/v4/capture");
        if (version !== refreshVersion) return;
        state = response;
      } catch (_) {
        // Не продлеваем cooldown из прежнего снимка при каждой ошибке связи.
        return;
      }
    }
    (state && state.points ? state.points : []).forEach((p) => {
      if (p.cooldown_seconds) cooldownUntil.set(p.code, Date.now() + p.cooldown_seconds * 1000);
    });
    draw();
    drawHud();
    if (selected) showCard(selected);
    // Панели дуэлей (capture-duel.js) нужны фракции, окно и точки.
    window.dispatchEvent(new CustomEvent("zhidao:capture-state", { detail: state }));
  }

  function tick() {
    if (question && Date.now() >= question.deadline) {
      question = null;
      noteText = "Время на ответ вышло";
      if (selected) showCard(selected);
      return;
    }
    let expired = false;
    document.querySelectorAll("#capturePointCard .capture-countdown").forEach((span) => {
      const left = Math.ceil((Number(span.dataset.until) - Date.now()) / 1000);
      span.textContent = `${Math.max(0, left)}${span.dataset.suffix}`;
      if (left <= 0) expired = true;
    });
    if (expired && !question && !busy && selected) showCard(selected);
  }

  function start() {
    if (document.hidden) return;
    tick();
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
  window.addEventListener("zhidao:capture-refresh", () => refresh());
  window.addEventListener("zhidao:auth", (event) => {
    refreshVersion++;
    session = event.detail;
    state = null;
    selected = null;
    question = null;
    armed = null;
    hudNote = "";
    cooldownUntil.clear();
    poolKeys.clear();
    $("capturePointCard").hidden = true;
    if (onMap()) start();
    else drawHud();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "campus-map") start();
    else stop();
  });
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (onMap()) start();
  });
  window.addEventListener("online", () => {
    if (!document.hidden && onMap() && !busy && !question) refresh();
  });
}());
