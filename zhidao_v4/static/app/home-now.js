"use strict";

/* «Сейчас в сезоне» на главной (дизайн-проход 2026-09-14). Что идёт прямо
   сейчас: лобби Протокола 60, Зомби и Саботажа, рынок, смена агентов, окно
   Захвата, новый скрытый файл. Данные — один лёгкий снимок GET /api/v4/today
   раз в минуту и только пока открыта главная. Касание строки открывает игру в
   каталоге «Ивентов», карту или архив истории. Имён, ролей и целей сервер сюда
   не присылает. */

(function () {
  const card = document.getElementById("homeNow");
  const list = document.getElementById("homeNowList");
  if (!card || !list) return;
  const REFRESH_MS = 60000;
  let session = window.ZhidaoSession || null;
  let timer = null;
  let signature = "";

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onHome = () => document.documentElement.dataset.currentScreen === "schedule";
  const hhmm = (iso) => (iso ? String(iso).slice(11, 16) : "");
  const LIVE = ["lobby", "running", "open"];

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
    market: (i) => (i.state === "open"
      ? { title: "Рынок Контрабанды открыт", note: i.joined ? `Вы на рынке · торгуют до ${i.close}` : `Торгуют до ${i.close}`, action: i.joined ? "Открыть" : "На рынок" }
      : { title: `Рынок откроется в ${i.open}`, note: "Утренний набор можно взять уже сейчас", action: "Открыть" }),
    agent: (i) => ({ title: "Смена тайных агентов", note: i.has_mission ? "У вас есть миссия" : "Смена идёт", action: "Открыть" }),
    capture: (i) => (i.state === "open"
      ? { title: "Захват кампуса · окно открыто", note: `До ${hhmm(i.until)}`, action: "Карта" }
      : { title: "Захват кампуса", note: i.until ? `Следующее окно в ${hhmm(i.until)}` : "Окон сегодня больше нет", action: "Карта" }),
    story: () => ({ title: "Новый скрытый файл", note: "Разгадайте — откроется слово Архитектора", action: "Архив" }),
  };

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function go(key) {
    if (key === "capture") { window.showScreen?.("campus-map"); return; }
    if (key === "story") { window.showScreen?.("story"); return; }
    window.showScreen?.("games");
    window.ZhidaoCatalog?.open(key);
  }

  function render(data) {
    const items = ((data && data.items) || []).filter((item) => LINES[item.key]);
    const next = JSON.stringify(items);
    if (next === signature) return;
    signature = next;
    card.hidden = items.length === 0;
    list.replaceChildren(...items.map((item) => {
      const line = LINES[item.key](item);
      const button = node("button", `now-row is-${item.key}${LIVE.includes(item.state) ? " is-live" : ""}`);
      button.type = "button";
      const text = node("span", "now-text");
      text.append(node("b", null, line.title), node("small", null, line.note));
      const action = node("span", "now-action", line.action);
      action.setAttribute("aria-hidden", "true");
      button.append(text, action);
      button.addEventListener("click", () => go(item.key));
      const row = node("li");
      row.append(button);
      return row;
    }));
  }

  async function refresh() {
    clearTimeout(timer);
    if (!signedIn()) {
      signature = "";
      card.hidden = true;
      return;
    }
    if (document.hidden || !onHome()) return;
    const account = session?.account?.id;
    try {
      const response = await fetch("/api/v4/today", { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
      if (account !== session?.account?.id) return;
      if (response.ok) render(await response.json());
      else if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
    } catch (_) {
      /* карточка подождёт следующей минуты */
    } finally {
      if (signedIn() && !document.hidden && onHome()) timer = setTimeout(refresh, REFRESH_MS);
    }
  }

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    signature = "";
    card.hidden = true;
    refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "schedule") refresh();
    else clearTimeout(timer);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimeout(timer);
    else refresh();
  });
  window.addEventListener("online", refresh);
  refresh();
}());
