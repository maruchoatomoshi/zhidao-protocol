// ===== Елизавета Сергеевна — отбой после 23:00 =====

const LIZA_IMG = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/liza_warning.png';
const LIZA_SEEN_KEY = 'lizaCurfewSeenDate';

const LIZA_PHRASES = [
  'Так, кто это у нас тут гуляет по приложению после отбоя? Быстро закрывай и спать —  магазин подождёт до утра',
  'О, полуночник нашёлся. За нарушение режима баллы не положены, а вот лекция от меня — пожалуйста',
  'Время — за 23:00. У нормальных людей сейчас отбой, а не открытие приложений. Закрывай и спать, утром глянешь рейтинг',
  'Так-так-так. Не спим? Я тоже не спала — составляла список нарушителей режима. Ты в нём первый',
  'Внимание, отбой! Поймала бы тебя в коридоре в такое время — стояли бы у двери до утра. Закрывай телефон',
  'Серьёзно? В это время положено спать, а не сидеть и залипать в игрульки. За пунктуальность баллов нет, а вот за отбой вы нарушаете равновесие системы',
];

let _lizaPopupTypeTimer = null;
let _lizaPollInterval = null;

function _getBeijingDateStr() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
}

function _getBeijingHour() {
  const h = new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai', hour: 'numeric', hour12: false });
  return parseInt(h);
}

function checkLizaCurfew() {
  try {
    if (_getBeijingHour() < 23) return;
    const dateStr = _getBeijingDateStr();
    if (localStorage.getItem(LIZA_SEEN_KEY) === dateStr) return;
    localStorage.setItem(LIZA_SEEN_KEY, dateStr);
    showLizaPopup();
  } catch (e) {}
}
window.checkLizaCurfew = checkLizaCurfew;

function startLizaCurfewPoller() {
  if (_lizaPollInterval) return;
  checkLizaCurfew();
  _lizaPollInterval = setInterval(checkLizaCurfew, 60000);
}
window.startLizaCurfewPoller = startLizaCurfewPoller;

// ===== Пасхалка: 7 тапов по главному лого =====
const LIZA_EASTER_PHRASES = [
  'Так, кто это тут тыкает в логотип семь раз подряд? Думал, что будет приз? Да, будет. Звание "Делать нечего 2026"',
  'Поздравляю, ты разблокировал секрет, нажав на картинку семь раз. Я одновременно горжусь и переживаю',
  'Нашёл пасхалку. Награды не будет, но я теперь знаю, что у тебя есть терпение на семь тапов',
];

let _logoTapCount = 0;
let _logoTapTimer = null;

function handleLogoEasterTap() {
  _logoTapCount++;
  clearTimeout(_logoTapTimer);
  _logoTapTimer = setTimeout(() => { _logoTapCount = 0; }, 1500);
  if (_logoTapCount >= 7) {
    _logoTapCount = 0;
    clearTimeout(_logoTapTimer);
    showLizaPopup(LIZA_EASTER_PHRASES[Math.floor(Math.random() * LIZA_EASTER_PHRASES.length)]);
  }
}
window.handleLogoEasterTap = handleLogoEasterTap;

function showLizaPopup(text) {
  const overlay = document.getElementById('lizaPopupOverlay');
  const imageEl = document.getElementById('lizaPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('lizaPopupText');
  if (!overlay || !textEl) return;

  if (imageEl) {
    imageEl.style.backgroundImage = `url('${LIZA_IMG}')`;
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
  _typeLizaText(text || LIZA_PHRASES[Math.floor(Math.random() * LIZA_PHRASES.length)]);
  try { tg.HapticFeedback.notificationOccurred('warning'); } catch (e) {}
}
window.showLizaPopup = showLizaPopup;

function _typeLizaText(text) {
  const textEl = document.getElementById('lizaPopupText');
  if (!textEl) return;
  if (_lizaPopupTypeTimer) { clearInterval(_lizaPopupTypeTimer); _lizaPopupTypeTimer = null; }
  textEl.innerHTML = '<span class="liza-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.liza-popup-typed');
  let i = 0;
  _lizaPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(_lizaPopupTypeTimer);
      _lizaPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeLizaPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('lizaPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  if (_lizaPopupTypeTimer) { clearInterval(_lizaPopupTypeTimer); _lizaPopupTypeTimer = null; }
  document.body.classList.remove('architect-popup-open');
}
window.closeLizaPopup = closeLizaPopup;
