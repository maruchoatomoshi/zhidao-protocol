"use strict";

/* Выбор оформления: «Аква» (по умолчанию) и «Луна-Аква».

   Раньше скин включался только адресом `?design=xp`. Для беглого просмотра в
   браузере этого хватало, но в мини-приложении MAX адрес набрать негде: его
   задаёт регистрация бота, и человек его не правит. Поэтому выбор переехал
   туда же, где живут тема и анимации, — в «Ещё → Вид», и хранится на
   устройстве.

   Устройство скопировано с theme.js намеренно: тот же ключ в localStorage,
   тот же атрибут на <html>, тот же делегированный клик. Инлайновые стили
   запрещены политикой безопасности (style-src 'self'), а атрибут ей не
   подчиняется.

   `?design=xp` продолжает работать и остаётся сильнее настройки, но ничего
   не записывает: ссылка «посмотри, как это выглядит» не должна менять
   человеку сохранённый выбор. */

(function () {
  const STORE_KEY = "zhidao.v4.design";
  const MODES = ["aero", "xp"];
  const LABEL = { aero: "Аква", xp: "Луна-Аква" };
  const LABEL_CN = { aero: "水色", xp: "月神" };

  const root = document.documentElement;

  function readMode() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      return MODES.includes(raw) ? raw : "aero";
    } catch (err) {
      return "aero";
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

  // Адрес сильнее сохранённого выбора, но не заменяет его.
  let override = null;
  try {
    const asked = new URLSearchParams(window.location.search).get("design");
    if (MODES.includes(asked)) override = asked;
  } catch (err) {
    /* Экзотический адрес — просто нет запроса. */
  }

  function apply() {
    const design = override || mode;
    root.dataset.design = design;
    document.querySelectorAll("[data-design-toggle]").forEach((btn) => {
      const value = btn.querySelector("[data-design-value]");
      if (value) value.textContent = LABEL[mode];
      const cn = btn.querySelector("[data-design-value-cn]");
      if (cn) cn.textContent = LABEL_CN[mode];
      btn.setAttribute("aria-label", `Оформление: ${LABEL[mode]}. Нажмите, чтобы сменить.`);
      // Пока адрес перебивает настройку, кнопка не врёт о том, что видно.
      btn.dataset.designOverridden = override ? "true" : "false";
    });
    // Переключатели в окне свойств профиля отмечают то, что видно сейчас.
    document.querySelectorAll("[data-design-choice]").forEach((input) => {
      input.checked = input.value === design;
    });
  }

  function choose(next) {
    if (!MODES.includes(next)) return;
    mode = next;
    writeMode(mode);
    // Человек выбрал руками — адрес больше не спорит.
    override = null;
    apply();
  }

  function cycle() {
    choose(MODES[(MODES.indexOf(mode) + 1) % MODES.length]);
  }

  document.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-design-toggle]");
    if (btn) cycle();
  });
  document.addEventListener("change", (event) => {
    const input = event.target.closest("[data-design-choice]");
    if (input && input.checked) choose(input.value);
  });

  /* Окно свойств профиля в Луне: вкладки «Вид» и «Помощь» и строка о том,
     кто вошёл и как. Слушатели делегированы: разметка может появиться
     позже этого файла. */
  function selectTab(tab, focus) {
    const tabs = Array.from(tab.closest("[role='tablist']").querySelectorAll("[data-xp-tab]"));
    tabs.forEach((other) => {
      const on = other === tab;
      other.setAttribute("aria-selected", String(on));
      other.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(other.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    });
    if (focus) tab.focus();
  }
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-xp-tab]");
    if (tab) selectTab(tab, false);
  });
  document.addEventListener("keydown", (event) => {
    const tab = event.target.closest("[data-xp-tab]");
    if (!tab || (event.key !== "ArrowRight" && event.key !== "ArrowLeft")) return;
    event.preventDefault();
    const tabs = Array.from(tab.closest("[role='tablist']").querySelectorAll("[data-xp-tab]"));
    const step = event.key === "ArrowRight" ? 1 : -1;
    selectTab(tabs[(tabs.indexOf(tab) + step + tabs.length) % tabs.length], true);
  });

  const ROLE_LABEL = { system_admin: "Системный администратор", architect: "Архитектор", operator: "Вожатый" };
  function accountKind(session) {
    if (!session || session.mode !== "authenticated") return "Вход не выполнен";
    const codes = (session.roles || []).map((role) => role.code);
    const role = ["system_admin", "architect", "operator"].find((code) => codes.includes(code));
    // Мост MAX есть только внутри мини-приложения; в браузере вход — по паролю.
    const viaMax = Boolean(window.WebApp && window.WebApp.initData);
    return `${role ? ROLE_LABEL[role] : "Участник"} · ${viaMax ? "вход через MAX" : "вход по паролю"}`;
  }
  window.addEventListener("zhidao:auth", (event) => {
    document.querySelectorAll("[data-account-kind]").forEach((el) => {
      el.textContent = accountKind(event.detail);
    });
  });

  apply();
  document.addEventListener("DOMContentLoaded", apply, { once: true });
}());
