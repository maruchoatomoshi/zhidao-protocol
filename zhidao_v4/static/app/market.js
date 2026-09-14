"use strict";

/* Рынок Контрабанды — торговля на весь кампус на один день (V4_GAMES.md §4.12).

   Вышел на рынок — получил утренний набор юаней и товаров. Торгуют вживую: один
   собирает предложение и показывает код, второй вводит код, видит предложение и
   соглашается. Патрульные NetWatch просят код сумки и вскрывают её. В 21:00
   итоги дня: топ-3 получают звёзды, юани и товары сгорают.

   Всё решает сервер (zhidao_v4/market.py). Панель перерисовывается, только
   когда ответ сервера изменился, — чтобы набранный код не стирался при опросе. */

(function () {
  const $ = (id) => document.getElementById(id);
  const LEAD = "Утром — юани и товары, днём — торг вживую по коду. Запрещёнка дорогая, но патруль NetWatch может вскрыть сумку. В 21:00 три самых богатых торговца получают звёзды";
  const POLL_MS = 8000;

  let session = window.ZhidaoSession || null;
  let data = null;
  let signature = "";
  let busy = false;
  let note = "";
  let armed = null;
  let poll = null;
  let builder = { give: { goods: {}, money: 0 }, want: { goods: {}, money: 0 } };
  let codeDraft = "";
  let bagDraft = "";
  let peeked = null;
  let lastInspection = null;
  let epoch = 0;
  let pending = null;
  const pendingKey = () => `zhidao.market.pending.${session?.account?.id || "guest"}`;
  function savePending(value) {
    pending = value;
    try {
      if (value) sessionStorage.setItem(pendingKey(), JSON.stringify(value));
      else sessionStorage.removeItem(pendingKey());
    } catch (_) { /* memory still protects retries while this page is open */ }
  }
  function restorePending() {
    try { pending = JSON.parse(sessionStorage.getItem(pendingKey()) || "null"); } catch (_) { pending = null; }
  }

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
  const catalog = () => Object.fromEntries(((data && data.catalog) || []).map((g) => [g.code, g]));

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
        const detail = Array.isArray(body.detail) ? "Проверьте, что введено." : body.detail;
        const error = new Error(typeof detail === "string" ? detail : "Запрос отклонён.");
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

  function goodLabel(code) {
    const g = catalog()[code];
    return g ? `${g.zh} ${g.ru}` : code;
  }

  function basketText(basket) {
    const parts = Object.entries((basket && basket.goods) || {}).map(([code, n]) => `${goodLabel(code)} ×${n}`);
    if (basket && basket.money) parts.push(`${basket.money} 元`);
    return parts.join(", ") || "ничего";
  }

  function codeInput(id, value, onInput, label) {
    const input = node("input", "market-input");
    input.id = id;
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.maxLength = 7;
    input.placeholder = "000 000";
    input.setAttribute("aria-label", label);
    input.value = value;
    input.disabled = busy;
    input.addEventListener("input", () => onInput(input.value));
    return input;
  }

  const digits = (text) => String(text || "").replace(/\D/g, "");

  function drawNews(me, parts) {
    const news = me.news;
    if (!news) return;
    let text = "";
    if (news.kind === "trade") text = `Обмен прошёл: отдали ${basketText(news.gave)}, получили ${basketText(news.got)}`;
    else if (news.kind === "inspected" && news.clean) text = `Патруль вскрыл вашу сумку — чисто. Патрульный заплатил вам ${news.fine} 元`;
    else if (news.kind === "inspected") text = `Патруль нашёл запрещёнку: ${basketText({ goods: news.caught })}. Штраф ${news.fine} 元`;
    if (text) parts.push(node("p", "market-news", text));
  }

  function drawStall(me, parts) {
    const box = node("section", `market-card is-${me.role}`);
    box.append(node("b", "market-role", me.role === "patrol" ? "Вы патрульный NetWatch" : "Вы торговец"),
      node("p", "market-stats", `${me.money} 元 · богатство ${me.wealth}${me.traded ? "" : " · сегодня ещё не торговали"}`));
    const chips = node("div", "market-goods");
    const goods = Object.entries(me.goods || {});
    if (!goods.length) chips.append(node("span", "market-chip is-empty", "товаров нет"));
    goods.forEach(([code, n]) => {
      const g = catalog()[code] || {};
      chips.append(node("span", `market-chip${g.legal === false ? " is-contraband" : ""}`, `${goodLabel(code)} ×${n}`));
    });
    box.append(chips);
    if (me.code) {
      box.append(node("span", "capture-label", "Код сумки"), node("b", "market-code", `${me.code.slice(0, 3)} ${me.code.slice(3)}`),
        node("p", "market-meta", "Патрульный просит — покажите код. Прятать нельзя"));
    }
    parts.push(box);
  }

  function stepper(side, key, max) {
    const row = node("span", "market-stepper");
    const value = key === "money" ? builder[side].money : (builder[side].goods[key] || 0);
    const set = (next) => {
      const clamped = Math.max(0, Math.min(max, next));
      if (key === "money") builder[side].money = clamped;
      else builder[side].goods[key] = clamped;
      draw();
    };
    row.append(button("btn btn-secondary", "−", () => set(value - (key === "money" ? 5 : 1))),
      node("b", null, String(value)), button("btn btn-secondary", "+", () => set(value + (key === "money" ? 5 : 1))));
    const label = `${side === "give" ? "Отдаю" : "Хочу"}: ${key === "money" ? "юани" : goodLabel(key)}`;
    row.firstElementChild.setAttribute("aria-label", `Уменьшить · ${label}`);
    row.lastElementChild.setAttribute("aria-label", `Увеличить · ${label}`);
    return row;
  }

  function drawOffer(me, parts) {
    const box = node("section", "market-card is-offer");
    if (data.offer) {
      box.append(node("span", "capture-label", "Ваше предложение — покажите код"),
        node("b", "market-code", `${data.offer.code.slice(0, 3)} ${data.offer.code.slice(3)}`),
        node("p", "market-meta", `Отдаёте: ${basketText(data.offer.give)}`),
        node("p", "market-meta", `Хотите: ${basketText(data.offer.want)}`),
        node("p", "market-meta", `Код живёт ещё около ${data.offer.expires_in} с`),
        button("btn btn-secondary", "Отменить", () => act("offer/cancel")));
      parts.push(box);
      return;
    }
    box.append(node("span", "capture-label", "Собрать предложение"));
    const table = node("div", "market-builder");
    table.append(node("span", "market-head", "Отдаю"), node("span", "market-head", "Товар"), node("span", "market-head", "Хочу"));
    (data.catalog || []).forEach((g) => {
      const owned = (me.goods || {})[g.code] || 0;
      table.append(stepper("give", g.code, owned),
        node("span", `market-name${g.legal ? "" : " is-contraband"}`, `${g.zh} ${g.ru} · ${g.value} 元`),
        stepper("want", g.code, data.max_offer_items));
    });
    table.append(stepper("give", "money", Math.min(me.money, data.max_offer_money)), node("span", "market-name", "юани 元"), stepper("want", "money", data.max_offer_money));
    box.append(table, button("btn btn-primary", "Показать код", makeOffer));
    parts.push(box);
  }

  function drawAccept(parts) {
    const box = node("section", "market-card");
    box.append(node("span", "capture-label", "Принять чужое предложение"));
    const form = node("div", "market-form");
    form.append(codeInput("marketOfferCode", codeDraft, (v) => { codeDraft = v; }, "Код предложения"),
      button("btn btn-secondary", "Посмотреть", peek));
    box.append(form);
    if (peeked) {
      box.append(node("p", "market-meta", `${peeked.from} отдаёт: ${basketText(peeked.give)}`),
        node("p", "market-meta", `и хочет взамен: ${basketText(peeked.want)}`),
        armedButton("accept", "btn btn-primary", "Согласиться", "Точно меняемся?", () => act("accept", { code: peeked.code })));
    }
    parts.push(box);
  }

  function drawInspect(me, parts) {
    const box = node("section", "market-card is-patrol");
    box.append(node("span", "capture-label", "Вскрыть сумку: попросите у торговца код"));
    if (me.rest_until) box.append(node("p", "market-meta", "Следующая проверка — через несколько минут"));
    const form = node("div", "market-form");
    form.append(codeInput("marketBagCode", bagDraft, (v) => { bagDraft = v; }, "Код сумки торговца"),
      armedButton("inspect", "btn btn-primary", "Вскрыть", "Точно вскрыть?", () => {
        if (digits(bagDraft).length !== 6) {
          note = "Код сумки — шесть цифр";
          draw();
          return;
        }
        act("inspect", { code: digits(bagDraft) });
      }));
    box.append(form);
    if (lastInspection) {
      box.append(node("p", "market-news", lastInspection.clean
        ? `Сумка чиста. Вы заплатили ${lastInspection.fine} 元`
        : `Запрещёнка: ${basketText({ goods: lastInspection.caught })}, штраф ${lastInspection.fine} 元 вам`));
    }
    parts.push(box);
  }

  function drawResults(parts) {
    const r = data.results;
    if (!r || !r.results || !r.results.length) return;
    parts.push(node("span", "capture-label", `Итоги рынка ${r.day}`));
    const list = node("ol", "market-results");
    r.results.slice(0, 5).forEach((row) => list.append(node("li", null,
      `${row.name} · ${row.wealth} 元${row.prize ? ` · +${row.prize}★` : ""}`)));
    parts.push(list);
    if (!r.prizes) parts.push(node("p", "market-meta", `На рынок вышло меньше ${data.min_players} человек — без звёзд`));
  }

  function draw() {
    const body = $("marketBody");
    const status = $("marketStatus");
    if (!body) return;
    if (!signedIn() || !data || data.season_id == null) {
      const message = !signedIn() ? "Войдите, чтобы торговать" : data ? "Нет активного сезона" : "Загружаем…";
      body.replaceChildren(node("p", "spy-lead", LEAD), node("p", "market-meta", message));
      status.textContent = "—";
      return;
    }
    const focusedId = document.activeElement && document.activeElement.id;
    const parts = [node("p", "spy-lead", LEAD)];
    if (data.balance_status === "test") parts.push(node("p", "market-meta", "Тестовый баланс · перед сезоном числа будут согласованы"));
    if (pending) {
      parts.push(node("p", "market-news", "Проверяемая операция сохранена. Повтор не спишет товары ещё раз."),
        button("btn btn-secondary", "Проверить результат", () => act(pending.action, pending.body, true)));
    }
    const prizes = (data.prizes || []).join("/");
    if (data.phase === "before") parts.push(node("p", "market-meta", `Рынок откроется в ${data.open}. Выйти и получить набор можно уже сейчас`));
    else if (data.phase === "open") parts.push(node("p", "market-meta", `Рынок открыт до ${data.close} · торговцев ${data.players} · патрульных ${data.patrols} · призы ${prizes}★`));
    else parts.push(node("p", "market-meta", "Рынок закрыт до утра"));
    const me = data.me;
    if (!me) {
      if (data.can_play && data.phase !== "closed") parts.push(button("btn btn-primary", "Выйти на рынок", () => act("join")));
    } else {
      drawNews(me, parts);
      drawStall(me, parts);
      if (data.phase === "open") {
        if (me.role === "patrol") drawInspect(me, parts);
        drawOffer(me, parts);
        drawAccept(parts);
      }
    }
    drawResults(parts);
    parts.push(node("p", "case-message", note));
    body.replaceChildren(...parts);
    status.textContent = data.phase === "open" ? `ТОРГ ДО ${data.close}` : data.phase === "before" ? `ОТКРЫТИЕ В ${data.open}` : "ЗАКРЫТО";
    if (focusedId && $(focusedId)) {
      const input = $(focusedId);
      input.focus();
      if (input.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length);
    }
  }

  // --- данные ------------------------------------------------------------------------------------

  function accept(body) {
    const before = data && data.me && data.me.news;
    data = body;
    const after = data.me && data.me.news;
    if (before && after && before.at !== after.at && !document.hidden) window.ZhidaoSounds?.play(after.kind === "trade" ? "buy" : "join");
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      draw();
    }
    schedule();
  }

  async function refresh() {
    const requestEpoch = epoch;
    if (!signedIn()) {
      data = null;
      signature = "";
      draw();
      return;
    }
    try {
      const result = await api("/api/v4/market");
      if (requestEpoch !== epoch) return;
      accept(result);
    } catch (error) {
      if (requestEpoch !== epoch) return;
      note = `${error.message} Сохранённые данные остаются на экране.`;
      draw();
    } finally {
      if (requestEpoch === epoch) schedule();
    }
  }

  async function act(action, body, retry = false) {
    if (busy) return;
    if (pending && !retry) { note = "Сначала нажмите «Проверить результат» предыдущей операции."; draw(); return; }
    const requestEpoch = epoch;
    const durable = ["join", "accept", "inspect"].includes(action);
    if (retry && pending.season !== data?.season_id) {
      savePending(null); note = "Сезон изменился. Результат старой операции проверьте у организатора."; draw(); return;
    }
    if (durable && !retry) savePending({ action, body: body || {}, key: crypto.randomUUID(), season: data?.season_id });
    busy = true;
    note = "";
    draw();
    try {
      const result = await api(`/api/v4/market/${action}`, { method: "POST", body, key: durable ? pending.key : null });
      if (requestEpoch !== epoch) return;
      if (durable) savePending(null);
      if (action === "accept") {
        peeked = null;
        codeDraft = "";
        window.showToast?.(`Обмен подтверждён: получили ${basketText(result.trade.got)}`);
        if (!result.replayed) window.ZhidaoRetro?.copyFile({ name: basketText(result.trade.got) });
      }
      if (action === "inspect") {
        bagDraft = "";
        lastInspection = result.inspection;
      }
      if (action === "offer") builder = { give: { goods: {}, money: 0 }, want: { goods: {}, money: 0 } };
      accept(result);
    } catch (error) {
      if (requestEpoch !== epoch) return;
      if (error.status >= 400 && error.status < 500) savePending(null);
      note = error.message;
      await refresh();
    } finally {
      if (requestEpoch === epoch) { busy = false; signature = ""; draw(); }
    }
  }

  function makeOffer() {
    const clean = (basket) => ({
      goods: Object.fromEntries(Object.entries(basket.goods).filter(([, n]) => n > 0)),
      money: basket.money,
    });
    act("offer", { give: clean(builder.give), want: clean(builder.want) });
  }

  async function peek() {
    if (busy) return;
    const requestEpoch = epoch;
    const code = digits(codeDraft);
    if (code.length !== 6) {
      note = "Код предложения — шесть цифр";
      draw();
      return;
    }
    busy = true;
    note = "";
    draw();
    try {
      const result = await api(`/api/v4/market/offers/${code}`);
      if (requestEpoch === epoch) peeked = result;
    } catch (error) {
      if (requestEpoch !== epoch) return;
      peeked = null;
      note = error.message;
    } finally {
      if (requestEpoch === epoch) { busy = false; draw(); }
    }
  }

  function schedule() {
    if (!signedIn() || !onGames() || document.hidden) {
      clearInterval(poll);
      poll = null;
      return;
    }
    if (!poll) poll = setInterval(() => { if (!busy) refresh(); }, POLL_MS);
  }

  // --- подключение -------------------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    epoch += 1;
    if (session?.account?.id && session.account.id !== event.detail?.account?.id) savePending(null);
    session = event.detail;
    restorePending();
    busy = false;
    builder = { give: { goods: {}, money: 0 }, want: { goods: {}, money: 0 } };
    data = null;
    signature = "";
    armed = null;
    note = "";
    codeDraft = "";
    bagDraft = "";
    peeked = null;
    lastInspection = null;
    draw();
    if (onGames()) refresh();
  });
  document.addEventListener("visibilitychange", () => {
    schedule();
    if (!document.hidden && onGames()) { data = null; refresh(); }
  });
  window.addEventListener("online", () => { if (onGames()) refresh(); });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "games") refresh();
    else schedule();
  });
  restorePending();
  draw();
}());
