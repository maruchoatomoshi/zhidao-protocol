"use strict";

/* Server-owned results. Pending request keys survive closing MAX; no RNG or
   balance mutation lives in this file. Preview never calls personal APIs. */
(function () {
  const $ = (id) => document.getElementById(id);
  const art = {
    implant_guanxi: "guanxi", implant_panda: "panda", implant_shaolin: "shaolin",
    implant_linguasoft: "linguasoft", implant_caishen: "caishen", implant_qilin: "qilin",
    implant_terracota: "terracota", implant_red_dragon: "honglong",
  };
  const tierNames = { gold: "Обычный / 普通", purple: "Редкий / 稀有", black: "Легендарный / 传说" };
  let session = null, seasons = [], selected = null, snapshot = null;
  let busy = false, epoch = 0, historyBefore = null, grantBefore = null, grantDraft = null;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }
  function status(message) { $("caseStatus").textContent = message; }
  function signedIn() { return session && session.mode === "authenticated"; }
  function base() { return `/api/v4/seasons/${selected.id}/cases`; }
  function storageKey(kind) { return `zhidao.cases.${session.account.id}.${selected.id}.${kind}`; }
  function pending(kind) {
    try { return JSON.parse(localStorage.getItem(storageKey(kind)) || "null"); }
    catch (_) { return null; }
  }
  function remember(kind, payload) {
    const old = pending(kind);
    if (old) return old;
    const value = { key: crypto.randomUUID(), payload };
    // Do not start a non-recoverable write in a WebView refusing storage.
    localStorage.setItem(storageKey(kind), JSON.stringify(value));
    return value;
  }
  function forget(kind) { localStorage.removeItem(storageKey(kind)); }

  async function api(path, options = {}) {
    if (!signedIn()) throw new Error("Для этого нужен вход.");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const headers = { Accept: "application/json" };
      if (options.key) {
        const token = document.cookie.split("; ").find(v => v.startsWith("zhidao_v4_csrf="));
        headers["X-CSRF-Token"] = token ? decodeURIComponent(token.slice(token.indexOf("=") + 1)) : "";
        headers["X-Idempotency-Key"] = options.key;
        headers["Content-Type"] = "application/json";
      }
      const response = await fetch(path, { method: options.key ? "POST" : "GET",
        headers, credentials: "same-origin", cache: "no-store", signal: controller.signal,
        body: options.key ? JSON.stringify(options.payload || {}) : undefined });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof data.detail === "string" ? data.detail : "Запрос отклонён. Проверьте поля.");
        error.status = response.status;
        throw error;
      }
      return data;
    } finally { clearTimeout(timer); }
  }

  function controls() {
    const retry = signedIn() && selected && pending("open");
    $("caseOpen").disabled = busy || !selected || (!retry && !(selected.can_play && snapshot && snapshot.scans > 0));
    $("caseOpen").textContent = retry ? "Восстановить результат" : "Сканировать · 1 попытка";
    document.querySelectorAll("[data-case-season]").forEach(n => { n.disabled = busy || !seasons.length; });
    document.querySelectorAll("[data-case-refresh]").forEach(n => { n.disabled = busy; });
    $("caseGrantFields").disabled = busy || (selected && selected.status !== "active") || !!(signedIn() && selected && pending("grant"));
    $("caseGrantSubmit").disabled = busy || !selected || selected.status !== "active";
    $("caseGrantSubmit").textContent = signedIn() && selected && pending("grant") ? "Восстановить выдачу" : "Проверить выдачу";
  }

  function clearPersonal() {
    snapshot = null;
    $("caseHistory").replaceChildren(node("p", "", "Открытий пока нет."));
    $("caseInventory").replaceChildren();
    $("caseGrantMembers").replaceChildren();
    $("caseGrantGroup").replaceChildren();
    $("caseGrantLog").replaceChildren();
    $("caseAdmin").hidden = true;
    $("caseItemCount").textContent = "— предметов";
    $("caseHistoryMore").hidden = true;
    $("caseGrantMore").hidden = true;
    $("caseGrantStatus").textContent = "";
    $("caseGrantReason").value = "";
    document.querySelectorAll("[data-case-stars]").forEach(n => { n.textContent = "— ★"; });
    document.querySelectorAll("[data-case-scans]").forEach(n => { n.textContent = "— / 7"; });
    $("caseResultDialog").close();
    $("caseGrantDialog").close();
    ["caseResultTitle", "caseResultNote", "caseResultBalance", "caseResultTier", "caseGrantSummary"].forEach(id => { $(id).textContent = ""; });
    $("caseResultArt").removeAttribute("src");
    document.querySelectorAll("[data-collection-season]").forEach(n => { n.textContent = "—"; });
  }

  function showResult(result) {
    $("caseResultTier").textContent = tierNames[result.tier];
    $("caseResultDialog").dataset.tier = result.tier;
    $("caseResultTitle").textContent = result.prize.name_ru;
    const image = $("caseResultArt"), filename = art[result.prize.code];
    image.hidden = !filename;
    if (filename) image.src = `./assets/implants/${filename}.webp`;
    else image.removeAttribute("src");
    const deferred = result.prize.reward.kind === "item" && result.prize.reward.effect_state === "pending";
    $("caseResultNote").textContent = (result.guard_used ? "Гарант судьбы перебросил пустышку. " : "") +
      (deferred ? "Предмет в коллекции. Его использование и эффекты ещё не подключены." :
        result.prize.code === "empty" ? "В этот раз пусто. Попытка использована." : "Награда сохранена на сервере.");
    $("caseResultBalance").textContent = `После открытия: ${result.stars} ★ · ${result.scans}/7 попыток · запись №${result.opening_id}`;
    if (!$("caseResultDialog").open) $("caseResultDialog").showModal();
  }

  function drawHistory(data, append = false) {
    const host = $("caseHistory");
    if (!append) host.replaceChildren();
    if (!data.items.length && !append) host.append(node("p", "", "Первый сигнал ещё впереди. Все результаты появятся здесь."));
    for (const row of data.items) {
      const button = node("button", "case-history-row");
      button.type = "button";
      button.append(node("strong", "", row.details.prize.name_ru), node("span", "", `№${row.id} · ${new Date(row.created_at).toLocaleString("ru-RU")}`));
      button.addEventListener("click", () => showResult({ ...row.details, opening_id: row.id, stars: row.stars_after, scans: row.scans_after }));
      host.append(button);
    }
    historyBefore = data.next_before;
    $("caseHistoryMore").hidden = !historyBefore;
  }

  function drawInventory(items) {
    const host = $("caseInventory");
    host.replaceChildren();
    $("collectionStatus").textContent = items.length ? "Ваши предметы. Метка показывает, подключён ли эффект." : "Пока пусто. Первый предмет появится после выигрыша.";
    let quantity = 0;
    for (const item of items) {
      quantity += item.quantity;
      const card = node("article", "case-owned-item");
      if (art[item.item_code]) {
        const image = node("img"); image.src = `./assets/implants/${art[item.item_code]}.webp`; image.alt = ""; image.loading = "lazy";
        card.append(image);
      } else card.append(node("span", "case-item-glyph", item.item_code === "fate_guard" ? "↻" : "◷"));
      card.append(node("h3", "", item.name_ru), node("strong", "case-item-quantity", `×${item.quantity}`),
        node("span", `case-effect ${item.effect_state}`, item.effect_state === "active" ? "Эффект работает" : "Эффект не подключён"));
      host.append(card);
    }
    $("caseItemCount").textContent = `${quantity} шт. / ${items.length} видов`;
  }

  function drawGrants(data, append = false) {
    if (!append) $("caseGrantLog").replaceChildren(node("h3", "", "Журнал выдачи"));
    for (const row of data.items) {
      const record = node("div", "case-grant-record");
      record.append(node("strong", "", `${row.display_name}: +${row.scans_delta}, запас ${row.scans_after}/7`),
        node("span", "", `${row.actor_name} · ${new Date(row.created_at).toLocaleString("ru-RU")}`),
        node("p", "", row.details.reason));
      $("caseGrantLog").append(record);
    }
    grantBefore = data.next_before;
    $("caseGrantMore").hidden = !grantBefore;
  }

  async function loadSelected() {
    if (!signedIn() || !selected || busy) return;
    const version = ++epoch, scope = selected, path = base();
    clearPersonal(); busy = true; controls(); status("Подключение к личному хранилищу…");
    document.querySelectorAll("[data-collection-season]").forEach(n => { n.textContent = scope.name; });
    try {
      const [data, roster, grants] = await Promise.all([
        scope.is_member ? api(`${path}/state`) : null,
        scope.can_manage ? api(`${path}/admin/roster`) : null,
        scope.can_manage ? api(`${path}/admin/grants`) : null,
      ]);
      if (version !== epoch) return;
      snapshot = data;
      if (data) {
        document.querySelectorAll("[data-case-stars]").forEach(n => { n.textContent = `${data.stars} ★`; });
        document.querySelectorAll("[data-case-scans]").forEach(n => { n.textContent = `${data.scans} / 7`; });
        drawHistory(data.history); drawInventory(data.inventory);
      } else $("collectionStatus").textContent = "У организатора нет личного участия в этом сезоне.";
      if (roster) {
        $("caseAdmin").hidden = false;
        for (const member of roster.members) {
          const label = node("label"); const input = node("input"); input.type = "checkbox"; input.value = member.id;
          label.append(input, node("span", "", `${member.display_name} · #${member.id} · ${member.scans}/7`));
          $("caseGrantMembers").append(label);
        }
        if (!roster.members.length) $("caseGrantMembers").append(node("p", "", "Нет активных участников сезона. Сначала настройте состав сезона."));
        for (const group of roster.groups) { const option = node("option", "", group.name); option.value = group.id; $("caseGrantGroup").append(option); }
        drawGrants(grants);
        const recovery = pending("grant");
        if (recovery) $("caseGrantStatus").textContent = `Ожидает восстановления прежняя выдача: по ${recovery.payload.amount} попыток. Причина: ${recovery.payload.reason}`;
      }
      status(pending("open") ? "Есть незавершённый запрос. Восстановите результат — новая попытка не спишется повторно." :
        scope.status !== "active" ? "Сезон не активен. Доступен только просмотр." :
          scope.can_play ? (data.scans ? "Готово к сканированию. Стоимость — одна попытка." : "Попыток пока нет. Их выдаёт организатор.") : "Доступ организатора: выдача попыток ниже.");
    } catch (error) {
      if (version === epoch) { status(error.message || "Нет связи. Обновите данные."); $("collectionStatus").textContent = "Данные не загрузились. Нажмите «Обновить»."; }
    } finally { if (version === epoch) { busy = false; controls(); } }
  }

  async function connect() {
    const version = ++epoch;
    clearPersonal(); selected = null; seasons = []; busy = false; controls();
    document.querySelectorAll("[data-case-mode]").forEach(n => { n.textContent = signedIn() ? "PERSONAL ACCOUNT" : "OFFLINE PREVIEW"; });
    if (!signedIn()) {
      document.querySelectorAll("[data-case-season]").forEach(n => { n.replaceChildren(node("option", "", "Войдите в аккаунт")); });
      $("collectionStatus").textContent = "В предпросмотре нет личных данных. Войдите, чтобы увидеть коллекцию.";
      status("В предпросмотре доступны только оформление и правила.");
      return;
    }
    status("Проверяем доступные сезоны…");
    try {
      const data = await api("/api/v4/cases/context");
      if (version !== epoch) return;
      seasons = data.seasons;
      let lastSeason;
      try { lastSeason = Number(localStorage.getItem(`zhidao.cases.${session.account.id}.season`)); } catch (_) { /* optional preference */ }
      selected = seasons.find(s => s.id === lastSeason) || seasons.find(s => s.status === "active") || seasons[0] || null;
      document.querySelectorAll("[data-case-season]").forEach(n => {
        n.replaceChildren();
        for (const season of seasons) { const o = node("option", "", `${season.name} · ${season.status}`); o.value = season.id; n.append(o); }
        if (selected) n.value = selected.id;
        else n.append(node("option", "", "Нет доступных сезонов"));
      });
      if (selected) await loadSelected();
      else { status("Организатор ещё не включил вас в состав сезона."); $("collectionStatus").textContent = "Нет доступного сезона. Обратитесь к организатору."; }
    } catch (error) { if (version === epoch) status(error.message || "Нет связи. Нажмите «Обновить»."); }
    controls();
  }

  async function scan() {
    if (busy || !signedIn() || !selected) return;
    const version = epoch, path = base(); let request;
    try { request = remember("open", {}); }
    catch (_) { status("Хранилище браузера недоступно. Разрешите данные сайта для безопасного восстановления открытия."); return; }
    busy = true; controls(); $("scanWindow").classList.add("is-scanning");
    $("scanWindow").setAttribute("aria-busy", "true");
    document.querySelector(".scanner-progress").hidden = false;
    status("Сканирование… результат сохраняется на сервере.");
    let savedResult = null;
    try {
      const [result] = await Promise.all([api(`${path}/open`, request),
        new Promise(resolve => setTimeout(resolve, matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 850))]);
      if (version !== epoch) return;
      forget("open"); savedResult = result;
    } catch (error) {
      if (version !== epoch) return;
      // Only definitive rejection permits a new request key. Network/5xx keep it.
      if ([400, 403, 404, 409, 422].includes(error.status)) forget("open");
      status(error.status ? error.message : "Связь прервалась. Нажмите «Восстановить результат»: повтор безопасен.");
    } finally {
      $("scanWindow").classList.remove("is-scanning"); $("scanWindow").removeAttribute("aria-busy");
      document.querySelector(".scanner-progress").hidden = true;
      if (version === epoch) { busy = false; controls(); }
    }
    if (savedResult) {
      await loadSelected();
      if (version + 1 === epoch) showResult(savedResult);
    }
  }

  async function submitGrant(request) {
    if (busy) return;
    const version = epoch, path = base(); busy = true; controls();
    $("caseGrantStatus").textContent = "Сохраняем выдачу…";
    let result;
    try {
      result = await api(`${path}/admin/grants`, request);
      if (version !== epoch) return;
      forget("grant");
    } catch (error) {
      if (version !== epoch) return;
      if ([400, 403, 404, 409, 422].includes(error.status)) forget("grant");
      $("caseGrantStatus").textContent = error.status ? error.message : "Нет подтверждения от сервера. Восстановите выдачу тем же запросом.";
    } finally { if (version === epoch) { busy = false; controls(); } }
    if (result && version === epoch) {
      await loadSelected();
      $("caseGrantStatus").textContent = result.results.map(r => `#${r.account_id}: +${r.granted} из ${r.requested}, запас ${r.scans}/7`).join("; ");
    }
  }

  $("caseGrantForm").addEventListener("submit", event => {
    event.preventDefault(); if (busy || !signedIn() || !selected) return;
    const old = pending("grant"); if (old) { submitGrant(old); return; }
    const ids = Array.from($("caseGrantMembers").querySelectorAll("input:checked"), n => Number(n.value));
    const group = $("caseGrantTarget").value === "group";
    grantDraft = { account_ids: group ? [] : ids, group_id: group ? Number($("caseGrantGroup").value) : null,
      amount: Number($("caseGrantAmount").value), reason: $("caseGrantReason").value.trim() };
    if ((!group && !ids.length) || (group && !grantDraft.group_id) || !grantDraft.reason) {
      $("caseGrantStatus").textContent = "Выберите получателей и укажите причину."; return;
    }
    const targets = group ? $("caseGrantGroup").selectedOptions[0].textContent :
      Array.from($("caseGrantMembers").querySelectorAll("input:checked"), n => n.parentElement.textContent).join(", ");
    $("caseGrantSummary").textContent = `${targets}. По ${grantDraft.amount} попыток. Причина: ${grantDraft.reason}`;
    $("caseGrantDialog").showModal();
  });
  $("caseGrantConfirm").addEventListener("click", () => {
    $("caseGrantDialog").close();
    try { submitGrant(remember("grant", grantDraft)); }
    catch (_) { $("caseGrantStatus").textContent = "Разрешите хранилище сайта перед выдачей."; }
  });
  $("caseGrantCancel").addEventListener("click", () => $("caseGrantDialog").close());
  $("caseGrantTarget").addEventListener("change", () => {
    const group = $("caseGrantTarget").value === "group";
    $("caseGrantMembers").hidden = group; $("caseGrantGroupLabel").hidden = !group;
  });
  $("caseOpen").addEventListener("click", scan);
  document.querySelectorAll("[data-case-close]").forEach(n => n.addEventListener("click", () => $("caseResultDialog").close()));
  document.querySelectorAll("[data-case-season]").forEach(n => n.addEventListener("change", () => {
    selected = seasons.find(s => s.id === Number(n.value));
    try { localStorage.setItem(`zhidao.cases.${session.account.id}.season`, n.value); } catch (_) { /* opening still requires recoverable storage */ }
    document.querySelectorAll("[data-case-season]").forEach(other => { other.value = n.value; });
    loadSelected();
  }));
  document.querySelectorAll("[data-case-refresh]").forEach(n => n.addEventListener("click", () => selected ? loadSelected() : connect()));
  async function more(kind) {
    if (busy || !selected) return;
    const version = epoch, path = base(); busy = true; controls();
    try {
      const data = await api(kind === "history" ? `${path}/history?before=${historyBefore}` : `${path}/admin/grants?before=${grantBefore}`);
      if (version === epoch) (kind === "history" ? drawHistory : drawGrants)(data, true);
    } catch (error) { if (version === epoch) status(error.message); }
    finally { if (version === epoch) { busy = false; controls(); } }
  }
  $("caseHistoryMore").addEventListener("click", () => more("history"));
  $("caseGrantMore").addEventListener("click", () => more("grants"));
  window.addEventListener("zhidao:auth", event => { session = event.detail; connect(); });
  window.addEventListener("zhidao:screen", event => {
    if (["cases", "collection"].includes(event.detail) && signedIn() && !busy) selected ? loadSelected() : connect();
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && signedIn() && !busy && !document.querySelector("dialog[open]") && ["cases", "collection"].includes(document.documentElement.dataset.currentScreen)) selected ? loadSelected() : connect();
  });
}());
