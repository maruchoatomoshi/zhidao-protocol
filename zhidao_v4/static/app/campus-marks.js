"use strict";

/* Метки на карте (V4_GAMES.md §4.2).

   По мотивам посланий Dark Souls: фразу собирают из шаблона и слова
   («Осторожно: геккон 壁虎») и оставляют там, где стоят. Метку видят все в
   сезоне на открытом участке тумана и могут отметить полезной.

   Что можно, сколько стоит и когда метка исчезнет, решает сервер
   (zhidao_v4/marks.py). Этот файл рисует слой поверх карты и не трогает её
   геометрию: campus-map.js сообщает, когда карта нарисована и какой масштаб,
   и отдаёт проекцию координат через window.ZhidaoCampus. */

(function () {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const DICTIONARY = "./assets/campus/marks.json";
  const CORE_PX = 7;      // радиус метки на экране при любом масштабе
  const GLOW_PX = 15;

  let session = window.ZhidaoSession || null;
  let dictionary = null;
  let state = null;
  let ui = null;
  let scale = 1;
  let selected = null;
  let busy = false;
  let pick = { template: null, word: null };
  let pendingKey = null;
  let hideArmed = null;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "campus-map";
  const newKey = () => `mark-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

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

  async function loadDictionary() {
    if (dictionary) return dictionary;
    const response = await fetch(DICTIONARY, { cache: "no-cache" });
    if (!response.ok) throw new Error("Словарь меток не загрузился.");
    dictionary = await response.json();
    return dictionary;
  }

  // Сервер пишет микросекунды; Safari их не разбирает — оставляем миллисекунды.
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));

  // --- слой на карте ------------------------------------------------------------------

  function unitsPerPixel() {
    if (!ui || !ui.svg) return 1;
    const rect = ui.svg.getBoundingClientRect();
    return rect.width ? ui.svg.viewBox.baseVal.width / rect.width : 1.5;
  }

  function resize() {
    if (!ui || !ui.layer) return;
    const k = unitsPerPixel() / scale;
    ui.layer.querySelectorAll(".campus-mark").forEach((mark) => {
      const [glow, core] = mark.children;
      glow.setAttribute("r", (GLOW_PX * k).toFixed(2));
      core.setAttribute("r", (CORE_PX * k).toFixed(2));
      core.setAttribute("stroke-width", (2 * k).toFixed(2));
    });
  }

  function draw() {
    if (!ui || !ui.layer) return;
    ui.layer.querySelector(".campus-marks")?.remove();
    if (!state || !state.marks.length || !window.ZhidaoCampus) return;
    const group = document.createElementNS(NS, "g");
    group.setAttribute("class", "campus-marks");
    const perCell = new Map();
    for (const mark of state.marks) {
      const point = window.ZhidaoCampus.project(mark.coordinates[0], mark.coordinates[1]);
      if (!point) continue;
      // Несколько меток в одной клетке расходятся спиралью, чтобы не слипаться.
      const cell = mark.coordinates.join(",");
      const index = perCell.get(cell) || 0;
      perCell.set(cell, index + 1);
      const offset = index ? 6 + index * 4 : 0;
      const angle = index * 2.4;
      const item = document.createElementNS(NS, "g");
      item.setAttribute("class", `campus-mark${mark.hidden ? " is-hidden" : ""}${mark.id === selected ? " is-selected" : ""}`);
      item.setAttribute("transform", `translate(${(point.x + Math.cos(angle) * offset).toFixed(1)} ${(point.y + Math.sin(angle) * offset).toFixed(1)})`);
      item.setAttribute("tabindex", "0");
      item.setAttribute("role", "button");
      item.setAttribute("aria-label", `Метка: ${mark.text.ru}`);
      item.dataset.markId = String(mark.id);
      const glow = document.createElementNS(NS, "circle");
      glow.setAttribute("class", "campus-mark-glow");
      const core = document.createElementNS(NS, "circle");
      core.setAttribute("class", "campus-mark-core");
      item.append(glow, core);
      group.append(item);
    }
    if (ui.me && ui.me.parentNode === ui.layer) ui.layer.insertBefore(group, ui.me);
    else ui.layer.append(group);
    resize();
  }

  // --- карточка метки ------------------------------------------------------------------

  function showCard(id) {
    const card = $("campusMarkCard");
    const mark = state && state.marks.find((m) => m.id === id);
    if (!mark) {
      card.hidden = true;
      selected = null;
      return;
    }
    if (selected !== id) hideArmed = null;
    selected = id;
    ui?.layer?.querySelectorAll(".campus-mark").forEach((g) => g.classList.toggle("is-selected", Number(g.dataset.markId) === id));
    const hours = Math.max(1, Math.round((timeOf(mark.expires_at) - Date.now()) / 3600000));
    const actions = node("div", "campus-mark-actions");
    if (state.quota && !mark.hidden) {
      const useful = node("button", "btn btn-secondary", mark.voted ? `Полезно · ${mark.useful} ✓` : `Полезно · ${mark.useful}`);
      useful.type = "button";
      useful.disabled = busy || mark.voted;
      useful.addEventListener("click", () => markUseful(mark));
      actions.append(useful);
    }
    if (state.can_moderate && !mark.hidden) {
      const hide = node("button", "btn btn-secondary", hideArmed === mark.id ? "Точно скрыть?" : "Скрыть метку");
      hide.type = "button";
      hide.disabled = busy;
      hide.addEventListener("click", () => hideMark(mark));
      actions.append(hide);
    }
    card.replaceChildren(
      node("span", "campus-mark-label", "Послание путешественника"),
      node("b", "campus-mark-text", mark.text.ru),
      node("p", "campus-mark-zh", `${mark.text.zh} · ${mark.text.pinyin}`),
      node("p", "campus-mark-meta", mark.hidden ? "Скрыта вожатым — участники её не видят."
        : `Полезно: ${mark.useful} · исчезнет примерно через ${hours} ч`),
      actions,
      node("p", "case-message campus-mark-note"));
    card.id = "campusMarkCard";
    card.hidden = false;
  }

  const cardNote = (text) => {
    const note = $("campusMarkCard").querySelector(".campus-mark-note");
    if (note) note.textContent = text || "";
  };

  async function markUseful(mark) {
    if (busy) return;
    busy = true;
    try {
      await api(`/api/v4/campus/marks/${mark.id}/useful`, { method: "POST" });
      await refresh();
      cardNote("Спасибо: метка проживёт на 12 часов дольше.");
    } catch (error) {
      cardNote(error.message);
    } finally {
      busy = false;
    }
  }

  async function hideMark(mark) {
    if (busy) return;
    if (hideArmed !== mark.id) {
      hideArmed = mark.id;
      showCard(mark.id);
      return;
    }
    busy = true;
    hideArmed = null;
    try {
      await api(`/api/v4/campus/marks/${mark.id}/hide`, { method: "POST" });
      await refresh();
      cardNote("Метка скрыта для участников.");
    } catch (error) {
      cardNote(error.message);
    } finally {
      busy = false;
    }
  }

  // --- новая метка -------------------------------------------------------------------------

  function chip(label, zh, pressed, onPick) {
    const button = node("button", "campus-mark-chip", label);
    button.type = "button";
    button.append(node("small", null, zh));
    button.setAttribute("aria-pressed", String(pressed));
    button.addEventListener("click", onPick);
    return button;
  }

  function drawComposer() {
    const box = $("campusMarkComposer");
    if (box.hidden || !dictionary) return;
    const quota = state && state.quota;
    const templates = node("div", "campus-mark-chips");
    dictionary.templates.forEach((t) => templates.append(chip(t.ru, t.zh, pick.template === t.code, () => {
      pick.template = t.code;
      pendingKey = null;
      drawComposer();
    })));
    const words = node("div", "campus-mark-words");
    const groups = new Map();
    dictionary.words.forEach((w) => {
      if (!groups.has(w.group)) groups.set(w.group, []);
      groups.get(w.group).push(w);
    });
    groups.forEach((list, group) => {
      const row = node("div", "campus-mark-chips");
      list.forEach((w) => row.append(chip(w.ru, w.zh, pick.word === w.code, () => {
        pick.word = w.code;
        pendingKey = null;
        drawComposer();
      })));
      words.append(node("p", "campus-mark-group", group), row);
    });

    const template = dictionary.templates.find((t) => t.code === pick.template);
    const word = dictionary.words.find((w) => w.code === pick.word);
    const preview = node("div", "campus-mark-preview");
    if (template && word) {
      preview.append(node("b", null, `${template.ru} ${word.ru}`), node("small", null, `${template.zh}${word.zh} · ${template.pinyin} ${word.pinyin}`));
    } else {
      preview.append(node("small", null, "Выберите начало фразы и слово."));
    }

    let price = "Войдите и вступите в сезон, чтобы оставлять метки.";
    let affordable = false;
    if (quota) {
      if (!quota.left) price = "Сегодня метки закончились. Завтра можно снова.";
      else if (!quota.next_price) { price = `Первая метка сегодня бесплатно · осталось ${quota.left} из ${quota.limit}`; affordable = true; }
      else {
        price = `Метка стоит ${quota.next_price}★ · осталось ${quota.left} из ${quota.limit} · у вас ${quota.stars}★`;
        affordable = quota.stars >= quota.next_price;
      }
    }
    const submit = node("button", "btn btn-primary", "Поставить там, где я стою");
    submit.type = "button";
    submit.disabled = busy || !template || !word || !affordable;
    submit.addEventListener("click", place);
    const cancel = node("button", "btn btn-secondary", "Отмена");
    cancel.type = "button";
    cancel.addEventListener("click", () => { box.hidden = true; });

    box.replaceChildren(
      node("span", "campus-mark-label", "Новое послание"),
      node("p", "campus-mark-group", "Начало"), templates,
      node("p", "campus-mark-group", "Слово"), words,
      preview,
      node("p", "campus-mark-meta", price),
      node("p", "case-message campus-mark-composer-note"),
      node("div", "campus-mark-actions"));
    box.lastChild.append(submit, cancel);
  }

  const composerNote = (text) => {
    const note = $("campusMarkComposer").querySelector(".campus-mark-composer-note");
    if (note) note.textContent = text || "";
  };

  function position() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("GPS недоступен на этом устройстве."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos.coords),
        (err) => reject(new Error(err.code === err.PERMISSION_DENIED ? "Доступ к геопозиции закрыт." : "Не удалось определить позицию.")),
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
    });
  }

  async function place() {
    if (busy || !pick.template || !pick.word) return;
    busy = true;
    drawComposer();
    composerNote("Ищем вас…");
    try {
      const coords = await position();
      pendingKey = pendingKey || newKey();
      const result = await api("/api/v4/campus/marks", {
        method: "POST", key: pendingKey,
        body: { lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy, template: pick.template, word: pick.word },
      });
      pendingKey = null;
      pick = { template: null, word: null };
      $("campusMarkComposer").hidden = true;
      window.showToast?.(result.fee ? `Метка оставлена · −${result.fee}★` : "Метка оставлена — её увидят все в сезоне");
      if (window.ZhidaoSounds) window.ZhidaoSounds.play("buy");
      if (window.ZhidaoCampus) await window.ZhidaoCampus.reload();   // клетка тумана могла открыться
      await refresh();
      if (result.mark) showCard(result.mark.id);
    } catch (error) {
      if (error.status) pendingKey = null;
      composerNote(error.status || !pendingKey ? error.message : "Нет связи. Нажмите ещё раз — метка не встанет дважды.");
    } finally {
      busy = false;
      drawComposer();
    }
  }

  async function openComposer() {
    try {
      await loadDictionary();
    } catch (error) {
      window.showToast?.(error.message);
      return;
    }
    const box = $("campusMarkComposer");
    box.hidden = false;
    drawComposer();
    requestAnimationFrame(() => box.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }

  // --- данные -----------------------------------------------------------------------------

  function drawToolbar() {
    const button = $("campusMarkOpen");
    button.hidden = !(state && state.quota);
  }

  async function refresh() {
    if (!signedIn()) {
      state = null;
    } else {
      try { state = await api("/api/v4/campus/marks"); } catch (_) { state = null; }
    }
    draw();
    drawToolbar();
    if (selected) showCard(selected);
    drawComposer();
  }

  // --- подключение --------------------------------------------------------------------------

  window.addEventListener("zhidao:campus-drawn", (event) => {
    ui = event.detail;
    draw();
  });
  window.addEventListener("zhidao:campus-view", (event) => {
    if (event.detail === scale) return;
    scale = event.detail;
    resize();
  });
  window.addEventListener("zhidao:campus-mark", (event) => showCard(event.detail));
  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    state = null;
    selected = null;
    pendingKey = null;
    $("campusMarkComposer").hidden = true;
    $("campusMarkCard").hidden = true;
    if (onScreen()) refresh();
    else drawToolbar();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "campus-map") refresh();
  });
  window.addEventListener("resize", resize);
  $("campusMarkOpen").addEventListener("click", openComposer);
}());
