"use strict";

const screens = Array.from(document.querySelectorAll("[data-screen]"));
const dockButtons = Array.from(document.querySelectorAll("[data-target]"));
const toast = document.querySelector("#toast");
const clock = document.querySelector("#clock");
let toastTimer;

function updateClock() {
  if (!clock) return;
  clock.textContent = new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function showScreen(target) {
  const next = screens.find((screen) => screen.dataset.screen === target);
  if (!next) return;

  screens.forEach((screen) => {
    const isActive = screen === next;
    screen.hidden = !isActive;
    screen.classList.toggle("active", isActive);
  });

  dockButtons.forEach((button) => {
    const isActive = button.dataset.target === target;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });

  document.documentElement.dataset.currentScreen = target;
  window.scrollTo({ top: 0, behavior: window.ZhidaoMotion?.enabled() ? "smooth" : "auto" });

  // Карта строится при первом открытии, а не на старте: данные и SVG нужны
  // только тем, кто до неё дошёл.
  if (target === "campus-map" && typeof window.initCampusMap === "function") {
    window.initCampusMap();
  }
  // Каталог имплантов — по той же причине: девять картинок грузить на старте
  // незачем, они нужны только тому, кто открыл каталог.
  if (target === "implants" && typeof window.initImplantCatalogue === "function") {
    window.initImplantCatalogue();
  }
  if (target === "cases" && typeof window.initCaseRules === "function") {
    window.initCaseRules();
  }
  window.dispatchEvent(new CustomEvent("zhidao:screen", { detail: target }));
  const back = window.WebApp && window.WebApp.initData && window.WebApp.BackButton;
  if (back) {
    if (["collection", "implants", "campus-map", "profile", "admin", "games", "meet", "trade", "antivirus"].includes(target)) back.show();
    else back.hide();
  }
}

function showToast(message) {
  if (!toast || !message) return;
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}

dockButtons.forEach((button) => {
  button.addEventListener("click", () => showScreen(button.dataset.target));
});

document.querySelectorAll("[data-toast]").forEach((button) => {
  button.addEventListener("click", () => showToast(button.dataset.toast));
});

document.querySelectorAll("[data-open-screen]").forEach((button) => {
  button.addEventListener("click", () => showScreen(button.dataset.openScreen));
});

// ===== Вкладки (REP: Сезон/Дневник, Магазин: Общее/VIP/Расходники, ...) =====
// Любая группа [data-tab-group="X"] с кнопками data-tab="Y" показывает
// соответствующую панель [data-tab-panel="X:Y"] и прячет остальные.
const tabGroups = new Map();
document.querySelectorAll("[data-tab-group]").forEach((group) => {
  const name = group.dataset.tabGroup;
  tabGroups.set(name, {
    buttons: Array.from(group.querySelectorAll("[data-tab]")),
    panels: Array.from(document.querySelectorAll(`[data-tab-panel^="${name}:"]`)),
  });
});

function selectTab(groupName, tabId) {
  const group = tabGroups.get(groupName);
  if (!group) return;
  group.buttons.forEach((button) => {
    const isActive = button.dataset.tab === tabId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  group.panels.forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== `${groupName}:${tabId}`;
    if (!panel.hidden) window.dispatchEvent(new CustomEvent("zhidao:tab", { detail: panel }));
  });
}

document.querySelectorAll("[data-tab-group] [data-tab]").forEach((button) => {
  const group = button.closest("[data-tab-group]");
  button.addEventListener("click", () => selectTab(group.dataset.tabGroup, button.dataset.tab));
});

updateClock();
window.setInterval(updateClock, 30_000);
showScreen("schedule");
window.addEventListener("DOMContentLoaded", () => {
  const bridge = window.WebApp;
  if (!bridge || !bridge.initData) return;
  bridge.ready();
  bridge.BackButton.onClick(() => {
    const dialog = document.querySelector("dialog[open]");
    if (dialog) { dialog.close(); return; }
    showScreen(document.documentElement.dataset.currentScreen === "implants" ? "collection" : "more");
  });
});
