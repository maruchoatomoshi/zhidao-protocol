/**
 * ZHIDAO Protocol — Вводная новелла "КОНТУР" (онбординг при первом входе)
 */

const INTRO_NOVEL_SEEN_KEY = 'introNovelSeen';

const INTRO_NOVEL_CAST = {
  system:    { name: 'СИСТЕМА',                 avatar: '📡', color: '#7d8a99' },
  mju:       { name: '👑 МИХАИЛ ЮРЬЕВИЧ // МЮ',  avatar: '👑', color: '#ff003c' },
  yulia:     { name: '🛡️ ЮЛИЯ ВИТАЛЬЕВНА',       avatar: '🛡️', color: '#fa00ff' },
  liza:      { name: '💬 ЕЛИЗАВЕТА СЕРГЕЕВНА',   avatar: '💬', color: '#00f0ff' },
  architect: { name: '🟢 АРХИТЕКТОР',            avatar: '🟢', color: '#00ff66' }
};

function _buildIntroNovelScenes() {
  const frozen = !!window.APP_FEATURE_FREEZE_ENABLED;
  const scenes = [
    { who: 'system', text: 'Соединение установлено... Добро пожаловать в КОНТУР' },
    { who: 'system', text: 'Ты — новый оператор Контура' },
    { who: 'system', text: 'Можешь спросить — почему в этот раз должно быть иначе, чем раньше' },
    { who: 'system', text: 'Потому что в этот раз за Контуром стоят живые люди, а не просто правила на бумаге — сейчас они выйдут на связь' },
    { who: 'mju', text: 'Я Михаил Юрьевич. Для своих — МЮ. Я слежу, чтобы Контур не превратился в хаос: дисциплина, сборы, правила. Без этого ничего не работает' },
    { who: 'mju', text: 'Будь на связи, не теряйся, не подводи стаю — и всё будет в порядке' },
    { who: 'yulia', text: 'Привет! Я Юлия Витальевна, вожатая. Сейчас я на удалённой орбите — на связи дистанционно, но всё равно слежу за вами и помогаю издалека' },
    { who: 'yulia', text: 'Если что — пиши, не бойся' },
    { who: 'liza', text: 'А я — Елизавета Сергеевна. Запутался в правилах — спрашивай у меня. Моя задача — твой комфорт и равновесие' },
    { who: 'liza', text: 'Контур большой, но мы рядом' }
  ];
  if (frozen) {
    scenes.push({ who: 'architect', text: 'Я — Марк Альбертович, в системе я Архитектор, который выстроил эту систему. Сейчас часть разделов ещё закрыта, но они будут открываться один за другим перед самой поездкой' });
    scenes.push({ who: 'architect', text: 'Заходи, смотри, что уже доступно сейчас. Остальное появится само — просто будь на связи. Контур запущен. Удачи, оператор' });
  } else {
    scenes.push({ who: 'architect', text: 'Я — Марк Альбертович, в системе я Архитектор, который выстроил эту систему: баллы, кейсы, рейтинг, дневник — всё это не просто игра, а способ сделать поездку живой и честной' });
    scenes.push({ who: 'architect', text: 'Заходи, открывай разделы, набирай очки, читай дневник. Контур запущен. Удачи, оператор' });
  }
  return scenes;
}

let _introNovelScenes = [];
let _introNovelIndex = 0;
let _introNovelTypeInterval = null;

function showIntroNovel(force) {
  try {
    if (!force && localStorage.getItem(INTRO_NOVEL_SEEN_KEY) === '1') return;
  } catch (e) {}
  _introNovelScenes = _buildIntroNovelScenes();
  _introNovelIndex = 0;
  const overlay = document.getElementById('introNovelOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  _renderIntroNovelScene();
}
window.showIntroNovel = showIntroNovel;

function _renderIntroNovelScene() {
  const scene = _introNovelScenes[_introNovelIndex];
  if (!scene) { closeIntroNovel(); return; }
  const cast = INTRO_NOVEL_CAST[scene.who] || INTRO_NOVEL_CAST.system;
  const titleEl = document.getElementById('introNovelTitle');
  const closeEl = document.getElementById('introNovelClose');
  const nextBtn = document.getElementById('introNovelNextBtn');
  if (titleEl) { titleEl.textContent = cast.name; titleEl.style.color = cast.color; titleEl.style.borderColor = cast.color + '66'; titleEl.style.background = cast.color + '14'; }
  if (closeEl) { closeEl.style.color = cast.color; closeEl.style.borderColor = cast.color + '4d'; }
  if (nextBtn) nextBtn.textContent = (_introNovelIndex === _introNovelScenes.length - 1) ? 'НАЧАТЬ ▸' : 'ДАЛЕЕ ▸';
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
  _introNovelIndex++;
  if (_introNovelIndex >= _introNovelScenes.length) {
    closeIntroNovel();
    return;
  }
  _renderIntroNovelScene();
}
window.introNovelNext = introNovelNext;

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
