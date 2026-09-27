"use strict";

/* Второй слой движения — то, что связывает экраны между собой.

   aero-motion.js проявляет панели экрана, retro.js даёт мелочи нулевых
   (цифры табло, блёстки под пальцем, подпрыгивающие значки). Не хватало
   движения самой навигации: подсветка вкладки внизу перескакивала с места
   на место, данные, пришедшие после входа на экран, возникали разом, а
   табло в шапке не отзывалось на переход. Этот файл добавляет ровно это.

   Правила те же, что у соседей: только косметика — ни одного запроса, ни
   одного решения за сервер; всё живёт при data-motion="full" и гаснет при
   выключенных анимациях, системном reduced-motion и свёрнутом приложении
   (там CSS-переходы снимает design-system-bridge.css целиком). */

(function () {
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const full = () => root.dataset.motion === "full" && !reduced.matches && !document.hidden;

  /* --- 1. Стеклянная капля под активной вкладкой нижней панели ----------
     Одна капля на всю панель, а не своя у каждой кнопки: при переходе она
     переплывает к новой вкладке. Положение считается от кнопки, поэтому
     капля верна при любой ширине экрана и при узкой раскладке. Без
     анимаций переход просто мгновенный — transition снимает мост. */
  const dock = document.querySelector(".app-dock");
  if (dock && "ResizeObserver" in window) {
    const glide = document.createElement("span");
    glide.className = "dock-glide";
    glide.setAttribute("aria-hidden", "true");
    dock.prepend(glide);
    dock.classList.add("has-glide");
    let placed = false;
    let last = "";

    const place = () => {
      const active = dock.querySelector("button.active");
      if (!active) { glide.hidden = true; return; }
      const box = dock.getBoundingClientRect();
      const btn = active.getBoundingClientRect();
      if (!btn.width) return;
      const x = btn.left - box.left - dock.clientLeft;
      const y = btn.top - box.top - dock.clientTop;
      const key = `${x}|${y}|${btn.width}|${btn.height}`;
      if (key === last) return;
      last = key;
      glide.hidden = false;
      // Первая расстановка — без полёта: капля не должна прилетать из угла
      // при открытии приложения.
      if (!placed) glide.classList.add("is-instant");
      glide.style.width = `${btn.width}px`;
      glide.style.height = `${btn.height}px`;
      glide.style.transform = `translate(${x}px, ${y}px)`;
      if (!placed) {
        placed = true;
        requestAnimationFrame(() => requestAnimationFrame(() => glide.classList.remove("is-instant")));
      }
    };

    new MutationObserver(place).observe(dock, { subtree: true, attributes: true, attributeFilter: ["class"] });
    new ResizeObserver(place).observe(dock);
    window.addEventListener("zhidao:screen", place);
    place();
  }

  /* --- 2. Списки собираются, а не возникают ------------------------------
     Подиум, таблица соседей, лента «Что нового», файлы архива, каталог игр
     приходят с сервера уже после того, как экран открылся, — поэтому
     проявление панелей их не застаёт, и они появлялись одним кадром.

     Строки проявляются лесенкой, только если список нарисован вскоре после
     входа на экран или смены вкладки. Периодическое обновление тех же
     данных строки не дёргает: в остальное время ничего не происходит. */
  const LISTS = [
    "#repPodium", "#repAround", "#diaryBoard", "#homeNowList", "#homeFeedList",
    "#storyList", "#implantList", "#gamesCatalog", "#tradeItems", "#meetGrid",
    "#shopVitrine", "#shopMine", "#caseInventory",
  ];
  const WINDOW_MS = 2500;
  let arrivedAt = performance.now();
  const arrived = () => { arrivedAt = performance.now(); };
  window.addEventListener("zhidao:screen", arrived);
  window.addEventListener("zhidao:tab", arrived);

  const settle = (node) => {
    node.classList.remove("motion-row");
    node.style.removeProperty("--row-delay");
  };

  function build(list, nodes) {
    if (!full() || performance.now() - arrivedAt > WINDOW_MS) return;
    if (!list.closest(".screen.active")) return;
    let index = 0;
    for (const node of nodes) {
      if (node.nodeType !== 1 || node.hidden) continue;
      node.style.setProperty("--row-delay", `${Math.min(index, 9) * 45}ms`);
      node.classList.remove("motion-row");
      // Перечитать стиль, чтобы повторная вставка того же узла тоже играла.
      void node.offsetWidth;
      node.classList.add("motion-row");
      node.addEventListener("animationend", () => settle(node), { once: true });
      index += 1;
    }
  }

  LISTS.forEach((selector) => {
    const list = document.querySelector(selector);
    if (!list) return;
    new MutationObserver((records) => {
      const added = [];
      records.forEach((record) => record.addedNodes.forEach((node) => added.push(node)));
      if (added.length) build(list, added);
    }).observe(list, { childList: true });
  });

  /* --- 2б. Карточка роли раскрывается --------------------------------------
     «Вы человек», «Вы первый зомби», цель агента, роль в Саботаже — главная
     новость экрана, а появлялась она так же, как абзац правил. Карточка
     раскрывается, когда появляется впервые и когда роль сменилась (заразили,
     вывели); опрос сервера, перерисовывающий то же самое, её не трогает. */
  const ROLE_HOSTS = { zombieBody: ".zombie-card", agentBody: ".agent-card", sabotageBody: ".sabotage-card" };
  Object.entries(ROLE_HOSTS).forEach(([id, selector]) => {
    const host = document.getElementById(id);
    if (!host) return;
    let lastKey = "";
    new MutationObserver(() => {
      const card = host.querySelector(selector);
      const key = card ? `${card.className}|${(card.firstElementChild && card.firstElementChild.textContent) || ""}` : "";
      if (key === lastKey) return;
      lastKey = key;
      if (!card || !full()) return;
      card.classList.add("role-arrive");
      card.addEventListener("animationend", () => card.classList.remove("role-arrive"), { once: true });
    }).observe(host, { childList: true });
  });

  /* --- 3. Один проход света по табло при переходе -------------------------
     Приём из описания дизайн-системы («один проход света по табло при
     входе экрана»): счётчик ★ в шапке ловит блик и отзывается на каждый
     переход, как настоящий прибор. */
  const board = document.querySelector(".header-balance");
  if (board) {
    window.addEventListener("zhidao:screen", () => {
      if (!full()) return;
      board.classList.remove("is-glinting");
      void board.offsetWidth;
      board.classList.add("is-glinting");
    });
    board.addEventListener("animationend", (event) => {
      if (event.animationName === "zd-board-glint") board.classList.remove("is-glinting");
    });
  }
})();
