/**
 * ZHIDAO Protocol — Вводная визуальная новелла (онбординг при первом входе)
 */

const INTRO_NOVEL_SEEN_KEY = 'introNovelSeen_20260623a';
const INTRO_NOVEL_GH = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/';

const INTRO_NOVEL_CAST = {
  system:    { name: 'СИСТЕМА',                 color: '#7d8a99', image: INTRO_NOVEL_GH + 'logo.png' },
  mju:       { name: 'МИХАИЛ ЮРЬЕВИЧ // МЮ',    color: '#ff003c', image: INTRO_NOVEL_GH + 'mu_happy.png' },
  yulia:     { name: 'ЮЛИЯ ВИТАЛЬЕВНА',          color: '#fa00ff', image: INTRO_NOVEL_GH + 'julia_based.png' },
  liza:      { name: 'ЕЛИЗАВЕТА СЕРГЕЕВНА',      color: '#00f0ff', image: INTRO_NOVEL_GH + 'liza_neutral-Photoroom.png' },
  tianhao:   { name: '孙天昊 СУНЬ ТЯНЬХАО',       color: '#ffaa00', image: INTRO_NOVEL_GH + 'tianhao_explaining.png' },
  architect: { name: 'АРХИТЕКТОР',               color: '#00ff66', image: INTRO_NOVEL_GH + 'architect_happy.png' }
};

