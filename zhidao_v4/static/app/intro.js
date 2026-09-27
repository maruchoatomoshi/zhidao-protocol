"use strict";

/* Заставка при запуске — пара к intro.css.

   Подключается в <head> обычным (не defer) скриптом: решение «играть или
   нет» принимается до первой отрисовки, иначе приложение мелькнуло бы под
   заставкой. Решение — атрибут data-intro на <html> (inline-стили запрещены
   политикой безопасности, атрибуты — нет):

   - "play" — показать: один раз за запуск (sessionStorage), только при
     включённых анимациях и без системного ограничения движения;
   - нет атрибута — заставки нет, приложение открывается сразу.

   Сцена ждёт, пока загрузятся слои (не дольше LOAD_LIMIT_MS): если сеть
   медленная, заставка тихо уступает приложению, а не держит его. Касание
   или клавиша пропускают. В конце логотип улетает туда, где он виден в
   приложении: в шапку или на экран входа. */

(function () {
  const SEEN_KEY = "zhidao.v4.intro-seen";
  const LOAD_LIMIT_MS = 1500;
  const PLAY_MS = 2350;      // когда начинается уход — после блика и подмены слоёв
  const LEAVE_MS = 560;
  const root = document.documentElement;

  function shouldPlay() {
    try {
      if (sessionStorage.getItem(SEEN_KEY)) return false;
      if (localStorage.getItem("zhidao.v4.motion") === "off") return false;
    } catch (err) {
      /* Хранилище недоступно — показать можно, запомнить нельзя. */
    }
    return !matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  if (!shouldPlay()) {
    // Картинки заставки прописаны как data-src и без неё не качаются;
    // сама разметка просто уходит.
    const drop = () => document.getElementById("appIntro")?.remove();
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", drop, { once: true });
    else drop();
    return;
  }
  root.dataset.intro = "play";
  try { sessionStorage.setItem(SEEN_KEY, "1"); } catch (err) { /* см. выше */ }

  // Слои начинают грузиться сразу, ещё до разбора <body>, — и только когда
  // заставка действительно будет играть: иначе это лишние 260 КБ на запуск.
  for (const name of ["plate", "dragon", "text", "pix", "glass", "logo"]) {
    const link = document.createElement("link");
    link.rel = "preload";
    link.as = "image";
    link.type = "image/webp";
    link.href = `./assets/intro/${name}.webp`;
    document.head.append(link);
  }

  function visible(el) {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > innerHeight) return null;
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return hit && (hit === el || el.contains(hit) || hit.closest(".app-intro")) ? r : null;
  }

  // Куда лететь: логотип на экране входа, пока он открыт, иначе — в шапке.
  function target() {
    const gate = document.getElementById("authGate");
    const onGate = gate && !gate.hidden && getComputedStyle(gate).display !== "none";
    return visible(onGate ? gate.querySelector(".auth-logo") : document.querySelector(".app-header .brand-logo"));
  }

  function start() {
    const intro = document.getElementById("appIntro");
    if (!intro) { delete root.dataset.intro; return; }
    const stage = intro.querySelector(".intro-stage");
    let done = false, leaveTimer = 0;

    function finish() {
      if (done) return;
      done = true;
      intro.remove();
      delete root.dataset.intro;
    }

    function leave(fast) {
      if (intro.classList.contains("is-leaving")) return;
      clearTimeout(leaveTimer);
      intro.classList.add("is-leaving");
      const from = stage.getBoundingClientRect();
      const to = !fast && target();
      let keyframes;
      if (to) {
        const dx = to.left + to.width / 2 - (from.left + from.width / 2);
        const dy = to.top + to.height / 2 - (from.top + from.height / 2);
        const k = to.width / from.width;
        keyframes = [
          { transform: "none", opacity: 1 },
          { transform: `translate(${dx * 0.55}px, ${dy * 0.45}px) scale(${0.5 + k * 0.5})`, opacity: 1, offset: 0.55 },
          { transform: `translate(${dx}px, ${dy}px) scale(${k})`, opacity: 1, offset: 0.92 },
          { transform: `translate(${dx}px, ${dy}px) scale(${k})`, opacity: 0 },
        ];
      } else {
        keyframes = [{ transform: "none", opacity: 1 }, { transform: "scale(.86)", opacity: 0 }];
      }
      const flight = stage.animate(keyframes, {
        duration: fast ? 260 : LEAVE_MS, easing: "cubic-bezier(.55, 0, .25, 1)", fill: "forwards",
      });
      flight.finished.then(finish, finish);
      setTimeout(finish, (fast ? 260 : LEAVE_MS) + 400);   // страховка, если анимация не отчиталась
    }

    function run() {
      if (done || intro.classList.contains("is-running")) return;
      intro.classList.add("is-running");
      leaveTimer = setTimeout(() => leave(false), PLAY_MS);
    }

    intro.addEventListener("pointerdown", () => leave(true));
    addEventListener("keydown", () => leave(true), { once: true });

    // Ждём слои: заставка с недогруженными слоями хуже, чем её отсутствие.
    const images = [...intro.querySelectorAll("img[data-src]")];
    images.forEach((img) => { img.src = img.dataset.src; });
    const ready = Promise.all(images.map((img) => (img.decode ? img.decode() : Promise.resolve()).catch(() => null)));
    const limit = new Promise((resolve) => setTimeout(() => resolve("late"), LOAD_LIMIT_MS));
    Promise.race([ready.then(() => "ok"), limit]).then((result) => {
      if (result === "ok") run();
      else leave(true);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
