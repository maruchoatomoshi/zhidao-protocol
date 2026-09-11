"use strict";

/* Магазин: витрина дня, покупки и надетая косметика (V4_GAMES.md §5).

   Витрину, цены и запас присылает сервер; экран ничего не решает. Покупка —
   второе касание и ключ повтора: если связь оборвалась после списания,
   повторное нажатие не спишет ★ второй раз. Надетое сразу уходит в
   cosmetics.js событием «zhidao:cosmetics». */

(function () {
  const $ = (id) => document.getElementById(id);
  const SLOT_NAMES = { wallpaper: "Обои", frame: "Рамка профиля", sounds: "Звуки" };
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let data = null;
  let armed = null;
  let busy = false;
  const pending = new Map();   // item_code → { key, day }

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "shop";
  const setStatus = (text) => { $("shopStatus").textContent = text || ""; };

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

  // --- превью товаров --------------------------------------------------------------

  function preview(item) {
    const box = node("div", "shop-preview");
    if (item.kind === "coupon") {
      box.append(node("span", "shop-ticket", "+30"));
    } else if (item.slot === "wallpaper") {
      box.dataset.wallpaperPreview = item.code;
    } else if (item.slot === "frame") {
      const avatar = node("span", "cosmetic-avatar");
      avatar.dataset.frame = item.code;
      box.append(avatar);
    } else if (item.slot === "sounds") {
      box.append(node("span", "shop-wave", "∿∿∿"));
      const listen = node("button", "shop-listen", "▶ Послушать");
      listen.type = "button";
      listen.addEventListener("click", () => window.ZhidaoSounds && window.ZhidaoSounds.preview(item.code));
      box.append(listen);
    }
    return box;
  }

  function swatch(item) {
    if (item.slot === "wallpaper") {
      const s = node("span", "swatch");
      s.dataset.wallpaperPreview = item.code;
      return s;
    }
    if (item.slot === "frame") {
      const s = node("span", "cosmetic-avatar");
      s.dataset.frame = item.code;
      return s;
    }
    return node("span", "shop-wave", "∿");
  }

  // --- отрисовка ---------------------------------------------------------------------

  function drawVitrine() {
    const host = $("shopVitrine");
    host.replaceChildren();
    const active = data.season_status === "active";
    for (const item of data.vitrine) {
      const card = node("article", `shop-card${item.kind === "coupon" ? " is-coupon" : ""}${item.remaining <= 0 ? " is-sold-out" : ""}`);
      const meta = node("div", "shop-meta");
      const left = node("span", `shop-left${item.remaining > 0 && item.remaining <= 2 ? " is-low" : ""}`,
        item.remaining > 0 ? `осталось ${item.remaining} из ${item.stock}` : "закончилось");
      meta.append(node("span", "shop-price", `${item.price}★`), left);
      const owned = item.kind === "cosmetic" && item.owned > 0;
      const isArmed = armed === item.code;
      let label = `Купить за ${item.price}★`;
      if (owned) label = "Уже есть";
      else if (item.remaining <= 0) label = "Закончилось";
      else if (data.stars < item.price) label = `Нужно ${item.price}★`;
      else if (isArmed) label = `Точно? −${item.price}★`;
      const button = node("button", `btn ${isArmed ? "btn-primary is-armed" : "btn-secondary"}`, label);
      button.type = "button";
      button.disabled = busy || !active || owned || item.remaining <= 0 || data.stars < item.price;
      button.addEventListener("click", () => buy(item));
      card.append(preview(item), node("b", null, item.name_ru), node("p", null, item.note_ru), meta, button);
      host.append(card);
    }
    if (!data.vitrine.length) host.append(node("p", "case-message", "Витрина пуста: сезон ещё не активен."));
  }

  function drawMine() {
    const host = $("shopMine");
    host.replaceChildren();
    $("shopCoupons").textContent = `КУПОНОВ «+30 МИНУТ»: ${data.walk_coupons}`;
    if (data.walk_coupons > 0) {
      host.append(node("p", "case-message", `Купонов «+30 минут»: ${data.walk_coupons}. Чтобы использовать, подойдите к вожатому — он погасит купон.`));
    }
    if (!data.cosmetics.length) {
      host.append(node("p", "case-message", "Косметики пока нет. Обои, рамки и звуки появляются на витрине каждое утро."));
      return;
    }
    for (const slot of ["wallpaper", "frame", "sounds"]) {
      const items = data.cosmetics.filter((item) => item.slot === slot);
      if (!items.length) continue;
      const group = node("div", "shop-slot");
      group.append(node("span", "spy-label", SLOT_NAMES[slot]));
      const row = node("div", "shop-slot-items");
      const off = node("button", "shop-owned", "Без");
      off.type = "button";
      off.setAttribute("aria-pressed", String(!data.equipped[slot]));
      off.addEventListener("click", () => equip(slot, null));
      row.append(off);
      for (const item of items) {
        const b = node("button", "shop-owned");
        b.type = "button";
        b.setAttribute("aria-pressed", String(data.equipped[slot] === item.code));
        b.append(swatch(item), node("span", null, item.name_ru));
        b.addEventListener("click", () => equip(slot, item.code));
        row.append(b);
      }
      group.append(row);
      host.append(group);
    }
  }

  function draw() {
    $("shopStars").textContent = `${data.stars} ★`;
    // Баланс показан и в профиле; без этого там оставалась цифра до покупки
    // (так было на первой живой проверке: 300★ при реальных 230★).
    document.querySelectorAll("[data-case-stars]").forEach((el) => { el.textContent = `${data.stars} ★`; });
    $("shopDay").textContent = data.shop_day.split("-").reverse().join(".");
    $("shopRefresh").textContent = `ОБНОВЛЕНИЕ ${data.refresh_at.slice(8, 10)}.${data.refresh_at.slice(5, 7)} В ${data.refresh_at.slice(11, 16)}`;
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
      $("shopStars").textContent = "— ★";
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
        : `«${item.name_ru}» у вас. Наденьте в разделе «Моё» ниже.`);
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
    pending.clear();
    // Косметику применяем сразу после входа, а не только при открытии магазина:
    // обои и рамка должны быть на месте с первой секунды.
    load();
  });
  window.addEventListener("zhidao:screen", (event) => { if (event.detail === "shop" && signedIn()) load(); });
}());
