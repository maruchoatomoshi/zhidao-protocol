"use strict";

/* Встречи: рукопожатие двух телефонов и пазл (V4_GAMES.md §3.2, §4.6).

   Один показывает код из шести цифр, второй его вводит — и оба получают
   кусок картинки. Какой кусок, решает сервер; экран только рисует пазл и ждёт
   ответа. Пока код показан, телефон раз в полторы секунды спрашивает, не
   ввёл ли его кто-нибудь, — так показавший тоже видит, что встреча случилась. */

(function () {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 1500;
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let season = null;
  let data = null;
  let offer = null;          // { code, ends }
  let pollTimer = null;
  let tickTimer = null;
  let highlight = null;      // { puzzle, piece } — только что полученный кусок
  let busy = false;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onScreen = () => document.documentElement.dataset.currentScreen === "meet";
  const setStatus = (text) => { $("meetStatus").textContent = text || ""; };

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

  function seasons() {
    if (!contextPromise) {
      contextPromise = api("/api/v4/cases/context")
        .then((body) => body.seasons || [])
        .catch((error) => { contextPromise = null; throw error; });
    }
    return contextPromise;
  }

  // --- пазл ---------------------------------------------------------------------------

  function drawGrid(puzzle) {
    const grid = $("meetGrid");
    grid.replaceChildren();
    grid.style.setProperty("--grid", String(puzzle.grid));
    grid.style.aspectRatio = puzzle.aspect || "1 / 1";
    const owned = new Set(puzzle.pieces);
    const total = puzzle.grid * puzzle.grid;
    for (let piece = 0; piece < total; piece += 1) {
      const tile = node("div", "meet-tile");
      if (owned.has(piece)) {
        const col = piece % puzzle.grid;
        const row = Math.floor(piece / puzzle.grid);
        const step = 100 / (puzzle.grid - 1);
        tile.style.backgroundImage = `url("${puzzle.image}")`;
        tile.style.backgroundSize = `${puzzle.grid * 100}% ${puzzle.grid * 100}%`;
        tile.style.backgroundPosition = `${col * step}% ${row * step}%`;
        if (highlight && highlight.puzzle === puzzle.code && highlight.piece === piece) tile.classList.add("is-new");
      } else {
        tile.classList.add("is-missing");
        tile.textContent = "?";
      }
      tile.setAttribute("aria-hidden", "true");
      grid.append(tile);
    }
    grid.setAttribute("role", "img");
    grid.setAttribute("aria-label", `${puzzle.title_ru}: собрано ${puzzle.pieces.length} из ${total}`);
    $("meetPuzzleTitle").textContent = puzzle.title_ru;
    $("meetProgress").textContent = `${puzzle.pieces.length} / ${total}`;
  }

  function drawGallery() {
    const host = $("meetGallery");
    host.replaceChildren();
    const done = data.puzzles.filter((p) => p.complete);
    if (!done.length) {
      host.append(node("p", "case-message", "Собранные картинки появятся здесь."));
      return;
    }
    for (const puzzle of done) {
      const item = node("div", "meet-thumb");
      const picture = node("span");
      picture.style.backgroundImage = `url("${puzzle.image}")`;
      picture.style.aspectRatio = puzzle.aspect || "1 / 1";
      picture.setAttribute("role", "img");
      picture.setAttribute("aria-label", puzzle.title_ru);
      item.append(picture, node("b", null, puzzle.title_ru));
      host.append(item);
    }
  }

  function draw() {
    const current = data.puzzles.find((p) => p.code === data.current) || data.puzzles[data.puzzles.length - 1];
    drawGrid(current);
    drawGallery();
    $("meetToday").textContent = `СЕГОДНЯ ВСТРЕЧ: ${data.met_today}`;
    const active = data.season_status === "active";
    $("meetShow").disabled = !active || busy;
    $("meetSubmit").disabled = !active || busy;
    if (!data.current) setStatus("Все пазлы сезона собраны. Встречи всё равно засчитываются — скоро будут новые картинки.");
  }

  async function load() {
    if (!signedIn()) {
      $("meetGrid").replaceChildren();
      setStatus("Войдите, чтобы собирать пазл из встреч.");
      $("meetShow").disabled = true;
      $("meetSubmit").disabled = true;
      return;
    }
    try {
      const list = await seasons();
      season = list.find((s) => s.is_member && s.status === "active") || list.find((s) => s.is_member) || null;
      if (!season) {
        setStatus("Пазл откроется, когда вас включат в сезон.");
        $("meetShow").disabled = true;
        $("meetSubmit").disabled = true;
        return;
      }
      data = await api(`/api/v4/seasons/${season.id}/puzzles`);
      draw();
    } catch (error) {
      setStatus(error.message);
    }
  }

  // «Встреча: Милана», а не «встреча с Милана»: склонять имена код не умеет.
  function describe(result) {
    if (!result.piece) return `Встреча: ${result.partner}. Засчитана — все пазлы уже собраны.`;
    const piece = result.piece;
    return piece.complete
      ? `Встреча: ${result.partner}. Последний кусок — «${piece.title_ru}» собран!`
      : `Встреча: ${result.partner}. Новый кусок, ${piece.have} из ${piece.total}.`;
  }

  async function met(result) {
    highlight = result.piece ? { puzzle: result.piece.puzzle, piece: result.piece.piece } : null;
    if (window.ZhidaoSounds) window.ZhidaoSounds.play(result.piece && result.piece.complete ? "win" : "buy");
    await load();
    setStatus(describe(result));
  }

  // --- показать код ----------------------------------------------------------------------

  function stopOffer() {
    clearInterval(pollTimer);
    clearInterval(tickTimer);
    pollTimer = null;
    tickTimer = null;
    offer = null;
    $("meetOffer").hidden = true;
  }

  function tickOffer() {
    if (!offer) return;
    const left = Math.max(0, Math.ceil((offer.ends - performance.now()) / 1000));
    $("meetOfferLeft").textContent = left ? `Код действует ещё ${left} с` : "Код истёк";
    if (!left) {
      stopOffer();
      setStatus("Код истёк. Покажите новый, когда будете рядом с человеком.");
    }
  }

  async function pollOffer() {
    if (!offer || document.hidden) return;
    try {
      const status = await api(`/api/v4/seasons/${season.id}/meet/offer/${offer.code}`);
      if (status.state === "met") {
        stopOffer();
        met(status);
      } else if (status.state === "expired") {
        stopOffer();
        setStatus("Код истёк. Покажите новый, когда будете рядом с человеком.");
      }
    } catch (_) {
      // Связь мигнула — спросим на следующем круге.
    }
  }

  async function showCode() {
    if (busy || !season) return;
    busy = true;
    setStatus("");
    try {
      const body = await api(`/api/v4/seasons/${season.id}/meet/offer`, { method: "POST" });
      offer = { code: body.code, ends: performance.now() + body.expires_in * 1000 };
      $("meetOfferCode").textContent = `${body.code.slice(0, 3)} ${body.code.slice(3)}`;
      $("meetOffer").hidden = false;
      clearInterval(pollTimer);
      clearInterval(tickTimer);
      pollTimer = setInterval(pollOffer, POLL_MS);
      tickTimer = setInterval(tickOffer, 250);
      tickOffer();
    } catch (error) {
      setStatus(error.message);
    } finally {
      busy = false;
    }
  }

  async function enterCode(event) {
    event.preventDefault();
    if (busy || !season) return;
    const code = $("meetCode").value.replace(/\D/g, "");
    if (code.length !== 6) {
      setStatus("Код встречи — шесть цифр.");
      return;
    }
    busy = true;
    try {
      const result = await api(`/api/v4/seasons/${season.id}/meet/accept`, { method: "POST", body: { code } });
      $("meetCode").value = "";
      await met(result);
    } catch (error) {
      setStatus(error.message);
    } finally {
      busy = false;
    }
  }

  // --- подключение ---------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    data = null;
    highlight = null;
    stopOffer();
    if (onScreen()) load();
  });
  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "meet") load();
    else stopOffer();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && offer) pollOffer(); });

  $("meetShow").addEventListener("click", showCode);
  $("meetForm").addEventListener("submit", enterCode);
  $("meetCode").addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
  });
  $("meetOfferCancel").addEventListener("click", stopOffer);
}());
