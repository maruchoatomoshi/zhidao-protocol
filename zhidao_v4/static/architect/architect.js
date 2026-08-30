"use strict";

const state = {
  csrf: "",
  account: null,
  roles: [],
  seasons: [],
  selectedSeason: null,
  overview: null,
  view: "overview",
  toastTimer: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  collectElements();
  bindEvents();
  restoreSession();
});

function collectElements() {
  const ids = [
    "loginView", "consoleView", "loginForm", "usernameInput", "passwordInput",
    "passwordToggle", "loginButton", "loginError", "logoutButton", "refreshButton",
    "identityInitial", "identityName", "identityRole", "viewKicker", "viewTitle",
    "heroSeasonStatus", "heroSeasonName", "heroSeasonMeta", "heroRevision",
    "editSeasonButton", "metricSeasons", "metricDrafts", "metricSessions",
    "metricAudit", "activityList", "seasonForm", "seasonCode", "seasonRevision",
    "seasonName", "seasonStart", "seasonEnd", "seasonTimezone", "seasonTheme",
    "seasonStatusBadge", "seasonSaveButton", "seasonSaveState", "previewName",
    "previewDates", "previewTheme", "systemSchema", "systemIdentity", "toast",
    "systemLogoutButton",
  ];
  ids.forEach((id) => { elements[id] = document.getElementById(id); });
}

