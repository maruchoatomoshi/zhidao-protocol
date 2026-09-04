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
  window.scrollTo({ top: 0, behavior: "smooth" });
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

const mapPins = Array.from(document.querySelectorAll("[data-map-point]"));
const mapPointIndex = document.querySelector("#mapPointIndex");
const mapPointKind = document.querySelector("#mapPointKind");
const mapPointTitle = document.querySelector("#mapPointTitle");
const mapPointDescription = document.querySelector("#mapPointDescription");
const mapAmapLink = document.querySelector("#mapAmapLink");
const mapBaiduLink = document.querySelector("#mapBaiduLink");

const campusPoints = {
  sports: {
    index: "01", kind: "SPORT / 体育",
    title: "海南陵水黎安国际教育创新试验区体育中心",
    description: "Стадион и спортивный центр в северо-западной части выбранного квартала.",
  },
  library: {
    index: "02", kind: "STUDY / 图书馆",
    title: "陵水黎安国际教育创新试验区图书馆",
    description: "Библиотека и международный учебный центр рядом с северной границей квартала.",
  },
  teaching: {
    index: "03", kind: "ACADEMIC / 教学",
    title: "陵水黎安国际教育创新实验区公共教学楼",
    description: "Общий учебный корпус — главный академический ориентир центральной части территории.",
    amap: "https://www.amap.com/place/B0IR1ZT9R2",
  },
  canteen: {
    index: "04", kind: "FOOD / 食堂",
    title: "陵水黎安国际教育创新试验区-1号食堂",
    description: "Столовая №1; отдельная точка питания и удобный ориентир для маршрутов между корпусами.",
    amap: "https://www.amap.com/place/B0J13ULQUA",
  },
};

function selectCampusPoint(pointId) {
  const point = campusPoints[pointId];
  if (!point) return;
  mapPins.forEach((item) => item.classList.toggle("active", item.dataset.mapPoint === pointId));
  if (mapPointIndex) mapPointIndex.textContent = point.index;
  if (mapPointKind) mapPointKind.textContent = point.kind;
  if (mapPointTitle) mapPointTitle.textContent = point.title;
  if (mapPointDescription) mapPointDescription.textContent = point.description;
  const query = encodeURIComponent(point.title);
  if (mapAmapLink) mapAmapLink.href = point.amap || `https://www.amap.com/ssr/search?query=${query}&city=469028`;
  if (mapBaiduLink) mapBaiduLink.href = point.baidu || `https://map.baidu.com/search/${query}`;
}

mapPins.forEach((pin) => {
  pin.addEventListener("click", () => selectCampusPoint(pin.dataset.mapPoint));
});

// ===== Вкладки (REP: Сезон/Дневник, Магазин: Общее/VIP/Расходники, ...) =====
// Generic segmented-tab controller: any [data-tab-group="X"] of buttons with
// data-tab="Y" shows the matching [data-tab-panel="X:Y"] and hides siblings.
const tabGroups = new Map();
document.querySelectorAll("[data-tab-group]").forEach((group) => {
  const name = group.dataset.tabGroup;
  const buttons = Array.from(group.querySelectorAll("[data-tab]"));
  const panels = Array.from(document.querySelectorAll(`[data-tab-panel^="${name}:"]`));
  tabGroups.set(name, { buttons, panels });
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
  });
}

document.querySelectorAll("[data-tab-group] [data-tab]").forEach((button) => {
  const group = button.closest("[data-tab-group]");
  button.addEventListener("click", () => selectTab(group.dataset.tabGroup, button.dataset.tab));
});

updateClock();
window.setInterval(updateClock, 30_000);
showScreen("schedule");
