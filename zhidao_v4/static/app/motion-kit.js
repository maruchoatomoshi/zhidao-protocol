"use strict";

/* Пружины и хореография — приёмы Motion (Framer Motion) без React.

   Решение пользователя 2026-09-27: взять из навыка motion-framer его
   приёмы — пружинную физику, варианты, каскад (stagger), жест нажатия
   (whileTap), анимацию ухода (AnimatePresence) и общий элемент (layoutId) —
   и сделать их на Web Animations API, без библиотеки и без фреймворка
   (V4 — чистые HTML/CSS/JS, CLAUDE.md).

   Пружина считается настоящим уравнением затухающего осциллятора
   (жёсткость, затухание, масса, начальная скорость) и превращается в
   CSS-кривую linear(…) из выборки точек: её понимают и CSS-анимации, и
   element.animate(). Кривая выходит за 1 — это и есть отскок; длительность
   берётся из времени, когда пружина успокоилась. В старом WebView без
   linear() вместо пружины стоит близкая кубическая кривая.

   Кривые выставляются переменными на <html> (--spring-pop и
   --spring-pop-ms и т. д.), поэтому CSS пишет
   `animation: x var(--spring-pop-ms, 420ms) var(--spring-pop, …)`.
   Файл грузится в <head> до intro.js: заставка тоже на пружинах.

   Всё — только косметика: ни запроса, ни решения за сервер. При
   выключенных анимациях, системном ограничении движения и свёрнутом
   приложении animate() ничего не запускает, enter() оставляет элементы как
   есть, exit() сразу выполняет обещание, жесты молчат. */

