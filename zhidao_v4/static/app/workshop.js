"use strict";

/* Мастерская дубликатов (V4_GAMES.md §4.8).

   Четыре одинаковых редких импланта → один новый имплант, гарантированно и
   без сбора звёзд. Какой предмет выйдет, решает не сервер вслепую — у
   каждого базового импланта ровно один целевой, экран его просто показывает
   заранее. Спрашивает второе касание и отправляет ключ повтора, чтобы обрыв
   связи не переплавил дважды. */

(function () {
  const $ = (id) => document.getElementById(id);
  const ART = {
    implant_guanxi: "guanxi", implant_panda: "panda", implant_shaolin: "shaolin",
    implant_linguasoft: "linguasoft", implant_caishen: "caishen", implant_qilin: "qilin",
    implant_terracota: "terracota", implant_red_dragon: "honglong",
    implant_jade_warden: "jade_warden", implant_diplomat: "diplomat", implant_golden_nexus: "golden_nexus",
  };
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let state = null;
  let busy = false;
  let armed = null;
  const pending = new Map();   // код предмета → ключ повтора неподтверждённой переплавки

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "workshop";
  const setNote = (text) => { $("workshopNote").textContent = text || ""; };
  const newKey = () => `craft-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const init = {
      method: options.method || "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    };
    if (init.method === "POST") {
      const cookie = document.cookie.split("; ").find((v) => v.startsWith("zhidao_v4_csrf="));
      init.headers["X-CSRF-Token"] = cookie ? decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) : "";
      init.headers["Content-Type"] = "application/json";
      if (options.key) init.headers["X-Idempotency-Key"] = options.key;
      init.body = JSON.stringify(options.body || {});
    }
    try {
      const response = await fetch(path, init);
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof body.detail === "string" ? body.detail : "Запрос отклонён.");
        error.status = response.status;
        throw error;
      }
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Сервер не ответил. Проверьте связь.");
      if (error instanceof TypeError) throw new Error("Нет связи с сервером.");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function seasons() {
    if (!contextPromise) {
      contextPromise = api("/api/v4/cases/context")
        .then((body) => body.seasons || [])
        .catch((error) => { contextPromise = null; throw error; });
    }
    return contextPromise;
  }

  function art(code, className) {
    const box = node("span", className);
    if (ART[code]) {
      const image = node("img");
      image.src = `./assets/implants/${ART[code]}.webp`;
      image.alt = "";
      image.loading = "lazy";
      box.append(image);
    } else {
      box.textContent = code === "fate_guard" ? "↻" : "◷";
    }
    return box;
  }

  // --- рецепты --------------------------------------------------------------------------

  function drawRecipes() {
    const host = $("workshopRecipes");
    host.replaceChildren();
    $("workshopStars").textContent = state ? `У ВАС ${state.stars}★` : "—";
    if (!state) return;
    if (!state.recipes.length) {
      host.append(node("p", "case-message", "Пока нечего переплавлять. Одинаковые предметы приходят из кейсов и обменов."));
      return;
    }
    const active = state.season_status === "active";
    for (const recipe of state.recipes) {
      const card = node("article", "workshop-recipe");
      const info = node("div", "workshop-info");
      info.append(node("b", null, recipe.name_ru),
        node("small", null, `у вас ×${recipe.quantity}`),
        node("p", "workshop-route", `${state.input} → 1 · ${recipe.to_name_ru}`));
      const button = node("button", recipe.ready ? "btn btn-primary" : "btn btn-secondary");
      button.type = "button";
      if (!recipe.ready) {
        button.disabled = true;
        button.textContent = `Нужно ещё ${recipe.missing} шт.`;
      } else {
        button.textContent = armed === recipe.code ? `Точно? −${state.input} шт.` : "Переплавить";
        button.disabled = busy || !active;
        button.addEventListener("click", () => craft(recipe));
      }
      card.append(art(recipe.code, "workshop-art"), info, button);
      host.append(card);
    }
  }

  async function refresh() {
    if (!signedIn()) {
      state = null;
      drawRecipes();
      $("workshopRecipes").replaceChildren(node("p", "case-message", "Войдите, чтобы открыть мастерскую."));
      return;
    }
    try {
      const list = await seasons();
      season = list.find((s) => s.is_member && s.status === "active") || list.find((s) => s.is_member) || null;
      if (!season) {
        state = null;
        drawRecipes();
        $("workshopRecipes").replaceChildren(node("p", "case-message", "Мастерская заработает, когда вас включат в сезон."));
        return;
      }
      state = await api(`/api/v4/seasons/${season.id}/workshop`);
      drawRecipes();
    } catch (error) {
      setNote(error.message);
    }
  }

  // --- переплавка -------------------------------------------------------------------------

  function showResult(result) {
    $("workshopForge").hidden = true;
    const host = $("workshopResult");
    host.replaceChildren(
      art(result.got.code, "workshop-result-art"),
      node("span", "spy-label", result.got.name_zh || ""),
      node("h3", null, result.got.name_ru),
      node("p", "spy-hint", `Ушло: ${result.gave.count} × «${result.gave.name_ru}». У вас ${result.stars}★.`));
    host.hidden = false;
    host.scrollIntoView({ block: "nearest", behavior: window.ZhidaoMotion?.enabled() ? "smooth" : "auto" });
  }

  async function craft(recipe) {
    if (busy || !season) return;
    if (armed !== recipe.code) {
      armed = recipe.code;
      drawRecipes();
      return;
    }
    armed = null;
    busy = true;
    setNote("");
    $("workshopResult").hidden = true;
    drawRecipes();
    const key = pending.get(recipe.code) || newKey();
    pending.set(recipe.code, key);
    try {
      const result = await api(`/api/v4/seasons/${season.id}/workshop/craft`,
        { method: "POST", key, body: { item_code: recipe.code } });
      pending.delete(recipe.code);
      showResult(result);
      if (!result.replayed && !document.hidden) {
        window.ZhidaoRetro?.reveal($("workshopResult"));
        if (window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
      }
    } catch (error) {
      $("workshopForge").hidden = true;
      if (error.status) pending.delete(recipe.code);
      setNote(error.status ? error.message : "Нет связи. Нажмите ещё раз — дважды переплавка не пройдёт.");
    } finally {
      busy = false;
      await refresh();
    }
  }

  // --- подключение ----------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    state = null;
    armed = null;
    pending.clear();
    if (onScreen()) refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail !== "workshop") return;
    setNote("");
    refresh();
  });
}());
