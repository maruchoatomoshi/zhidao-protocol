"use strict";

/* Обмен дубликатами из рук в руки (V4_GAMES.md §4.5).

   Экран ничего не решает: что можно отдать, хватает ли звёзд и лимита,
   состоялся ли обмен — отвечает сервер. Пока открыт обмен, телефон раз в
   полторы секунды спрашивает его состояние: так оба видят, что выбрал и
   подтвердил другой. Предметы двигаются только после двух подтверждений. */

(function () {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 1500;
  const ART = {
    implant_guanxi: "guanxi", implant_panda: "panda", implant_shaolin: "shaolin",
    implant_linguasoft: "linguasoft", implant_caishen: "caishen", implant_qilin: "qilin",
    implant_terracota: "terracota", implant_red_dragon: "honglong",
  };
  const RARITY = { gold: "обычный", purple: "редкий", black: "легендарный" };
  const STATES = { open: "ЖДЁМ СОБЕСЕДНИКА", ready: "ПОДТВЕРЖДЕНИЕ", done: "ОБМЕН СОСТОЯЛСЯ", cancelled: "ОТМЕНЁН", failed: "НЕ СОСТОЯЛСЯ" };

  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let overview = null;
  let current = null;        // вид открытого обмена от сервера
  let selected = null;       // выбранный свой дубликат
  let pollTimer = null;
  let busy = false;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "trade";
  const setStatus = (text) => { $("tradeStatus").textContent = text || ""; };

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
        const detail = Array.isArray(body.detail) ? "Запрос заполнен неверно." : body.detail;
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

  function seasons() {
    if (!contextPromise) {
      contextPromise = api("/api/v4/cases/context")
        .then((body) => body.seasons || [])
        .catch((error) => { contextPromise = null; throw error; });
    }
    return contextPromise;
  }

  const base = () => `/api/v4/seasons/${season.id}/trade`;

  // --- карточка предмета -------------------------------------------------------------

  function itemCard(item, extra) {
    const card = node("span", `trade-item-card is-${item.tier}`);
    if (ART[item.code]) {
      const image = node("img");
      image.src = `./assets/implants/${ART[item.code]}.webp`;
      image.alt = "";
      image.loading = "lazy";
      card.append(image);
    } else {
      card.append(node("span", "trade-glyph", "◷"));
    }
    card.append(node("b", null, item.name_ru), node("small", "trade-tier", RARITY[item.tier] || item.tier));
    if (extra) card.append(node("small", null, extra));
    return card;
  }

  // --- начало: мои дубликаты ------------------------------------------------------------

  function drawStart() {
    $("tradeStart").hidden = false;
    $("tradeRoom").hidden = true;
    const host = $("tradeItems");
    host.replaceChildren();
    if (!overview) return;
    $("tradeLimit").textContent = `${overview.trades_today} / ${overview.limit} сегодня`;
    $("tradeToday").textContent = `У ВАС ${overview.stars}★ · СБОР ${overview.fee}★`;
    if (!overview.items.length) {
      host.append(node("p", "case-message", "Дубликатов пока нет. Обменять можно предмет из кейсов, которого у вас больше одного."));
    }
    for (const item of overview.items) {
      const b = node("button", "trade-item");
      b.type = "button";
      b.setAttribute("aria-pressed", String(selected === item.code));
      b.append(itemCard(item, `у вас ×${item.quantity}`));
      b.addEventListener("click", () => {
        selected = selected === item.code ? null : item.code;
        drawStart();
      });
      host.append(b);
    }
    const blocked = !selected || busy || overview.season_status !== "active" || overview.trades_today >= overview.limit;
    $("tradeOffer").disabled = blocked;
    $("tradeJoinSubmit").disabled = blocked;
    if (!selected && overview.items.length) setStatus("Сначала выберите, какой дубликат отдаёте.");
  }

  async function loadOverview() {
    if (!signedIn()) {
      overview = null;
      $("tradeItems").replaceChildren();
      setStatus("Войдите, чтобы меняться дубликатами.");
      $("tradeOffer").disabled = true;
      $("tradeJoinSubmit").disabled = true;
      return;
    }
    try {
      const list = await seasons();
      season = list.find((s) => s.is_member && s.status === "active") || list.find((s) => s.is_member) || null;
      if (!season) {
        setStatus("Обмен откроется, когда вас включат в сезон.");
        return;
      }
      overview = await api(base());
      if (selected && !overview.items.some((item) => item.code === selected)) selected = null;
      if (overview.current) {
        await openTrade(overview.current);
        return;
      }
      setStatus("");
      drawStart();
    } catch (error) {
      setStatus(error.message);
    }
  }

  // --- открытый обмен ---------------------------------------------------------------------

  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
      if (!current || document.hidden || busy) return;
      try {
        show(await api(`${base()}/${current.code}`));
      } catch (error) {
        if (error.status === 404) closeRoom("Обмен закрыт.");
      }
    }, POLL_MS);
  }

  function side(title, entry, emptyText, isPartner) {
    const box = node("div", "trade-side");
    box.append(node("span", "spy-label", title));
    if (!entry) {
      box.append(node("p", "case-message", emptyText));
      return box;
    }
    box.append(itemCard(entry.item, isPartner && entry.name ? `от: ${entry.name}` : null));
    box.append(node("small", `trade-confirm${entry.confirmed ? " is-on" : ""}`, entry.confirmed ? "подтвердил(а)" : "ещё не подтвердил(а)"));
    return box;
  }

  function show(view) {
    current = view;
    $("tradeStart").hidden = true;
    $("tradeRoom").hidden = false;
    $("tradeRoomState").textContent = STATES[view.state] || view.state;
    const body = $("tradeRoomBody");
    const parts = [];

    if (view.state === "open" && view.role === "a") {
      const plate = node("div", "spy-code-plate");
      plate.append(node("span", "spy-label", "Покажите код собеседнику"),
        node("b", "spy-code", `${view.code.slice(0, 3)} ${view.code.slice(3)}`),
        node("span", "spy-hint", `Код действует ещё ${view.expires_in} с`));
      parts.push(plate);
    }

    const swap = node("div", "trade-swap");
    swap.append(side("Вы отдаёте", view.you, "", false),
      node("span", "trade-arrow", "⇄"),
      side("Вы получаете", view.partner, "Ждём, пока собеседник введёт код и выберет свой дубликат.", true));
    parts.push(swap);

    if (view.state === "ready") {
      if (view.gives_rarer) {
        parts.push(node("p", "spy-banner trade-warning",
          "Внимание: вы отдаёте более редкий предмет, чем получаете. Обмен не отменить — подтвердите, только если вы правда этого хотите."));
      }
      if (!view.you.confirmed) {
        const confirm = node("button", "btn btn-primary",
          view.gives_rarer ? "Отдаю более редкое — подтверждаю" : `Подтвердить обмен (−${view.fee}★)`);
        confirm.type = "button";
        confirm.disabled = busy;
        confirm.addEventListener("click", () => act("confirm", { acknowledge_unequal: Boolean(view.gives_rarer) }));
        parts.push(confirm);
      } else {
        parts.push(node("p", "spy-lead", "Вы подтвердили. Ждём подтверждения собеседника."));
      }
    }

    if (view.state === "done" && view.result) {
      const done = node("div", "spy-reveal");
      done.append(node("h3", null, "Обмен состоялся"),
        node("p", "spy-lead", `Вы получили «${view.result.got}», отдали «${view.result.gave}».`),
        node("p", "spy-hint", `Сбор −${view.result.fee}★, у вас ${view.result.stars}★.`));
      parts.push(done);
    }
    if (["cancelled", "failed"].includes(view.state) && view.message) {
      parts.push(node("p", "spy-banner", view.message));
    }
    if (["done", "cancelled", "failed"].includes(view.state)) {
      const back = node("button", "btn btn-secondary", "К моим дубликатам");
      back.type = "button";
      back.addEventListener("click", () => closeRoom(""));
      parts.push(back);
      stopPolling();
      if (view.state === "done" && window.ZhidaoSounds) window.ZhidaoSounds.play("buy");
    } else {
      startPolling();
    }
    body.replaceChildren(...parts);
  }

  async function openTrade(code) {
    try {
      show(await api(`${base()}/${code}`));
    } catch (error) {
      closeRoom(error.message);
    }
  }

  function closeRoom(message) {
    stopPolling();
    current = null;
    selected = null;
    loadOverview().then(() => { if (message) setStatus(message); });
  }

  async function act(action, bodyData) {
    if (busy || !current) return;
    busy = true;
    try {
      show(await api(`${base()}/${current.code}/${action}`, { method: "POST", body: bodyData }));
    } catch (error) {
      $("tradeRoomBody").prepend(node("p", "spy-banner", error.message));
    } finally {
      busy = false;
    }
  }

  async function offer() {
    if (busy || !selected || !season) return;
    busy = true;
    try {
      show(await api(`${base()}/offer`, { method: "POST", body: { item_code: selected } }));
    } catch (error) {
      setStatus(error.message);
    } finally {
      busy = false;
    }
  }

  async function join(event) {
    event.preventDefault();
    if (busy || !season) return;
    const code = $("tradeCode").value.replace(/\D/g, "");
    if (code.length !== 6) {
      setStatus("Код обмена — шесть цифр.");
      return;
    }
    if (!selected) {
      setStatus("Сначала выберите, какой дубликат отдаёте.");
      return;
    }
    busy = true;
    try {
      show(await api(`${base()}/join`, { method: "POST", body: { code, item_code: selected } }));
      $("tradeCode").value = "";
    } catch (error) {
      setStatus(error.message);
    } finally {
      busy = false;
    }
  }

  // --- подключение ---------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    overview = null;
    current = null;
    selected = null;
    stopPolling();
    if (onScreen()) loadOverview();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "trade") loadOverview();
    else stopPolling();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && onScreen() && current) openTrade(current.code);
  });

  $("tradeOffer").addEventListener("click", offer);
  $("tradeJoinForm").addEventListener("submit", join);
  $("tradeCode").addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
  });
  $("tradeCancel").addEventListener("click", () => { if (current) act("cancel"); });
}());
