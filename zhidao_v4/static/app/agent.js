"use strict";

/* Тайный агент — игра на всю смену (V4_GAMES.md §4.12).

   У каждого вступившего — тайная цель и безобидная миссия на день. Всё решает
   сервер (zhidao_v4/agent.py): круг, миссии, очки и звёзды. Сюда приходит
   только своя цель и вопрос от своего агента, когда тот сам спросил. Панель
   перерисовывается, только когда ответ сервера изменился, — чтобы выбранный
   в списке подозреваемый не сбрасывался при опросе. */

(function () {
  const $ = (id) => document.getElementById(id);
  const LEAD = "У каждого агента — тайная цель и безобидная миссия на день. Выполнил — очки и новая цель. Но за тобой тоже кто-то охотится: вычисли его";
  const POLL_MS = 20000;

  let session = window.ZhidaoSession || null;
  let data = null;
  let signature = "";
  let busy = false;
  let note = "";
  let armed = null;
  let suspect = "";
  let poll = null;

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function button(className, text, onClick) {
    const b = node("button", className, text);
    b.type = "button";
    b.disabled = busy;
    b.addEventListener("click", onClick);
    return b;
  }

  // Опасное действие — двумя нажатиями: первое меняет надпись на вопрос.
  function armedButton(kind, className, label, confirmLabel, action) {
    return button(className, armed === kind ? confirmLabel : label, () => {
      if (armed !== kind) {
        armed = kind;
        draw();
        return;
      }
      armed = null;
      action();
    });
  }

  const signedIn = () => Boolean(session && session.mode === "authenticated");
  const onGames = () => document.documentElement.dataset.currentScreen === "games";
  const timeOf = (iso) => Date.parse(String(iso).replace(/\.(\d{3})\d*Z$/, ".$1Z"));
  const clock = (iso) => new Date(timeOf(iso)).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });

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
        throw new Error(typeof body.detail === "string" ? body.detail : "Запрос отклонён.");
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

  // --- куски панели ------------------------------------------------------------------------

  function newsText(news) {
    if (!news) return "";
    const at = news.at ? ` · ${clock(news.at)}` : "";
    if (news.kind === "mission") {
      const stars = news.stars ? `, +${news.stars}★` : " (звёзды за сегодня уже получены)";
      return `Миссия засчитана: +${news.points} очка агента${stars}. У вас новая цель${at}`;
    }
    if (news.kind === "refused") return `Цель ответила «нет». Миссия осталась за вами${at}`;
    if (news.kind === "exposed") return `Вас вычислили! Цель сменилась${at}`;
    if (news.kind === "guess") {
      return news.right ? `Вы вычислили своего агента: +${news.points} очка${at}` : `Не угадали агента: ${news.points} очко${at}`;
    }
    return "";
  }

  function drawIncoming(parts) {
    const box = node("section", "agent-card is-incoming");
    box.append(
      node("b", null, `Агент ${data.incoming.agent} говорит, что выполнил миссию:`),
      node("p", "agent-mission", data.incoming.mission_text),
      node("p", "agent-meta", "Это правда?"),
    );
    const actions = node("div", "capture-actions");
    actions.append(
      button("btn btn-primary", "Да, меня поймали", () => act("answer", { yes: true })),
      armedButton("refuse", "btn btn-secondary", "Нет", "Точно нет?", () => act("answer", { yes: false })),
    );
    box.append(actions);
    parts.push(box);
  }

  function drawTarget(parts) {
    const t = data.target;
    if (!t) {
      if (data.running) {
        parts.push(node("p", "agent-meta", data.players < data.min_players
          ? `Ждём агентов: нужно ${data.min_players}, вступило ${data.players}`
          : "Цель придёт с новым кругом — завтра в 07:00"));
      }
      return;
    }
    const box = node("section", "agent-card");
    box.append(
      node("span", "capture-label", "Ваша цель"),
      node("b", "agent-target", t.name),
      node("p", "agent-mission", t.mission.text_ru),
      node("p", "agent-meta", t.mission.hint_ru),
    );
    if (t.mission.kind === "confirm") {
      if (t.asking) box.append(node("p", "agent-meta is-ok", "Ждём ответа цели…"));
      else if (t.asks_left > 0) box.append(armedButton("ask", "btn btn-primary", "Миссия выполнена", "Точно? Цель узнает, что вы её агент", () => act("ask")));
      else box.append(node("p", "agent-meta", "На сегодня вопросов этой цели больше нет"));
    }
    parts.push(box);
  }

  function drawGuess(parts) {
    const box = node("section", "agent-card is-guess");
    box.append(node("span", "capture-label", "Кто за вами охотится?"));
    if (data.you.guess_used) {
      box.append(node("p", "agent-meta", "Сегодня вы уже называли агента. Завтра — снова"));
      parts.push(box);
      return;
    }
    const select = document.createElement("select");
    select.className = "agent-select";
    select.setAttribute("aria-label", "Кого назвать агентом");
    select.append(new Option("Выберите участника", ""));
    data.suspects.forEach((s) => select.append(new Option(s.name, String(s.account_id))));
    select.value = data.suspects.some((s) => String(s.account_id) === suspect) ? suspect : "";
    select.disabled = busy;
    select.addEventListener("change", () => { suspect = select.value; });
    box.append(
      select,
      node("p", "agent-meta", `Угадали — +${data.points.reveal} очка и агент теряет цель. Ошиблись — −${data.points.wrong_guess}. Раз в день`),
      armedButton("guess", "btn btn-secondary", "Назвать агента", "Точно он?", () => {
        if (!suspect) {
          note = "Сначала выберите, кого назвать";
          draw();
          return;
        }
        act("guess", { suspect: Number(suspect) });
      }),
    );
    parts.push(box);
  }

  function drawYou(parts) {
    const you = data.you;
    if (!you || !you.joined) {
      if (you && you.excluded) parts.push(node("p", "agent-meta", "Вожатый исключил вас из этой смены агентов"));
      else if (data.can_play) parts.push(button("btn btn-primary", "Вступить в игру", () => act("join")));
      return;
    }
    parts.push(node("p", "agent-stats",
      `Очки агента: ${you.points} · миссий ${you.missions} · раскрытий ${you.reveals} · ★ сегодня ${you.stars_today} из ${data.reward.daily_limit}`));
    const news = newsText(you.news);
    if (news) parts.push(node("p", "agent-news", news));
    if (data.incoming) drawIncoming(parts);
    drawTarget(parts);
    if (data.running && data.suspects.length) drawGuess(parts);
    parts.push(armedButton("leave", "btn btn-secondary agent-leave", "Я не участвую", "Точно выйти? Очки сгорят", () => act("leave")));
  }

  function drawRating(parts) {
    if (!data.rating || !data.rating.length) return;
    parts.push(node("span", "capture-label", "Рейтинг агентов"));
    const list = node("ol", "agent-rating");
    data.rating.slice(0, 10).forEach((r) => {
      const item = node("li");
      item.append(node("b", null, r.name), node("span", null, `${r.points} очк. · миссий ${r.missions}`));
      list.append(item);
    });
    parts.push(list);
  }

  function drawShifts(parts) {
    const last = data.shifts && data.shifts[0];
    if (!last) return;
    const best = last.results.filter((r) => r.best).map((r) => r.name);
    parts.push(node("p", "agent-meta", `Смена ${last.number} окончена${best.length ? `. Лучший агент: ${best.join(", ")}` : ""}`));
  }

  function drawStaff(parts) {
    const actions = node("div", "capture-actions");
    if (!data.running) {
      actions.append(button("btn btn-primary", "Начать смену агентов", () => act("start")));
    } else {
      actions.append(
        button("btn btn-secondary", "Пересобрать круг", () => act("reshuffle")),
        armedButton("finish", "btn btn-secondary", "Подвести итоги смены", "Точно подвести итоги?", () => act("finish")),
      );
    }
    parts.push(node("span", "capture-label", "Вожатому"), actions);
    const players = (data.staff && data.staff.players) || [];
    if (!players.length) return;
    const list = node("ul", "agent-staff");
    players.forEach((p) => {
      const item = node("li");
      item.append(node("b", null, p.name), node("span", null, p.excluded ? "исключён" : `очков ${p.points} · отказов ${p.refusals}`));
      if (!p.excluded) {
        item.append(armedButton(`exclude-${p.account_id}`, "btn btn-secondary", "Исключить", "Точно исключить?",
          () => act("exclude", { account_id: p.account_id })));
      }
      list.append(item);
    });
    parts.push(list);
  }

  function draw() {
    const body = $("agentBody");
    const status = $("agentStatus");
    if (!body) return;
    if (!signedIn() || !data || data.season_id == null) {
      const message = !signedIn() ? "Войдите, чтобы играть" : data ? "Нет активного сезона" : "Загружаем…";
      body.replaceChildren(node("p", "spy-lead", LEAD), node("p", "agent-meta", message));
      status.textContent = "—";
      return;
    }
    const parts = [node("p", "spy-lead", LEAD)];
    if (!data.running) {
      parts.push(node("p", "agent-meta", data.can_manage
        ? "Смена агентов не идёт. Начните её, когда агенты вступят"
        : "Смену запускает вожатый. Вступить можно уже сейчас"));
    }
    drawYou(parts);
    drawRating(parts);
    drawShifts(parts);
    if (data.can_manage) drawStaff(parts);
    parts.push(node("p", "case-message", note));
    body.replaceChildren(...parts);
    status.textContent = data.running ? `СМЕНА ${data.shift} · МИССИИ ${data.hours[0]}–${data.hours[1]}` : "СМЕНА НЕ ИДЁТ";
  }

  // --- данные ------------------------------------------------------------------------------------

  let quietRefresh = true;
  let refreshing = false;
  function accept(body) {
    const before = !quietRefresh && !document.hidden && onGames() ? (data && data.you && data.you.news) : null;
    quietRefresh = false;
    data = body;
    const after = data.you && data.you.news;
    if (before && after && after.kind === "mission" && before.at !== after.at && !document.hidden && window.ZhidaoSounds) {
      window.ZhidaoSounds.play("rare");
    }
    const next = JSON.stringify(body);
    if (next !== signature) {
      signature = next;
      draw();
      if (before && after && before.at !== after.at) window.ZhidaoRetro?.reveal(document.getElementById("agentBody"));
    }
    schedule();
  }

  async function refresh() {
    if (!signedIn()) {
      data = null;
      signature = "";
      draw();
      return;
    }
    if (refreshing) return;
    refreshing = true;
    const account = session?.account?.id;
    try {
      const response = await api("/api/v4/agent");
      if (account !== session?.account?.id) return;
      accept(response);
    } catch (_) {
      quietRefresh = true;
      const status = document.getElementById("agentStatus");
      if (status) status.textContent = "Нет связи · повторяем автоматически";
    } finally {
      refreshing = false;
      schedule();
    }
  }

  async function act(action, body) {
    if (busy) return;
    busy = true;
    note = "";
    draw();
    try {
      accept(await api(`/api/v4/agent/${action}`, { method: "POST", body }));
      if (action === "guess") suspect = "";
    } catch (error) {
      note = error.message;
      await refresh();
    } finally {
      busy = false;
      signature = "";
      draw();
    }
  }

  function schedule() {
    if (!signedIn() || !onGames() || document.hidden) {
      clearInterval(poll);
      poll = null;
      return;
    }
    if (!poll) poll = setInterval(() => { if (!busy) refresh(); }, POLL_MS);
  }

  // --- подключение -------------------------------------------------------------------------------

  window.addEventListener("zhidao:auth", (event) => {
    quietRefresh = true;
    session = event.detail;
    data = null;
    signature = "";
    armed = null;
    note = "";
    suspect = "";
    draw();
    if (onGames()) refresh();
  });
  window.addEventListener("zhidao:screen", (event) => {
    quietRefresh = true;
    if (event.detail === "games") refresh();
    else schedule();
  });
  document.addEventListener("visibilitychange", () => {
    quietRefresh = true;
    schedule();
    if (!document.hidden && onGames() && !busy) refresh();
  });
  window.addEventListener("online", () => {
    quietRefresh = true;
    if (!document.hidden && onGames() && !busy) refresh();
  });
  draw();
}());
