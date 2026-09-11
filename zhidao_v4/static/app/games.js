"use strict";

/* Isolated, public teaching examples. Never read room state or call an API. */
(function () {
  const dialog = document.getElementById("gameGuide");
  const body = document.getElementById("gameGuideBody");
  if (!dialog || !body) return;
  const lessons = {
    outage: {
      title: "Сбой системы",
      rules: ["От 2 игроков: один техник видит модули, остальные эксперты видят инструкцию. Общайтесь голосом, не показывайте экраны друг другу.", "Техник описывает надписи и детали. Эксперты находят правило и объясняют действие. Ответы наугад опасны: третья ошибка завершает раунд.", "Лёгкий режим: 2 модуля за 5 минут; обычный: 3 за 5 минут; сложный: 4 за 4 минуты. Нужно исправить все модули до конца времени.", "Тренировка ниже без таймера. Это отдельные вымышленные ситуации, не инструкция к модулям текущей партии. За успешный раунд каждый получает одно очко вечера, без ★ и REP."],
      steps: [
        { text: "Вы техник. Эксперт спрашивает, что вы видите. Как помочь?", options: ["Точно описать надписи и расположение", "Нажимать кнопки по очереди"], correct: 0, why: "Эксперт не видит модуль: точное описание позволяет выбрать правило." },
        { text: "Учебная инструкция: выберите левую кнопку. На учебной панели две кнопки. Какую нажать?", options: ["Левую", "Правую"], correct: 0, why: "Сначала описание и инструкция, затем действие. Это пример общения, не правило настоящего модуля." },
        { text: "В настоящей партии уже две ошибки. Вы не поняли ответ эксперта.", options: ["Угадать", "Уточнить и повторить команду вслух"], correct: 1, why: "Третья ошибка завершит раунд. Короткое уточнение безопаснее догадки." }
      ]
    },
    meet: {
      title: "Пазл встреч",
      rules: ["Встречайтесь с другим участником: один показывает шестизначный код, второй вводит его. Код действует 60 секунд; QR пока нет.", "Оба получают недостающий кусочек пазла 3×3. Ничего отдавать или платить не нужно. Одна пара получает кусочки один раз за сезон-день; новый день начинается в 07:00.", "После девяти кусочков картинка собрана. При встрече может передаться игровой вирус, если один участник заражён и нет защиты."],
      steps: [
        { text: "Друг получил кусочек от вас. Вы свой потеряли?", options: ["Нет, кусочки получают оба", "Да"], correct: 0, why: "Встреча создаёт прогресс обоим, а не отнимает его." },
        { text: "Код просрочился. Что делать?", options: ["Создать новый код", "Продолжать вводить старый"], correct: 0, why: "Код действует только 60 секунд." },
        { text: "Сегодня вы уже встречались с этим участником. Как получить новый кусочек?", options: ["Повторять тот же код", "Познакомиться с другим участником"], correct: 1, why: "Для одной пары действует лимит один раз за сезон-день." }
      ]
    },
    trade: {
      title: "Обмен дубликатами",
      rules: ["Обмениваются только дубликаты из кейсов: один экземпляр остаётся у владельца. Косметика и купоны не участвуют.", "Первый выбирает предмет и показывает код на 3 минуты; второй вводит код и выбирает свой предмет. Оба проверяют предложение и подтверждают.", "Сбор — 5★ с каждого, максимум 3 обмена за сезон-день. Более редкий предмет можно отдать после отдельного предупреждения.", "До двух подтверждений предметы не перемещаются. Если перед завершением не хватает денег или дубликата, обмен целиком отменяется. Возможна передача игрового вируса."],
      steps: [
        { text: "У вас один экземпляр предмета. Можно обменять его?", options: ["Нет, нужен дубликат", "Да"], correct: 0, why: "Последний экземпляр остаётся у владельца." },
        { text: "Кто платит сбор 5★?", options: ["Только создатель", "Каждый участник"], correct: 1, why: "Перед подтверждением убедитесь, что оба согласны со сбором." },
        { text: "Вы отдаёте более редкий предмет. Что требуется?", options: ["Отдельно подтвердить неравный обмен", "Ничего"], correct: 0, why: "Сервер требует явного подтверждения от владельца более редкого предмета." }
      ]
    },
    virus: {
      title: "Вирус Протокола",
      rules: ["Это игровой эффект, не настоящий вирус устройства. При встрече или обмене с заражённым шанс передачи 50%, если нет фаервола.", "Без лечения эффект проходит через 6 часов. Бесплатное лечение: правильно ответить минимум на 4 из 5 вопросов по словам.", "Антивирус без теста стоит 15★, фаервол — 20★ до конца сезон-дня в 07:00. Перед покупкой прочитайте подтверждение. Эта тренировка ничего не списывает."],
      steps: [
        { text: "Игровой вирус повредил телефон?", options: ["Нет, это эффект внутри приложения", "Да"], correct: 0, why: "Он меняет оформление, а не файлы устройства." },
        { text: "Можно вылечиться бесплатно?", options: ["Нет", "Да, пройти тест"], correct: 1, why: "Нужно 4 верных ответа из 5. Также эффект проходит сам через 6 часов." },
        { text: "Фаервол действует навсегда?", options: ["Нет, до 07:00 нового сезон-дня", "Да"], correct: 0, why: "Это временная защита, а не постоянная покупка." }
      ]
    },
    spy: {
      title: "Шпион Протокола",
      rules: [
        "Соберите 4–8 человек. Один создаёт комнату, остальные вводят четырёхзначный код. Ведущий выбирает перевод и длительность 5–12 минут.",
        "Удерживайте свою карточку пальцем или клавишей пробела. Все, кроме шпиона, знают общее место и свою роль. Не показывайте карточку соседям.",
        "Задавайте вопросы голосом. Обычным игрокам нужно вычислить шпиона, не назвав место; шпиону — понять место и не выдать себя.",
        "У каждого одно обвинение за раунд. При обвинении таймер обсуждения останавливается. Голосуют все, кроме обвиняемого; любое «нет» снимает обвинение.",
        "Единогласное «да» осуждает сразу. Через минуту нужны большинство всего стола, минимум два «да» и ни одного «нет». Свёрнутые приложения не уменьшают число необходимых голосов.",
        "Шпион может назвать место во время обсуждения: верный ответ приносит ему победу, неверный — поражение. Если время вышло, шпиона выбирает большинство всего стола.",
        "Очки остаются только на этот вечер: шпиону 4 за угаданное место или осуждение невиновного, 2 за выживание. Обычным игрокам 1 за победу, успешному обвинителю 2 вместо 1. ★ и REP не меняются."
      ],
      steps: [
        { text: "Вы обычный игрок, место — столовая. Какой вопрос лучше задать?", options: ["Что здесь обычно берут?", "Мы ведь в столовой?"], correct: 0, why: "Первый вопрос проверяет знание места, но не выдаёт шпиону его название." },
        { text: "Теперь вы шпион. Карточка не показывает место. Что делать?", options: ["Попросить соседа показать карточку", "Слушать ответы и задавать осторожные вопросы"], correct: 1, why: "Секреты остаются на личных экранах. Шпион собирает подсказки из разговора." },
        { text: "Во время обвинения один участник нажал «нет». Что произойдёт?", options: ["Обвинение снимается", "Этот участник выбывает"], correct: 0, why: "Одно «нет» снимает обвинение. Сам голосующий не выбывает." }
      ]
    },
    cipher: {
      title: "Шифровальщики",
      rules: [
        "Соберите 4–8 человек, разделитесь на синих и красных. В каждой команде минимум двое: капитан и отгадчик. Состав выбирают в лобби.",
        "На поле 25 слов: 9 карточек первой команды, 8 второй, 7 пустых и один вирус. Цвета закрытых карточек видят только капитаны.",
        "Капитан вслух произносит одно русское слово-подсказку и число. На телефоне вводит только число от 1 до 9. Экран капитана нельзя показывать команде.",
        "Команда выбирает слова по подсказке. Попыток на одну больше указанного числа. После первой попытки можно закончить ход.",
        "Своя карточка продолжает ход. Пустая или чужая передаёт ход соперникам. Вирус немедленно приносит победу другой команде.",
        "Откройте все свои карточки раньше соперников. Игра без таймера; победителям по одному очку вечера, без ★ и REP. Перевод или пиньинь можно выбрать в лобби."
      ],
      steps: [
        { text: "Капитан сказал «Транспорт, 2». Сколько максимум попыток у команды?", options: ["Две", "Три"], correct: 1, why: "Две по подсказке плюс одна дополнительная. Необязательно использовать все." },
        { text: "Учебный пример: вы открыли пустую карточку. Что дальше?", options: ["Ход переходит другой команде", "Можно выбирать, пока не кончатся попытки"], correct: 0, why: "Пустая карточка сразу заканчивает ход, даже если попытки ещё были." },
        { text: "Кому можно видеть цвета закрытых карточек?", options: ["Всем членам команды", "Только капитанам"], correct: 1, why: "Отгадчики узнают цвета только после открытия. Вирус нужно обойти." }
      ]
    }
  };
  const make = (tag, text) => { const el = document.createElement(tag); el.textContent = text; return el; };
  function button(text, action) {
    const el = make("button", text); el.type = "button"; el.className = "btn btn-secondary";
    el.addEventListener("click", action); return el;
  }
  function rules(lesson) {
    body.replaceChildren();
    const list = document.createElement("ol");
    lesson.rules.forEach(text => list.append(make("li", text)));
    body.append(list, button("Попробовать · 3 шага", () => step(lesson, 0)));
  }
  function step(lesson, index) {
    body.replaceChildren();
    if (index === lesson.steps.length) {
      body.append(make("h3", "Основы пройдены"), make("p", "Теперь соберите компанию. Правила доступны и во время партии; таймер настоящей игры при чтении не останавливается."), button("Повторить обучение", () => step(lesson, 0)), button("Посмотреть правила", () => rules(lesson)));
      return;
    }
    const task = lesson.steps[index];
    const feedback = make("p", ""); feedback.setAttribute("role", "status");
    const next = button("Далее", () => step(lesson, index + 1)); next.disabled = true;
    body.append(make("h3", `Шаг ${index + 1} из ${lesson.steps.length}`), make("p", task.text));
    task.options.forEach((text, choice) => body.append(button(text, () => {
      feedback.textContent = choice === task.correct ? `Верно. ${task.why}` : "Попробуйте другой ответ. Это безопасная тренировка — штрафов нет.";
      next.disabled = choice !== task.correct;
    })));
    body.append(feedback, next);
    next.addEventListener("click", () => body.querySelector("button")?.focus(), { once: true });
  }
  document.querySelectorAll("[data-game-guide]").forEach(el => el.addEventListener("click", () => {
    const lesson = lessons[el.dataset.gameGuide]; if (!lesson) return;
    document.getElementById("gameGuideTitle").textContent = lesson.title;
    rules(lesson); dialog.showModal();
  }));
  dialog.querySelectorAll("[data-guide-close]").forEach(el => el.addEventListener("click", () => dialog.close()));
})();

