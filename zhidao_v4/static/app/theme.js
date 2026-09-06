"use strict";

/* Переключение дневного и ночного вида.

   Три состояния, а не два: «как в системе», «день», «ночь». Отдельное
   системное состояние нужно, потому что телефон сам темнеет по расписанию,
   и приложение должно идти за ним, пока человек не решил иначе.

   Выбор хранится на устройстве. Атрибут data-theme ставится на <html>:
   inline-стили запрещены политикой безопасности (style-src 'self'), а
   атрибут ей не подчиняется. */

(function () {
  const STORE_KEY = "zhidao.v4.theme";
  const MODES = ["system", "light", "dark"];
  const LABEL = { system: "Как в системе", light: "Дневная", dark: "Ночная" };
  const LABEL_CN = { system: "系统", light: "白天", dark: "夜间" };

  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  function readMode() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      return MODES.includes(raw) ? raw : "system";
    } catch (err) {
      return "system";
    }
  }

  function writeMode(mode) {
    try {
      localStorage.setItem(STORE_KEY, mode);
    } catch (err) {
      /* Приватное окно или запрет данных сайта. Сеанс всё равно работает. */
    }
  }

  let mode = readMode();

  function resolved() {
    if (mode === "system") return media.matches ? "dark" : "light";
    return mode;
  }

  function apply() {
    const theme = resolved();
    root.dataset.theme = theme;
    // Строка состояния браузера красится под фон приложения: иначе на
    // телефоне сверху остаётся светлая полоса поверх ночного вида.
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#04182e" : "#d8f2fb");

    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      const value = btn.querySelector("[data-theme-value]");
      if (value) value.textContent = LABEL[mode];
      const cn = btn.querySelector("[data-theme-value-cn]");
      if (cn) cn.textContent = LABEL_CN[mode];
      btn.setAttribute("aria-label", `Тема: ${LABEL[mode]}. Нажмите, чтобы сменить.`);
    });
  }

  function cycle() {
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    writeMode(mode);
    apply();
  }

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-theme-toggle]");
    if (btn) cycle();
  });

  // Пока выбрано «как в системе», следим за системной настройкой.
  media.addEventListener("change", () => { if (mode === "system") apply(); });

  apply();
}());
