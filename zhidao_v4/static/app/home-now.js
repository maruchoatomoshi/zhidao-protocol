"use strict";

/* Главная без дублей (решение пользователя 2026-09-15). Главная показывает
   только то, что меняется и касается человека лично; списки игр живут в
   «Ивентах», попытки — в «Кейсах».

   - «Сейчас» — одна строка, самое срочное из снимка GET /api/v4/today. Нет
     срочного — карточки нет, и остров на главной снова крупный (data-calm).
   - «Что нового» — строки журнала, которые с человеком сделали другие или
     игра, с прошлого входа. Что уже видено, помнит это устройство: номер
     последней показанной записи запоминается, когда человек уходит с главной.

   Данные — один лёгкий снимок раз в минуту и только пока открыта главная.
   Имён, ролей и целей сервер сюда не присылает. */

(function () {
  const screen = document.querySelector('[data-screen="schedule"]');
  const card = document.getElementById("homeNow");
  const list = document.getElementById("homeNowList");
  const feedCard = document.getElementById("homeFeed");
  const feedList = document.getElementById("homeFeedList");
  const feedEmpty = document.getElementById("homeFeedEmpty");
  if (!screen || !card || !list || !feedCard || !feedList || !feedEmpty) return;
  const REFRESH_MS = 60000;
  let session = window.ZhidaoSession || null;
  let timer = null;
  let signature = "";
  let shownUpTo = 0;

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onHome = () => document.documentElement.dataset.currentScreen === "schedule";
  const hhmm = (iso) => (iso ? String(iso).slice(11, 16) : "");
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* только до перезагрузки */ } },
  };
  const seenKey = () => `zhidao.v4.feed.seen.${session?.account?.id}`;

  const LINES = {
    royale: (i) => (i.state === "lobby"
      ? { title: "Протокол 60 · лобби открыто", note: i.players ? `Заходите — в лобби уже ${i.players}` : "Лобби ждёт первых игроков", action: "Войти" }
      : { title: "Протокол 60 идёт", note: `В игре осталось ${i.alive}`, action: "Смотреть" }),
    zombie: (i) => (i.state === "lobby"
      ? { title: "Зомби-протокол · лобби открыто", note: "Раунд скоро начнётся", action: "Войти" }
      : { title: "Зомби-протокол идёт", note: "Раунд уже начался", action: "Открыть" }),
    sabotage: (i) => (i.state === "lobby"
      ? { title: "Саботаж · лобби открыто", note: "Игра скоро начнётся", action: "Войти" }
      : { title: "Саботаж идёт", note: "Игра на кампусе уже началась", action: "Открыть" }),
    capture: (i) => ({ title: "Захват кампуса · окно открыто", note: `До ${hhmm(i.until)}`, action: "Карта" }),
    agent: () => ({ title: "Тайный агент", note: "У вас есть миссия на сегодня", action: "Открыть" }),
    market: (i) => ({ title: "Рынок Контрабанды открыт", note: `Торгуют до ${i.close}`, action: "На рынок" }),
  };

  /* Самое срочное — одно. Лобби раньше идущей игры: в лобби ещё можно успеть. */
  const URGENT = [
    (i) => i.key === "royale" && i.state === "lobby",
    (i) => (i.key === "zombie" || i.key === "sabotage") && i.state === "lobby",
    (i) => ["royale", "zombie", "sabotage"].includes(i.key) && i.state === "running",
    (i) => i.key === "capture" && i.state === "open",
    (i) => i.key === "agent" && i.has_mission,
    (i) => i.key === "market" && i.state === "open" && !i.joined,
  ];

  const GAME = { royale: "Протокол 60", zombie: "Зомби-протокол", sabotage: "Саботаж", smuggle: "Контрабанда", market: "Рынок Контрабанды" };
  const CATALOG = { royale: "royale", zombie: "zombie", sabotage: "sabotage", smuggle: "table", market: "market" };

  function reward(f) {
    const signed = (n) => (n > 0 ? `+${n}` : String(n));
    const parts = [];
    if (f.rep) parts.push(`${signed(f.rep)} REP`);
    if (f.stars) parts.push(`${signed(f.stars)}★`);
    return parts.join(" · ");
  }

  const FEED = {
    diary: (f) => ({ title: "Вожатый оценил дневник", note: reward(f) || "Оценка обновлена", icon: "nav-rating.png", go: () => window.showScreen?.("rating") }),
    prize: (f) => ({ title: `Приз: ${GAME[f.game] || "игра"}`, note: reward(f), icon: "desktop-spy.svg", go: () => { window.showScreen?.("games"); window.ZhidaoCatalog?.open(CATALOG[f.game]); } }),
    trade: () => ({ title: "Обмен состоялся", note: "Предмет уже в коллекции", icon: "nav-cases.png", go: () => window.showScreen?.("collection") }),
    story: (f) => ({ title: "Награда за скрытые файлы", note: reward(f), icon: "desktop-archive.svg", go: () => window.showScreen?.("story") }),
    scans: (f) => ({ title: "Вожатый выдал попытки кейса", note: `+${f.scans} к попыткам`, icon: "nav-cases.png", go: () => window.showScreen?.("cases") }),
  };

  function when(iso) {
    const moment = new Date(iso);
    if (Number.isNaN(moment.getTime())) return "";
    const today = new Date().toDateString() === moment.toDateString();
    return today
      ? moment.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
      : moment.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  }

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function go(key) {
    if (key === "capture") { window.showScreen?.("campus-map"); return; }
    window.showScreen?.("games");
    window.ZhidaoCatalog?.open(key);
  }

  function drawNow(item) {
    card.hidden = !item;
    screen.dataset.calm = String(!item);
    if (!item) { list.replaceChildren(); return; }
    const line = LINES[item.key](item);
    const button = node("button", `now-row is-${item.key} is-live`);
    button.type = "button";
    const text = node("span", "now-text");
    text.append(node("b", null, line.title), node("small", null, line.note));
    const action = node("span", "now-action", line.action);
    action.setAttribute("aria-hidden", "true");
    button.append(text, action);
    button.addEventListener("click", () => go(item.key));
    const row = node("li");
    row.append(button);
    list.replaceChildren(row);
  }

  function feedRow(line, time, fresh) {
    const button = node("button", "feed-row");
    button.type = "button";
    const icon = node("img", "feed-icon");
    icon.src = `./assets/icons/${line.icon}`;
    icon.alt = "";
    const text = node("span", "feed-text");
    text.append(node("b", null, line.title));
    if (line.note) text.append(node("small", null, line.note));
    button.append(icon, text, node("span", "feed-time", time));
    if (fresh) {
      const badge = node("b", "feed-new", "NEW!");
      badge.setAttribute("aria-hidden", "true");
      button.append(badge);
    }
    button.addEventListener("click", line.go);
    const row = node("li");
    row.append(button);
    return row;
  }

  function drawFeed(data) {
    feedCard.hidden = !data.season_id;
    const stored = Number(store.get(seenKey()));
    const seen = Number.isFinite(stored) ? stored : 0;
    const entries = (data.feed || []).filter((f) => FEED[f.kind] && f.id > seen);
    shownUpTo = Math.max(seen, ...(data.feed || []).map((f) => f.id));
    const rows = entries.map((f) => feedRow(FEED[f.kind](f), when(f.at), false));
    // Открытый скрытый файл — не запись журнала, а состояние: висит, пока его не разгадали.
    if ((data.items || []).some((i) => i.key === "story")) {
      rows.unshift(feedRow({ title: "Открылся скрытый файл", note: "Разгадайте — откроется слово Архитектора", icon: "desktop-archive.svg",
        go: () => window.showScreen?.("story") }, "", true));
    }
    feedList.replaceChildren(...rows);
    feedEmpty.hidden = rows.length > 0;
  }

  function remember() {
    if (signedIn() && shownUpTo) store.set(seenKey(), String(shownUpTo));
  }

  function render(data) {
    const next = JSON.stringify(data);
    if (next === signature) return;
    signature = next;
    const items = (data && data.items) || [];
    const urgent = URGENT.map((test) => items.find(test)).find(Boolean);
    drawNow(urgent && LINES[urgent.key] ? urgent : null);
    drawFeed(data || {});
  }

  function reset() {
    signature = "";
    shownUpTo = 0;
    card.hidden = true;
    feedCard.hidden = true;
    screen.dataset.calm = "true";
  }

  async function refresh() {
    clearTimeout(timer);
    if (!signedIn()) { reset(); return; }
    if (document.hidden || !onHome()) return;
    const account = session?.account?.id;
    try {
      const response = await fetch("/api/v4/today", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
      if (account !== session?.account?.id) return;
      if (response.ok) render(await response.json());
      else if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
    } catch (_) {
      /* карточки подождут следующей минуты */
    } finally {
      if (signedIn() && !document.hidden && onHome()) timer = setTimeout(refresh, REFRESH_MS);
    }
  }

  window.addEventListener("zhidao:auth", (event) => {
    remember();
    session = event.detail;
    reset();
    refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "schedule") refresh();
    else { clearTimeout(timer); remember(); signature = ""; }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { clearTimeout(timer); remember(); }
    else refresh();
  });
  window.addEventListener("online", refresh);
  reset();
  refresh();
}());
