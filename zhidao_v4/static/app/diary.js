"use strict";

/* Дневник: оценка бумажного дневника (V4_GAMES.md, V4_DECISIONS §1).

   Две половины одного экрана:
   - вожатый в админке ставит за день 0–3 звезды и бонус каждому участнику;
   - участник на экране REP видит свои оценки и общий рейтинг дневников.

   Награды считает сервер по diary.json; здесь их только показывают. Правка
   несёт ревизию, которую видел вожатый: если оценку уже поменял другой
   вожатый, сервер отвечает 409, и лист перечитывается, а не перезаписывает
   чужую оценку. Потерянный ответ повторяется с тем же ключом — награда не
   начислится дважды. */

(function () {
  const $ = (id) => document.getElementById(id);
  let session = window.ZhidaoSession || null;
  let contextPromise = null;
  let rules = null;
  let sheet = null;
  let sheetSeason = null;
  const pending = new Map();   // account_id → { key, body } неподтверждённой правки
  const busyRows = new Set();

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function signedIn() { return Boolean(session && session.mode === "authenticated"); }

  function newKey() {
    if (window.crypto && crypto.randomUUID) return `diary-${crypto.randomUUID()}`;
    return `diary-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

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
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const detail = Array.isArray(data.detail) ? "Запрос заполнен неверно." : data.detail;
        const error = new Error(typeof detail === "string" ? detail : "Запрос отклонён.");
        error.status = response.status;
        throw error;
      }
      return data;
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
        .then((data) => data.seasons || [])
        .catch((error) => { contextPromise = null; throw error; });
    }
    return contextPromise;
  }

  function pick(list, predicate) {
    return list.find((s) => predicate(s) && s.status === "active") || list.find(predicate) || null;
  }

  async function loadRules() {
    if (!rules) rules = await api("/api/v4/diary/rules");
    return rules;
  }

  const starsText = (n) => "★".repeat(n) + "☆".repeat(3 - n);
  const shortDate = (iso) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
  const signed = (n) => (n > 0 ? `+${n}` : String(n));
  const visible = (panel) => {
    const el = document.querySelector(`[data-tab-panel="${panel}"]`);
    return Boolean(el && !el.hidden);
  };
  const onScreen = (name) => document.documentElement.dataset.currentScreen === name;

  // --- участник: мои оценки и рейтинг -------------------------------------------

  function stat(label, value) {
    const box = node("div", "diary-stat");
    box.append(node("span", null, label), node("b", null, String(value)));
    return box;
  }

  function drawMine(mine) {
    const head = node("div", "diary-mine-head");
    head.append(stat("Звёзд", mine.total_stars), stat("Дней", mine.days_rated),
      stat("Бонусов", mine.bonus_count), stat("REP", mine.rep));
    const days = node("div", "diary-days");
    if (!mine.items.length) {
      days.append(node("p", "diary-note", "Оценок пока нет. Их ставит вожатый по бумажному дневнику."));
    }
    for (const item of mine.items.slice(0, 14)) {
      const chip = node("div", "diary-day");
      chip.append(node("span", null, shortDate(item.entry_date)), node("b", null, starsText(item.stars)));
      chip.setAttribute("aria-label", `${item.entry_date}: ${item.stars} из 3${item.bonus ? ", бонус" : ""}`);
      if (item.bonus) chip.append(node("i", null, "+ бонус"));
      chip.append(node("small", null, `+${item.rep_reward} REP · +${item.stars_reward}★`));
      days.append(chip);
    }
    $("diaryMine").replaceChildren(node("span", "diary-label", "МОИ ОЦЕНКИ"), head, days);
  }

  function drawBoard(items) {
    const host = $("diaryBoard");
    host.replaceChildren(node("span", "diary-label", "РЕЙТИНГ ДНЕВНИКОВ"));
    if (!items.length) {
      host.append(node("p", "diary-note", "В сезоне пока нет участников."));
      return;
    }
    items.forEach((item, index) => {
      const row = node("div", `board-row diary-row${item.is_you ? " is-you" : ""}`);
      row.append(node("span", "board-rank", String(index + 1).padStart(2, "0")));
      const avatar = node("span", "board-avatar cosmetic-avatar");
      if (item.frame) avatar.dataset.frame = item.frame;
      avatar.setAttribute("aria-hidden", "true");
      row.append(avatar);
      const lines = node("span", "board-lines");
      lines.append(node("b", "diary-name", item.display_name),
        node("small", "diary-sub", `${item.days_rated} дн. · бонусов ${item.bonus_count} · +${item.diary_rep} REP`));
      row.append(lines, node("span", "diary-value", `${item.total_stars}★`));
      host.append(row);
    });
  }

  async function loadBoard() {
    const mineHost = $("diaryMine");
    if (!signedIn()) {
      mineHost.replaceChildren(node("p", "diary-note", "Войдите, чтобы увидеть свои оценки и рейтинг дневников."));
      $("diaryBoard").replaceChildren();
      return;
    }
    mineHost.replaceChildren(node("p", "diary-note", "Загрузка…"));
    try {
      const list = await seasons();
      const season = pick(list, (s) => s.is_member) || pick(list, (s) => s.can_manage);
      if (!season) {
        mineHost.replaceChildren(node("p", "diary-note", "Вас ещё не включили в сезон. Оценки появятся после старта поездки."));
        $("diaryBoard").replaceChildren();
        return;
      }
      const board = await api(`/api/v4/seasons/${season.id}/diary/leaderboard`);
      if (season.is_member) {
        drawMine(await api(`/api/v4/seasons/${season.id}/diary/mine`));
      } else {
        mineHost.replaceChildren(node("p", "diary-note", "Вы смотрите рейтинг как организатор: своих оценок у вас нет."));
      }
      drawBoard(board.items);
    } catch (error) {
      mineHost.replaceChildren(node("p", "diary-note", error.message));
    }
  }

  // --- вожатый: лист оценок за день -----------------------------------------------

  function setStatus(text) { $("diarySheetStatus").textContent = text || ""; }

  function shiftDate(iso, days) {
    const moment = new Date(`${iso}T00:00:00Z`);
    moment.setUTCDate(moment.getUTCDate() + days);
    return moment.toISOString().slice(0, 10);
  }

  function updateCount() {
    if (!sheet) return;
    const rated = sheet.members.filter((m) => m.stars || m.bonus).length;
    $("diarySheetCount").textContent = `${rated} из ${sheet.members.length} оценено`;
  }

  function describe(result) {
    const parts = [`${signed(result.rep_delta)} REP`, `${signed(result.stars_delta)}★`];
    if (result.scans_delta > 0) parts.push("+1 попытка кейса");
    let text = `Сохранено: ${parts.join(" · ")}`;
    if (result.stars_clamped) text += ". Часть ★ уже потрачена — баланс остановлен на нуле";
    return `${text}.`;
  }

  function drawMemberRow(member, locked) {
    const busy = busyRows.has(member.account_id);
    const row = node("div", `diary-sheet-row${busy ? " is-busy" : ""}`);
    row.dataset.accountId = String(member.account_id);

    const copy = node("div", "diary-sheet-copy");
    copy.append(node("b", null, member.display_name),
      node("small", null, member.revision ? `оценка от: ${member.rated_by}` : "оценки нет"));

    const controls = node("div", "diary-sheet-controls");
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", `Оценка дневника: ${member.display_name}`);
    for (let n = 0; n <= 3; n += 1) {
      const b = node("button", "btn btn-secondary", n === 0 ? "0" : `${n}★`);
      b.type = "button";
      b.setAttribute("aria-label", `${n} из 3`);
      // Без оценки не выбрано ничего: подсвеченный «0» читался как «вожатый
      // уже поставил ноль», хотя дневник ещё не смотрели.
      b.setAttribute("aria-pressed", String(member.revision > 0 && member.stars === n));
      b.disabled = locked || busy;
      b.addEventListener("click", () => save(member, n, member.bonus));
      controls.append(b);
    }
    const bonus = node("button", "btn btn-secondary diary-bonus", "Бонус");
    bonus.type = "button";
    bonus.setAttribute("aria-pressed", String(member.bonus));
    bonus.disabled = locked || busy;
    bonus.addEventListener("click", () => save(member, member.stars, !member.bonus));
    controls.append(bonus);

    row.append(copy, controls);
    const note = pending.has(member.account_id) && !busy
      ? "Не отправлено: нет связи. Нажмите ту же оценку ещё раз."
      : member.note;
    if (note) row.append(node("small", "diary-row-note", note));
    return row;
  }

  function redrawRow(member) {
    const old = $("diarySheet").querySelector(`[data-account-id="${member.account_id}"]`);
    if (old) old.replaceWith(drawMemberRow(member, sheet.season_status !== "active"));
  }

  function drawSheet() {
    const host = $("diarySheet");
    host.replaceChildren();
    const locked = sheet.season_status !== "active";
    if (locked) host.append(node("p", "case-message", "Сезон не активен: оценки доступны только для просмотра."));
    if (!sheet.members.length) host.append(node("p", "case-message", "В сезоне нет активных участников."));
    let group;
    for (const member of sheet.members) {
      if (member.group !== group) {
        group = member.group;
        host.append(node("span", "diary-group", group || "Без группы"));
      }
      host.append(drawMemberRow(member, locked));
    }
    updateCount();
  }

  async function loadSheet(date) {
    const host = $("diarySheet");
    setStatus("");
    if (!signedIn()) {
      host.replaceChildren(node("p", "case-message", "Список появится после входа."));
      return;
    }
    host.replaceChildren(node("p", "case-message", "Загрузка…"));
    try {
      const list = await seasons();
      sheetSeason = pick(list, (s) => s.can_manage);
      if (!sheetSeason) {
        host.replaceChildren(node("p", "case-message", "Нет сезона, в котором у вас права вожатого."));
        return;
      }
      const r = await loadRules();
      $("diaryRules").textContent =
        `1★ — +${r.rep[1]} REP и +${r.stars[1]}★ · 2★ — +${r.rep[2]} и +${r.stars[2]}★ · ` +
        `3★ — +${r.rep[3]} и +${r.stars[3]}★, первый раз за день ещё попытка кейса · бонус — +${r.rep_bonus} и +${r.stars_bonus}★`;
      sheet = await api(`/api/v4/seasons/${sheetSeason.id}/diary/day${date ? `?date=${encodeURIComponent(date)}` : ""}`);
      pending.clear();
      $("diaryDate").value = sheet.entry_date;
      $("diaryDate").max = sheet.today;
      $("diaryNext").disabled = sheet.entry_date >= sheet.today;
      drawSheet();
    } catch (error) {
      host.replaceChildren(node("p", "case-message", error.message));
    }
  }

  async function save(member, stars, bonus) {
    if (busyRows.has(member.account_id) || !sheet) return;
    const body = {
      account_id: member.account_id,
      entry_date: sheet.entry_date,
      stars,
      bonus,
      expected_revision: member.revision,
    };
    // Повтор той же правки после обрыва связи идёт с прежним ключом: если
    // первый запрос всё-таки дошёл, сервер вернёт сохранённый ответ, а не
    // начислит награду второй раз.
    const old = pending.get(member.account_id);
    const key = old && JSON.stringify(old.body) === JSON.stringify(body) ? old.key : newKey();
    pending.set(member.account_id, { key, body });
    busyRows.add(member.account_id);
    member.note = "";
    redrawRow(member);
    let reloaded = false;
    try {
      const result = await api(`/api/v4/seasons/${sheetSeason.id}/diary/ratings`, { method: "POST", body, key });
      pending.delete(member.account_id);
      member.stars = result.stars;
      member.bonus = result.bonus;
      member.revision = result.revision;
      if (result.changed) member.rated_by = (session.account && session.account.display_name) || "вы";
      member.note = result.changed ? describe(result) : "Без изменений.";
    } catch (error) {
      if (error.status === 409) {
        pending.delete(member.account_id);
        busyRows.delete(member.account_id);
        reloaded = true;
        await loadSheet(sheet.entry_date);
        setStatus(error.message);
        return;
      }
      if (error.status) {
        pending.delete(member.account_id);
        member.note = error.message;
      }
    } finally {
      if (!reloaded) {
        busyRows.delete(member.account_id);
        redrawRow(member);
        updateCount();
      }
    }
  }

  // --- подключение ---------------------------------------------------------------

  function refreshVisible() {
    if (onScreen("rating") && visible("rating:diary")) loadBoard();
    if (onScreen("admin") && visible("admin:diary")) loadSheet(sheet ? sheet.entry_date : null);
  }

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    contextPromise = null;
    sheet = null;
    pending.clear();
    refreshVisible();
  });

  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "rating" && visible("rating:diary")) loadBoard();
    if (event.detail === "admin" && visible("admin:diary")) loadSheet(sheet ? sheet.entry_date : null);
  });

  window.addEventListener("zhidao:tab", (event) => {
    const name = event.detail && event.detail.dataset.tabPanel;
    if (name === "rating:diary" && onScreen("rating")) loadBoard();
    if (name === "admin:diary" && onScreen("admin")) loadSheet(sheet ? sheet.entry_date : null);
  });

  $("diaryDate").addEventListener("change", (event) => {
    if (event.target.value) loadSheet(event.target.value);
  });
  $("diaryPrev").addEventListener("click", () => { if (sheet) loadSheet(shiftDate(sheet.entry_date, -1)); });
  $("diaryNext").addEventListener("click", () => { if (sheet) loadSheet(shiftDate(sheet.entry_date, 1)); });
}());
