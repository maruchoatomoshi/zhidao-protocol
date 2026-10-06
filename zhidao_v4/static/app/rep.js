"use strict";

/* REP сезона на экране рейтинга (решение пользователя 2026-09-15).

   «Моё место»: номер, REP на табло и сколько осталось до места выше. Ниже —
   тройка лидеров и соседи рядом. Всей таблицы из шестидесяти человек нет:
   последние места не видны всем. Данные — GET /api/v4/seasons/{id}/rep/board;
   сервер сам не присылает никого вне тройки и соседей. */

(function () {
  const $ = (id) => document.getElementById(id);
  const me = $("repMe");
  const podium = $("repPodium");
  const around = $("repAround");
  const note = $("repNote");
  if (!me || !podium || !around || !note) return;
  const SEGMENTS = 12;
  let session = window.ZhidaoSession || null;
  let busy = false;

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "rating";
  const visible = () => {
    const panel = document.querySelector('[data-tab-panel="rating:season"]');
    return Boolean(panel && !panel.hidden);
  };

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  async function get(path) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
      throw new Error(typeof data.detail === "string" ? data.detail : "Рейтинг сейчас недоступен.");
    }
    return data;
  }

  function avatar(item, className) {
    const face = node("span", `${className} cosmetic-avatar`);
    if (item.frame) face.dataset.frame = item.frame;
    face.setAttribute("aria-hidden", "true");
    window.ZhidaoAvatar?.paint(face, item.display_name);
    return face;
  }

  function skeleton() {
    podium.replaceChildren(...[["second", 2], ["first", 1], ["third", 3]].map(([place, rank]) => {
      const slot = node("div", `podium-slot ${place}`);
      slot.append(node("span", "podium-avatar"), node("span", "podium-rank", String(rank)));
      return slot;
    }));
  }

  function drawPodium(leaders) {
    const places = [["second", 1], ["first", 0], ["third", 2]];
    podium.replaceChildren(...places.filter(([, index]) => leaders[index]).map(([place, index], order) => {
      const item = leaders[index];
      const slot = node("div", `podium-slot ${place}${item.is_you ? " is-you" : ""}`);
      slot.style.setProperty("--i", String(order));
      if (place === "first") slot.append(node("span", "podium-crown"));
      // Ступень постамента: место крупно на самой ступени (rep-polish.css).
      slot.append(avatar(item, "podium-avatar"), node("span", "podium-rank", String(item.rank)),
        node("b", "podium-name", item.display_name), node("small", "podium-rep", `${item.rep} REP`),
        node("span", "podium-step", String(item.rank)));
      return slot;
    }));
  }

  function drawAround(items) {
    around.replaceChildren(...items.map((item) => {
      const row = node("div", `board-row diary-row${item.is_you ? " is-you" : ""}`);
      const lines = node("span", "board-lines");
      const name = node("b", "diary-name", item.display_name);
      lines.append(name);
      if (item.is_you) lines.append(node("small", "diary-sub", "это ты"));
      row.append(node("span", "board-rank", String(item.rank).padStart(2, "0")), avatar(item, "board-avatar"), lines,
        node("span", "diary-value rep-value", String(item.rep)));
      return row;
    }));
  }

  const plural = (n, forms) => {
    const a = Math.abs(n) % 100;
    const b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b === 1) return forms[0];
    if (b > 1 && b < 5) return forms[1];
    return forms[2];
  };

  let baseline;
  let baselineKey = "";

  // Что изменилось с прошлого открытия на этом устройстве. Сервер ничего не присылает:
  // прошлые место и REP помнит само устройство, поэтому в первый раз сравнивать не с чем.
  function drawDelta(data) {
    let delta = $("repDelta");
    if (!delta) {
      delta = node("span", "rep-delta");
      delta.id = "repDelta";
      document.querySelector(".rep-me-place")?.append(delta);
    }
    const key = `zhidao.v4.rep.last.${session?.account?.id || "guest"}`;
    // Точка отсчёта -- то, что запомнено до открытия этой страницы. Экран перерисовывается
    // несколько раз за открытие; сравнивать надо с одним и тем же, а не с самим собой.
    if (baseline === undefined || baselineKey !== key) {
      baselineKey = key;
      try { baseline = JSON.parse(localStorage.getItem(key) || "null"); } catch (_) { baseline = null; }
    }
    const last = baseline;
    try { localStorage.setItem(key, JSON.stringify({ rank: data.me.rank, rep: data.me.rep })); } catch (_) { /* только до перезагрузки */ }
    delta.replaceChildren();
    delta.className = "rep-delta";
    delta.hidden = true;
    if (!last || typeof last.rank !== "number" || typeof last.rep !== "number") return 0;
    const places = last.rank - data.me.rank;
    const points = data.me.rep - last.rep;
    if (places > 0) delta.append(node("span", "is-up", `▲ на ${places} ${plural(places, ["место", "места", "мест"])} выше`));
    else if (places < 0) delta.append(node("span", "is-down", `▼ на ${-places} ${plural(places, ["место", "места", "мест"])} ниже`));
    if (points !== 0) delta.append(node("span", points > 0 ? "is-gain" : "is-down", `${points > 0 ? "+" : "−"}${Math.abs(points)} REP с прошлого раза`));
    delta.hidden = !delta.childElementCount;
    return places;
  }

  function drawMe(data) {
    me.hidden = !data.me;
    if (!data.me) return;
    me.dataset.tier = data.me.rank <= 3 ? String(data.me.rank) : "n";
    const moved = drawDelta(data);
    if (moved > 0) {
      me.classList.add("is-rankup");
      setTimeout(() => me.classList.remove("is-rankup"), 2200);
    }
    $("repRank").textContent = String(data.me.rank);
    $("repTotal").textContent = `из ${data.total}`;
    $("repPoints").textContent = String(data.me.rep);
    let ratio = 1;
    if (data.me.next_rep == null) {
      $("repNextLabel").textContent = "Ты первый в сезоне";
      $("repNextGap").textContent = "";
    } else {
      const gap = data.me.next_rep - data.me.rep;
      $("repNextLabel").textContent = `До ${data.me.rank - 1}-го места`;
      $("repNextGap").textContent = gap > 0 ? `${gap} REP` : "поровну — нужен ещё 1 REP";
      ratio = data.me.next_rep > 0 ? data.me.rep / data.me.next_rep : 0;
    }
    const lit = Math.max(0, Math.min(SEGMENTS, Math.round(ratio * SEGMENTS)));
    $("repProgress").replaceChildren(...Array.from({ length: SEGMENTS }, (_, i) => {
      const segment = node("i", i < lit ? "is-on" : null);
      segment.style.setProperty("--n", String(i));
      return segment;
    }));
  }

  function reset(text) {
    me.hidden = true;
    skeleton();
    around.replaceChildren();
    note.textContent = text;
    note.hidden = false;
  }

  async function load() {
    if (busy || !onScreen() || !visible()) return;
    if (!signedIn()) { reset("Войдите, чтобы увидеть рейтинг сезона."); return; }
    busy = true;
    try {
      const seasons = (await get("/api/v4/cases/context")).seasons || [];
      const pick = (test) => seasons.find((s) => test(s) && s.status === "active") || seasons.find(test) || null;
      const season = pick((s) => s.is_member) || pick((s) => s.can_manage);
      if (!season) { reset("Вас ещё не включили в сезон. Рейтинг появится после старта поездки."); return; }
      const data = await get(`/api/v4/seasons/${season.id}/rep/board`);
      drawMe(data);
      if (data.leaders.length) drawPodium(data.leaders); else skeleton();
      drawAround(data.around);
      note.textContent = !data.leaders.length ? "В сезоне пока нет участников."
        : data.me ? "" : "Своего места у организатора нет — видна только тройка лидеров.";
      note.hidden = !note.textContent;
    } catch (error) {
      reset(error.message);
    } finally {
      busy = false;
    }
  }

  window.addEventListener("zhidao:auth", (event) => { session = event.detail; load(); });
  window.addEventListener("zhidao:screen", (event) => { if (event.detail === "rating") load(); });
  window.addEventListener("zhidao:tab", (event) => {
    if (event.detail && event.detail.dataset.tabPanel === "rating:season") load();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
}());