(function () {
  const root = document.documentElement;
  const reducedMedia = matchMedia("(prefers-reduced-motion: reduce)");
  const supportsLinear = window.CSS && CSS.supports && CSS.supports("animation-timing-function", "linear(0, 1)");

  function motionOn() {
    if (reducedMedia.matches || document.hidden) return false;
    const set = root.dataset.motion;
    if (set) return set === "full";
    try { return localStorage.getItem("zhidao.v4.motion") !== "off"; } catch (err) { return true; }
  }

  /* --- пружина ------------------------------------------------------------ */

  // Положение пружины из 0 в 1 во времени t (с): затухающий осциллятор.
  function solver({ stiffness = 100, damping = 10, mass = 1, velocity = 0 }) {
    const w0 = Math.sqrt(stiffness / mass);
    const zeta = damping / (2 * Math.sqrt(stiffness * mass));
    const v0 = -velocity;
    if (zeta < 1) {
      const wd = w0 * Math.sqrt(1 - zeta * zeta);
      return (t) => 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + ((zeta * w0 + v0) / wd) * Math.sin(wd * t));
    }
    if (zeta === 1) return (t) => 1 - Math.exp(-w0 * t) * (1 + (w0 + v0) * t);
    const r1 = -w0 * (zeta - Math.sqrt(zeta * zeta - 1));
    const r2 = -w0 * (zeta + Math.sqrt(zeta * zeta - 1));
    const c2 = (-v0 - r1) / (r2 - r1);
    const c1 = -1 - c2;
    return (t) => 1 + c1 * Math.exp(r1 * t) + c2 * Math.exp(r2 * t);
  }

  const cache = new Map();
  function spring(options) {
    const opts = typeof options === "string" ? PRESETS[options] : options || PRESETS.gentle;
    const key = JSON.stringify(opts);
    if (cache.has(key)) return cache.get(key);
    const x = solver(opts);
    // Длительность — пока пружина не успокоилась: отклонение меньше 0,1 %
    // и держится так хотя бы 50 мс подряд.
    const step = 1 / 240;
    let t = 0, calm = 0, end = 0;
    while (t < 4) {
      t += step;
      if (Math.abs(1 - x(t)) < 0.001) { calm += step; if (calm >= 0.05) { end = t - calm; break; } } else calm = 0;
    }
    if (!end) end = 4;
    const duration = Math.max(120, Math.round(end * 1000));
    const points = Math.min(80, Math.max(24, Math.round(duration / 12)));
    const samples = [];
    let overshoots = false;
    for (let i = 0; i <= points; i += 1) {
      const v = i === points ? 1 : x((i / points) * end);
      if (v > 1.001) overshoots = true;
      samples.push(Number(v.toFixed(4)));
    }
    const easing = supportsLinear ? `linear(${samples.join(", ")})`
      : overshoots ? "cubic-bezier(.34, 1.56, .64, 1)" : "cubic-bezier(.2, .75, .22, 1)";
    const result = { easing, duration };
    cache.set(key, result);
    return result;
  }

  // Пресеты навыка (gentle/wobbly/stiff/slow) и два своих: pop — появление
  // с заметным отскоком, press — возврат кнопки после нажатия.
  const PRESETS = {
    gentle: { stiffness: 100, damping: 20 },
    wobbly: { stiffness: 200, damping: 10 },
    stiff: { stiffness: 400, damping: 30 },
    slow: { stiffness: 50, damping: 20 },
    pop: { stiffness: 320, damping: 18 },
    press: { stiffness: 600, damping: 16 },
    glide: { stiffness: 170, damping: 24 },
  };
  for (const name of Object.keys(PRESETS)) {
    const s = spring(name);
    root.style.setProperty(`--spring-${name}`, s.easing);
    root.style.setProperty(`--spring-${name}-ms`, `${s.duration}ms`);
  }

  /* --- варианты, каскад, уход ------------------------------------------ */

  // Состояния «до» для enter() и «после» для exit() — как variants в Motion.
  // Конечное состояние всегда естественное (none), поэтому после анимации
  // элемент остаётся тем, чем его сделал CSS.
  const VARIANTS = {
    rise: { opacity: 0, translate: "0 14px" },
    drop: { opacity: 0, translate: "0 -18px" },
    pop: { opacity: 0, scale: ".82" },
    fade: { opacity: 0 },
    left: { opacity: 0, translate: "-18px 0" },
    right: { opacity: 0, translate: "18px 0" },
    flip: { opacity: 0, transform: "perspective(700px) rotateX(-70deg)" },
  };
  const REST = { opacity: 1, translate: "0 0", scale: "1", transform: "none" };

  function frames(from) {
    const to = {};
    for (const prop of Object.keys(from)) to[prop] = REST[prop];
    return [from, to];
  }

  function animate(el, keyframes, { spring: name = "gentle", delay = 0, duration, easing, fill = "backwards", composite } = {}) {
    if (!el || !motionOn() || !el.animate) return null;
    const s = spring(name);
    return el.animate(keyframes, {
      duration: duration || s.duration, easing: easing || s.easing, delay, fill, ...(composite ? { composite } : {}),
    });
  }

  // Каскад: задержка i-го элемента. Как stagger() в Motion, с потолком,
  // чтобы длинный список не заставлял ждать последнюю строку.
  function stagger(index, step = 40, max = 320) {
    return Math.min(index * step, max);
  }

  function enter(elements, variant = "rise", { spring: name = "pop", step = 40, delay = 0, max } = {}) {
    const list = elements instanceof Element ? [elements] : [...(elements || [])];
    const from = VARIANTS[variant] || variant;
    return list.map((el, i) => animate(el, frames(from), { spring: name, delay: delay + stagger(i, step, max) }));
  }

  // Уход: обещание выполняется, когда элемент доиграл (или сразу, если
  // анимации выключены). Как exit у AnimatePresence — снимать/прятать
  // элемент вызывающий код решает сам, уже после.
  function exit(el, variant = "fade", { duration = 180, easing = "cubic-bezier(.4, 0, 1, 1)" } = {}) {
    const to = VARIANTS[variant] || variant;
    const a = animate(el, [frames(to)[1], to], { duration, easing, fill: "forwards" });
    return a ? a.finished.catch(() => null) : Promise.resolve();
  }

  // Общий элемент (layoutId): запомнить место, изменить разметку, и
  // элемент пружиной доезжает со старого места на новое (FLIP).
  function flip(el, mutate, { spring: name = "glide" } = {}) {
    if (!el) { mutate(); return null; }
    const first = el.getBoundingClientRect();
    mutate();
    const last = el.getBoundingClientRect();
    const dx = first.left - last.left, dy = first.top - last.top;
    const sx = last.width ? first.width / last.width : 1, sy = last.height ? first.height / last.height : 1;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01) return null;
    return animate(el, [
      { transformOrigin: "0 0", transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` },
      { transformOrigin: "0 0", transform: "none" },
    ], { spring: name });
  }

  /* --- жест нажатия (whileTap) ----------------------------------------- */

  const PRESSABLE = [
    "button:not(:disabled)", "a.btn", "[data-press]", ".catalog-tile", ".hub-tile",
    ".game-card", ".podium-slot", ".implant-card", ".shop-item", ".case-item",
  ].join(",");
  const pressed = new Map();

  function pressDepth(el) {
    const r = el.getBoundingClientRect();
    // Маленькая кнопка проседает сильнее, большая карточка — едва: глазу
    // одинаково заметно, а крупный блок не «прыгает».
    return 1 - Math.min(0.05, 10 / Math.max(r.width, r.height, 1));
  }

  function release(el) {
    const was = pressed.get(el);
    if (!was) return;
    pressed.delete(el);
    const current = getComputedStyle(el).scale;
    was.cancel();
    const from = current && current !== "none" ? current : String(was.depth);
    const s = spring("press");
    el.animate([{ scale: from }, { scale: "1" }], { duration: s.duration, easing: s.easing });
  }

  function bindPress() {
    document.addEventListener("pointerdown", (event) => {
      if (!motionOn() || event.button > 0) return;
      const el = event.target.closest(PRESSABLE);
      if (!el || el.closest("[data-no-press], .app-intro, input, select, textarea, .campus-map-svg")) return;
      const depth = pressDepth(el);
      const a = el.animate([{ scale: "1" }, { scale: String(depth) }],
        { duration: 110, easing: "cubic-bezier(.3, 0, .5, 1)", fill: "forwards" });
      a.depth = depth;
      pressed.get(el)?.cancel();
      pressed.set(el, a);
    }, { passive: true });
    for (const type of ["pointerup", "pointercancel", "dragstart"]) {
      document.addEventListener(type, () => { [...pressed.keys()].forEach(release); }, { passive: true });
    }
    // Палец увели с кнопки — она отпускается сразу, как в Motion.
    document.addEventListener("pointerleave", (event) => { if (pressed.has(event.target)) release(event.target); }, true);
  }

  /* --- наведение мышью (whileHover) --------------------------------------
     Только настоящая мышь: на телефоне «наведения» нет, а залипший подъём
     после касания выглядел бы как ошибка. Через Web Animations, а не CSS:
     у кнопок уже есть свои переходы цвета, и их нельзя перебить. */
  const HOVERABLE = ".btn:not(:disabled), .catalog-tile, .hub-tile, .game-card, .podium-slot";
  const lifted = new Map();

  function lift(el, up) {
    const was = lifted.get(el);
    const from = was ? getComputedStyle(el).translate : "0 0";
    was?.cancel();
    const s = spring(up ? "stiff" : "gentle");
    const a = el.animate([{ translate: from === "none" ? "0 0" : from }, { translate: up ? "0 -2px" : "0 0" }],
      { duration: s.duration, easing: s.easing, fill: up ? "forwards" : "none" });
    if (up) lifted.set(el, a); else lifted.delete(el);
  }

  function bindHover() {
    document.addEventListener("pointerover", (event) => {
      if (event.pointerType !== "mouse" || !motionOn()) return;
      const el = event.target.closest(HOVERABLE);
      if (el && !lifted.has(el) && !el.closest("[data-no-press], .app-intro")) lift(el, true);
    });
    document.addEventListener("pointerout", (event) => {
      if (event.pointerType !== "mouse") return;
      const el = event.target.closest(HOVERABLE);
      if (el && lifted.has(el) && !el.contains(event.relatedTarget)) lift(el, false);
    });
  }

  /* --- уход экрана (AnimatePresence для экранов) ------------------------- */

  // showScreen прячет прежний экран сразу и синхронно — код вокруг на это
  // рассчитывает. Поэтому уходит не сам экран, а его снимок: копия без id и
  // без доступа (inert), поверх на своём прежнем месте, растворяется и
  // исчезает. Новый экран в это время собирается своими панелями.
  function leaveScreen(prev, rect) {
    if (!prev || !rect || !motionOn() || rect.height < 20) return;
    const ghost = prev.cloneNode(true);
    ghost.querySelectorAll("[id]").forEach((n) => n.removeAttribute("id"));
    ghost.removeAttribute("id");
    ghost.hidden = false;
    ghost.inert = true;
    ghost.setAttribute("aria-hidden", "true");
    ghost.classList.add("screen-ghost");
    ghost.classList.remove("active");
    ghost.style.setProperty("--ghost-top", `${rect.top}px`);
    ghost.style.setProperty("--ghost-left", `${rect.left}px`);
    ghost.style.setProperty("--ghost-width", `${rect.width}px`);
    prev.after(ghost);
    const a = ghost.animate([{ opacity: 1, translate: "0 0", scale: "1" }, { opacity: 0, translate: "0 -10px", scale: ".985" }],
      { duration: 200, easing: "cubic-bezier(.4, 0, 1, 1)", fill: "forwards" });
    const drop = () => ghost.remove();
    a.finished.then(drop, drop);
    setTimeout(drop, 600);
  }

  function ready() {
    bindPress();
    bindHover();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready, { once: true });
  else ready();

  window.ZhidaoKit = Object.freeze({
    spring, presets: PRESETS, variants: VARIANTS, on: motionOn,
    animate, enter, exit, stagger, flip, leaveScreen,
  });
})();
