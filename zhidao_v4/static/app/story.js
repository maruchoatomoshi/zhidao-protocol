"use strict";

/* Скрытые файлы (V4_GAMES.md §4.4).

   Фрагмент дня появляется в одном из мест интерфейса нулевых: сообщение от
   незнакомого контакта в нижней строке, файл в Корзине, окно ошибки на
   главной, битый ярлык, «Свойства» в профиле, сигнал на карте. Какой фрагмент
   открыт, разгадан ли он и какое слово он дал, решает сервер (story.py); ответы
   сюда не приходят, их сверяет только он.

   «Архив» появляется после первой разгадки: там собирается сообщение
   Архитектора и лежат все открытые файлы — на случай, если окно закрыли. */

(function () {
  const $ = (id) => document.getElementById(id);
  const REFRESH_MS = 60000;
  const WATCHED = ["schedule", "more", "profile", "campus-map", "story"];
  let session = window.ZhidaoSession || null;
  let data = null;
  let loadedAt = 0;
  let loading = null;
  let dialog = null;
  let busy = false;
  const shownErrors = new Set();

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const screen = () => document.documentElement.dataset.currentScreen;

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

  function refresh(force) {
    if (!signedIn()) {
      data = null;
      render();
      return Promise.resolve();
    }
    if (!force && data && Date.now() - loadedAt < REFRESH_MS) {
      render();
      return Promise.resolve();
    }
    if (!loading) {
      loading = api("/api/v4/story")
        .then((body) => { data = body.season_id ? body : null; loadedAt = Date.now(); render(); })
        .catch(() => { /* история подождёт следующего захода */ })
        .finally(() => { loading = null; });
    }
    return loading;
  }

  const current = () => (data ? data.fragments.find((f) => f.state === "open") : null);
  const waitingPlace = () => (data ? data.fragments.find((f) => f.state === "locked_place") : null);
  const placeName = (f) => (f.place ? `${f.place.name_ru || "место кампуса"}${f.place.name_zh ? ` ${f.place.name_zh}` : ""}` : "");

  // --- поверхности -----------------------------------------------------------------------

  function render() {
    const open = current();
    const surface = open ? open.surface : null;
    $("storyBinTile").hidden = surface !== "recycle_bin";
    $("storyLinkTile").hidden = surface !== "broken_shortcut";
    $("storyProperties").hidden = surface !== "properties";
    $("storyArchiveTile").hidden = !(data && data.fragments.some((f) => f.state === "solved"));
    renderFooter(surface === "icq" ? open : null);
    renderPlace(surface === "place" ? open : waitingPlace());
    if (surface === "error_window" && screen() === "schedule") popError(open);
    if (screen() === "story") renderArchive();
  }

  function renderFooter(fragment) {
    let link = $("storyMessageLink");
    if (!fragment) {
      link?.remove();
      return;
    }
    if (!link) {
      link = node("button", "story-message-link");
      link.id = "storyMessageLink";
      link.type = "button";
      link.addEventListener("click", () => openFragment(current()));
      document.querySelector(".terminal-footer")?.append(link);
    }
    link.textContent = `✉ 1 новое сообщение · ${fragment.sender || "неизвестный"}`;
  }

  function renderPlace(fragment) {
    const card = $("storyPlaceCard");
    if (!fragment) {
      card.hidden = true;
      return;
    }
    const open = fragment.state === "open";
    const parts = [
      node("span", "story-place-label", open ? "Сигнал найден" : "Слабый сигнал"),
      node("b", null, placeName(fragment)),
      node("p", null, open ? "Файл на этом месте открыт — его можно прочитать"
        : "Когда группа откроет это место на карте, файл станет доступен"),
    ];
    if (open) {
      const button = node("button", "btn btn-primary", "Открыть файл");
      button.type = "button";
      button.addEventListener("click", () => openFragment(fragment));
      parts.push(button);
    }
    card.replaceChildren(...parts);
    card.hidden = false;
  }

  function popError(fragment) {
    if (shownErrors.has(fragment.code) || document.querySelector(".story-error")) return;
    shownErrors.add(fragment.code);
    const box = node("div", "story-error");
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-label", fragment.title);
    const bar = node("div", "story-error-bar");
    bar.append(node("b", null, fragment.title));
    const body = node("div", "story-error-body");
    body.append(node("span", "story-error-icon", "!"), node("p", null, (fragment.body || [])[0] || "Неизвестная ошибка."));
    const actions = node("div", "story-error-actions");
    const more = node("button", "btn btn-primary", "Подробнее");
    more.type = "button";
    more.addEventListener("click", () => { box.remove(); openFragment(fragment); });
    const ok = node("button", "btn btn-secondary", "ОК");
    ok.type = "button";
    ok.addEventListener("click", () => box.remove());
    actions.append(more, ok);
    box.append(bar, body, actions);
    document.body.append(box);
  }

  // --- окно фрагмента -------------------------------------------------------------------

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "story-dialog";
    dialog.setAttribute("aria-labelledby", "storyDialogTitle");
    document.body.append(dialog);
    return dialog;
  }

  function openFragment(fragment) {
    if (!fragment) return;
    const d = ensureDialog();
    d.dataset.surface = fragment.surface;
    drawDialog(fragment);
    if (!d.open) d.showModal();
  }

  function drawDialog(fragment, wrong = false) {
    const bar = node("div", "story-titlebar");
    const title = node("h2", null, fragment.title);
    title.id = "storyDialogTitle";
    const close = node("button", null, "×");
    close.type = "button";
    close.setAttribute("aria-label", "Закрыть");
    close.addEventListener("click", () => dialog.close());
    bar.append(title, close);

    const body = node("div", "story-dialog-body");
    if (fragment.sender) body.append(node("p", "story-sender", `От: ${fragment.sender}`));
    (fragment.body || []).forEach((line) => body.append(node("p", "story-line", line)));
    if (fragment.state === "solved") {
      body.append(node("p", "story-question", fragment.question), node("p", "story-found", `Найдено слово: «${fragment.word}»`));
    } else {
      body.append(node("p", "story-question", fragment.question));
      const form = node("form", `story-form${wrong ? " is-wrong" : ""}`);
      const input = node("input");
      input.type = "text";
      input.maxLength = 80;
      input.autocomplete = "off";
      input.setAttribute("aria-label", "Ответ");
      const submit = node("button", "btn btn-primary", "Ответить");
      submit.type = "submit";
      form.append(input, submit);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        send(fragment, input.value);
      });
      body.append(form);
      const hint = node("details", "story-hint");
      hint.append(node("summary", null, "Подсказка"), node("p", null, fragment.hint || "Подсказки нет."));
      body.append(hint);
      if (wrong) body.append(node("p", "story-wrong", "Ошибка. Проверьте и попробуйте ещё раз"));
    }
    body.append(node("p", "case-message story-note"));
    dialog.replaceChildren(bar, body);
    if (wrong) dialog.querySelector("input")?.focus();
  }

  async function send(fragment, text) {
    if (busy || !text.trim()) return;
    busy = true;
    try {
      const result = await api(`/api/v4/story/${fragment.code}/answer`, { method: "POST", body: { answer: text } });
      if (!result.correct) {
        drawDialog(fragment, true);
        return;
      }
      if (window.ZhidaoSounds) window.ZhidaoSounds.play("rare");
      window.showToast?.(`Найдено слово: «${result.word}»`);
      await refresh(true);
      const solved = data && data.fragments.find((f) => f.code === fragment.code);
      if (solved && dialog.open) drawDialog(solved);
      if (result.complete && typeof window.showScreen === "function") {
        dialog.close();
        window.showScreen("story");
      }
    } catch (error) {
      const note = dialog.querySelector(".story-note");
      if (note) note.textContent = error.message;
    } finally {
      busy = false;
    }
  }

  // --- архив -------------------------------------------------------------------------------

  function stateText(fragment) {
    if (fragment.state === "solved") return `Слово: «${fragment.word}»`;
    if (fragment.state === "open") return "Ждёт ответа";
    if (fragment.state === "locked_place") return `Откройте на карте: ${placeName(fragment)}`;
    return "Сначала разгадайте предыдущий файл";
  }

  function renderArchive() {
    const message = $("storyMessage");
    const list = $("storyList");
    const finale = $("storyFinale");
    if (!data) {
      message.textContent = signedIn() ? "Архив пуст" : "Войдите, чтобы открыть архив";
      list.replaceChildren();
      finale.hidden = true;
      $("storyProgress").textContent = "—";
      return;
    }
    message.replaceChildren(...data.message.map((word) => node("span", word ? "story-word is-found" : "story-word", word || "____")));
    $("storyProgress").textContent = `${data.message.filter(Boolean).length} / ${data.total}`;
    list.replaceChildren(...data.fragments.map((fragment) => {
      const row = node("div", `story-row is-${fragment.state}`);
      const info = node("div", "story-row-info");
      info.append(node("b", null, `${String(fragment.number).padStart(2, "0")} · ${fragment.title}`), node("small", null, stateText(fragment)));
      row.append(info);
      if (fragment.state === "open" || fragment.state === "solved") {
        const button = node("button", "btn btn-secondary", fragment.state === "open" ? "Открыть" : "Перечитать");
        button.type = "button";
        button.addEventListener("click", () => openFragment(fragment));
        row.append(button);
      }
      return row;
    }));
    if (data.released < data.total) list.append(node("p", "case-message", "Следующий файл появится в 07:00."));
    finale.hidden = !data.complete;
    if (data.complete) {
      const portrait = node("img", "story-architect");
      portrait.src = "./assets/story/architect.webp";
      portrait.alt = "Архитектор";
      finale.replaceChildren(portrait, ...(data.epilogue || []).map((line) => node("p", "story-epilogue", line)),
        node("p", "story-signature", data.signature || ""));
    }
  }

  // --- подключение -----------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    data = null;
    loadedAt = 0;
    refresh(true);
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (!WATCHED.includes(event.detail)) return;
    if (event.detail === "story") renderArchive();
    refresh(false);
  });
  ["storyBinTile", "storyLinkTile", "storyProperties"].forEach((id) => {
    $(id).addEventListener("click", () => openFragment(current()));
  });
}());
