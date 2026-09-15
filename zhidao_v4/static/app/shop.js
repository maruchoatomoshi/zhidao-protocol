"use strict";

/* Магазин: витрина дня, покупки и надетая косметика (V4_GAMES.md §5).

   Витрину, цены и запас присылает сервер; экран ничего не решает. Покупка —
   второе касание и ключ повтора: если связь оборвалась после списания,
   повторное нажатие не спишет ★ второй раз. Надетое сразу уходит в
   cosmetics.js событием «zhidao:cosmetics».

   Экран по макету 2026-09-16 — две вкладки, «Витрина» и «Моё». Разметка
   разная для двух оформлений: в Акве купон карточкой и косметика строками с
   ценой на кнопке; в Луне таблица «Товар · Цена · Осталось» с панелью
   описания выбранного и «Моё» как окно свойств экрана. Сменили оформление —
   экран перерисовывается сам. */

(function () {
  const $ = (id) => document.getElementById(id);
  const SLOTS = ["wallpaper", "frame", "sounds"];
  const SLOT_NAMES = { wallpaper: "Обои", frame: "Рамка профиля", sounds: "Звуки" };
  const SLOT_CN = { wallpaper: "壁纸", frame: "头像框", sounds: "声音" };
  const NONE_NAMES = { wallpaper: "Без обоев", frame: "Без рамки", sounds: "Без звуков" };
  const LOOK_NOTE = "Рамку видят другие — в рейтинге и за игровым столом. Обои и звуки — только у тебя.";
  const WAVE_ICON = '<svg viewBox="0 0 40 40" aria-hidden="true"><path d="M5 20h2M10 15v10M15 10v20M20 14v12M25 17v6" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"></path><circle cx="30" cy="29" r="8" fill="#0a7cc2" stroke="#ffffff" stroke-width="1.5"></circle><path d="M28 25.5v7l6-3.5Z" fill="#ffffff"></path></svg>';
  const PLAY_ICON = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9" fill="#0a7cc2"></circle><path d="M8 6v8l6-4Z" fill="#ffffff"></path></svg>';
  const CHECK_ICON = '<svg viewBox="0 0 12 10" aria-hidden="true"><path d="M1 5l3.5 3.5L11 1.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path></svg>';
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let data = null;
  let armed = null;
  let selected = null;         // выбранная строка таблицы в Луне
  let busy = false;
  const pending = new Map();   // item_code → { key, day }

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const isXp = () => document.documentElement.dataset.design === "xp";
  const setStatus = (text) => { $("shopStatus").textContent = text || ""; };
  const dayLabel = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
  const refreshTime = () => data.refresh_at.slice(11, 16);

  function newKey() {
    if (window.crypto && crypto.randomUUID) return `shop-${crypto.randomUUID()}`;
    return `shop-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

  function seasons() {
    if (!contextPromise) {
      contextPromise = api("/api/v4/cases/context")
        .then((body) => body.seasons || [])
        .catch((error) => { contextPromise = null; throw error; });
    }
    return contextPromise;
  }

  // --- общие детали ------------------------------------------------------------------

  function listen(code) {
    if (window.ZhidaoSounds) window.ZhidaoSounds.preview(code);
  }

  /* Превью товара. Внутри строки таблицы Луны вся строка — кнопка, поэтому
     превью звука там не кнопка: «Послушать» живёт в панели описания. */
  function preview(item, interactive) {
    if (item.kind === "coupon") return node("span", "shop-ticket", "+30");
    if (item.slot === "wallpaper") {
      const swatch = node("span", "shop-swatch");
      swatch.dataset.wallpaperPreview = item.code;
      return swatch;
    }
    if (item.slot === "frame") {
      const box = node("span", "shop-frame");
      const avatar = node("span", "cosmetic-avatar");
      avatar.dataset.frame = item.code;
      box.append(avatar);
      return box;
    }
    const sound = node(interactive ? "button" : "span", "shop-sound");
    sound.innerHTML = WAVE_ICON;
    if (interactive) {
      sound.type = "button";
      sound.setAttribute("aria-label", `Послушать: ${item.name_ru}`);
      sound.addEventListener("click", () => listen(item.code));
    }
    return sound;
  }

  function listenButton(item, withText) {
    const button = node("button", "shop-listen");
    button.type = "button";
    button.innerHTML = PLAY_ICON;
    if (withText) button.append("Послушать");
    button.setAttribute("aria-label", `Послушать: ${item.name_ru}`);
    button.addEventListener("click", () => listen(item.code));
    return button;
  }

  function offer(item) {
    if (item.kind === "cosmetic" && item.owned > 0) return "owned";
    if (item.remaining <= 0) return "sold";
    if (data.season_status !== "active") return "closed";
    if (data.stars < item.price) return "short";
    return armed === item.code ? "armed" : "ready";
  }

  function stockText(item, short) {
    if (item.remaining <= 0) return "закончилось";
    if (short && item.remaining > 2) return `${item.remaining} из ${item.stock}`;
    return `осталось ${item.remaining} из ${item.stock}`;
  }

  function buyControl(item, wide) {
    const state = offer(item);
    if (state === "owned") {
      const chip = node("span", "shop-owned-chip");
      chip.innerHTML = CHECK_ICON;
      chip.append("Уже есть");
      return chip;
    }
    const labels = {
      sold: "Закончилось",
      closed: "Витрина закрыта",
      short: `Нужно ${item.price}★`,
      armed: `Точно? −${item.price}★`,
      ready: wide ? `Купить за ${item.price}★` : `${item.price}★`,
    };
    const button = node("button", `shop-buy is-${state}${wide ? " is-wide" : ""}`, labels[state]);
    button.type = "button";
    button.disabled = busy || (state !== "ready" && state !== "armed");
    button.addEventListener("click", () => buy(item));
    return button;
  }

  function couponNote() {
    const note = node("p", "shop-coupon-note");
    note.append(node("b", null, `Купон «+30 минут» × ${data.walk_coupons}`), " — гасит вожатый.");
    return note;
  }

  function lookScreen() {
    const screen = node("span", "shop-look-screen");
    if (data.equipped.wallpaper) screen.dataset.wallpaperPreview = data.equipped.wallpaper;
    const avatar = node("span", "cosmetic-avatar");
    if (data.equipped.frame) avatar.dataset.frame = data.equipped.frame;
    screen.append(avatar);
    return screen;
  }

  const accountName = () => (session && session.account && session.account.display_name) || "";

  // --- витрина: Аква -----------------------------------------------------------------

  function drawAquaVitrine(host) {
    const coupon = data.vitrine.find((item) => item.kind === "coupon");
    if (coupon) {
      const card = node("article", "shop-coupon");
      const text = node("div", "shop-coupon-text");
      text.append(node("span", "shop-label", "КУПОН · 优惠券"), node("b", null, coupon.name_ru), node("span", "shop-note", coupon.note_ru));
      const foot = node("div", "shop-coupon-foot");
      foot.append(node("span", `shop-stock${coupon.remaining > 0 && coupon.remaining <= 2 ? " is-low" : ""}`, stockText(coupon, false)),
        buyControl(coupon, true));
      card.append(preview(coupon, true), text, foot);
      host.append(card);
    }
    const cosmetics = data.vitrine.filter((item) => item.kind !== "coupon");
    if (!cosmetics.length) return;
    const list = node("article", "shop-list");
    const head = node("div", "shop-list-head");
    head.append(node("span", "shop-label", "КОСМЕТИКА ДНЯ · 装饰"), node("span", "shop-refresh", `смена в ${refreshTime()}`));
    list.append(head);
    for (const item of cosmetics) {
      const row = node("div", "shop-row");
      const text = node("div", "shop-row-text");
      const meta = node("span", "shop-row-meta", SLOT_NAMES[item.slot]);
      if (offer(item) !== "owned") {
        meta.append(" · ", node(item.remaining <= 2 ? "b" : "span", `shop-stock${item.remaining <= 2 ? " is-low" : ""}`, stockText(item, true)));
      }
      text.append(node("b", null, item.name_ru), meta);
      row.append(preview(item, true), text, buyControl(item, false));
      list.append(row);
    }
    host.append(list);
  }

  // --- витрина: Луна -----------------------------------------------------------------

  function drawXpVitrine(host) {
    if (!data.vitrine.some((item) => item.code === selected)) {
      const first = data.vitrine.find((item) => offer(item) === "ready") || data.vitrine[0];
      selected = first.code;
    }
    const win = node("article", "shop-xp-window");
    const head = node("div", "shop-table-head");
    head.setAttribute("aria-hidden", "true");
    head.append(node("span", null, "Товар"), node("span", null, "Цена"), node("span", null, "Осталось"));
    win.append(head);
    for (const item of data.vitrine) {
      const state = offer(item);
      const row = node("button", `shop-table-row${item.kind === "coupon" ? " is-coupon" : ""}${state === "owned" ? " is-owned" : ""}`);
      row.type = "button";
      row.setAttribute("aria-pressed", String(item.code === selected));
      const name = node("span", "shop-table-name");
      name.append(preview(item, false), node("span", null, item.name_ru));
      let left = `${item.remaining} из ${item.stock}`;
      let leftClass = item.remaining > 0 && item.remaining <= 2 ? " is-low" : "";
      if (state === "owned") { left = "куплено"; leftClass = " is-owned"; }
      else if (item.remaining <= 0) left = "нет";
      row.append(name, node("span", "shop-table-price", `${item.price}★`), node("span", `shop-table-left${leftClass}`, left));
      row.addEventListener("click", () => {
        if (selected === item.code) return;
        selected = item.code;
        if (armed !== item.code) armed = null;
        drawVitrine(true);
      });
      win.append(row);
    }

    const item = data.vitrine.find((entry) => entry.code === selected);
    const details = node("div", "shop-details");
    const text = node("div", "shop-details-text");
    text.append(node("b", null, item.name_ru), node("span", "shop-note", item.note_ru));
    if (item.slot === "frame") text.append(node("span", "shop-note", "Её видят другие — в рейтинге и за игровым столом."));
    const actions = node("div", "shop-details-actions");
    actions.append(buyControl(item, true));
    if (item.slot === "sounds") actions.append(listenButton(item, true));
    details.append(preview(item, false), text, actions);
    win.append(details);
    win.append(node("div", "case-statusbar shop-statusbar",
      `Товаров: ${data.vitrine.length} · смена ${dayLabel(data.refresh_at)} в ${refreshTime()}`));
    host.append(win);
  }

  function drawVitrine(focusSelected) {
    const host = $("shopVitrine");
    host.replaceChildren();
    if (!data) return;
    if (!data.vitrine.length) {
      host.append(node("p", "case-message", "Витрина пуста: сезон ещё не активен."));
      return;
    }
    if (isXp()) drawXpVitrine(host);
    else drawAquaVitrine(host);
    if (focusSelected) {
      const row = host.querySelector(".shop-table-row[aria-pressed='true']");
      if (row) row.focus();
    }
  }

  // --- моё ------------------------------------------------------------------------------

  function chip(slot, item) {
    const worn = (item ? item.code : null) === (data.equipped[slot] || null);
    const button = node("button", `shop-chip${item && slot !== "sounds" ? " has-swatch" : ""}`);
    button.type = "button";
    button.disabled = busy;
    button.setAttribute("aria-pressed", String(worn));
    if (item && slot === "wallpaper") {
      const swatch = node("span", "shop-swatch");
      swatch.dataset.wallpaperPreview = item.code;
      button.append(swatch);
    } else if (item && slot === "frame") {
      const avatar = node("span", "cosmetic-avatar");
      avatar.dataset.frame = item.code;
      button.append(avatar);
    }
    const name = item ? item.name_ru.replace(/^Звуки\s+/, "") : "Без";
    button.append(node("span", null, name));
    if (item && item.kind === "award") button.append(node("b", "shop-award", "награда"));
    if (worn) button.insertAdjacentHTML("beforeend", CHECK_ICON);
    button.addEventListener("click", () => { if (!worn) equip(slot, item ? item.code : null); });
    return button;
  }

  function drawAquaMine(host) {
    const look = node("article", "shop-look");
    const text = node("div", "shop-look-text");
    text.append(node("span", "shop-label", "КАК ТЕБЯ ВИДЯТ · 形象"), node("b", null, accountName()), node("span", "shop-note", LOOK_NOTE));
    look.append(lookScreen(), text);
    host.append(look);
    if (data.walk_coupons > 0) host.append(couponNote());

    const wardrobe = node("article", "shop-wardrobe");
    if (!data.cosmetics.length) {
      wardrobe.append(node("p", "shop-note", "Косметики пока нет. Обои, рамки и звуки появляются на витрине каждое утро."));
    }
    for (const slot of SLOTS) {
      const items = data.cosmetics.filter((item) => item.slot === slot);
      if (!items.length) continue;
      const group = node("div", "shop-slot");
      group.append(node("span", "shop-label", `${SLOT_NAMES[slot].toUpperCase()} · ${SLOT_CN[slot]}`));
      const row = node("div", "shop-chips");
      row.append(chip(slot, null));
      for (const item of items) {
        row.append(chip(slot, item));
        if (slot === "sounds") row.append(listenButton(item, items.length === 1));
      }
      group.append(row);
      wardrobe.append(group);
    }
    host.append(wardrobe);
  }

  function drawXpMine(host) {
    const win = node("article", "shop-xp-window shop-xp-mine");
    const top = node("div", "shop-monitor-row");
    const monitor = node("span", "shop-monitor");
    monitor.append(lookScreen(), node("i"), node("i"));
    const text = node("span", "shop-note");
    text.append(node("b", null, accountName()), node("br"), LOOK_NOTE);
    top.append(monitor, text);
    win.append(top);
    if (!data.cosmetics.length) {
      win.append(node("p", "shop-note", "Косметики пока нет. Обои, рамки и звуки появляются на витрине каждое утро."));
    }
    for (const slot of SLOTS) {
      const items = data.cosmetics.filter((item) => item.slot === slot);
      if (!items.length) continue;
      const fieldset = node("fieldset", "shop-xp-fieldset");
      const legend = node("legend", null, `${SLOT_NAMES[slot]} `);
      legend.append(node("span", null, SLOT_CN[slot]));
      fieldset.append(legend);
      for (const item of [null, ...items]) {
        const label = node("label", "shop-xp-choice");
        const input = node("input");
        input.type = "radio";
        input.name = `shop-${slot}`;
        input.value = item ? item.code : "";
        input.checked = (item ? item.code : null) === (data.equipped[slot] || null);
        input.disabled = busy;
        input.addEventListener("change", () => { if (input.checked) equip(slot, input.value || null); });
        label.append(input, item ? item.name_ru : NONE_NAMES[slot]);
        if (item && item.kind === "award") label.append(node("span", "shop-award", "награда"));
        if (item && slot === "sounds") {
          const line = node("div", "shop-xp-sound");
          line.append(label, listenButton(item, true));
          fieldset.append(line);
        } else {
          fieldset.append(label);
        }
      }
      win.append(fieldset);
    }
    win.append(node("div", "case-statusbar shop-statusbar", "Надетое меняется сразу"));
    host.append(win);
    if (data.walk_coupons > 0) host.append(couponNote());
  }

  function drawMine() {
    const host = $("shopMine");
    host.replaceChildren();
    if (!data) return;
    if (isXp()) drawXpMine(host);
    else drawAquaMine(host);
  }

  function draw() {
    // Баланс показан и в шапке; без этого там оставалась цифра до покупки
    // (так было на первой живой проверке: 300★ при реальных 230★).
    document.querySelectorAll("[data-case-stars]").forEach((el) => { el.textContent = `${data.stars} ★`; });
    $("shopDay").textContent = `витрина на ${dayLabel(data.shop_day)}`;
    drawVitrine();
    drawMine();
  }

  function applyCosmetics(equipped) {
    window.dispatchEvent(new CustomEvent("zhidao:cosmetics", { detail: equipped }));
  }

  async function load() {
    if (!signedIn()) {
      data = null;
      $("shopVitrine").replaceChildren();
      $("shopMine").replaceChildren(node("p", "case-message", "Покупки появятся здесь после входа."));
      $("shopDay").textContent = "витрина дня";
      setStatus("Войдите, чтобы увидеть витрину дня.");
      applyCosmetics({});
      return;
    }
    try {
      const list = await seasons();
      season = list.find((s) => s.is_member && s.status === "active") || list.find((s) => s.is_member) || null;
      if (!season) {
        setStatus("Витрина откроется, когда вас включат в сезон.");
        applyCosmetics({});
        return;
      }
      data = await api(`/api/v4/seasons/${season.id}/shop`);
      applyCosmetics(data.equipped);
      setStatus(data.season_status === "active" ? "" : "Сезон не активен: витрина закрыта.");
      draw();
    } catch (error) {
      setStatus(error.message);
    }
  }

  async function buy(item) {
    if (busy || !data) return;
    if (armed !== item.code) {
      armed = item.code;
      setStatus(`Нажмите ещё раз, чтобы купить «${item.name_ru}» за ${item.price}★.`);
      drawVitrine();
      return;
    }
    armed = null;
    busy = true;
    drawVitrine();
    const old = pending.get(item.code);
    const key = old && old.day === data.shop_day ? old.key : newKey();
    pending.set(item.code, { key, day: data.shop_day });
    try {
      await api(`/api/v4/seasons/${season.id}/shop/buy`,
        { method: "POST", body: { item_code: item.code, shop_day: data.shop_day }, key });
      pending.delete(item.code);
      if (window.ZhidaoSounds) window.ZhidaoSounds.play("buy");
      busy = false;
      await load();
      setStatus(item.kind === "coupon"
        ? "Купон «+30 минут» у вас. Покажите вожатому, когда захотите им воспользоваться."
        : `«${item.name_ru}» у вас. Наденьте на вкладке «Моё».`);
    } catch (error) {
      if (error.status) pending.delete(item.code);
      busy = false;
      setStatus(error.status ? error.message : "Нет связи. Купите ещё раз — повтор не спишет звёзды дважды.");
      if (error.status === 409) await load();
      else drawVitrine();
    }
  }

  async function equip(slot, code) {
    if (busy || !data) return;
    busy = true;
    try {
      const body = await api(`/api/v4/seasons/${season.id}/shop/equip`, { method: "POST", body: { slot, item_code: code } });
      data.equipped = body.equipped;
      applyCosmetics(data.equipped);
      setStatus(code ? "Надето." : "Снято.");
    } catch (error) {
      setStatus(error.message);
    } finally {
      busy = false;
      drawMine();
    }
  }

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    armed = null;
    selected = null;
    pending.clear();
    // Косметику применяем сразу после входа, а не только при открытии магазина:
    // обои и рамка должны быть на месте с первой секунды.
    load();
  });
  window.addEventListener("zhidao:screen", (event) => { if (event.detail === "shop" && signedIn()) load(); });
  // Разметка витрины своя у каждого оформления: сменили — перерисовываем.
  new MutationObserver(() => {
    if (!data) return;
    drawVitrine();
    drawMine();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-design"] });
}());
