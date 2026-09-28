"use strict";

/* Метки на кампусе — панель вожатого на экране карты (сервер: beacons.py).

   Порядок работы (V4_GAMES.md §3.7):
   1. «Выпустить метки» — у точек появляются коды;
   2. «Печать табличек» — страница beacon-print.html, печатают с компьютера;
   3. у каждой таблички на месте — «Установить метку здесь»: скан таблички с
      точным GPS; это и есть подтверждение точки;
   4. если метку сорвали, перевесили или код утёк — «Перевыпустить»: старая
      табличка перестаёт действовать, печатается и вешается новая.

   Панель видна только тому, кому сервер отдал статус (права — на сервере). */

(function () {
  const panel = document.getElementById("beaconPanel");
  if (!panel) return;
  let state = null;
  let busy = false;
  let armed = "";
  let note = "";

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function csrf() {
    const cookie = document.cookie.split("; ").find((v) => v.startsWith("zhidao_v4_csrf="));
    return cookie ? decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) : "";
  }

  async function api(path, options = {}) {
    const init = { method: options.method || "GET", credentials: "same-origin", cache: "no-store",
      headers: { Accept: "application/json" } };
    if (init.method === "POST") {
      init.headers["Content-Type"] = "application/json";
      init.headers["X-CSRF-Token"] = csrf();
      if (options.key) init.headers["X-Idempotency-Key"] = options.key;
      init.body = JSON.stringify(options.body || {});
    }
    const response = await fetch(path, init);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof body.detail === "string" ? body.detail : "Запрос отклонён.");
      error.status = response.status;
      throw error;
    }
    return body;
  }

  const key = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/-/g, "");

  async function load() {
    try {
      state = await api("/api/v4/beacons");
    } catch (_) {
      state = null;   // не штат или нет сезона — панели нет
    }
    draw();
  }

  function when(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  async function act(fn) {
    if (busy) return;
    busy = true;
    draw();
    try {
      note = await fn();
    } catch (error) {
      if (!error.cancelled) note = error.message;
    } finally {
      busy = false;
      armed = "";
      await load();
    }
  }

  function issue(points, label) {
    return act(async () => {
      await api("/api/v4/beacons/issue", { method: "POST", key: key(), body: { points } });
      return `${label}. Распечатайте таблички и повесьте их на места`;
    });
  }

  function install(point) {
    return act(async () => {
      note = "Сканируйте табличку… для установки нужна точность до " + state.install_accuracy_m + " м";
      draw();
      const text = await window.ZhidaoBeacon.read(point.name_ru);
      const coords = await window.ZhidaoBeacon.position();
      const result = await api("/api/v4/beacons/install", {
        method: "POST", body: { text, lat: coords.latitude, lon: coords.longitude, accuracy_m: coords.accuracy },
      });
      window.dispatchEvent(new Event("zhidao:beacons-changed"));
      return `Метка «${result.name_ru}» установлена · ${result.offset_m} м от объекта на карте`;
    });
  }

  function draw() {
    if (!state) { panel.hidden = true; return; }
    panel.hidden = false;
    const head = node("div", "beacon-head");
    head.append(node("h2", "", "Метки на кампусе"), node("span", "beacon-cn", "标记"));
    const issued = state.points.filter((p) => p.issued).length;
    const installedCount = state.points.filter((p) => p.installed).length;
    const lead = node("p", "beacon-lead",
      `Выпущено ${issued} из ${state.points.length}, висят ${installedCount}. Ход у точки с меткой — только сканом таблички в ${state.radius_m} м от неё.`);
    const tools = node("div", "beacon-tools");
    const missing = state.points.filter((p) => !p.issued).map((p) => p.point);
    if (missing.length) {
      const b = node("button", "btn btn-primary", `Выпустить метки (${missing.length})`);
      b.type = "button";
      b.disabled = busy;
      b.addEventListener("click", () => issue(missing, `Выпущено меток: ${missing.length}`));
      tools.append(b);
    }
    if (issued) {
      const print = node("a", "btn btn-secondary", "Печать табличек");
      print.href = "./beacon-print.html";
      print.target = "_blank";
      print.rel = "noopener";
      tools.append(print);
    }
    const list = node("ul", "beacon-list");
    for (const p of state.points) {
      const li = node("li", `beacon-row${p.installed ? " is-installed" : p.issued ? " is-issued" : ""}`);
      const title = node("div", "beacon-name");
      title.append(node("b", "", p.name_ru || p.point));
      if (p.name_zh) title.append(node("span", "", p.name_zh));
      const stateText = p.installed ? `висит с ${when(p.installed_at)}` : p.issued ? "выпущена, не установлена" : "нет метки";
      li.append(title, node("span", "beacon-state", stateText));
      if (p.far_scans) {
        li.append(node("p", "beacon-alert",
          `Сканировали далеко от места: ${p.far_scans} раз, последний — ${when(p.far_last_at)}. Проверьте табличку: её могли перевесить или сфотографировать.`));
      }
      const row = node("div", "beacon-row-actions");
      if (p.issued) {
        const put = node("button", "btn btn-secondary", p.installed ? "Переустановить здесь" : "Установить метку здесь");
        put.type = "button";
        put.disabled = busy;
        put.addEventListener("click", () => install(p));
        row.append(put);
        const again = node("button", "btn btn-secondary", armed === p.point ? "Точно? Старая табличка перестанет работать" : "Перевыпустить");
        again.type = "button";
        again.disabled = busy;
        again.addEventListener("click", () => {
          if (armed !== p.point) { armed = p.point; draw(); return; }
          issue([p.point], `Метка «${p.name_ru || p.point}» перевыпущена`);
        });
        row.append(again);
      }
      if (row.childElementCount) li.append(row);
      list.append(li);
    }
    panel.replaceChildren(head, lead, tools, list, node("p", "case-message beacon-note", note));
  }

  window.addEventListener("zhidao:screen", (event) => { if (event.detail === "campus-map") load(); });
  window.addEventListener("zhidao:auth", () => { state = null; draw(); });
})();
