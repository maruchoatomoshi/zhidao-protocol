"use strict";

/* Служебный контур: то, что видит вожатый, оператор и Архитектор.

   Это не «панель с правами». Права живут на сервере: каждый endpoint здесь
   сам проверяет роль, и спрятанная кнопка ничего не защищает (V4_AUTH). Всё,
   что делает этот файл, — не показывает того, чем человек всё равно не
   сможет воспользоваться, и честно называет отказ, когда сервер отвечает 403.

   Отсюда же правило про разделы. Роли бывают глобальные и сезонные: выдача
   попыток принимает сезонную, а ростер и сводка требуют глобальной. Поэтому
   плитка «Админка» появляется у любого служебного аккаунта, а каждая панель
   отвечает за свой доступ отдельно — иначе пришлось бы либо прятать нужное,
   либо обещать невозможное.

   Ничего не выдумывается: если данные не пришли, панель говорит об этом, а не
   рисует правдоподобные числа. */

(function () {
  const $ = (id) => document.getElementById(id);
  const PRIVILEGED = ["operator", "architect", "system_admin"];
  const ROLE_NAMES = {
    participant: "Участник",
    operator: "Оператор",
    architect: "Архитектор",
    system_admin: "Системный администратор",
  };
  const COUNT_NAMES = {
    accounts: "Аккаунты",
    seasons: "Сезоны",
    draft_seasons: "Черновики",
    active_sessions: "Сессии",
    audit_entries: "Журнал",
  };

  let session = null;
  const loaded = new Set();
  let armedAccountId = null;   // подтверждение выдачи кода: второй клик

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function signedIn() { return session && session.mode === "authenticated"; }

  function roleCodes() {
    return signedIn() ? (session.roles || []).map((role) => role.code) : [];
  }

  function privileged() {
    return roleCodes().some((code) => PRIVILEGED.includes(code));
  }

  /* Наивысшая роль — для шильдика. Порядок именно такой: администратор шире
     архитектора, архитектор шире оператора. */
  function topRole() {
    return ["system_admin", "architect", "operator"].find((code) => roleCodes().includes(code)) || null;
  }

  async function api(path, options = {}) {
    if (!signedIn()) throw new Error("Для этого нужен вход.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const headers = { Accept: "application/json" };
      if (options.method === "POST") {
        const cookie = document.cookie.split("; ").find((v) => v.startsWith("zhidao_v4_csrf="));
        headers["X-CSRF-Token"] = cookie ? decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) : "";
      }
      const response = await fetch(path, {
        method: options.method || "GET",
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof data.detail === "string" ? data.detail : "Запрос отклонён.");
        error.status = response.status;
        throw error;
      }
      return data;
    } finally { clearTimeout(timer); }
  }

  /* Отказ по правам — не поломка. Формулируем так, чтобы человек понял, что
     делать: просить роль, а не обновлять страницу. */
  function explain(error, need) {
    if (error.status === 403) return `Недостаточно прав. Нужна роль: ${need}.`;
    if (error.status === 401) return "Сессия истекла. Войдите заново.";
    return error.message || "Нет связи с сервером.";
  }

  // --- шапка контура -------------------------------------------------------

  function drawIdentity() {
    const badge = $("adminBadge");
    const code = topRole();
    badge.textContent = code ? ROLE_NAMES[code] : "—";
    badge.dataset.role = code || "";

    const host = $("adminRoles");
    host.replaceChildren();
    const roles = signedIn() ? session.roles || [] : [];
    if (!roles.length) {
      host.append(node("span", "admin-role-chip is-empty", "ролей нет"));
      return;
    }
    for (const role of roles) {
      const chip = node("span", "admin-role-chip", ROLE_NAMES[role.code] || role.code);
      // Сезонная роль действует только внутри своего сезона, и это стоит
      // видеть до того, как упрёшься в 403 на общем разделе.
      if (role.season_id != null) chip.append(node("i", null, `сезон #${role.season_id}`));
      else chip.classList.add("is-global");
      host.append(chip);
    }
  }

  // --- сводка --------------------------------------------------------------

  async function loadOverview() {
    const counts = $("adminCounts");
    const activity = $("adminActivity");
    counts.replaceChildren(node("p", "case-message", "Загрузка…"));
    activity.replaceChildren();
    let data;
    try {
      data = await api("/api/v4/admin/overview");
    } catch (error) {
      counts.replaceChildren(node("p", "case-message", explain(error, "архитектор или системный администратор")));
      $("adminSchema").textContent = "SCHEMA —";
      return;
    }
    counts.replaceChildren();
    for (const [key, value] of Object.entries(data.counts || {})) {
      const gauge = node("div", "admin-gauge");
      gauge.append(node("span", null, COUNT_NAMES[key] || key));
      gauge.append(node("strong", null, new Intl.NumberFormat("ru-RU").format(value)));
      counts.append(gauge);
    }
    $("adminSchema").textContent = `SCHEMA ${data.schema_version}`;

    const entries = data.recent_activity || [];
    if (!entries.length) {
      activity.append(node("p", "case-message", "Журнал пуст."));
      return;
    }
    for (const entry of entries) {
      const row = node("div", "admin-log-row");
      row.append(node("b", null, entry.action));
      row.append(node("span", null,
        `${entry.entity_type}${entry.entity_id != null ? ` #${entry.entity_id}` : ""}` +
        `${entry.season_id != null ? ` · сезон #${entry.season_id}` : ""}`));
      row.append(node("small", null, `${entry.actor || "система"} · ${entry.occurred_at}`));
      activity.append(row);
    }
  }

  // --- ростер и коды сопряжения -------------------------------------------

  function drawCode(account, code) {
    const card = $("adminCodeCard");
    card.hidden = false;
    $("adminCodeFor").textContent = `${account.display_name} · #${account.id}`;
    // Пробел посередине: восьмизначное число диктуют голосом, и группами по
    // четыре его не теряют.
    $("adminCodeValue").textContent = `${code.slice(0, 4)} ${code.slice(4)}`;
    $("adminCodeValue").dataset.raw = code;
    $("adminCodeStatus").textContent = "";
    card.scrollIntoView({ behavior: window.ZhidaoMotion?.enabled() ? "smooth" : "auto", block: "nearest" });
  }

  function disarm() {
    armedAccountId = null;
    document.querySelectorAll("[data-code-button]").forEach((button) => {
      button.textContent = "Код MAX";
      button.classList.remove("is-armed");
    });
  }

  async function issueCode(account, button) {
    // Выдача аннулирует прежний код этого человека. Если он уже продиктован,
    // повторное нажатие ломает вход — поэтому подтверждение, а не мгновенное
    // действие. Отдельного диалога нет намеренно: кнопка спрашивает сама.
    //
    // Предупреждение при этом стоит рядом, а не на кнопке: длинная надпись
    // внутри кнопки съедала колонку с именем, и строка ростера рассыпалась
    // по букве в строку.
    if (armedAccountId !== account.id) {
      disarm();
      armedAccountId = account.id;
      button.textContent = "Точно?";
      button.classList.add("is-armed");
      $("adminRosterStatus").textContent =
        `Нажмите ещё раз, чтобы выдать код для «${account.display_name}». Прежний код этого участника перестанет работать.`;
      return;
    }
    armedAccountId = null;
    button.classList.remove("is-armed");
    $("adminRosterStatus").textContent = "";
    button.disabled = true;
    button.textContent = "Выдаём…";
    try {
      const data = await api(`/api/v4/admin/accounts/${account.id}/link-codes`, { method: "POST" });
      drawCode(account, data.code);
    } catch (error) {
      $("adminRosterStatus").textContent = explain(error, "оператор, архитектор или системный администратор");
    } finally {
      button.disabled = false;
      button.textContent = "Код MAX";
    }
  }

  function drawRoster(items) {
    const host = $("adminRoster");
    disarm();
    host.replaceChildren();
    if (!items.length) {
      host.append(node("p", "case-message", "Никого не нашлось. Попробуйте другую часть имени."));
      $("adminRosterCount").textContent = "0 записей";
      return;
    }
    for (const account of items) {
      const row = node("div", "admin-roster-row");
      const left = node("div", "admin-roster-copy");
      left.append(node("b", null, account.display_name));
      const marks = node("span", "admin-roster-marks");
      marks.append(node("i", `admin-mark ${account.max_linked ? "is-on" : "is-off"}`,
        account.max_linked ? "MAX привязан" : "MAX не привязан"));
      if (account.status !== "active") marks.append(node("i", "admin-mark is-warn", account.status));
      if (account.login) marks.append(node("i", "admin-mark", account.login));
      left.append(marks);
      left.append(node("small", null, `#${account.id}`));
      row.append(left);

      const button = node("button", "btn btn-secondary admin-code-btn", "Код MAX");
      button.type = "button";
      button.dataset.codeButton = "1";
      button.addEventListener("click", () => issueCode(account, button));
      row.append(button);
      host.append(row);
    }
    $("adminRosterCount").textContent = `${items.length} ${items.length === 1 ? "запись" : "записей"}`;
  }

  async function loadRoster(query) {
    const host = $("adminRoster");
    $("adminRosterStatus").textContent = "";
    host.replaceChildren(node("p", "case-message", "Загрузка ростера…"));
    try {
      const search = query ? `?query=${encodeURIComponent(query)}&limit=50` : "?limit=50";
      const data = await api(`/api/v4/admin/accounts${search}`);
      drawRoster(data.items || []);
    } catch (error) {
      host.replaceChildren(node("p", "case-message", explain(error, "оператор, архитектор или системный администратор")));
      $("adminRosterCount").textContent = "— записей";
    }
  }

  // --- сезоны --------------------------------------------------------------

  async function loadSeasons() {
    const host = $("adminSeasons");
    host.replaceChildren(node("p", "case-message", "Загрузка…"));
    let data;
    try {
      data = await api("/api/v4/seasons");
    } catch (error) {
      host.replaceChildren(node("p", "case-message", explain(error, "вход в аккаунт")));
      return;
    }
    host.replaceChildren();
    const items = data.items || [];
    if (!items.length) {
      host.append(node("p", "case-message", "Сезонов пока нет."));
      return;
    }
    for (const season of items) {
      const row = node("div", "admin-season-row");
      row.append(node("b", null, season.name));
      row.append(node("i", "admin-mark", season.status));
      row.append(node("small", null,
        `${season.code} · ${season.starts_on || "—"} → ${season.ends_on || "—"} · ${season.timezone || "—"}`));
      host.append(row);
    }
  }

  // --- переключение панелей ------------------------------------------------

  const LOADERS = {
    overview: loadOverview,
    roster: () => loadRoster(""),
    seasons: loadSeasons,
  };

  function openPanel(name, force = false) {
    const load = LOADERS[name];
    if (!load || !signedIn()) return;
    if (!force && loaded.has(name)) return;
    loaded.add(name);
    load();
  }

  function currentPanel() {
    const active = document.querySelector('[data-tab-group="admin"] [data-tab].active');
    return active ? active.dataset.tab : "overview";
  }

  /* Вожатому «Сводка» всегда отвечает отказом: она требует глобальной роли
     архитектора. Открывать раздел на заведомо закрытой панели — плохая
     встреча, поэтому оператору сразу показываем ростер: за ним он и пришёл. */
  function selectDefaultPanel() {
    const wanted = roleCodes().some((code) => ["architect", "system_admin"].includes(code))
      ? "overview" : "roster";
    const button = document.querySelector(`[data-tab-group="admin"] [data-tab="${wanted}"]`);
    if (button && !button.classList.contains("active")) button.click();
  }

  function reset() {
    loaded.clear();
    armedAccountId = null;
    $("adminCodeCard").hidden = true;
    $("adminRosterStatus").textContent = "";
  }

  // --- подключение ---------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    reset();
    drawIdentity();
    // Плитка появляется только у служебных аккаунтов. Это удобство, а не
    // защита: сервер всё равно проверит роль на каждом запросе.
    $("adminHubTile").hidden = !privileged();
    selectDefaultPanel();
    if (document.documentElement.dataset.currentScreen === "admin") openPanel(currentPanel());
  });

  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "admin") openPanel(currentPanel());
  });

  window.addEventListener("zhidao:tab", (event) => {
    const panel = event.detail;
    if (!panel || !String(panel.dataset.tabPanel || "").startsWith("admin:")) return;
    // Только если раздел открыт: вкладку переключает и код при входе, а
    // запрашивать ростер у человека, который в админку ещё не заходил, незачем.
    if (document.documentElement.dataset.currentScreen !== "admin") return;
    openPanel(panel.dataset.tabPanel.slice("admin:".length));
  });

  $("adminRosterForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loaded.add("roster");
    loadRoster($("adminRosterQuery").value.trim());
  });

  $("adminRefresh").addEventListener("click", () => openPanel(currentPanel(), true));

  $("adminCodeCopy").addEventListener("click", async () => {
    const raw = $("adminCodeValue").dataset.raw || "";
    try {
      await navigator.clipboard.writeText(raw);
      $("adminCodeStatus").textContent = "Код скопирован.";
    } catch (_) {
      // В WebView MAX буфер обмена может быть закрыт. Это не ошибка: код и так
      // на экране, его просто продиктуют.
      $("adminCodeStatus").textContent = "Буфер обмена недоступен — продиктуйте код с экрана.";
    }
  });

  $("adminCodeHide").addEventListener("click", () => {
    $("adminCodeCard").hidden = true;
    $("adminCodeValue").textContent = "";
    delete $("adminCodeValue").dataset.raw;
  });
}());
