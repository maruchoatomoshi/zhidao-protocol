"use strict";

/* Adapted from Beijing js/instruction.js. Public help only, no game actions. */
(function () {
  const dialog = document.getElementById("appGuide");
  const body = document.getElementById("appGuideBody");
  const chapters = [
    ["schedule", "Привет, путешественник", "Я Юлия Витальевна — помощник Протокола. Здесь начинается твоя поездка на Хайнань. Открывай приложение из MAX. Просмотр оформления без входа не показывает личные данные и не позволяет играть или покупать."],
    ["profile", "Твой профиль", "Кнопка справа вверху открывает профиль. Здесь выбираются Аква или Луна-Аква, светлая и тёмная темы, движение и звуки, и отсюда же снова открывается эта инструкция."],
    ["schedule", "Сегодня", "Главная — точка входа в поездку. Здесь видно, что идёт прямо сейчас, твой день и что нового с прошлого входа; баланс — в шапке. Если написано «Маршрут ещё не активирован», расписание ещё не подключено: не принимай пустой экран за отмену мероприятий, уточни планы у вожатого."],
    ["rating", "REP и звёзды — не одно и то же", "REP показывает вклад в сезон и не тратится в магазине. ★ — валюта для покупок. Очки игр и юани рынка — отдельный счёт; некоторые игры дополнительно выдают награды по своим правилам. Проверяй условия на экране игры. Пекинские балансы автоматически не переносятся."],
    ["rating", "Бумажный дневник", "Веди дневник на бумаге, а в приложении смотри оценки вожатого. Оценки дают REP и ★ по правилам сезона. Первая оценка на три звезды за день даёт попытку кейса, если в запасе есть место. Самостоятельно отправлять текст дневника через приложение не нужно."],
    ["cases", "Кейсы", "Одно сканирование расходует одну попытку; в запасе максимум семь. Попытки выдаёт организатор, также они могут приходить за дневник. Сервер сохраняет результат, а анимация лишь показывает его. После обрыва связи вернись в кейсы и проверь историю — не нужно платить за показ результата повторно. Вероятности и призы находятся в справке кейсов."],
    ["collection", "Коллекция и импланты", "В «Ещё → Коллекция» находятся выигранные предметы. Каталог описывает возможные находки, а коллекция — то, чем ты владеешь. Неподключённые эффекты отмечены отдельно: старые пекинские описания не означают, что пассивные бонусы уже начисляются."],
    ["shop", "Магазин и косметика", "Магазин теперь в «Ещё». Витрина обновляется в 07:00 по времени сезона, количество товаров ограничено. Обои, рамки и звуки меняют оформление. Купон «+30 минут» погашает вожатый — покупка не разрешает уйти без согласования. Перед подтверждением проверяй цену и баланс."],
    ["games", "Ивенты — играем вместе", "Внизу открой «Ивенты». Здесь игры за столом, Протокол 60, Тайный агент, Рынок Контрабанды и игры на кампусе. Для комнат вводят код, общие игры запускает ведущий. Перед первой партией открой «Как играть?» — там правила и безопасные тренировки без наград. Секретные экраны не показывай соседям. GPS-игры запускаются только в согласованных и проверенных местах."],
    ["meet", "Встречи и пазл", "В «Ещё → Встречи» покажи другому участнику код или введи его код. Он действует 60 секунд. Оба получают недостающий кусочек пазла, ничего не теряя. Одна и та же пара получает кусочки один раз за сезон-день. Пазл собирается из девяти частей."],
    ["trade", "Обмен дубликатами", "Можно обменять только лишние экземпляры предметов из кейсов: последний остаётся у тебя. Выберите предметы, проверьте предложение и подтвердите оба. Сейчас сбор — 5★ с каждого, лимит — три обмена за сезон-день. Неравный обмен требует отдельного согласия. Никому не сообщай пароль — для обмена нужен только код."],
    ["antivirus", "Игровой вирус", "Вирус Протокола — эффект внутри приложения, не заражение телефона. Он может передаться при встрече или обмене. Можно пройти бесплатный тест на слова, дождаться окончания эффекта или купить лечение. Фаервол — временная защита. Актуальную стоимость смотри до подтверждения; инструкция ничего не списывает."],
    ["campus-map", "Карта кампуса", "Карта находится в «Ещё». Туман показывает исследованную территорию; отметка требует разрешения на геолокацию и достаточной точности GPS. Это не карта людей. Географию ещё проверяют: маршрут и безопасность уточняй у вожатого, особенно если карта расходится с местностью."],
    ["more", "Все разделы", "В «Ещё» собраны остальные разделы: Встречи, Обмен, Антивирус, Мастерская, Коллекция, Карта и Магазин. Не все разделы уже подключены; пекинские штрафы и расписания здесь не действуют автоматически — выполняй инструкции команды поездки."],
    ["profile", "Настрой под себя", "В профиле выбираются Аква или Луна-Аква, светлая и тёмная темы, движение и звуки. Если анимации мешают, отключи их: правила игры не изменятся. Купленные звуки необязательны. При проблеме запомни раздел и действие, затем обратись к вожатому — пароль и коды входа передавать не нужно."],
  ];
  let index = 0;
  let returnScreen = "more";
  const node = (tag, text) => { const el = document.createElement(tag); el.textContent = text; return el; };
  const button = (label, action) => { const el = node("button", label); el.type = "button"; el.className = "btn btn-secondary"; el.addEventListener("click", action); return el; };
  function clear() { body.replaceChildren(); dialog.scrollTop = 0; }
  function chooser() {
    dialog.classList.remove("is-tour"); clear();
    body.append(node("p", "Как в пекинской версии: можно прочитать справку или пройти экскурсию с Юлией Витальевной. Тексты обновлены для Хайнаня."),
      button("Текстовая инструкция", textGuide), button("Экскурсия по приложению", () => { index = 0; tour(); }));
  }
  function textGuide() {
    dialog.classList.remove("is-tour"); clear();
    chapters.forEach(([, title, text]) => { const section = document.createElement("details"); section.append(node("summary", title), node("p", text)); body.append(section); });
    body.append(button("Назад к выбору", chooser));
  }
  function tour() {
    clear(); dialog.classList.add("is-tour");
    const [screen, title, text] = chapters[index];
    if (typeof showScreen === "function") showScreen(screen);
    const pose = index === chapters.length - 1 ? "goodbyeing" : [3, 5, 10, 11, 13].includes(index) ? "thinking" : [0, 1, 6, 9].includes(index) ? "based" : "explaining";
    const portrait = document.createElement("img"); portrait.src = `./assets/guide/julia-${pose}.png`; portrait.alt = "Юлия Витальевна, помощник Протокола";
    portrait.className = "app-guide-portrait";
    const count = node("p", `Шаг ${index + 1} из ${chapters.length}`); count.setAttribute("role", "status");
    const stage = node("div", ""); stage.className = "app-guide-scene";
    const frame = node("div", ""); frame.className = "app-guide-frame"; frame.append(portrait);
    const heading = node("div", ""); heading.className = "app-guide-heading";
    const name = node("span", "Юлия Витальевна · помощник Протокола"); name.className = "app-guide-name";
    heading.append(name, count, node("h3", title));
    const speech = node("p", text); speech.className = "app-guide-speech";
    stage.append(frame, heading, speech); body.append(stage);
    const controls = document.createElement("div"); controls.className = "app-guide-controls";
    const prev = button("Назад", () => { index--; tour(); }); prev.disabled = index === 0;
    controls.append(prev, button(index === chapters.length - 1 ? "Готово" : "Далее", () => {
      if (index === chapters.length - 1) dialog.close(); else { index++; tour(); }
    }), button("Все разделы", textGuide));
    body.append(controls); controls.querySelectorAll("button")[1].focus();
  }
  document.querySelectorAll("[data-app-guide]").forEach(el => el.addEventListener("click", () => {
    returnScreen = document.documentElement.dataset.currentScreen || "more";
    chooser(); dialog.showModal();
  }));
  document.getElementById("appGuideClose").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { if (typeof showScreen === "function") showScreen(returnScreen); });
})();
