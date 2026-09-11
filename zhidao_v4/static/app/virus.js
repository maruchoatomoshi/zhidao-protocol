"use strict";

/* Вирус Протокола на экране (V4_GAMES.md §4.7).

   Заражён ли человек, решает сервер; здесь — только смешные последствия:
   дрожащие иконки, съехавший рабочий стол и окна ошибок в духе нулевых.
   Дрожание уважает настройку анимаций. Сам «вирус» ничего не ломает: ни одна
   кнопка не перестаёт работать.

   Экран «Антивирус»: тест из пяти китайских слов (лечит бесплатно), антивирус
   без теста и фаервол за ★ — второе касание и ключ повтора, как у витрины.
   В админке Архитектор выпускает первый вирус. */

(function () {
  const $ = (id) => document.getElementById(id);
  const LINES = [
    "Обнаружен файл 爱你.vbs. Открыть? Он, кажется, уже открыт.",
    "Иконки решили потанцевать. Протокол не возражает.",
    "Ошибка 0x4E2D: в системе слишком много счастья.",
    "Рабочий стол слегка поехал. Это нормально. Наверное.",
    "Вирус передаёт привет Архитектору и просит не лечиться.",
    "Сохранить изменения в «дневник.txt»? Ой, у вас же бумажный.",
  ];
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let state = null;
  let test = null;            // { questions, picks }
  let armed = null;
  let busy = false;
  let popupTimer = null;
  let expireTimer = null;
  const pending = new Map();  // антивирус/фаервол → ключ повтора

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = (name) => document.documentElement.dataset.currentScreen === name;
  const setNote = (text) => { $("virusNote").textContent = text || ""; };
  const newKey = (kind) => `${kind}-${window.crypto && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

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

  // --- эффекты -------------------------------------------------------------------------

  function hidePopup() { $("virusPopup").hidden = true; }

  function showPopup() {
    if (!state || !state.infected) return;
    $("virusPopupText").textContent = LINES[Math.floor(Math.random() * LINES.length)];
    $("virusPopup").hidden = false;
  }

  function apply(infected) {
    const root = document.documentElement;
    clearInterval(popupTimer);
    popupTimer = null;
    if (infected) {
      root.dataset.virus = "on";
      // Первое окно не сразу, дальше — не чаще раза в минуту: смешно, а не мешает.
      setTimeout(showPopup, 20000);
      popupTimer = setInterval(showPopup, 75000);
    } else {
      delete root.dataset.virus;
      hidePopup();
    }
  }

  // --- экран антивируса ------------------------------------------------------------------

  function formatLeft(seconds) {
    // Сначала округляем до минут, потом делим на часы: иначе выходит «5 ч 60 мин».
    const total = Math.max(1, Math.ceil(seconds / 60));
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    if (!hours) return `${minutes} мин`;
    return minutes ? `${hours} ч ${minutes} мин` : `${hours} ч`;
  }

  function drawStatus() {
    const host = $("virusStatus");
    host.replaceChildren();
    if (!state) return;
    const badge = $("virusBadge");
    if (state.infected) {
      badge.textContent = "ЗАРАЖЕНО";
      host.append(node("b", "virus-state is-infected", "Система заражена"),
        node("span", null, `Без лечения пройдёт через ${formatLeft(state.seconds_left)}.`));
    } else {
      badge.textContent = "ЧИСТО";
      host.append(node("b", "virus-state is-clean", "Система чиста"));
      if (!state.firewall) host.append(node("span", null, "Фаервол защитит до утра."));
    }
    if (state.firewall) {
      // Время сезона, а не телефона: фаервол гаснет в 07:00 по поясу поездки.
      const until = new Date(state.firewall_until).toLocaleTimeString("ru-RU",
        { hour: "2-digit", minute: "2-digit", timeZone: (season && season.timezone) || "Asia/Shanghai" });
      host.append(node("span", "virus-firewall", `Фаервол включён до ${until}`));
    }
    $("virusStars").textContent = `У ВАС ${state.stars}★`;
    const active = state.season_status === "active";
    $("virusTestStart").hidden = !state.infected || Boolean(test);
    $("virusAntivirus").hidden = !state.infected;
    $("virusFirewall").hidden = state.firewall;
    $("virusTestStart").disabled = busy || !active;
    $("virusAntivirus").disabled = busy || !active || state.stars < state.prices.antivirus;
    $("virusFirewall").disabled = busy || !active || state.stars < state.prices.firewall;
    $("virusAntivirus").textContent = armed === "antivirus" ? `Точно? −${state.prices.antivirus}★` : `Антивирус без теста · ${state.prices.antivirus}★`;
    $("virusFirewall").textContent = armed === "firewall" ? `Точно? −${state.prices.firewall}★` : `Фаервол до 07:00 · ${state.prices.firewall}★`;
  }

  function drawTest() {
    const host = $("virusTest");
    host.hidden = !test;
    host.replaceChildren();
    if (!test) return;
    host.append(node("span", "spy-label", `Антивирус: переведите слова, нужно ${state.test.pass} из ${state.test.size}`));
    test.questions.forEach((question, index) => {
      const box = node("div", "virus-question");
      box.append(node("b", "virus-zh", question.zh), node("small", null, question.pinyin));
      const options = node("div", "virus-options");
      question.options.forEach((option, choice) => {
        const b = node("button", "btn btn-secondary", option);
        b.type = "button";
        b.setAttribute("aria-pressed", String(test.picks[index] === choice));
        b.addEventListener("click", () => { test.picks[index] = choice; drawTest(); });
        options.append(b);
      });
      box.append(options);
      host.append(box);
    });
    const submit = node("button", "btn btn-primary", "Проверить");
    submit.type = "button";
    submit.disabled = busy || test.picks.some((pick) => pick == null);
    submit.addEventListener("click", submitTest);
    host.append(submit);
  }

  async function refresh() {
    clearTimeout(expireTimer);
    if (!signedIn()) {
      state = null;
      apply(false);
      return;
    }
    try {
      const list = await seasons();
      season = list.find((s) => s.is_member && s.status === "active") || list.find((s) => s.is_member) || null;
      if (!season) {
        state = null;
        apply(false);
        if (onScreen("antivirus")) setNote("Антивирус заработает, когда вас включат в сезон.");
        return;
      }
      state = await api(`/api/v4/seasons/${season.id}/virus`);
      apply(state.infected);
      if (state.infected) expireTimer = setTimeout(refresh, (state.seconds_left + 2) * 1000);
      drawStatus();
      drawTest();
    } catch (error) {
      if (onScreen("antivirus")) setNote(error.message);
    }
  }

  async function startTest() {
    if (busy || !season) return;
    busy = true;
    setNote("");
    try {
      const body = await api(`/api/v4/seasons/${season.id}/virus/test`, { method: "POST" });
      test = { questions: body.questions, picks: body.questions.map(() => null) };
    } catch (error) {
      setNote(error.message);
    } finally {
      busy = false;
      drawStatus();
      drawTest();
    }
  }

  async function submitTest() {
    if (busy || !test) return;
    busy = true;
    try {
      const result = await api(`/api/v4/seasons/${season.id}/virus/test/answer`, { method: "POST", body: { answers: test.picks } });
      test = null;
      setNote(result.cured
        ? `Верно ${result.correct} из ${result.size}. Вирус удалён!`
        : `Верно ${result.correct} из ${result.size}, нужно ${result.pass}. Попробуйте новый тест.`);
      if (result.cured && window.ZhidaoSounds) window.ZhidaoSounds.play("win");
    } catch (error) {
      test = null;
      setNote(error.message);
    } finally {
      busy = false;
      await refresh();
    }
  }

  async function buy(kind) {
    if (busy || !state) return;
    if (armed !== kind) {
      armed = kind;
      drawStatus();
      return;
    }
    armed = null;
    busy = true;
    drawStatus();
    const key = pending.get(kind) || newKey(kind);
    pending.set(kind, key);
    try {
      await api(`/api/v4/seasons/${season.id}/virus/${kind}`, { method: "POST", key });
      pending.delete(kind);
      setNote(kind === "antivirus" ? "Вирус удалён." : "Фаервол включён до утра: вирусы собеседников отскочат.");
      if (window.ZhidaoSounds) window.ZhidaoSounds.play("buy");
    } catch (error) {
      if (error.status) pending.delete(kind);
      setNote(error.status ? error.message : "Нет связи. Нажмите ещё раз — звёзды дважды не спишутся.");
    } finally {
      busy = false;
      await refresh();
    }
  }

  // --- админка: выпуск вируса -----------------------------------------------------------

  function isArchitect() {
    return signedIn() && (session.roles || []).some((role) =>
      ["architect", "system_admin"].includes(role.code) && role.season_id == null);
  }

  async function loadRelease() {
    const box = $("virusAdmin");
    box.hidden = !isArchitect();
    if (box.hidden) return;
    try {
      const list = await seasons();
      const target = list.find((s) => s.can_manage && s.status === "active") || list.find((s) => s.can_manage);
      if (!target) {
        $("virusReleaseStatus").textContent = "Нет сезона для выпуска.";
        return;
      }
      box.dataset.season = String(target.id);
      const roster = await api(`/api/v4/seasons/${target.id}/cases/admin/roster`);
      const select = $("virusReleaseTarget");
      select.replaceChildren(...roster.members.map((member) => new Option(member.display_name, String(member.id))));
    } catch (error) {
      $("virusReleaseStatus").textContent = error.message;
    }
  }

  let releaseArmed = false;
  async function release(event) {
    event.preventDefault();
    const seasonId = $("virusAdmin").dataset.season;
    const select = $("virusReleaseTarget");
    if (!seasonId || !select.value) return;
    const name = select.options[select.selectedIndex].text;
    if (!releaseArmed) {
      releaseArmed = true;
      $("virusReleaseButton").textContent = "Точно?";
      $("virusReleaseStatus").textContent = `Нажмите ещё раз, чтобы заразить: ${name}.`;
      return;
    }
    releaseArmed = false;
    $("virusReleaseButton").textContent = "Выпустить";
    try {
      await api(`/api/v4/seasons/${seasonId}/virus/release`, { method: "POST", body: { account_id: Number(select.value) } });
      $("virusReleaseStatus").textContent = `Вирус выпущен: ${name}. Дальше он расходится сам.`;
    } catch (error) {
      $("virusReleaseStatus").textContent = error.message;
    }
  }

  // --- подключение --------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    test = null;
    armed = null;
    pending.clear();
    refresh();
    if (onScreen("admin")) loadRelease();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "antivirus") refresh();
    if (event.detail === "admin") loadRelease();
  });
  window.addEventListener("zhidao:tab", (event) => {
    if (event.detail && event.detail.dataset.tabPanel === "admin:economy") loadRelease();
  });
  window.addEventListener("zhidao:virus-check", refresh);

  $("virusTestStart").addEventListener("click", startTest);
  $("virusAntivirus").addEventListener("click", () => buy("antivirus"));
  $("virusFirewall").addEventListener("click", () => buy("firewall"));
  $("virusPopupClose").addEventListener("click", hidePopup);
  $("virusPopupOk").addEventListener("click", hidePopup);
  $("virusPopupCure").addEventListener("click", () => {
    hidePopup();
    if (typeof window.showScreen === "function") window.showScreen("antivirus");
  });
  $("virusReleaseForm").addEventListener("submit", release);
}());
