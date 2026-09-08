/* Cosmetic controller. Never chooses a prize, changes balances, or sends a request. */
(function () {
  "use strict";
  const root = document.documentElement;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let preference = "auto", activeScan = null;
  try { preference = localStorage.getItem("zhidao.v4.motion") === "off" ? "off" : "auto"; } catch (_) { /* optional preference */ }
  function enabled() { return preference !== "off" && !reduced.matches && !document.hidden; }
  function applyPreference() {
    root.dataset.motion = reduced.matches ? "reduced" : preference === "off" ? "off" : "full";
    root.dataset.appVisible = String(!document.hidden);
    document.querySelectorAll("[data-motion-toggle]").forEach(button => {
      button.setAttribute("aria-pressed", String(preference !== "off" && !reduced.matches));
      button.setAttribute("aria-label", reduced.matches ? "Уменьшение движения включено в системе" :
        preference === "off" ? "Анимации выключены. Включить" : "Анимации включены. Выключить");
      button.querySelector("[data-motion-label]").textContent = reduced.matches ? "Системное ограничение" : preference === "off" ? "Выключены" : "Включены";
    });
    if (!enabled()) activeScan?.skip();
  }
  document.querySelectorAll("[data-motion-toggle]").forEach(button => button.addEventListener("click", () => {
    if (reduced.matches) {
      window.showToast?.("Уменьшение движения задано в настройках устройства.");
      return;
    }
    preference = preference === "off" ? "auto" : "off";
    try { localStorage.setItem("zhidao.v4.motion", preference); } catch (_) { /* still works for this session */ }
    applyPreference();
  }));
  reduced.addEventListener("change", applyPreference);
  document.addEventListener("visibilitychange", applyPreference);

  const addresses = { schedule: "today", rating: "rep", shop: "supplies", cases: "scanner", tasks: "missions",
    more: "desktop", profile: "identity", collection: "collection", implants: "catalogue", "campus-map": "campus" };
  function enter(container) {
    if (!container || !enabled()) return;
    const panels = Array.from(container.children).filter(n => !n.hidden && !n.classList.contains("screen-intro"));
    panels.slice(0, 8).forEach((panel, index) => {
      panel.classList.remove("motion-enter");
      panel.style.setProperty("--enter-delay", `${Math.min(index * 30, 150)}ms`);
    });
    requestAnimationFrame(() => {
      if (!enabled() || container.hidden) return;
      panels.slice(0, 8).forEach(panel => panel.classList.add("motion-enter"));
    });
  }
  function screen(target) {
    document.getElementById("terminalAddress").textContent = `zhidao://${addresses[target] || "today"}`;
    enter(Array.from(document.querySelectorAll("[data-screen]")).find(n => n.dataset.screen === target));
  }
  window.addEventListener("zhidao:screen", event => screen(event.detail));
  window.addEventListener("zhidao:tab", event => enter(event.detail));
  let session = window.ZhidaoSession;
  function sessionLabel() {
    const authenticated = session?.mode === "authenticated";
    document.getElementById("terminalSession").textContent = !navigator.onLine ? "Нет сети · данные могут быть устаревшими" :
      authenticated ? "Личный контур участника" : "Просмотр оформления";
    if (!authenticated) document.querySelectorAll("[data-account-name]").forEach(n => { n.textContent = "Гость · просмотр оформления"; });
  }
  window.addEventListener("zhidao:auth", event => { session = event.detail; sessionLabel(); });
  window.addEventListener("online", sessionLabel); window.addEventListener("offline", sessionLabel);

  function beginScan(recovery = false) {
    activeScan?.finish();
    const host = document.getElementById("scanWindow"), coordinate = host.querySelector(".scanner-coordinate");
    let timer, waitTimer, wake, finished = false;
    const started = performance.now();
    const wait = ms => new Promise(resolve => { wake = resolve; waitTimer = setTimeout(resolve, ms); });
    function phase(name) {
      if (finished) return;
      host.dataset.scanPhase = name;
      const order = ["contact", "scan", "reveal"], current = order.indexOf(name);
      host.querySelectorAll("[data-scan-step]").forEach(n => {
        const step = order.indexOf(n.dataset.scanStep);
        n.classList.toggle("is-current", step === current);
        n.classList.toggle("is-complete", step < current);
      });
      coordinate.textContent = name === "reveal" ? "SIGNAL : RECEIVED" : recovery ? "RESTORE : REQUEST" : "SIGNAL : SEARCHING";
    }
    const controller = {
      skip() { clearTimeout(timer); clearTimeout(waitTimer); if (wake) { wake(); wake = null; } },
      async resolve() {
        if (enabled() && !recovery && !finished) await wait(Math.max(0, 750 - (performance.now() - started)));
        clearTimeout(timer);
        phase("reveal"); // This is called only after the server saved the actual outcome.
        if (enabled() && !recovery && !finished) await wait(650);
      },
      finish() {
        if (finished) return;
        controller.skip(); finished = true; delete host.dataset.scanPhase;
        host.querySelectorAll("[data-scan-step]").forEach(n => n.classList.remove("is-current", "is-complete"));
        coordinate.textContent = "SIGNAL : STANDBY";
        if (activeScan === controller) activeScan = null;
      }
    };
    activeScan = controller;
    phase("contact");
    if (enabled()) timer = setTimeout(() => phase("scan"), 250);
    return controller;
  }
  window.ZhidaoMotion = Object.freeze({ enabled, beginScan });
  applyPreference(); sessionLabel(); screen(root.dataset.currentScreen || "schedule");
}());
