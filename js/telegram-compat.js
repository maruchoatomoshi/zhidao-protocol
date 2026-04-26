(function () {
  const tg = window.Telegram && window.Telegram.WebApp;

  function isIOS() {
    const platform = tg && tg.platform ? String(tg.platform).toLowerCase() : "";
    const ua = navigator.userAgent || "";
    return platform.includes("ios") || /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function px(value) {
    const num = Number(value);
    return Number.isFinite(num) && num > 0 ? `${num}px` : "0px";
  }

  function getViewportHeight() {
    if (tg && Number(tg.viewportStableHeight) > 0) {
      return Number(tg.viewportStableHeight);
    }

    if (tg && Number(tg.viewportHeight) > 0) {
      return Number(tg.viewportHeight);
    }

    if (window.visualViewport && Number(window.visualViewport.height) > 0) {
      return Number(window.visualViewport.height);
    }

    return window.innerHeight || document.documentElement.clientHeight || 0;
  }

  function syncTelegramViewport() {
    const height = getViewportHeight();

    if (height > 0) {
      document.documentElement.style.setProperty("--app-height", `${height}px`);
      document.documentElement.style.setProperty("--tg-viewport-height", `${height}px`);
    }

    const width = window.visualViewport && Number(window.visualViewport.width) > 0
      ? Number(window.visualViewport.width)
      : window.innerWidth || document.documentElement.clientWidth || 0;

    if (width > 0) {
      document.documentElement.style.setProperty("--app-width", `${width}px`);
    }

    const safe = tg && tg.safeAreaInset ? tg.safeAreaInset : {};
    const contentSafe = tg && tg.contentSafeAreaInset ? tg.contentSafeAreaInset : {};

    const top = Math.max(Number(safe.top) || 0, Number(contentSafe.top) || 0);
    const right = Math.max(Number(safe.right) || 0, Number(contentSafe.right) || 0);
    const bottom = Math.max(Number(safe.bottom) || 0, Number(contentSafe.bottom) || 0);
    const left = Math.max(Number(safe.left) || 0, Number(contentSafe.left) || 0);

    document.documentElement.style.setProperty("--tg-safe-top", px(top));
    document.documentElement.style.setProperty("--tg-safe-right", px(right));
    document.documentElement.style.setProperty("--tg-safe-bottom", px(bottom));
    document.documentElement.style.setProperty("--tg-safe-left", px(left));
  }

  function initTelegramCompat() {
    const ios = isIOS();
    document.documentElement.classList.toggle("tg-webapp", Boolean(tg));
    document.documentElement.classList.toggle("tg-ios", ios);
    document.body.classList.toggle("tg-webapp", Boolean(tg));
    document.body.classList.toggle("tg-ios", ios);

    if (tg) {
      try { tg.ready(); } catch (e) {}
      try { tg.expand(); } catch (e) {}
      try {
        if (typeof tg.onEvent === "function") {
          tg.onEvent("viewportChanged", syncTelegramViewport);
          tg.onEvent("safeAreaChanged", syncTelegramViewport);
          tg.onEvent("contentSafeAreaChanged", syncTelegramViewport);
        }
      } catch (e) {}
    }

    syncTelegramViewport();

    window.addEventListener("resize", syncTelegramViewport);
    window.addEventListener("orientationchange", function () {
      setTimeout(syncTelegramViewport, 250);
      setTimeout(syncTelegramViewport, 700);
    });

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncTelegramViewport);
      window.visualViewport.addEventListener("scroll", syncTelegramViewport);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTelegramCompat);
  } else {
    initTelegramCompat();
  }

  window.syncTelegramViewport = syncTelegramViewport;
})();
