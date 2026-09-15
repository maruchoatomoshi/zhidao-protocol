"use strict";

/* Каталог «Ивентов».

   Дизайн-проход 2026-09-14: вместо ленты из девяти окон — плитки с обложками:
   касание открывает одно окно игры, «Все игры» возвращает к плиткам. Окна и их
   скрипты не меняются. Каталог прячет чужие окна своим атрибутом
   data-catalog-hidden, а атрибут hidden окон по-прежнему ведут их собственные
   скрипты (например, games.js переключает стол и комнату). Кто сидит в комнате
   настольной игры, тому окно стола открывается само.

   Решение пользователя 2026-09-15: сверху — то, во что можно играть прямо
   сейчас (крупные плитки со значком состояния), ниже — игры по коду комнаты,
   ещё ниже и бледнее — то, что откроется позже. Состояния — тот же снимок
   GET /api/v4/today, что у главной, раз в минуту и только пока открыт каталог. */

(function () {
  const screen = document.querySelector('[data-screen="games"]');
  const catalog = document.getElementById("gamesCatalog");
  const back = document.getElementById("gamesBack");
  const room = document.getElementById("gameRoom");
  if (!screen || !catalog || !back) return;
  const REFRESH_MS = 60000;

  const GAMES = [
    { key: "royale", title: "Протокол 60", zh: "大逃杀", cover: "cover-royale", note: "вся смена · ведёт вожатый" },
    { key: "market", title: "Рынок Контрабанды", zh: "黑市", cover: "cover-market", note: "обмен с 09:00 до 21:00" },
    { key: "agent", title: "Тайный агент", zh: "特工", cover: "cover-agent", note: "весь день · тайная цель" },
    { key: "zombie", title: "Зомби-протокол", zh: "丧尸", cover: "cover-zombie", note: "раунд 20 минут · запускает вожатый" },
    { key: "sabotage", title: "Саботаж", zh: "破坏", cover: "cover-sabotage", note: "кампус · 30 минут · запускает вожатый" },
    { key: "capture", title: "Захват кампуса", zh: "占领", cover: "cover-capture", note: "фракции · нужен GPS" },
    { key: "table", title: "Игры за столом", zh: "游戏", cover: "cover-spy", note: "Шпион, Шифровальщики, Сбой системы, Контрабанда" },
  ];
  const GROUPS = [
    { key: "live", title: "Идёт сейчас", zh: "进行中" },
    { key: "room", title: "По коду комнаты", zh: "房间" },
    { key: "later", title: "Позже", zh: "稍后" },
  ];

  let session = window.ZhidaoSession || null;
  let open = null;
  let timer = null;
  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onGames = () => document.documentElement.dataset.currentScreen === "games";
  const inRoom = () => Boolean(room && !room.hidden);
  const hhmm = (iso) => (iso ? String(iso).slice(11, 16) : "");

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const groups = {};
  GROUPS.forEach((group) => {
    const section = node("section", `catalog-group is-${group.key}`);
    const heading = node("h2", "catalog-heading", group.title);
    const zh = node("span", null, group.zh);
    zh.lang = "zh";
    zh.setAttribute("aria-hidden", "true");
    heading.append(zh);
    const grid = node("div", "catalog-grid");
    section.append(heading, grid);
    catalog.append(section);
    groups[group.key] = { section, grid };
  });

  const tiles = new Map();
  GAMES.forEach((game) => {
    const tile = node("button", "catalog-tile");
    tile.type = "button";
    tile.dataset.key = game.key;
    const img = node("img");
    img.src = `./assets/games/${game.cover}.webp`;
    img.alt = "";
    img.width = 960;
    img.height = 360;
    img.loading = "lazy";
    img.decoding = "async";
    const title = node("b", null, game.title);
    const zh = node("span", null, game.zh);
    zh.lang = "zh";
    zh.setAttribute("aria-hidden", "true");
    title.append(zh);
    const note = node("small", null, game.note);
    const text = node("span", "catalog-tile-text");
    text.append(title, note);
    const badge = node("span", "catalog-badge");
    badge.hidden = true;
    tile.append(img, text, badge);
    tile.addEventListener("click", () => show(game.key));
    tiles.set(game.key, { game, tile, note, badge });
  });

  function place(key, group, badgeText, badgeKind, noteText) {
    const entry = tiles.get(key);
    entry.badge.hidden = !badgeText;
    entry.badge.textContent = badgeText || "";
    entry.badge.className = `catalog-badge${badgeKind ? ` is-${badgeKind}` : ""}`;
    entry.note.textContent = noteText || entry.game.note;
    groups[group].grid.append(entry.tile);
  }

  function classify(items) {
    const by = Object.fromEntries((items || []).map((item) => [item.key, item]));
    GAMES.forEach(({ key }) => {
      const item = by[key];
      if (key === "table") {
        place(key, "room", inRoom() ? "В КОМНАТЕ" : "", "lobby");
      } else if (["royale", "zombie", "sabotage"].includes(key) && item) {
        if (item.state === "lobby") {
          place(key, "live", key === "royale" && item.players ? `ЛОББИ · ${item.players}` : "ЛОББИ", "lobby", "вожатый открыл лобби");
        } else {
          place(key, "live", "ИДЁТ", "lobby", key === "royale" ? `в игре осталось ${item.alive}` : "игра уже началась");
        }
      } else if (key === "market" && item) {
        if (item.state === "open") place(key, "live", "ОТКРЫТ", "open", item.joined ? `ты на рынке · до ${item.close}` : `торгуют до ${item.close}`);
        else place(key, "later", "", "", `откроется в ${item.open}`);
      } else if (key === "agent" && item) {
        place(key, "live", "СМЕНА", "open", item.has_mission ? "у тебя миссия на сегодня" : "смена агентов идёт");
      } else if (key === "capture" && item) {
        if (item.state === "open") place(key, "live", "ОКНО ОТКРЫТО", "open", `захват до ${hhmm(item.until)}`);
        else place(key, "later", "", "", item.until ? `окно захвата откроется в ${hhmm(item.until)}` : "окон сегодня больше нет");
      } else {
        place(key, "later");
      }
    });
    GROUPS.forEach((group) => { groups[group.key].section.hidden = groups[group.key].grid.childElementCount === 0; });
  }

  function render() {
    catalog.hidden = open !== null;
    back.hidden = open === null;
    screen.querySelectorAll("[data-catalog]").forEach((win) => {
      if (open !== null && win.dataset.catalog === open) win.removeAttribute("data-catalog-hidden");
      else win.setAttribute("data-catalog-hidden", "");
    });
    const table = tiles.get("table");
    table.badge.hidden = !inRoom();
    table.badge.textContent = inRoom() ? "В КОМНАТЕ" : "";
  }

  function show(key) {
    open = key;
    render();
    window.scrollTo({ top: 0 });
    back.querySelector("button")?.focus({ preventScroll: true });
  }

  async function refresh() {
    clearTimeout(timer);
    if (!onGames() || document.hidden) return;
    if (!signedIn()) { classify([]); return; }
    const account = session?.account?.id;
    try {
      const response = await fetch("/api/v4/today", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
      if (account !== session?.account?.id) return;
      if (response.ok) classify((await response.json()).items);
      else if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
    } catch (_) {
      /* плитки остаются на прежних местах */
    } finally {
      if (signedIn() && onGames() && !document.hidden) timer = setTimeout(refresh, REFRESH_MS);
    }
  }

  back.querySelector("[data-catalog-back]")?.addEventListener("click", () => {
    const was = open;
    open = null;
    render();
    catalog.querySelector(`.catalog-tile[data-key="${was}"]`)?.focus({ preventScroll: true });
  });

  // Вход в комнату (или выход из неё) замечаем по атрибуту hidden окна комнаты.
  if (room) {
    new MutationObserver(() => {
      if (inRoom() && open === null) show("table");
      else render();
    }).observe(room, { attributes: true, attributeFilter: ["hidden"] });
  }

  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail !== "games") { clearTimeout(timer); return; }
    open = inRoom() ? "table" : null;
    render();
    refresh();
  });
  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    classify([]);
    refresh();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });

  // Главная («Сейчас», «Что нового») открывает игру сразу: showScreen уже сбросил каталог.
  window.ZhidaoCatalog = Object.freeze({
    open(key) {
      if (GAMES.some((game) => game.key === key)) show(key);
    },
  });

  classify([]);
  render();
}());
