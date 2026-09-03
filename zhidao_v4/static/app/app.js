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

updateClock();
window.setInterval(updateClock, 30_000);
showScreen("schedule");
