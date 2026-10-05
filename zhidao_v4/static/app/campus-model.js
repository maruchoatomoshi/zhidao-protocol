"use strict";

/* Макет кампуса: объёмная иллюстрация в стеклянном колпаке.

   Это не карта: здания и расстояния условные (модель из Blender, v02), поэтому
   на экране прямо так и написано. Настоящая карта кампуса лежит отдельно
   (campus-map.js). Тяжёлая часть -- three.js, 0.6 МБ, и сама модель -- грузится
   только при первом открытии экрана. Сборка бандла: tools/diorama. */

(function () {
  const DIORAMA_SCRIPT = "./campus-diorama.js?v=17aa5c160f";
  const DIORAMA_MODEL = "./assets/campus/campus-diorama.glb?v=4d2e20d111";

  const MOODS = {
    morning: "Утро: низкое тёплое солнце, длинные тени.",
    day: "День: яркий свет, весь кампус как на ладони.",
    evening: "Вечер: закат, в окнах загорается свет.",
    night: "Ночь: светятся окна корпусов и общежитий.",
  };
  const VIEWS = {
    overview: "Весь кампус под колпаком. Крутите пальцем, щипком приближайте.",
    plaza: "Центральная площадь с фонтаном и высотным корпусом.",
    sports: "Стадион с беговой дорожкой и спортивный корпус.",
    dorms: "Общежития и баскетбольные площадки.",
    coast: "Берег и набережная.",
  };

  const $ = (id) => document.getElementById(id);
  let controller = null;
  let loading = null;
  let mood = "day";
  let view = "overview";

  function motionOn() {
    const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return !reduced && (!window.ZhidaoMotion || window.ZhidaoMotion.enabled());
  }

  function hasWebGL() {
    try {
      const canvas = document.createElement("canvas");
      return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
    } catch (_) {
      return false;
    }
  }

  function loadScript() {
    if (window.ZhidaoDiorama) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = DIORAMA_SCRIPT;
      tag.onload = resolve;
      tag.onerror = () => reject(new Error("script"));
      document.head.append(tag);
    });
  }

  function setStatus(text, busy) {
    const status = $("dioramaStatus");
    if (!status) return;
    status.textContent = text || "";
    status.hidden = !text;
    status.dataset.busy = busy ? "1" : "0";
  }

  function caption() {
    const text = $("dioramaCaption");
    if (text) text.textContent = `${VIEWS[view]} ${MOODS[mood]}`;
  }

  function pressed(group, value) {
    document.querySelectorAll(`[data-diorama-${group}]`).forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset[`diorama${group[0].toUpperCase()}${group.slice(1)}`] === value));
    });
  }

  function bind() {
    document.querySelectorAll("[data-diorama-mood]").forEach((button) => {
      button.addEventListener("click", () => {
        mood = button.dataset.dioramaMood;
        pressed("mood", mood);
        $("dioramaStage").dataset.mood = mood;
        if (controller) controller.setMood(mood);
        caption();
      });
    });
    document.querySelectorAll("[data-diorama-view]").forEach((button) => {
      button.addEventListener("click", () => {
        view = button.dataset.dioramaView;
        pressed("view", view);
        if (controller) controller.setView(view);
        caption();
      });
    });
    const spin = $("dioramaSpin");
    if (spin) {
      spin.addEventListener("click", () => {
        const on = spin.getAttribute("aria-pressed") !== "true";
        spin.setAttribute("aria-pressed", String(on));
        if (controller) controller.setSpin(on);
      });
    }
  }

  async function init() {
    if (controller || loading) return;
    const stage = $("dioramaStage");
    const holder = $("dioramaView");
    if (!stage || !holder) return;
    if (!hasWebGL()) {
      setStatus("На этом устройстве не получается показать объёмную сцену. Настоящая карта кампуса есть в разделе «Карта».", false);
      return;
    }
    setStatus("Собираем макет…", true);
    loading = (async () => {
      try {
        await loadScript();
        controller = await window.ZhidaoDiorama.mount(holder, {
          model: DIORAMA_MODEL,
          motion: motionOn(),
          skyTarget: stage,
          onProgress: (share) => setStatus(`Собираем макет… ${Math.round(share * 100)}%`, true),
        });
        setStatus("", false);
        stage.dataset.ready = "1";
        controller.setMood(mood);
        controller.setView(view);
      } catch (_) {
        setStatus("Не удалось загрузить макет. Проверьте связь и откройте экран ещё раз.", false);
      } finally {
        loading = null;
      }
    })();
  }

  window.initCampusModel = init;
  bind();
  caption();
}());