function bindEvents() {
  elements.loginForm.addEventListener("submit", handleLogin);
  elements.logoutButton.addEventListener("click", handleLogout);
  elements.systemLogoutButton.addEventListener("click", handleLogout);
  elements.refreshButton.addEventListener("click", () => loadConsole(true));
  elements.editSeasonButton.addEventListener("click", () => switchView("season"));
  elements.seasonForm.addEventListener("submit", handleSeasonSave);
  elements.passwordToggle.addEventListener("click", togglePassword);
  [elements.seasonName, elements.seasonStart, elements.seasonEnd, elements.seasonTimezone, elements.seasonTheme]
    .forEach((input) => input.addEventListener("input", handleSeasonDraftInput));
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD"].includes(method)) {
    const csrf = state.csrf || readCookie("zhidao_v4_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (options.idempotencyKey) headers["X-Idempotency-Key"] = options.idempotencyKey;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const contentType = response.headers.get("content-type") || "";
  const data = response.status === 204
    ? null
    : contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = data && typeof data === "object" ? data.detail : data;
    const error = new Error(message || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function restoreSession() {
  state.csrf = readCookie("zhidao_v4_csrf");
  try {
    const me = await api("/api/v4/auth/me");
    acceptIdentity(me);
    if (!hasArchitectAccess()) {
      await api("/api/v4/auth/logout", { method: "POST" });
      resetState();
      throw new Error("Для этой консоли требуется роль Архитектора");
    }
    showConsole();
    await loadConsole(false);
  } catch (error) {
    showLogin();
  }
}

async function handleLogin(event) {
  event.preventDefault();
  setLoginBusy(true);
  elements.loginError.hidden = true;
  try {
    const result = await api("/api/v4/auth/login", {
      method: "POST",
      body: {
        username: elements.usernameInput.value.trim(),
        password: elements.passwordInput.value,
      },
    });
    state.csrf = result.csrf_token;
    acceptIdentity(result);
    if (!hasArchitectAccess()) {
      await api("/api/v4/auth/logout", { method: "POST" });
      resetState();
      throw new Error("Для этой консоли требуется роль Архитектора");
    }
    elements.passwordInput.value = "";
    showConsole();
    await loadConsole(false);
  } catch (error) {
    elements.loginError.textContent = friendlyError(error, "Не удалось войти");
    elements.loginError.hidden = false;
  } finally {
    setLoginBusy(false);
  }
}

async function handleLogout() {
  try {
    await api("/api/v4/auth/logout", { method: "POST" });
  } catch (error) {
    if (error.status !== 401) showToast(friendlyError(error, "Ошибка выхода"), true);
  } finally {
    resetState();
    showLogin();
  }
}

function acceptIdentity(payload) {
  state.account = payload.account;
  state.roles = payload.roles || [];
  const name = state.account.display_name || "Architect";
  elements.identityName.textContent = name;
  elements.identityInitial.textContent = firstGrapheme(name);
  elements.identityRole.textContent = roleLabel();
  elements.systemIdentity.textContent = name;
}

function hasArchitectAccess() {
  return state.roles.some((role) =>
    role.season_id === null && ["architect", "system_admin"].includes(role.code));
}

function roleLabel() {
  if (state.roles.some((role) => role.code === "architect" && role.season_id === null)) return "Архитектор";
  if (state.roles.some((role) => role.code === "system_admin" && role.season_id === null)) return "Системный администратор";
  return "Нет доступа";
}

async function loadConsole(notify) {
  elements.refreshButton.disabled = true;
  try {
    const [seasonPayload, overview] = await Promise.all([
      api("/api/v4/seasons"),
      api("/api/v4/admin/overview"),
    ]);
    state.seasons = seasonPayload.items || [];
    state.overview = overview;
    state.selectedSeason = state.seasons.find((season) => season.code === "hainan-v4")
      || state.seasons[0]
      || null;
    renderConsole();
    if (notify) showToast("Данные синхронизированы");
  } catch (error) {
    if (error.status === 401) {
      resetState();
      showLogin();
      return;
    }
    showToast(friendlyError(error, "Не удалось обновить данные"), true);
  } finally {
    elements.refreshButton.disabled = false;
  }
}

function renderConsole() {
  renderOverview();
  renderSeasonForm();
  renderSystem();
}

function renderOverview() {
  const season = state.selectedSeason;
  const counts = state.overview?.counts || {};
  elements.metricSeasons.textContent = counts.seasons ?? "—";
  elements.metricDrafts.textContent = counts.draft_seasons ?? "—";
  elements.metricSessions.textContent = counts.active_sessions ?? "—";
  elements.metricAudit.textContent = counts.audit_entries ?? "—";
  if (season) {
    elements.heroSeasonName.textContent = season.name;
    elements.heroSeasonStatus.textContent = season.status.toUpperCase();
    elements.heroSeasonMeta.textContent = `${formatDateRange(season)} · ${season.timezone}`;
    elements.heroRevision.textContent = `REV ${season.revision}`;
    elements.editSeasonButton.disabled = season.status !== "draft";
  } else {
    elements.heroSeasonName.textContent = "Сезон не создан";
    elements.heroSeasonMeta.textContent = "Выполните bootstrap Architect";
    elements.editSeasonButton.disabled = true;
  }
  renderActivity(state.overview?.recent_activity || []);
}

function renderActivity(items) {
  elements.activityList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-activity";
    empty.textContent = "Журнал пока пуст";
    elements.activityList.append(empty);
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "activity-item";
    const mark = document.createElement("span");
    mark.className = "activity-mark";
    mark.textContent = actionGlyph(item.action);
    const copy = document.createElement("span");
    copy.className = "activity-copy";
    const title = document.createElement("strong");
    title.textContent = actionLabel(item.action);
    const detail = document.createElement("small");
    detail.textContent = `${item.actor || "SYSTEM"} · ${item.entity_type} ${item.entity_id || ""}`.trim();
    copy.append(title, detail);
    const time = document.createElement("time");
    time.className = "activity-time";
    time.dateTime = item.occurred_at;
    time.textContent = formatMoment(item.occurred_at);
    row.append(mark, copy, time);
    elements.activityList.append(row);
  });
}

function renderSeasonForm() {
  const season = state.selectedSeason;
  if (!season) return;
  elements.seasonCode.value = season.code;
  elements.seasonRevision.value = String(season.revision);
  elements.seasonName.value = season.name;
  elements.seasonStart.value = season.starts_on || "";
  elements.seasonEnd.value = season.ends_on || "";
  setSelectValue(elements.seasonTimezone, season.timezone, "Asia/Shanghai");
  setSelectValue(elements.seasonTheme, season.theme_key, "hainan-aqua");
  elements.seasonStatusBadge.lastChild.textContent = season.status.toUpperCase();
  elements.seasonSaveState.textContent = "Изменений нет";
  updatePreview();
}

function renderSystem() {
  elements.systemSchema.textContent = `v${state.overview?.schema_version ?? "—"}`;
}

function handleSeasonDraftInput() {
  elements.seasonSaveState.textContent = "Есть несохранённые изменения";
  updatePreview();
}

function updatePreview() {
  elements.previewName.textContent = elements.seasonName.value.trim() || "ZHIDAO Hainan";
  elements.previewTheme.textContent = elements.seasonTheme.value || "hainan-aqua";
  const start = elements.seasonStart.value;
  const end = elements.seasonEnd.value;
  elements.previewDates.textContent = start || end
    ? `${start ? formatDate(start) : "…"} — ${end ? formatDate(end) : "…"}`
    : "Даты не заданы";
}

async function handleSeasonSave(event) {
  event.preventDefault();
  const season = state.selectedSeason;
  if (!season) return;
  elements.seasonSaveButton.disabled = true;
  elements.seasonSaveState.textContent = "Сохраняю…";
  try {
    const updated = await api(`/api/v4/seasons/${season.id}`, {
      method: "PATCH",
      idempotencyKey: `architect:season:${season.id}:${crypto.randomUUID()}`,
      body: {
        expected_revision: season.revision,
        name: elements.seasonName.value.trim(),
        starts_on: elements.seasonStart.value || null,
        ends_on: elements.seasonEnd.value || null,
        timezone: elements.seasonTimezone.value,
        theme_key: elements.seasonTheme.value || null,
      },
    });
    state.selectedSeason = updated;
    state.seasons = state.seasons.map((item) => item.id === updated.id ? updated : item);
    renderConsole();
    showToast("Конфигурация Hainan сохранена");
  } catch (error) {
    elements.seasonSaveState.textContent = "Не сохранено";
    if (error.status === 409) await loadConsole(false);
    showToast(friendlyError(error, "Не удалось сохранить сезон"), true);
  } finally {
    elements.seasonSaveButton.disabled = false;
  }
}

function switchView(view) {
  state.view = view;
  const titles = {
    overview: ["CONTROL SURFACE", "Обзор протокола"],
    season: ["SEASON CONFIG", "Сезон Hainan"],
    system: ["SYSTEM STATUS", "Состояние системы"],
  };
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    const active = panel.dataset.panel === view;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  elements.viewKicker.textContent = titles[view][0];
  elements.viewTitle.textContent = titles[view][1];
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showConsole() {
  document.body.dataset.surface = "console";
  elements.loginView.hidden = true;
  elements.consoleView.hidden = false;
}

function showLogin() {
  document.body.dataset.surface = "login";
  elements.consoleView.hidden = true;
  elements.loginView.hidden = false;
  elements.usernameInput.focus();
}

function resetState() {
  state.csrf = "";
  state.account = null;
  state.roles = [];
  state.seasons = [];
  state.selectedSeason = null;
  state.overview = null;
}

function setLoginBusy(busy) {
  elements.loginButton.disabled = busy;
  elements.loginButton.firstElementChild.textContent = busy ? "Проверяю контур…" : "Открыть контур";
}

function togglePassword() {
  const reveal = elements.passwordInput.type === "password";
  elements.passwordInput.type = reveal ? "text" : "password";
  elements.passwordToggle.textContent = reveal ? "Скрыть" : "Показать";
  elements.passwordToggle.setAttribute("aria-label", reveal ? "Скрыть пароль" : "Показать пароль");
}

function readCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((cookie) => cookie.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : "";
}

function setSelectValue(select, value, fallback) {
  const desired = value || fallback;
  const exists = Array.from(select.options).some((option) => option.value === desired);
  select.value = exists ? desired : fallback;
}

function firstGrapheme(value) {
  return Array.from(value.trim())[0]?.toUpperCase() || "A";
}

function formatDateRange(season) {
  if (!season.starts_on && !season.ends_on) return "Даты не заданы";
  return `${season.starts_on ? formatDate(season.starts_on) : "…"} — ${season.ends_on ? formatDate(season.ends_on) : "…"}`;
}

function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function formatMoment(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function actionLabel(action) {
  const labels = {
    "account.created": "Создан локальный аккаунт",
    "role.assigned": "Назначена роль",
    "auth.login_succeeded": "Вход в консоль",
    "auth.login_failed": "Неудачная попытка входа",
    "auth.logout": "Выход из консоли",
    "season.created": "Создан черновик сезона",
    "season.updated": "Обновлена конфигурация сезона",
  };
  return labels[action] || action;
}

function actionGlyph(action) {
  if (action.startsWith("auth.")) return "⌁";
  if (action.startsWith("season.")) return "◎";
  if (action.startsWith("role.")) return "◇";
  return "◈";
}

function friendlyError(error, fallback) {
  if (error.status === 401) return "Неверный логин или пароль";
  if (error.status === 403) return "Недостаточно прав или устарела CSRF-сессия";
  if (error.status === 409) return error.message || "Данные уже изменились. Экран обновлён.";
  if (error.status === 429) return "Слишком много попыток. Подождите минуту.";
  return error.message || fallback;
}

function showToast(message, error = false) {
  clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.hidden = false;
  state.toastTimer = setTimeout(() => { elements.toast.hidden = true; }, 3400);
}