function _buildIntroNovelScenes() {
  const prelaunch = !!window.APP_FEATURE_FREEZE_ENABLED || !!window.APP_LAUNCH_LOCK_ENABLED;
  const finalStart = prelaunch ? 'fA1' : 'fB1';
  return {
    s1:  { who: 'system', text: 'Соединение установлено... Добро пожаловать в ZHIDAO Protocol', next: 's2' },
    s2:  { who: 'system', text: 'Ты — новый оператор ZHIDAO Protocol', next: 's3' },
    s3:  { who: 'system', text: 'До старта поездки осталось немного времени Некоторые разделы уже активны Некоторые ждут разрешения', next: 's4' },
    s4:  { who: 'system', text: 'Можешь спросить: почему в этот раз должно быть иначе, чем раньше', choices: [
            { label: 'Потому что теперь всё под контролем?', next: 's5a' },
            { label: 'Потому что это не просто поездка?', next: 's5b' },
            { label: 'Пока не понимаю', next: 's5c' }
          ] },
    s5a: { who: 'system', text: 'Отчасти Дело не только в контроле, но и в том, кто стоит за ним', next: 's6' },
    s5b: { who: 'system', text: 'Именно Это история, которая пишется здесь и сейчас', next: 's6' },
    s5c: { who: 'system', text: 'Ничего, сейчас поймёшь', next: 's6' },
    s6:  { who: 'system', text: 'Раньше правила жили в чатах, таблицах, голосовых сообщениях и памяти взрослых', next: 's7' },
    s7:  { who: 'system', text: 'Но в поездке всё меняется быстро: сборы, занятия, маршруты, отбой, вопросы, потерянные вещи, внезапные поручения', next: 's8' },
    s8:  { who: 'system', text: 'Протокол создан, чтобы всё это не распалось на хаос', next: 's9' },
    s9:  { who: 'system', text: 'Но Протокол не просто набор правил', next: 's10' },
    s10: { who: 'system', text: 'За ним стоят живые люди Сейчас они выйдут на связь', next: 's11' },

    s11: { who: 'mju', text: 'Я Михаил Юрьевич, главный в нашей поездке', next: 's12' },
    s12: { who: 'mju', text: 'Я слежу, чтобы Протокол не превратился в хаос: дисциплина, сборы, правила Без этого ничего не работает', next: 's13' },
    s13: { who: 'mju', text: 'Будь на связи, не теряйся, не подводи стаю, и всё будет в порядке', next: 's14' },
    s14: { who: 'mju', text: 'Если система просит отметиться — отметься Если сказали быть в точке сбора, будь там Это не формальность', next: 's14h' },
    s14h: { who: 'mju', text: 'Дальше подключится тот, кто всегда на связи, даже если физически далеко', next: 's15' },
    s15: { who: 'system', text: 'Узел дисциплины подключён', next: 's16r' },
    s16r: { who: 'yulia', text: 'Узнаю Михаила Юрьевича — сразу к делу Ладно, теперь я', next: 's16' },

    s16: { who: 'yulia', text: 'Привет! Я Юлия Витальевна, вожатая', next: 's17' },
    s17: { who: 'yulia', text: 'Сейчас я на удалённой орбите, на связи дистанционно, но всё равно слежу за вами и помогаю издалека', next: 's18' },
    s18: { who: 'yulia', text: 'Если что, пиши, не бойся', next: 's19' },
    s19: { who: 'yulia', text: 'В поездке не бывает глупых вопросов Бывает только момент, когда ты промолчал, а потом стало сложнее', next: 's19h' },
    s19h: { who: 'yulia', text: 'Если что-то про комфорт и нервы — это не ко мне, это к тому, кто рядом с вами физически, а не на орбите', next: 's20' },
    s20: { who: 'system', text: 'Узел связи подключён', next: 's21r' },
    s21r: { who: 'liza', text: 'Юлия Витальевна меня уже представила, спасибо ей Сейчас по порядку', next: 's21' },

    s21: { who: 'liza', text: 'А я, Елизавета Сергеевна', next: 's22' },
    s22: { who: 'liza', text: 'Запутался в правилах, спрашивай у меня Моя задача — твой комфорт и равновесие', next: 's23' },
    s23: { who: 'liza', text: 'Протокол большой, но мы рядом', next: 's24' },
    s24: { who: 'liza', text: 'Не надо пытаться разобраться во всём одному В этой системе помощь — тоже часть прогресса', next: 's24h' },
    s24h: { who: 'liza', text: 'Скоро на связь выйдет тот, кто говорит на двух языках сразу Он — про Пекин, а я — про то, что происходит у вас внутри', next: 's25' },
    s25: { who: 'system', text: 'Узел равновесия подключён', next: 's26' },

    s26: { who: 'system', text: 'Внешний контур отвечает...', next: 's27' },
    s27: { who: 'system', text: 'BEIJING NODE // ожидание подтверждения', next: 's28r' },
    s28r: { who: 'tianhao', text: 'Елизавета Сергеевна предупредила, что я скоро появлюсь 她说得对 — она права', next: 's28' },
    s28: { who: 'tianhao', text: '我叫孙天昊, я Сунь Тяньхао', next: 's29' },
    s29: { who: 'tianhao', text: 'Когда вы окажетесь в Пекине и мы с вами увидимся, город перестанет быть картинкой на карте', next: 's30' },
    s30: { who: 'tianhao', text: 'Там будут улицы, метро, столовые, магазины, фразы, которые нужно понять быстро, и ситуации, которых нет в учебнике', next: 's31' },
    s31: { who: 'tianhao', text: 'Я буду помогать вам с языком и бытовыми фразами Иногда одна правильная фраза экономит много сил', next: 's32' },
    s32: { who: 'tianhao', text: 'Слушай подсказки Повторяй Используй Китайский нужен не только на уроке', next: 's32h' },
    s32h: { who: 'tianhao', text: 'Дальше на связь выйдет тот, кто всё это построил Он не любит долгие предисловия', next: 's33' },
    s33: { who: 'system', text: 'Внешний контур Пекина подключён', next: 's34' },

    s34: { who: 'system', text: 'Остался последний узел', next: 's35' },
    s35: { who: 'system', text: 'ARCHITECT ACCESS // подтверждение...', next: 's36r' },
    s36r: { who: 'architect', text: 'Дисциплина, связь, равновесие, китайский — все узлы на месте Я просто завершаю круг', next: 's36' },
    s36: { who: 'architect', text: 'Я Марк Альбертович', next: 's37' },
    s37: { who: 'architect', text: 'В системе я Архитектор Я выстроил этот протокол: профиль, рейтинг, дневник, задания, магазин, события и всё, что будет сопровождать поездку', next: 's38' },
    s38: { who: 'architect', text: 'Но важно понять сразу: это не просто игра', next: 's39' },
    s39: { who: 'architect', text: 'Баллы ничего не значат, если за ними нет действий Рейтинг ничего не значит, если за ним нет вклада Протокол видит не слова, а участие', choices: [
            { label: 'Я готов подключиться', next: 's40a' },
            { label: 'А если я ошибусь?', next: 's40b' },
            { label: 'Что мне делать сейчас?', next: 's40c' }
          ] },
    s40a: { who: 'architect', text: 'Хорошо Тогда просто начни с малого: будь на связи, следи за объявлениями, не пропускай отметки', next: finalStart },
    s40b: { who: 'architect', text: 'Ошибки будут Для этого рядом люди Главное — не скрываться от системы и не пытаться ломать правила', next: finalStart },
    s40c: { who: 'architect', text: 'Смотри доступные разделы Читай объявления Проверяй профиль Остальное откроется, когда придёт время', next: finalStart },

    fA1: { who: 'architect', text: 'Сейчас часть разделов ещё закрыта Это не ошибка', next: 'fA2' },
    fA2: { who: 'architect', text: 'Протокол не открывается сразу полностью Он будет запускаться поэтапно — ближе к поездке и по мере готовности группы', next: 'fA3' },
    fA3: { who: 'architect', text: 'Заходи, смотри, что уже доступно сейчас Проверяй профиль, следи за объявлениями, привыкай к интерфейсу', next: 'fA4' },
    fA4: { who: 'architect', text: 'Остальное появится само Просто будь на связи', next: 'fA5' },
    fA5: { who: 'system', text: 'PRE-LAUNCH MODE активен', next: 'fA6' },
    fA6: { who: 'architect', text: 'Протокол запущен Удачи, оператор', next: null },

    fB1: { who: 'architect', text: 'Доступ открыт Протокол перешёл в боевой режим', next: 'fB2' },
    fB2: { who: 'architect', text: 'Баллы, рейтинг, дневник, задания, события — всё это теперь часть поездки', next: 'fB3' },
    fB3: { who: 'architect', text: 'Помогай группе, отмечайся вовремя, участвуй в событиях, используй китайский и не забывай смотреть объявления', next: 'fB4' },
    fB4: { who: 'architect', text: 'Протокол не требует идеальности Он требует участия', next: 'fB5' },
    fB5: { who: 'system', text: 'BEIJING MODE активен', next: 'fB6' },
    fB6: { who: 'architect', text: 'Протокол запущен Удачи, оператор', next: null }
  };
}

