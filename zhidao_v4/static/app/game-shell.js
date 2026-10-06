"use strict";

/* Игра на весь экран (решение пользователя 2026-09-27: «игры в
   полноэкранном режиме … чтобы детям было удобно»).

   Любая игра, открытая из «Ивентов», занимает весь экран приложения: шапка,
   адресная строка, нижняя панель и строка состояния уходят, остаётся окно
   игры с узкой верхней полосой («‹ Игры», название, выход из комнаты).
   Системного полноэкранного режима у мини-приложения MAX нет — это
   полноэкранность внутри приложения, и работает она одинаково в MAX, в
   браузере телефона и на компьютере.

   Здесь же — то, что нужно ребёнку с телефоном в руке посреди игры:
   - MAX не закрывает приложение свайпом вниз, пока игра открыта, а во время
     идущего раунда ещё и переспрашивает перед закрытием;
   - вибрация на событиях игры (ZhidaoGameShell.haptic) — через мост MAX,
     а в браузере телефона через navigator.vibrate.

   Какая игра открыта, решает каталог (games-catalog.js); этот файл только
   следует за ним и ничего не отправляет на сервер. */

(function () {
  const root = document.documentElement;
  const bridge = () => (window.WebApp && window.WebApp.initData ? window.WebApp : null);
  const quiet = (promise) => { if (promise && typeof promise.catch === "function") promise.catch(() => {}); };

  let full = false;
  let openKey = null;   // какая игра открыта: "table", "zombie", "royale"…
  let live = false;
  // Модули игр опрашивают сервер и в фоне; событие или «идёт раунд» от игры,
  // которая сейчас не открыта, этот экран не касается.
  const mine = (key) => !key || key === openKey;

  function setSwipes(locked) {
    const app = bridge();
    if (!app) return;
    try {
      quiet(locked ? app.disableVerticalSwipes?.() : app.enableVerticalSwipes?.());
    } catch (_) { /* старый клиент MAX без этих методов */ }
  }

  function setClosingGuard(on) {
    const app = bridge();
    if (!app) return;
    try {
      if (on) app.enableClosingConfirmation?.();
      else app.disableClosingConfirmation?.();
    } catch (_) { /* не критично */ }
  }

  function setFull(key) {
    openKey = key || null;
    const next = Boolean(key);
    if (next) root.dataset.gameFull = key;
    else delete root.dataset.gameFull;
    if (next === full) return;
    full = next;
    setSwipes(full);
    if (!full && live) { live = false; setClosingGuard(false); }
  }

  /* Идёт ли раунд, в котором человек участвует: тогда закрытие MAX
     переспрашивает. Вызывают модули игр при смене статуса. */
  function setLive(on, key) {
    if (!mine(key)) return;
    const next = Boolean(on) && full;
    if (next === live) return;
    live = next;
    setClosingGuard(live);
  }

  /* Вибрация. Виды — по смыслу события, а не по силе:
     tap — лёгкий отклик на выбор; turn — твой ход / раунд начался;
     alert — с тобой что-то случилось (заразили, вывели, собрание);
     win / lose — итог. Выключенные анимации вибрацию не гасят: это не
     движение на экране, а сигнал, который ребёнок чувствует рукой. */
  const PATTERNS = { tap: 12, turn: [30, 60, 30], alert: [80, 60, 80, 60, 120], win: [40, 50, 40, 50, 160], lose: [200], stamp: 45, hard: [70, 40, 50] };
  function haptic(kind) {
    const app = bridge();
    const hf = app && app.HapticFeedback;
    try {
      if (hf) {
        if (kind === "tap") quiet(hf.selectionChanged());
        else if (kind === "turn") quiet(hf.impactOccurred("medium"));
        else if (kind === "alert") quiet(hf.notificationOccurred("warning"));
        else if (kind === "win") quiet(hf.notificationOccurred("success"));
        else if (kind === "lose") quiet(hf.notificationOccurred("error"));
        else if (kind === "stamp") quiet(hf.impactOccurred("heavy"));
        else if (kind === "hard") quiet(hf.notificationOccurred("warning"));
        return;
      }
    } catch (_) { /* падаем на navigator.vibrate */ }
    if (navigator.vibrate && PATTERNS[kind] !== undefined) {
      try { navigator.vibrate(PATTERNS[kind]); } catch (_) { /* вибрации нет */ }
    }
  }

  /* Звуки игр. Синтез WebAudio, как у наборов из магазина, — ни одной
     чужой записи. Звучат только в открытой игре и выключаются кнопкой в
     верхней полосе (выбор хранится на устройстве). Купленный набор остаётся
     голосом всего приложения; здесь — только события самой игры. */
  const SOUND_KEY = "zhidao.v4.game-sound";
  let soundOn = true;
  try { soundOn = localStorage.getItem(SOUND_KEY) !== "off"; } catch (_) { /* по умолчанию звук есть */ }
  const TUNES = {
    start: [[523, 0.08, "triangle"], [659, 0.08, "triangle"], [784, 0.1, "triangle"], [1047, 0.2, "sine"]],
    turn: [[880, 0.07, "sine"], [1175, 0.14, "sine"]],
    alert: [[466, 0.1, "square"], [0, 0.05], [466, 0.1, "square"], [349, 0.2, "sawtooth"]],
    tick: [[1318, 0.035, "sine"]],
    win: [[523, 0.1, "triangle"], [659, 0.1, "triangle"], [784, 0.1, "triangle"], [1047, 0.32, "sine"]],
    lose: [[392, 0.14, "triangle"], [330, 0.14, "triangle"], [262, 0.34, "sine"]],
  };
  /* Удар штампа: низкий «тум» с падающим тоном и короткий шлепок бумаги
     (шум через полосовой фильтр). «Задержано» -- ниже, тяжелее и с резким
     зуммером сверху. Задержка нужна, чтобы звук пришёл ровно в тот момент,
     когда анимированный штамп долетает до бумаги. */
  const STAMPS = {
    stamp: { from: 190, to: 62, body: 0.5, slap: 0.28, buzz: 0, zap: [500, 2600] },
    "stamp-hard": { from: 140, to: 44, body: 0.65, slap: 0.34, buzz: 196, zap: [2400, 300] },
  };
  function stamp(spec, delay) {
    const ctx = context();
    if (!ctx) return;
    const t = ctx.currentTime + 0.005 + delay;
    const osc = ctx.createOscillator();
    const body = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(spec.from, t);
    osc.frequency.exponentialRampToValueAtTime(spec.to, t + 0.13);
    body.gain.setValueAtTime(0.0001, t);
    body.gain.exponentialRampToValueAtTime(spec.body, t + 0.008);
    body.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    osc.connect(body).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.22);
    const length = Math.floor(ctx.sampleRate * 0.09);
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) data[i] = (Math.random() * 2 - 1) * (1 - i / length);
    const noise = ctx.createBufferSource();
    const band = ctx.createBiquadFilter();
    const slap = ctx.createGain();
    noise.buffer = buffer;
    band.type = "bandpass";
    band.frequency.value = 1900;
    band.Q.value = 0.9;
    slap.gain.setValueAtTime(spec.slap, t);
    slap.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    noise.connect(band).connect(slap).connect(ctx.destination);
    noise.start(t);
    if (spec.zap) {
      // Цифровой «зап»: пропущено -- звук идёт вверх, задержано -- вниз.
      const zap = ctx.createOscillator();
      const zapGain = ctx.createGain();
      zap.type = "sawtooth";
      zap.frequency.setValueAtTime(spec.zap[0], t);
      zap.frequency.exponentialRampToValueAtTime(spec.zap[1], t + 0.09);
      zapGain.gain.setValueAtTime(0.0001, t);
      zapGain.gain.exponentialRampToValueAtTime(0.05, t + 0.01);
      zapGain.gain.exponentialRampToValueAtTime(0.0001, t + 0.11);
      zap.connect(zapGain).connect(ctx.destination);
      zap.start(t);
      zap.stop(t + 0.13);
    }
    if (spec.buzz) {
      const buzz = ctx.createOscillator();
      const gain = ctx.createGain();
      buzz.type = "square";
      buzz.frequency.value = spec.buzz;
      gain.gain.setValueAtTime(0.0001, t + 0.05);
      gain.gain.exponentialRampToValueAtTime(0.08, t + 0.06);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.17);
      buzz.connect(gain).connect(ctx.destination);
      buzz.start(t + 0.05);
      buzz.stop(t + 0.19);
    }
  }

  let audio = null;
  function context() {
    if (!audio) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return null;
      audio = new Ctx();
    }
    if (audio.state === "suspended") audio.resume().catch(() => {});
    return audio;
  }
  // Телефон разрешает звук только после касания — будим контекст первым.
  document.addEventListener("pointerdown", () => { if (full && soundOn) context(); }, { passive: true });
  function tune(notes) {
    const ctx = context();
    if (!ctx) return;
    let at = ctx.currentTime + 0.01;
    for (const [freq, duration, wave] of notes) {
      if (freq) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = wave || "sine";
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.09, at + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
        osc.connect(gain).connect(ctx.destination);
        osc.start(at);
        osc.stop(at + duration + 0.02);
      }
      at += duration;
    }
  }

  /* Событие игры: звук и вибрация одним вызовом. Модули описывают, что
     случилось (start, turn, alert, tick, win, lose), а не как это звучит. */
  const HAPTIC_OF = { start: "turn", turn: "turn", alert: "alert", win: "win", lose: "lose", stamp: "stamp", "stamp-hard": "hard" };
  const motionOn = () => root.dataset.motion === "full" && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const openWindow = () => document.querySelector('[data-screen="games"] > .case-window[data-catalog]:not([data-catalog-hidden]):not([hidden])');

  /* Видимая сторона события: крупная плашка посреди экрана («Раунд 2»,
     «Ваш ход, капитан», «Вас обвиняют!») в цвете игры, подсветка краёв на
     «твой ход», красная вспышка с толчком на тревоге. Плашка сама уходит
     через секунду и не мешает нажимать — под ней можно играть. */
  function show(name, title, sub) {
    if (!motionOn()) return;
    const win = openWindow();
    if (!win) return;
    // Края окна — через Web Animations, а не классом: смена CSS-анимации
    // окна заново проиграла бы его разворачивание на весь экран.
    const glow = getComputedStyle(win).getPropertyValue("--game-light").trim() || "#2ec2ea";
    const none = "inset 0 0 0 0 rgba(0, 0, 0, 0)";
    if (name === "turn" || name === "start") {
      win.animate([{ boxShadow: none }, { boxShadow: `inset 0 0 0 6px ${glow}, inset 0 0 40px ${glow}`, offset: .35 }, { boxShadow: none }],
        { duration: 900, easing: "ease-out" });
    } else if (name === "alert") {
      win.animate([
        { boxShadow: none, transform: "none" },
        { boxShadow: "inset 0 0 0 8px #ff3b30, inset 0 0 60px rgba(255, 59, 48, .6)", transform: "translateX(-6px)", offset: .15 },
        { transform: "translateX(6px)", offset: .3 },
        { transform: "translateX(-4px)", offset: .45 },
        { transform: "translateX(3px)", offset: .6 },
        { boxShadow: none, transform: "none" },
      ], { duration: 620, easing: "ease-out" });
    }
    if (!title) return;
    win.querySelector(".game-callout")?.remove();
    const callout = document.createElement("div");
    callout.className = `game-callout is-${name}`;
    callout.setAttribute("aria-hidden", "true");
    const plate = document.createElement("div");
    const b = document.createElement("b");
    b.textContent = title;
    plate.append(b);
    if (sub) {
      const small = document.createElement("small");
      small.textContent = sub;
      plate.append(small);
    }
    callout.append(plate);
    win.append(callout);
    setTimeout(() => callout.remove(), 1700);
  }

  function cue(event, key) {
    if (!full || !event || !mine(key)) return;
    const { name, title, sub } = typeof event === "string" ? { name: event } : event;
    if (HAPTIC_OF[name]) haptic(HAPTIC_OF[name]);
    show(name, title, sub);
    if (STAMPS[name]) {
      if (soundOn && !document.hidden) {
        try { stamp(STAMPS[name], motionOn() ? 0.11 : 0); } catch (_) { /* без звука игра не ломается */ }
      }
      return;
    }
    if (!soundOn || !TUNES[name] || document.hidden) return;
    // Победу купленный набор уже сыграл (games.js) — второй мелодии не нужно.
    if (name === "win" && window.ZhidaoSounds?.hasPack?.()) return;
    try { tune(TUNES[name]); } catch (_) { /* без звука игра не ломается */ }
  }

  // Кнопка звука — рядом с «‹ Все игры» в верхней полосе игры.
  const back = document.getElementById("gamesBack");
  if (back) {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-secondary game-sound-toggle";
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const speaker = document.createElementNS(svgNS, "path");
    speaker.setAttribute("d", "M4 9h4l5-4v14l-5-4H4z");
    const waves = document.createElementNS(svgNS, "path");
    waves.setAttribute("class", "game-sound-waves");
    waves.setAttribute("d", "M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12");
    const cross = document.createElementNS(svgNS, "path");
    cross.setAttribute("class", "game-sound-cross");
    cross.setAttribute("d", "M16 9l6 6M22 9l-6 6");
    svg.append(speaker, waves, cross);
    toggle.append(svg);
    const paint = () => {
      toggle.setAttribute("aria-pressed", String(soundOn));
      toggle.setAttribute("aria-label", soundOn ? "Звук игры включён. Выключить" : "Звук игры выключен. Включить");
      toggle.dataset.on = soundOn ? "1" : "0";
    };
    toggle.addEventListener("click", () => {
      soundOn = !soundOn;
      try { localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off"); } catch (_) { /* выбор живёт до перезагрузки */ }
      paint();
      if (soundOn) cue("turn");
    });
    paint();
    back.append(toggle);
  }

  window.addEventListener("zhidao:game-open", (event) => setFull(event.detail || null));
  window.addEventListener("zhidao:screen", (event) => { if (event.detail !== "games") setFull(null); });

  /* Главное действие — вниз, под палец. Модуль большой игры помечает его
     .game-actionbar и после отрисовки зовёт settle(body): полосы уезжают в
     конец окна (там их прилепит game-shell.css), а строка с ответом
     сервера («Код — шесть цифр…») встаёт в полосу над кнопкой — рядом с
     тем, что её вызвало. */
  function settle(body) {
    if (!body) return;
    const bars = Array.from(body.querySelectorAll(".game-actionbar"));
    if (!bars.length) return;
    bars.forEach((bar) => body.append(bar));
    const message = Array.from(body.children).find((el) => el.classList.contains("case-message"));
    if (message && message.textContent.trim()) bars[0].prepend(message);
  }

  window.ZhidaoGameShell = Object.freeze({
    haptic,
    cue,
    settle,
    setLive,
    isFull: () => full,
  });
})();
