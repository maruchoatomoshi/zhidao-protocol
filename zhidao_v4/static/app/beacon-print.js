"use strict";

/* Таблички меток на печать. Матрицу QR считает сервер проверенной
   библиотекой (zhidao_v4/vendor/qrcodegen.py); здесь она только рисуется
   квадратами SVG — без стилей в разметке (политика безопасности). */

(function () {
  const NS = "http://www.w3.org/2000/svg";
  const QUIET = 4;   // белое поле вокруг QR по стандарту — без него сканер путается

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function qrSvg(matrix, label) {
    const n = matrix.length;
    const size = n + QUIET * 2;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("class", "label-qr");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
    svg.setAttribute("shape-rendering", "crispEdges");
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("width", size);
    bg.setAttribute("height", size);
    bg.setAttribute("fill", "#fff");
    svg.append(bg);
    // Одна строка пути на весь код: тысяча <rect> печатаются медленно.
    let d = "";
    matrix.forEach((row, y) => {
      for (let x = 0; x < row.length; x += 1) {
        if (row[x] === "1") d += `M${x + QUIET} ${y + QUIET}h1v1h-1z`;
      }
    });
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "#000");
    svg.append(path);
    return svg;
  }

  function label(item) {
    const card = node("article", "label");
    const top = node("div", "label-top");
    top.append(node("b", "", "ZHIDAO PROTOCOL"), node("span", "", "知道 · игровая метка"));
    const names = node("div", "label-names");
    names.append(node("strong", "", item.name_ru || item.point));
    if (item.name_zh) names.append(node("span", "label-zh", item.name_zh));
    const how = node("p", "label-how",
      "Сделайте ход у этой точки в ZHIDAO — приложение попросит отсканировать метку. Засчитывается только рядом с табличкой.");
    const code = node("p", "label-code");
    code.append(node("span", "", "Код, если камера не читает: "), node("b", "", item.code));
    const keep = node("div", "label-keep");
    keep.append(
      node("p", "", "Учебная игра. Пожалуйста, не снимайте и не переносите табличку."),
      node("p", "label-zh", "教学游戏标记，请勿移除。"),
      node("p", "", "Educational game marker — please do not remove."));
    const side = node("div", "label-side");
    side.append(code, how, keep);
    card.append(top, names, qrSvg(item.qr, `QR метки «${item.name_ru || item.point}»`), side);
    return card;
  }

  async function load() {
    const status = document.getElementById("printStatus");
    try {
      const response = await fetch("/api/v4/beacons/labels", { credentials: "same-origin", cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Нет доступа.");
      const labels = body.labels || [];
      document.getElementById("labels").replaceChildren(...labels.map(label));
      status.textContent = labels.length
        ? `${labels.length} табличек · по две на лист A4. Китайская строка — черновик: проверьте у знающего язык до печати.`
        : "Меток ещё нет: выпустите их на экране карты.";
      document.getElementById("printNow").disabled = !labels.length;
    } catch (error) {
      status.textContent = `${error.message} Войдите в ZHIDAO как вожатый в этом же браузере.`;
    }
  }

  document.getElementById("printNow").addEventListener("click", () => window.print());
  load();
})();