let _introNovelScenes = {};
let _introNovelCurrentId = 's1';
let _introNovelTypeInterval = null;

function showIntroNovel(force) {
  try {
    if (!force && localStorage.getItem(INTRO_NOVEL_SEEN_KEY) === '1') return;
  } catch (e) {}
  _introNovelScenes = _buildIntroNovelScenes();
  _introNovelCurrentId = 's1';
  const overlay = document.getElementById('introNovelOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  _renderIntroNovelScene();
}
window.showIntroNovel = showIntroNovel;

function _renderIntroNovelScene() {
  const scene = _introNovelScenes[_introNovelCurrentId];
  if (!scene) { closeIntroNovel(); return; }
  const cast = INTRO_NOVEL_CAST[scene.who] || INTRO_NOVEL_CAST.system;
  const titleEl = document.getElementById('introNovelTitle');
  const closeEl = document.getElementById('introNovelClose');
  const nextBtn = document.getElementById('introNovelNextBtn');
  const choicesEl = document.getElementById('introNovelChoices');
  const imageEl = document.getElementById('introNovelImage');
  if (titleEl) { titleEl.textContent = cast.name; titleEl.style.color = cast.color; titleEl.style.borderColor = cast.color + '66'; titleEl.style.background = cast.color + '14'; }
  if (closeEl) { closeEl.style.color = cast.color; closeEl.style.borderColor = cast.color + '4d'; }
  if (imageEl) {
    imageEl.style.backgroundImage = `url('${cast.image}')`;
    imageEl.classList.toggle('intro-novel-image-contain', scene.who === 'system');
  }

  if (scene.choices && scene.choices.length) {
    if (nextBtn) nextBtn.style.display = 'none';
    if (choicesEl) {
      choicesEl.style.display = 'flex';
      choicesEl.innerHTML = scene.choices.map((c, i) =>
        `<button class="intro-novel-btn" onclick="introNovelChoose(${i})">${escapeHtml(c.label)}</button>`
      ).join('');
    }
  } else {
    if (choicesEl) { choicesEl.style.display = 'none'; choicesEl.innerHTML = ''; }
    if (nextBtn) {
      nextBtn.style.display = '';
      nextBtn.textContent = scene.next ? 'ПРОДОЛЖИТЬ ПОДКЛЮЧЕНИЕ ▸' : 'ЗАВЕРШИТЬ ▸';
    }
  }
  _typeIntroNovelText(scene.text);
}

function _typeIntroNovelText(text) {
  const el = document.getElementById('introNovelText');
  if (!el) return;
  if (_introNovelTypeInterval) clearInterval(_introNovelTypeInterval);
  el.textContent = '';
  let i = 0;
  _introNovelTypeInterval = setInterval(() => {
    el.textContent += text[i] || '';
    i++;
    if (i >= text.length) clearInterval(_introNovelTypeInterval);
  }, 18);
}

function introNovelNext() {
  const scene = _introNovelScenes[_introNovelCurrentId];
  if (!scene || !scene.next) { closeIntroNovel(); return; }
  _introNovelCurrentId = scene.next;
  _renderIntroNovelScene();
}
window.introNovelNext = introNovelNext;

function introNovelChoose(choiceIndex) {
  const scene = _introNovelScenes[_introNovelCurrentId];
  if (!scene || !scene.choices || !scene.choices[choiceIndex]) return;
  _introNovelCurrentId = scene.choices[choiceIndex].next;
  _renderIntroNovelScene();
}
window.introNovelChoose = introNovelChoose;

function introNovelSkip() {
  closeIntroNovel();
}
window.introNovelSkip = introNovelSkip;

function closeIntroNovel() {
  if (_introNovelTypeInterval) clearInterval(_introNovelTypeInterval);
  try { localStorage.setItem(INTRO_NOVEL_SEEN_KEY, '1'); } catch (e) {}
  const overlay = document.getElementById('introNovelOverlay');
  if (overlay) overlay.style.display = 'none';
}
window.closeIntroNovel = closeIntroNovel;
