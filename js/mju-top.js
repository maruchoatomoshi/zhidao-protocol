// ===== МЮ — реакция на топ-1 рейтинга =====

const MJU_TOP_IMG = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/mu_happy.png';
const MJU_TOP_SEEN_KEY = 'mjuTop1Notified';

const MJU_TOP_PHRASES = [
  'Минуточку внимания. Топ-1 рейтинга — это ты? Узнаю стиль настоящего оператора. Так держать!',
  'Ого. Первое место. Если бы я был удивлён — но я не удивлён, я сразу знал, кто здесь лидер',
  'Поздравляю с первым местом! Главное теперь — не расслабляться, рейтинг штука переменчивая',
  'Первое место в рейтинге. Достойно. Запомни этот момент — конкуренты уже что-то придумывают',
];

let _mjuTopPopupTypeTimer = null;

function checkMjuTopRank(rank) {
  try {
    const seen = localStorage.getItem(MJU_TOP_SEEN_KEY) === '1';
    if (rank === 1) {
      if (!seen) {
        localStorage.setItem(MJU_TOP_SEEN_KEY, '1');
        showMjuTopPopup();
      }
    } else if (seen) {
      localStorage.removeItem(MJU_TOP_SEEN_KEY);
    }
  } catch (e) {}
}
window.checkMjuTopRank = checkMjuTopRank;

function showMjuTopPopup(text) {
  const overlay = document.getElementById('mjuTopPopupOverlay');
  const imageEl = document.getElementById('mjuTopPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('mjuTopPopupText');
  if (!overlay || !textEl) return;

  if (imageEl) {
    imageEl.style.backgroundImage = `url('${MJU_TOP_IMG}')`;
    imageEl.style.animation = 'none';
    void imageEl.offsetWidth;
    imageEl.style.animation = '';
  }
  if (box) {
    box.style.animation = 'none';
    void box.offsetWidth;
    box.style.animation = '';
  }

  document.body.classList.add('architect-popup-open');
  overlay.style.display = 'flex';
  _typeMjuTopText(text || MJU_TOP_PHRASES[Math.floor(Math.random() * MJU_TOP_PHRASES.length)]);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}
window.showMjuTopPopup = showMjuTopPopup;

function _typeMjuTopText(text) {
  const textEl = document.getElementById('mjuTopPopupText');
  if (!textEl) return;
  if (_mjuTopPopupTypeTimer) { clearInterval(_mjuTopPopupTypeTimer); _mjuTopPopupTypeTimer = null; }
  textEl.innerHTML = '<span class="mju-top-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.mju-top-popup-typed');
  let i = 0;
  _mjuTopPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(_mjuTopPopupTypeTimer);
      _mjuTopPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeMjuTopPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('mjuTopPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  if (_mjuTopPopupTypeTimer) { clearInterval(_mjuTopPopupTypeTimer); _mjuTopPopupTypeTimer = null; }
  document.body.classList.remove('architect-popup-open');
}
window.closeMjuTopPopup = closeMjuTopPopup;
