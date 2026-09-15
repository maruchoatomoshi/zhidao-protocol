"use strict";

/* Интернет нулевых поверх приложения (V4_DESIGN.md, «Интернет нулевых»).

   Решение пользователя 2026-09-12: приложение смотрелось бездушно. Здесь:
   бегущая строка новостей сезона, цифры «счётчика посещений» для ★ и
   сигналов, значки NEW! на новых разделах и новых предметах, иконки,
   которые подпрыгивают от касания, и блёстки под пальцем.

   Правила: строка показывает только настоящие данные сервера, ничего не
   выдумывает; всё движение живёт при data-motion="full" и исчезает при
   выключенных анимациях и системном reduced-motion; ни одна кнопка не
   ждёт анимацию. */

(function () {
  const root = document.documentElement;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const motion = () => root.dataset.motion === "full" && !document.hidden && !reducedMotion.matches;
  function stopDecoration() {
    root.dataset.pageHidden = String(document.hidden);
    if (!motion()) document.querySelectorAll(".zd-finale,.zd-copy,.zd-sparkles > *").forEach((node) => node.remove());
  }
  document.addEventListener("visibilitychange", stopDecoration);
  reducedMotion.addEventListener("change", stopDecoration);
  new MutationObserver(stopDecoration).observe(root, { attributes:true, attributeFilter:["data-motion"] });
  stopDecoration();
  let session = window.ZhidaoSession || null;
  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* только на эту сессию */ } },
  };
  const readJson = (key, fallback) => {
    try { return JSON.parse(store.get(key)) ?? fallback; } catch (_) { return fallback; }
  };

  // --- цифры счётчика --------------------------------------------------------------------

  /* Источник — прежний <strong data-case-stars>/<strong data-case-scans>: его
     по-прежнему обновляют cases.js и shop.js, он же остаётся для скринридера.
     Ячейки рисуются рядом и следят за текстом источника. */
  function renderCounter(counter, source) {
    const segments = source.textContent.split("/").map((part) => (part.match(/\d+/) || ["-"])[0]);
    if (counter.dataset.counterFor === "stars" && segments[0] !== "-") segments[0] = segments[0].padStart(4, "0");
    const value = segments.join("/");
    if (counter.dataset.value === value) return;
    const previous = counter.dataset.value || "";
    counter.dataset.value = value;
    counter.replaceChildren();
    [...value].forEach((char, index) => {
      const cell = document.createElement(char === "/" ? "i" : "b");
      cell.textContent = char;
      if (char !== "/" && previous && previous[index] !== char && motion()) cell.classList.add("is-rolling");
      counter.append(cell);
    });
    source.closest(".status-module, .header-balance, .rep-me-points")?.classList.add("has-counter");
  }

  document.querySelectorAll("[data-counter-for]").forEach((counter) => {
    const source = counter.parentElement.querySelector("strong");
    if (!source) return;
    renderCounter(counter, source);
    new MutationObserver(() => renderCounter(counter, source))
      .observe(source, { childList: true, characterData: true, subtree: true });
  });

  // --- бегущая строка ----------------------------------------------------------------------

  const ticker = document.getElementById("homeTicker");
  let tickerBusy = false;

  async function get(path) {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function plural(n, one, few, many) {
    const tens = n % 100, units = n % 10;
    if (tens > 10 && tens < 20) return many;
    if (units === 1) return one;
    if (units > 1 && units < 5) return few;
    return many;
  }

  async function news() {
    if (!signedIn()) return ["Добро пожаловать в ZHIDAO Hainan", "Войдите, чтобы видеть новости своего сезона"];
    const seasons = (await get("/api/v4/cases/context")).seasons || [];
    const season = seasons.find((s) => s.is_member && s.status === "active");
    if (!season) return ["Добро пожаловать в ZHIDAO Hainan", "Сезон ещё не начался — новости появятся с его стартом"];
    const base = `/api/v4/seasons/${season.id}`;
    const [shop, meet, trade, virus] = await Promise.allSettled(
      [`${base}/shop`, `${base}/puzzles`, `${base}/trade`, `${base}/virus`].map(get));
    const lines = [];
    if (virus.status === "fulfilled") {
      const v = virus.value;
      lines.push(v.infected ? "⚠ В системе вирус Протокола — загляните в «Антивирус»"
        : v.firewall ? "Фаервол включён до утра" : "Система чиста: вирусов не обнаружено");
    }
    if (shop.status === "fulfilled") {
      const left = (shop.value.vitrine || []).filter((item) => item.remaining > 0).length;
      const time = String(shop.value.refresh_at || "").slice(11, 16) || "07:00";
      lines.push(left ? `Витрина дня: в продаже ${left} ${plural(left, "товар", "товара", "товаров")} · обновление в ${time}`
        : `Витрину раскупили · новая в ${time}`);
    }
    if (meet.status === "fulfilled") {
      const m = meet.value;
      const current = (m.puzzles || []).find((p) => p.code === m.current);
      lines.push(`Встреч сегодня: ${m.met_today}` +
        (current ? ` · пазл «${current.title_ru}» ${current.pieces.length}/${current.total}` : " · все пазлы собраны"));
    }
    if (trade.status === "fulfilled") lines.push(`Обменов сегодня: ${trade.value.trades_today} из ${trade.value.limit}`);
    return lines.length ? lines : ["ZHIDAO Hainan на связи"];
  }

  function drawTicker(lines) {
    const run = (hidden) => {
      const box = document.createElement("span");
      box.className = "zd-ticker-run";
      if (hidden) box.setAttribute("aria-hidden", "true");
      lines.forEach((text) => {
        const item = document.createElement("span");
        item.textContent = text;
        box.append(item);
      });
      return box;
    };
    // Две одинаковые половины: сдвиг на -50% замыкает строку без рывка.
    ticker.replaceChildren(run(false), run(true));
    ticker.style.setProperty("--ticker-duration", `${Math.max(16, Math.round(lines.join("").length * 0.24))}s`);
  }

  async function refreshTicker() {
    if (!ticker || tickerBusy) return;
    tickerBusy = true;
    try { drawTicker(await news()); } catch (_) { /* строка остаётся прежней */ } finally { tickerBusy = false; }
  }

  setInterval(() => {
    if (!document.hidden && root.dataset.currentScreen === "schedule") refreshTicker();
  }, 90000);

  // --- значки NEW! ---------------------------------------------------------------------------

  const SEEN_KEY = "zhidao.v4.seen";
  const seen = readJson(SEEN_KEY, {});

  function badge(host) {
    if (host.querySelector(":scope > .new-badge")) return;
    const mark = document.createElement("b");
    mark.className = "new-badge";
    mark.textContent = "NEW!";
    mark.setAttribute("aria-hidden", "true");
    host.append(mark);
  }

  function refreshBadges() {
    document.querySelectorAll("[data-new]").forEach((host) => {
      if (seen[host.dataset.new]) host.querySelector(":scope > .new-badge")?.remove();
      else badge(host);
    });
  }

  function markSeen(key) {
    if (!key || seen[key] || !document.querySelector(`[data-new="${key}"]`)) return;
    seen[key] = Date.now();
    store.set(SEEN_KEY, JSON.stringify(seen));
    refreshBadges();
  }

  /* Новые предметы коллекции: код, которого этот человек на этом устройстве
     ещё не видел. При первом открытии всё уже лежащее считается увиденным —
     иначе NEW! горел бы на каждом предмете разом. */
  const inventory = document.getElementById("caseInventory");
  if (inventory) {
    new MutationObserver(() => {
      const cards = inventory.querySelectorAll("[data-item-code]");
      if (!cards.length || !signedIn() || !session.account) return;
      const key = `zhidao.v4.seen.items.${session.account.id}`;
      const stored = readJson(key, null);
      const known = new Set(Array.isArray(stored) ? stored : []);
      cards.forEach((card) => {
        if (stored && !known.has(card.dataset.itemCode)) badge(card);
        known.add(card.dataset.itemCode);
      });
      store.set(key, JSON.stringify([...known]));
    }).observe(inventory, { childList: true });
  }

  // --- живые иконки --------------------------------------------------------------------------

  document.addEventListener("click", (event) => {
    const host = event.target.closest(".hub-tile, .app-dock button, .desktop-shortcuts button, .admin-nav-btn");
    if (!host || !motion()) return;
    host.classList.remove("is-poked");
    void host.offsetWidth; // перезапуск анимации при повторном касании
    host.classList.add("is-poked");
    setTimeout(() => host.classList.remove("is-poked"), 700);
  });

  // В «Ещё» время от времени одна из иконок оживает сама, как GIF на странице.
  setInterval(() => {
    if (!motion() || root.dataset.currentScreen !== "more") return;
    const tiles = [...document.querySelectorAll('[data-screen="more"] .hub-tile:not([hidden])')];
    const tile = tiles[Math.floor(Math.random() * tiles.length)];
    if (!tile) return;
    tile.classList.add("is-wiggle");
    setTimeout(() => tile.classList.remove("is-wiggle"), 950);
  }, 4200);

  // --- блёстки ---------------------------------------------------------------------------------

  const layer = document.createElement("div");
  layer.className = "zd-sparkles";
  layer.setAttribute("aria-hidden", "true");
  document.body.append(layer);
  const GLYPHS = ["✦", "★", "✧", "✦", "·", "★"];

  document.addEventListener("pointerdown", (event) => {
    if (!motion() || (event.pointerType === "mouse" && event.button !== 0)) return;
    // Карта тянется пальцем, поля ввода — для печати: там блёстки мешают.
    if (event.target.closest("input, textarea, select, .campus-map")) return;
    if (layer.childElementCount > 36) return;
    for (let i = 0; i < 6; i += 1) {
      const star = document.createElement("i");
      const angle = (Math.PI * 2 * i) / 6 + Math.random() * 0.6;
      const distance = 22 + Math.random() * 26;
      star.textContent = GLYPHS[i];
      star.style.left = `${event.clientX}px`;
      star.style.top = `${event.clientY}px`;
      star.style.setProperty("--dx", `${Math.round(Math.cos(angle) * distance)}px`);
      star.style.setProperty("--dy", `${Math.round(Math.sin(angle) * distance)}px`);
      star.style.setProperty("--hue", String(Math.round(Math.random() * 360)));
      star.addEventListener("animationend", () => star.remove(), { once: true });
      setTimeout(() => star.remove(), 1200); // если анимация так и не запустилась
      layer.append(star);
    }
  }, { passive: true });

  // --- подключение -----------------------------------------------------------------------------

  // --- игры: журнал комнаты, финалы, копирование ---------------------------------------------

  /* Кто зашёл, вышел, пропал со связи и вернулся — из разницы двух списков
     игроков между опросами. Это системные строки, не чат: свободного текста
     между детьми нет. Глаголы в настоящем времени — без угадывания рода. */
  function roomEvents(previous, next, you) {
    const before = new Map(previous.map((player) => [player.account_id, player]));
    const after = new Set(next.map((player) => player.account_id));
    const events = [];
    for (const player of next) {
      const old = before.get(player.account_id);
      if (!old) events.push({ kind: "join", name: player.display_name, you: player.account_id === you });
      else if (old.present && !player.present) events.push({ kind: "away", name: player.display_name });
      else if (!old.present && player.present) events.push({ kind: "back", name: player.display_name });
    }
    for (const player of previous) {
      if (!after.has(player.account_id)) events.push({ kind: "leave", name: player.display_name });
    }
    return events;
  }

  function eventText(event) {
    if (event.kind === "join") return event.you ? "Вы заходите в комнату" : `${event.name} заходит в комнату`;
    if (event.kind === "leave") return `${event.name} покидает комнату`;
    if (event.kind === "away") return `${event.name} пропадает со связи`;
    return `${event.name} снова на связи`;
  }

  function el(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function dismissible(overlay, ms) {
    const onKey = (event) => { if (event.key === "Escape") close(); };
    const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
    overlay.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    setTimeout(close, ms);
  }

  /* Финал партии: WordArt и пиксельный фейерверк у тех, кто получил очки;
     «синий экран», если Сбой системы проигран; остальным — «Раунд окончен».
     Карточка с итогом остаётся в комнате — оверлей её только предваряет. */
  function finale(options) {
    if (!motion()) return;
    document.querySelector(".zd-finale")?.remove();
    const overlay = el("div", `zd-finale is-${options.kind}`);
    overlay.setAttribute("role", "status");
    if (options.kind === "bsod") {
      const screen = el("div", "zd-bsod");
      const hint = el("p", null, "Итог остаётся в комнате · Esc — скрыть ");
      hint.append(el("span", "zd-bsod-cursor", "_"));
      screen.append(
        el("b", "zd-bsod-head", "ZHIDAO PROTOCOL"),
        el("p", null, "Обнаружена неустранимая ошибка. Система остановлена, чтобы не повредить Хайнань."),
        el("p", null, `*** STOP: 0x0000DEAD (${options.reason})`),
        el("p", null, "Совет: техник описывает, эксперты читают инструкцию вслух. Попробуйте ещё раунд."),
        hint);
      overlay.append(screen);
      document.body.append(overlay);
      dismissible(overlay, 1800);
      return;
    }
    const win = options.kind === "win";
    overlay.append(el("div", `zd-wordart${win ? "" : " is-muted"}`, win ? "ПОБЕДА!" : "РАУНД ОКОНЧЕН"));
    if (win) overlay.append(el("p", "zd-finale-sub", `+${options.points} ${plural(options.points, "очко", "очка", "очков")} вечера`));
    if (win && motion()) {
      [48, 200, 330].forEach((hue, burst) => {
        const firework = el("span", "zd-firework");
        firework.setAttribute("aria-hidden", "true");
        firework.style.left = `${20 + burst * 30}%`;
        firework.style.top = `${22 + (burst % 2) * 16}%`;
        for (let i = 0; i < 12; i += 1) {
          const spark = el("i");
          const angle = (Math.PI * 2 * i) / 12;
          spark.style.setProperty("--dx", `${Math.round(Math.cos(angle) * 70)}px`);
          spark.style.setProperty("--dy", `${Math.round(Math.sin(angle) * 70)}px`);
          spark.style.setProperty("--hue", String(hue + (i % 3) * 20));
          spark.style.setProperty("--delay", `${burst * 0.35}s`);
          firework.append(spark);
        }
        overlay.append(firework);
      });
    }
    document.body.append(overlay);
    dismissible(overlay, 1800);
  }

  /* Окно «Копирование» перед итогом обмена — чистая декорация: предметы уже
     перенёс сервер. Без анимаций окна нет вовсе. */
  function copyFile(options) {
    if (!motion()) return;
    document.querySelector(".zd-copy")?.remove();
    const win = el("div", "zd-copy");
    win.setAttribute("aria-hidden", "true");
    const scene = el("div", "zd-copy-scene");
    scene.append(el("span", "zd-folder is-from"), el("span", "zd-paper"), el("span", "zd-folder is-to"));
    const bar = el("span", "zd-copy-bar");
    bar.append(el("i"));
    const body = el("div", "zd-copy-body");
    body.append(scene, el("b", null, `«${options.name}»`), el("span", null, "Из: собеседник → в: мои предметы"), bar,
      el("small", null, "Предмет уже в коллекции"));
    win.append(el("div", "zd-copy-title", "Копирование…"), body);
    document.body.append(win);
    dismissible(win, 1800);
  }

  // A short, non-blocking reveal of an already confirmed result.
  const pulses = new Set();
  function reveal(host) {
    if (!host || !motion()) return;
    const effect = host.animate([{ opacity:.6, transform:"translateY(4px)" }, { opacity:1, transform:"none" }],
      { duration:240, easing:"ease-out" });
    pulses.add(effect);
    effect.finished.catch(() => {}).finally(() => pulses.delete(effect));
  }
  function cancelPulses() { if (!motion()) { pulses.forEach((effect) => effect.cancel()); pulses.clear(); } }
  document.addEventListener("visibilitychange", cancelPulses);
  reducedMotion.addEventListener("change", cancelPulses);
  new MutationObserver(cancelPulses).observe(root, { attributes:true, attributeFilter:["data-motion"] });
  window.ZhidaoRetro = Object.freeze({ roomEvents, eventText, finale, copyFile, reveal });

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    refreshTicker();
  });
  window.addEventListener("zhidao:screen", (event) => {
    markSeen(event.detail);
    if (event.detail === "schedule") refreshTicker();
  });
  refreshBadges();
  refreshTicker();
}());
