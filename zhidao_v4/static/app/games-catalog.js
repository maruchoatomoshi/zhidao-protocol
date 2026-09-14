"use strict";

/* Каталог «Ивентов» (дизайн-проход 2026-09-14). Вместо ленты из девяти окон —
   плитки с обложками: касание открывает одно окно игры, «Все игры» возвращает
   к плиткам. Окна и их скрипты не меняются. Каталог прячет чужие окна своим
   атрибутом data-catalog-hidden, а атрибут hidden окон по-прежнему ведут их
   собственные скрипты (например, games.js переключает стол и комнату).
   Кто сидит в комнате настольной игры, тому окно стола открывается само. */

(function () {
  const screen = document.querySelector('[data-screen="games"]');
  const catalog = document.getElementById("gamesCatalog");
  const back = document.getElementById("gamesBack");
  const room = document.getElementById("gameRoom");
  if (!screen || !catalog || !back) return;

  const GAMES = [
    { key: "table", title: "Игры за столом", zh: "游戏", cover: "cover-spy", note: "Шпион, Шифровальщики, Сбой системы, Контрабанда · по коду комнаты", wide: true },
    { key: "royale", title: "Протокол 60", zh: "大逃杀", cover: "cover-royale", note: "вся смена · ведёт вожатый" },
    { key: "capture", title: "Захват кампуса", zh: "占领", cover: "cover-capture", note: "фракции · нужен GPS" },
    { key: "agent", title: "Тайный агент", zh: "特工", cover: "cover-agent", note: "весь день · тайная цель" },
    { key: "market", title: "Рынок Контрабанды", zh: "黑市", cover: "cover-market", note: "обмен с 09:00 до 21:00" },
    { key: "zombie", title: "Зомби-протокол", zh: "丧尸", cover: "cover-zombie", note: "раунд 20 минут" },
    { key: "sabotage", title: "Саботаж", zh: "破坏", cover: "cover-sabotage", note: "кампус · 30 минут" },
  ];

  let open = null;
  const inRoom = () => Boolean(room && !room.hidden);

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  GAMES.forEach((game) => {
    const tile = node("button", `catalog-tile${game.wide ? " is-wide" : ""}`);
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
    const text = node("span", "catalog-tile-text");
    text.append(title, node("small", null, game.note));
    tile.append(img, text);
    if (game.key === "table") {
      const live = node("span", "catalog-live", "В КОМНАТЕ");
      live.hidden = true;
      tile.append(live);
    }
    tile.addEventListener("click", () => show(game.key));
    catalog.append(tile);
  });

  function render() {
    catalog.hidden = open !== null;
    back.hidden = open === null;
    screen.querySelectorAll("[data-catalog]").forEach((win) => {
      if (open !== null && win.dataset.catalog === open) win.removeAttribute("data-catalog-hidden");
      else win.setAttribute("data-catalog-hidden", "");
    });
    const live = catalog.querySelector(".catalog-live");
    if (live) live.hidden = !inRoom();
  }

  function show(key) {
    open = key;
    render();
    window.scrollTo({ top: 0 });
    back.querySelector("button")?.focus({ preventScroll: true });
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
    if (event.detail !== "games") return;
    open = inRoom() ? "table" : null;
    render();
  });

  render();
}());