/* Игры за столом: общий каркас комнаты (V4_GAMES.md §3.1).

   Здесь то, что одинаково у всех игр: создать комнату или войти по коду,
   опрашивать сервер, пока экран открыт, считать таймеры, рисовать стол с
   очками и подтверждать необратимое вторым касанием. Сами правила и экраны
   партии — в game-spy.js и game-cipher.js; каждая игра регистрирует свой
   рисовальщик через window.ZhidaoGames.register.

   Телефон здесь не судья. Кто шпион, чьи слова на поле, чем кончилось
   голосование — решает сервер; экран показывает только то, что сервер
   прислал именно этому игроку. Кнопку можно подделать; исход нельзя.

   Свернули MAX, заблокировали телефон — опрос встаёт; вернулись — первым
   делом спрашиваем, что изменилось. Партия от этого не ломается: она живёт
   на сервере. */

(function () {
  const $ = (id) => document.getElementById(id);
  const POLL_MS = 2000;
  const TITLES = { spy: "Шпион Протокола", cipher: "Шифровальщики", outage: "Сбой системы" };
  const EXE = { spy: "SPY.EXE", cipher: "CIPHER.EXE", outage: "OUTAGE.EXE" };
  const renderers = {};

  let session = window.ZhidaoSession || null;
  let view = null;
  let switches = {};
  let signature = "";
  let pollTimer = null;
  let clockTimer = null;
  let refreshing = false;
  let inFlight = false;
  let phaseKey = null;
  let phaseEntrance = false;
  let phaseAnimation = null;
  const motionQuery = matchMedia("(prefers-reduced-motion: reduce)");
  function stopRestrictedMotion() {
    if (motionQuery.matches || document.documentElement.dataset.motion !== "full") phaseAnimation?.cancel();
  }
  motionQuery.addEventListener("change", stopRestrictedMotion);
  new MutationObserver(stopRestrictedMotion).observe(document.documentElement, { attributes: true, attributeFilter: ["data-motion"] });
  let local = {};           // состояние экрана игры; обнуляется при смене фазы
  let armed = null;         // выбор, ждущий второго касания
  let armedLabel = "";
  let leaveArmed = false;
  let holding = false;      // палец на скрытой карточке: перерисовку откладываем
  let pendingDraw = false;
  let timers = {};          // ключ → момент конца по performance.now()
  const zeroRefreshed = new Set();

  function node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  }

  function button(className, text, onClick) {
    const b = node("button", className, text);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }

  function signedIn() { return Boolean(session && session.mode === "authenticated"); }
  function onScreen() { return document.documentElement.dataset.currentScreen === "games"; }

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
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) window.dispatchEvent(new Event("zhidao:session-expired"));
        const error = new Error(typeof data.detail === "string" ? data.detail : "Запрос отклонён.");
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

  function nameOf(id) {
    const player = view && view.players.find((p) => p.account_id === Number(id));
    return player ? player.display_name : "игрок вышел";
  }

  function setNote(text) {
    const target = view ? $("gameNote") : $("gameIntroStatus");
    if (target) target.textContent = text || "";
  }

  // --- время -------------------------------------------------------------------

  function format(seconds) {
    const s = Math.max(0, Math.ceil(seconds));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  /* Сервер присылает «осталось N секунд», а не момент на своих часах: часы
     телефона бывают сбиты на минуты. Локально отсчитываем от получения и
     подправляем, только если разошлись заметно — иначе цифры прыгают. */
  function setTimer(key, seconds) {
    if (seconds == null) return;
    const end = performance.now() + seconds * 1000;
    if (timers[key] == null || Math.abs(timers[key] - end) > 1500) timers[key] = end;
  }

  function tickClocks() {
    const now = performance.now();
    document.querySelectorAll("#gameRoom [data-timer]").forEach((el) => {
      const key = el.dataset.timer;
      if (timers[key] == null) return;
      const left = (timers[key] - now) / 1000;
      el.firstChild.textContent = format(left);
      el.classList.toggle("is-low", left <= 30);
      // Время вышло на экране — спрашиваем сервер сразу, не дожидаясь опроса.
      if (left <= 0 && !zeroRefreshed.has(key)) {
        zeroRefreshed.add(key);
        refresh();
      }
    });
  }

  function timerEl(key, seconds, caption) {
    const el = node("div", "spy-timer");
    el.dataset.timer = key;
    el.append(document.createTextNode(format(seconds || 0)));
    if (caption) el.append(node("small", null, caption));
    return el;
  }

  // --- опрос -------------------------------------------------------------------

  function startPolling() {
    if (!view || !onScreen() || document.hidden) return;
    if (!pollTimer) pollTimer = setInterval(() => { if (!inFlight) refresh(); }, POLL_MS);
    if (!clockTimer) clockTimer = setInterval(tickClocks, 250);
  }

  function stopPolling() {
    clearInterval(pollTimer);
    clearInterval(clockTimer);
    pollTimer = null;
    clockTimer = null;
  }

  async function refresh() {
    if (!signedIn()) { drawIntro(); return; }
    if (refreshing) return;
    refreshing = true;
    try {
      apply(await api("/api/v4/games/rooms/current"));
    } catch (error) {
      setNote(error.message);
    } finally {
      refreshing = false;
    }
  }

  function reset() {
    view = null;
    signature = "";
    phaseKey = null;
    local = {};
    armed = null;
    timers = {};
    zeroRefreshed.clear();
  }

  function apply(data) {
    if (data && data.switches) switches = data.switches;
    if (!data || !data.room) {
      reset();
      stopPolling();
      drawIntro();
      return;
    }
    const renderer = renderers[data.room.game];
    if (!renderer) {
      setNote("Эту игру приложение пока не знает. Обновите страницу.");
      return;
    }
    const key = `${data.room.code}|${data.room.game}|${renderer.phaseKey(data.game)}`;
    if (key !== phaseKey) {
      phaseEntrance = phaseKey !== null;
      // Подсказка прошлой фазы («нажмите ещё раз…») к новой не относится.
      if (phaseKey !== null) $("gameNote").textContent = "";
      // Партия только что закончилась у меня на глазах — звук, если есть набор.
      if (phaseKey !== null && renderer.finished && renderer.finished(data.game) && window.ZhidaoSounds) {
        window.ZhidaoSounds.play("win");
      }
      phaseKey = key;
      local = {};
      armed = null;
      timers = {};
      zeroRefreshed.clear();
    }
    view = data;
    if (renderer.sync) renderer.sync(context());
    const next = [
      data.room.revision,
      data.players.map((p) => `${p.account_id}:${p.present ? 1 : 0}`).join(","),
    ].join("|");
    if (next !== signature) {
      signature = next;
      draw();
    }
    startPolling();
  }

  // --- действия -------------------------------------------------------------------

  async function run(task) {
    if (inFlight) return;
    inFlight = true;
    setNote("");
    try {
      apply(await task());
    } catch (error) {
      setNote(error.message);
      if (error.status === 404) refresh();
    } finally {
      inFlight = false;
    }
  }

  const post = (suffix, body) =>
    api(`/api/v4/games/rooms/${view.room.code}${suffix}`, { method: "POST", body });

  function redraw() {
    if (!view) return;
    signature = "";
    apply(view);
  }

  /* Обвинение, голос, открытая карточка — необратимы. Первое касание только
     выбирает, второе подтверждает: промах пальцем в толпе за столом не
     должен решать партию. Подсказка встаёт прямо над списком, где выбирают. */
  function confirmTwice(key, label, commit) {
    if (armed !== key) {
      armed = key;
      armedLabel = label;
      redraw();
      return;
    }
    armed = null;
    commit();
  }

  function armedBanner(prefix) {
    if (!armed || !armed.startsWith(prefix)) return null;
    return node("p", "spy-banner", `Нажмите ещё раз, чтобы подтвердить: ${armedLabel}.`);
  }

  function leave() {
    if (!leaveArmed) {
      leaveArmed = true;
      setNote("Нажмите × ещё раз, чтобы выйти из комнаты. Если идёт партия, ваше место за столом опустеет.");
      setTimeout(() => { leaveArmed = false; }, 4000);
      return;
    }
    leaveArmed = false;
    run(() => post("/leave"));
  }

  // --- общие детали экрана ----------------------------------------------------------

  function codePlate() {
    const plate = node("div", "spy-code-plate");
    plate.append(node("span", "spy-label", "Код комнаты"), node("b", "spy-code", view.room.code),
      node("span", "spy-hint", "Продиктуйте его остальным"));
    return plate;
  }

  function segmented(options, current, onPick) {
    const row = node("div", "spy-segmented");
    row.style.gridTemplateColumns = `repeat(${options.length}, minmax(0, 1fr))`;
    for (const [value, label] of options) {
      const b = button("btn btn-secondary", label, () => onPick(value));
      b.setAttribute("aria-pressed", String(current === value));
      row.append(b);
    }
    return row;
  }

  function playersList(opts = {}) {
    const wrap = node("div", "spy-actions");
    wrap.append(node("span", "spy-label", opts.label || "За столом · очки вечера"));
    if (opts.armedPrefix) {
      const banner = armedBanner(opts.armedPrefix);
      if (banner) wrap.append(banner);
    }
    const list = node("div", "spy-players");
    for (const player of view.players) {
      const eligible = Boolean(opts.selectable && opts.selectable(player));
      const row = node(eligible ? "button" : "div", "spy-player");
      if (eligible) {
        row.type = "button";
        if (opts.keyFor && armed === opts.keyFor(player)) row.classList.add("is-armed");
        row.addEventListener("click", () => opts.onPick(player));
      }
      if (!player.present) row.classList.add("is-away");
      // Аватар с рамкой, купленной на витрине; точка присутствия — в углу.
      const avatar = node("span", "spy-avatar cosmetic-avatar");
      if (player.frame) avatar.dataset.frame = player.frame;
      avatar.setAttribute("aria-hidden", "true");
      const dot = node("span", `spy-dot${player.present ? " is-on" : ""}`);
      avatar.append(dot);
      const name = node("span", "spy-player-name", player.display_name);
      const tags = [];
      if (player.account_id === view.room.host_account_id) tags.push("ведущий");
      if (player.account_id === view.you) tags.push("вы");
      if (opts.tags) tags.push(...opts.tags(player));
      if (!player.present) tags.push("нет на связи");
      if (tags.length) name.append(node("small", null, tags.join(" · ")));
      row.append(avatar, name, node("span", "spy-score", String(player.score)));
      list.append(row);
    }
    wrap.append(list);
    return wrap;
  }

  function context() {
    return {
      view,
      room: view.room,
      game: view.game,
      you: view.you,
      local,
      node,
      button,
      format,
      nameOf,
      timerEl,
      setTimer,
      codePlate,
      segmented,
      playersList,
      armedBanner,
      confirmTwice,
      redraw,
      armed: () => armed,
      disarm: () => { armed = null; },
      banner: (text) => node("p", "spy-banner", text),
      act: (action, body) => run(() => post(`/${view.room.game}/${action}`, body)),
      settings: (body) => run(() => post("/settings", body)),
      setHolding: (value) => {
        holding = value;
        if (!value && pendingDraw) draw();
      },
    };
  }

  // --- отрисовка ------------------------------------------------------------------

  function drawIntro() {
    $("gameIntro").hidden = false;
    $("gameRoom").hidden = true;
    document.querySelectorAll("[data-create-game]").forEach((b) => {
      b.disabled = !signedIn() || switches[b.dataset.createGame] === false;
    });
    $("gameJoinSubmit").disabled = !signedIn();
    const off = Object.entries(switches).filter(([, on]) => on === false).map(([game]) => TITLES[game] || game);
    if (!signedIn()) $("gameIntroStatus").textContent = "Войдите, чтобы играть.";
    else if (off.length) $("gameIntroStatus").textContent = `Сейчас выключено организаторами: ${off.join(", ")}.`;
  }

  function draw() {
    if (holding) { pendingDraw = true; return; }
    pendingDraw = false;
    const renderer = renderers[view.room.game];
    const c = context();
    $("gameIntro").hidden = true;
    $("gameRoom").hidden = false;
    $("gameRoomTitle").textContent = `${TITLES[view.room.game] || "Игра"} · ${view.room.code}`;
    $("gameRoomPhase").textContent = renderer.phaseName(c.game, c.room);
    $("gameRoomExe").textContent = EXE[view.room.game] || "GAME.EXE";
    $("gameRoomBody").replaceChildren(...renderer.draw(c).filter(Boolean));
    $("gameRoom").dataset.game = view.room.game;
    if (phaseEntrance && document.documentElement.dataset.motion === "full" && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      phaseAnimation?.cancel();
      phaseAnimation = $("gameRoomBody").animate([{ opacity: .55, transform: "translateY(6px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 220, easing: "ease-out" });
    }
    phaseEntrance = false;
    tickClocks();
  }

  // --- подключение ---------------------------------------------------------------

  window.ZhidaoGames = {
    register(game, renderer) {
      renderers[game] = renderer;
      if (view && view.room.game === game) redraw();
    },
  };

  window.addEventListener("zhidao:auth", (event) => {
    session = event.detail;
    reset();
    stopPolling();
    $("gameIntroStatus").textContent = "";
    drawIntro();
    if (onScreen() && signedIn()) refresh();
  });

  window.addEventListener("zhidao:screen", (event) => {
    if (event.detail === "games") refresh();
    else stopPolling();
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling();
    else if (onScreen()) refresh();
  });

  document.querySelectorAll("[data-create-game]").forEach((b) => {
    b.addEventListener("click", () =>
      run(() => api("/api/v4/games/rooms", { method: "POST", body: { game: b.dataset.createGame } })));
  });

  $("gameJoinCode").addEventListener("input", (event) => {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 4);
  });

  $("gameJoinForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const code = $("gameJoinCode").value.replace(/\D/g, "");
    if (code.length !== 4) {
      $("gameIntroStatus").textContent = "Код комнаты — четыре цифры.";
      return;
    }
    run(() => api("/api/v4/games/rooms/join", { method: "POST", body: { code } }));
  });

  $("gameLeave").addEventListener("click", leave);

  drawIntro();
}());
