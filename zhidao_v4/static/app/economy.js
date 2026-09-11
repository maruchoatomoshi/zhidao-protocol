"use strict";

/* Экономика сезона в админке: тратятся ли звёзды — и купоны «+30 минут».

   Всё, что здесь показано, считает сервер из журнала экономики; экран только
   рисует. Купон гасится вторым касанием и с ключом повтора: если связь
   оборвалась после погашения, повторное нажатие не спишет второй купон. */

(function () {
  const $ = (id) => document.getElementById(id);
  const OPERATION_NAMES = {
    "case.open": "Открытия кейсов",
    "case.grant": "Выдача попыток",
    "diary.rate": "Оценки дневника",
    "coupon.redeem": "Погашение купонов",
    "shop.buy": "Покупки на витрине",
  };
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let data = null;
  let armed = null;
  let busy = false;
  const pending = new Map();   // account_id → ключ неподтверждённого погашения

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const fmt = (n) => new Intl.NumberFormat("ru-RU").format(n);
  const percent = (value) => (value == null ? "—" : `${Math.round(value * 100)}%`);
  function plural(n, one, few, many) {
    const tens = n % 100;
    const ones = n % 10;
    if (tens >= 11 && tens <= 14) return many;
    if (ones === 1) return one;
    if (ones >= 2 && ones <= 4) return few;
    return many;
  }
  const panelVisible = () => {
    const el = document.querySelector('[data-tab-panel="admin:economy"]');
    return Boolean(el && !el.hidden && document.documentElement.dataset.currentScreen === "admin");
  };

  function newKey() {
    if (window.crypto && crypto.randomUUID) return `redeem-${crypto.randomUUID()}`;
    return `redeem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

  function gauge(label, value) {
    const box = node("div", "admin-gauge");
    box.append(node("span", null, label), node("strong", null, value));
    return box;
  }

  function drawGauges() {
    $("economySeason").textContent = `${data.season_name} · ${data.season_status}`;
    $("economyGauges").replaceChildren(
      gauge("★ у участников", fmt(data.stars_total)),
      gauge("Средний баланс", data.stars_average == null ? "—" : `${fmt(data.stars_average)}★`),
      gauge("Медиана", data.stars_median == null ? "—" : `${fmt(data.stars_median)}★`),
      gauge("У первых 10", percent(data.top10_share)),
      gauge("Потрачено", percent(data.spent_ratio)),
    );
    const warning = $("economyWarning");
    warning.hidden = !data.hoarding;
    warning.textContent = data.hoarding
      ? "Звёзды копятся: за дни с операциями потрачено меньше трети заработанного. Пора обновить витрину или объявить общую цель группы."
      : "";
  }

  function drawDays() {
    const host = $("economyDays");
    host.replaceChildren();
    if (!data.days.length) {
      host.append(node("p", "case-message", "Операций в этом сезоне ещё не было."));
      return;
    }
    const max = Math.max(1, ...data.days.map((day) => Math.max(day.minted, day.burned)));
    for (const day of data.days) {
      const row = node("div", "economy-day");
      row.setAttribute("role", "img");
      row.setAttribute("aria-label", `${day.date}: выпущено ${day.minted}★, потрачено ${day.burned}★`);
      const bars = node("div", "economy-bars");
      const minted = node("span", "economy-bar is-minted");
      minted.style.width = `${(day.minted / max) * 100}%`;
      const burned = node("span", "economy-bar is-burned");
      burned.style.width = `${(day.burned / max) * 100}%`;
      bars.append(minted, burned);
      row.append(node("b", null, `${day.date.slice(8, 10)}.${day.date.slice(5, 7)}`), bars,
        node("small", null, `+${fmt(day.minted)} / −${fmt(day.burned)}`));
      host.append(row);
    }
  }

  function drawSources() {
    const host = $("economySources");
    host.replaceChildren();
    if (!data.sources.length) {
      host.append(node("p", "case-message", "Источников пока нет."));
      return;
    }
    for (const source of data.sources) {
      const row = node("div", "economy-source");
      row.append(node("span", null, OPERATION_NAMES[source.operation] || source.operation),
        node("small", null, `+${fmt(source.minted)} / −${fmt(source.burned)} · ${fmt(source.operations)} опер.`));
      host.append(row);
    }
  }

  function drawCoupons() {
    const host = $("economyCoupons");
    host.replaceChildren();
    const coupons = data.coupons;
    const total = coupons.reduce((sum, c) => sum + c.quantity, 0);
    $("economyCouponCount").textContent = `${total} ${plural(total, "купон", "купона", "купонов")}`;
    if (!coupons.length) host.append(node("p", "case-message", "Купонов сейчас ни у кого нет."));
    for (const coupon of coupons) {
      const row = node("div", "admin-roster-row");
      const copy = node("div", "admin-roster-copy");
      copy.append(node("b", null, coupon.display_name), node("small", null, `купонов: ${coupon.quantity}`));
      const isArmed = armed === coupon.account_id;
      const b = node("button", `btn btn-secondary admin-code-btn${isArmed ? " is-armed" : ""}`, isArmed ? "Точно?" : "Погасить");
      b.type = "button";
      b.disabled = busy || data.season_status !== "active";
      b.addEventListener("click", () => redeem(coupon));
      row.append(copy, b);
      host.append(row);
    }
  }

  function draw() {
    drawGauges();
    drawDays();
    drawSources();
    drawCoupons();
  }

  async function load() {
    if (!signedIn()) {
      $("economyGauges").replaceChildren(node("p", "case-message", "Данные появятся после входа."));
      return;
    }
    $("economyGauges").replaceChildren(node("p", "case-message", "Загрузка…"));
    try {
      const list = await seasons();
      season = list.find((s) => s.can_manage && s.status === "active") || list.find((s) => s.can_manage) || null;
      if (!season) {
        $("economyGauges").replaceChildren(node("p", "case-message", "Нет сезона, в котором у вас права вожатого."));
        return;
      }
      data = await api(`/api/v4/seasons/${season.id}/economy/overview`);
      draw();
    } catch (error) {
      $("economyGauges").replaceChildren(node("p", "case-message", error.message));
    }
  }

  async function redeem(coupon) {
    if (busy) return;
    if (armed !== coupon.account_id) {
      armed = coupon.account_id;
      $("economyCouponStatus").textContent = `Нажмите ещё раз, чтобы погасить купон: ${coupon.display_name}, 30 минут.`;
      drawCoupons();
      return;
    }
    armed = null;
    busy = true;
    drawCoupons();
    const key = pending.get(coupon.account_id) || newKey();
    pending.set(coupon.account_id, key);
    try {
      await api(`/api/v4/seasons/${season.id}/economy/coupons/redeem`,
        { method: "POST", body: { account_id: coupon.account_id }, key });
      pending.delete(coupon.account_id);
      $("economyCouponStatus").textContent = `Погашено: ${coupon.display_name}, +30 минут. Запись в журнале.`;
      busy = false;
      await load();
    } catch (error) {
      if (error.status) pending.delete(coupon.account_id);
      $("economyCouponStatus").textContent = error.status
        ? error.message
        : "Нет связи. Погасите ещё раз — повтор не спишет второй купон.";
      busy = false;
      drawCoupons();
    }
  }

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    data = null;
    armed = null;
    pending.clear();
    if (panelVisible()) load();
  });
  window.addEventListener("zhidao:screen", () => { if (panelVisible()) load(); });
  window.addEventListener("zhidao:tab", (event) => {
    if (event.detail && event.detail.dataset.tabPanel === "admin:economy" && panelVisible()) load();
  });
  $("adminRefresh").addEventListener("click", () => { if (panelVisible()) load(); });
}());
