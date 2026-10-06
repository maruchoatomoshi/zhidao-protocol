"use strict";

/* Главная: баннер «Окно в Хайнань» следит за временем на острове.

   Часы Хайнаня -- это пояс Asia/Shanghai (UTC+8, без перехода на летнее время),
   не пояс телефона: человек в Москве или в самолёте видит тот день, который
   сейчас за окном кампуса. Меняются только оформление (небо: утро, день, вечер,
   ночь), приветствие в заголовке и строка «координаты · время». Данных с сервера
   нет, ничего не выдумано. */

(function () {
  const card = document.querySelector(".journey-card");
  const title = document.getElementById("scheduleTitle");
  if (!card) return;
  const index = card.querySelector(".journey-index span");
  const COORDS = index ? index.textContent.trim() : "";

  const sky = document.createElement("span");
  sky.className = "journey-sky";
  sky.setAttribute("aria-hidden", "true");
  card.prepend(sky);

  const HELLO = { dawn: "Доброе утро", day: "Добрый день", evening: "Добрый вечер", night: "Доброй ночи" };

  function hainanTime() {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date());
      return { h: Number(parts.find((p) => p.type === "hour").value) % 24, m: Number(parts.find((p) => p.type === "minute").value) };
    } catch (_) {
      const shifted = new Date(Date.now() + (new Date().getTimezoneOffset() + 480) * 60000);
      return { h: shifted.getHours(), m: shifted.getMinutes() };
    }
  }

  const phaseOf = (h, m) => {
    const t = h + m / 60;
    if (t >= 5 && t < 8) return "dawn";
    if (t >= 8 && t < 17) return "day";
    if (t >= 17 && t < 19.5) return "evening";
    return "night";
  };

  let lastPhase = "";
  function paint() {
    const { h, m } = hainanTime();
    const phase = phaseOf(h, m);
    if (phase !== lastPhase) {
      lastPhase = phase;
      card.dataset.phase = phase;
      if (title) {
        const br = document.createElement("br");
        title.replaceChildren(document.createTextNode(`${HELLO[phase]},`), br, document.createTextNode("путешественник"));
      }
    }
    if (index) index.textContent = `${COORDS} · ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")} 海南`;
  }

  paint();
  setInterval(paint, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) paint(); });
})();
