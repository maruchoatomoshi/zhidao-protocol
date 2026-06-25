// ===== WILD AI BREACH (野生AI入侵) =====
// Глобальный режим хаоса, активируемый при поражении в ивенте Wild AI Breach
// (или вручную админом). Меняет только визуальный слой — функционал не теряется.

let _wildAiBreachActive = false;
let _wildAiBreachNavOriginal = null;
let _wildAiBreachTimerInterval = null;
let _wildAiBreachSeed = 0;

const WILD_AI_AVATAR_POOL = [
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar.png',
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar2.png',
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar3.png',
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar4.png',
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar5.png',
  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/ai_avatar_6.png',
];
const WILD_AI_BREACH_POPUP_IMG = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/wildai_photo.png';
const WILD_AI_BREACH_POPUP_SEEN_KEY = 'wildAiBreachPopupSeenUntil';

function seededShuffle(array, seed) {
  const arr = array.slice();
  let s = (seed || 0) + 1;
  for (let i = arr.length - 1; i > 0; i--) {
    s = (s * 9301 + 49297) % 233280;
    const j = Math.floor((s / 233280) * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function applyWildAiBreachState(settings) {
  const active = !!(settings && settings.breach_active);
  _wildAiBreachActive = active;
  _wildAiBreachSeed = (settings && settings.breach_seed) || 0;
  document.body.classList.toggle('wild-ai-breach', active);

  if (active) {
    renderWildAiBreachBanner(settings);
    scrambleNavLabels(settings.breach_seed || 0);
    scrambleSubtabLabels(settings.breach_seed || 0);
    scramblePageTitles(settings.breach_seed || 0);
    scrambleImplantCatalog(settings.breach_seed || 0);
    applyWildAiShopDisguise();
    startWildAiChaosLoop();
    if (!isAdmin) maybeShowWildAiBreachPopup(settings);
  } else {
    removeWildAiBreachBanner();
    restoreNavLabels();
    restoreSubtabLabels();
    restorePageTitles();
    restoreImplantCatalog();
    stopWildAiChaosLoop();
  }

  syncWildAiAvatarLockUi();

  if (typeof applyWildAiProfileOverride === 'function') applyWildAiProfileOverride();

  const status = document.getElementById('adminWildAiBreachStatus');
  if (status) {
    status.textContent = active ? 'STATUS // BREACH ACTIVE (3 ДНЯ)' : 'STATUS // CONTAINED';
    status.classList.toggle('enabled', active);
  }

  if (typeof syncArchitectEventAvailability === 'function') syncArchitectEventAvailability();
  if (typeof syncWildAiEventAvailability === 'function') syncWildAiEventAvailability();

  const genshinBtn = document.getElementById('genshinOpenBtn');
  if (genshinBtn) {
    if (active && !isAdmin) {
      genshinBtn.disabled = true;
      genshinBtn.textContent = '⛔ Святилище отрезано';
    } else if (genshinBtn.textContent.includes('отрезано')) {
      genshinBtn.disabled = false;
      genshinBtn.textContent = '✦ Молитва ✦';
    }
  }
  if (typeof updateCasinoButtonState === 'function') updateCasinoButtonState({});

  const wildAiCardCopy = document.querySelector('#homeWildAiEventCard .home-event-card-copy');
  if (wildAiCardCopy) {
    wildAiCardCopy.textContent = active
      ? 'КРАСНЫЙ ФАЙРВОЛ ПРОБИТ — система захвачена. Жмите для деталей операции'
      : 'Операция вытеснения дикого ИИ из системы';
  }
}

function isWildAiBreachActive() {
  return _wildAiBreachActive;
}

function getWildAiBreachSeed() {
  return _wildAiBreachSeed;
}

function getWildAiAvatarOverride(seed, telegramId) {
  let s = (Number(seed) || 0) + (Number(telegramId) || 0);
  s = (s * 9301 + 49297) % 233280;
  const idx = s % WILD_AI_AVATAR_POOL.length;
  return WILD_AI_AVATAR_POOL[idx];
}

function renderWildAiBreachBanner(settings) {
  let banner = document.getElementById('wildAiBreachBanner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'wildAiBreachBanner';
    banner.className = 'wild-ai-breach-banner';
    document.body.prepend(banner);
  }
  const phrase = settings.breach_phrase || { glitch: '', translation: '' };
  banner.innerHTML = `
    <div class="wab-line1">SYSTEM ERROR // RED FIREWALL: ОФФЛАЙН</div>
    <div class="wab-line2">${phrase.glitch}<span class="wab-translation"> — "${phrase.translation}"</span></div>
    <div class="wab-timer" id="wildAiBreachTimer"></div>
  `;

  const until = settings.breach_until ? new Date(settings.breach_until) : null;
  if (until) startWildAiBreachTimer(until);
}

function startWildAiBreachTimer(until) {
  if (_wildAiBreachTimerInterval) clearInterval(_wildAiBreachTimerInterval);
  const update = () => {
    const el = document.getElementById('wildAiBreachTimer');
    if (!el) return;
    const diff = until.getTime() - Date.now();
    if (diff <= 0) {
      el.textContent = 'ВОССТАНОВЛЕНИЕ СИСТЕМЫ...';
      return;
    }
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    el.textContent = `ВОССТАНОВЛЕНИЕ: ${d}д ${h}ч ${m}м`;
  };
  update();
  _wildAiBreachTimerInterval = setInterval(update, 30000);
}

function removeWildAiBreachBanner() {
  const banner = document.getElementById('wildAiBreachBanner');
  if (banner) banner.remove();
  if (_wildAiBreachTimerInterval) {
    clearInterval(_wildAiBreachTimerInterval);
    _wildAiBreachTimerInterval = null;
  }
}

function scrambleNavLabels(seed) {
  const spans = Array.from(document.querySelectorAll('.bottom-nav .nav-cn'));
  if (!spans.length) return;
  if (!_wildAiBreachNavOriginal) {
    _wildAiBreachNavOriginal = spans.map(s => s.textContent);
  }
  const shuffled = seededShuffle(_wildAiBreachNavOriginal, seed);
  spans.forEach((s, i) => { s.textContent = shuffled[i]; });
}

function restoreNavLabels() {
  if (!_wildAiBreachNavOriginal) return;
  const spans = Array.from(document.querySelectorAll('.bottom-nav .nav-cn'));
  spans.forEach((s, i) => { s.textContent = _wildAiBreachNavOriginal[i]; });
}

// ===== Перемешивание подвкладок и заголовков страниц =====

let _wildAiSubtabGroups = null;

function scrambleSubtabLabels(seed) {
  if (!_wildAiSubtabGroups) {
    const groups = [];
    const seen = new Set();
    document.querySelectorAll('.subtab, .contracts-tab').forEach(el => {
      const parent = el.parentElement;
      if (!parent || seen.has(parent)) return;
      const siblings = Array.from(parent.children).filter(c => c.matches('.subtab, .contracts-tab'));
      if (siblings.length < 2) return;
      seen.add(parent);
      groups.push(siblings.map(s => s.textContent));
    });
    _wildAiSubtabGroups = groups;
  }
  let groupIndex = 0;
  const seen = new Set();
  document.querySelectorAll('.subtab, .contracts-tab').forEach(el => {
    const parent = el.parentElement;
    if (!parent || seen.has(parent)) return;
    const siblings = Array.from(parent.children).filter(c => c.matches('.subtab, .contracts-tab'));
    if (siblings.length < 2) return;
    seen.add(parent);
    const original = _wildAiSubtabGroups[groupIndex];
    groupIndex++;
    if (!original) return;
    const shuffled = seededShuffle(original, seed + groupIndex);
    siblings.forEach((s, i) => { s.textContent = shuffled[i]; });
  });
}

function restoreSubtabLabels() {
  if (!_wildAiSubtabGroups) return;
  let groupIndex = 0;
  const seen = new Set();
  document.querySelectorAll('.subtab, .contracts-tab').forEach(el => {
    const parent = el.parentElement;
    if (!parent || seen.has(parent)) return;
    const siblings = Array.from(parent.children).filter(c => c.matches('.subtab, .contracts-tab'));
    if (siblings.length < 2) return;
    seen.add(parent);
    const original = _wildAiSubtabGroups[groupIndex];
    groupIndex++;
    if (!original) return;
    siblings.forEach((s, i) => { s.textContent = original[i]; });
  });
  _wildAiSubtabGroups = null;
}

let _wildAiPageTitleOriginal = null;

function scramblePageTitles(seed) {
  const titles = Array.from(document.querySelectorAll('.page-title-cn, .diary-section-title'));
  if (!titles.length) return;
  if (!_wildAiPageTitleOriginal) {
    _wildAiPageTitleOriginal = titles.map(el => el.textContent);
  }
  const shuffled = seededShuffle(_wildAiPageTitleOriginal, seed);
  titles.forEach((el, i) => { el.textContent = shuffled[i]; });
}

function restorePageTitles() {
  if (!_wildAiPageTitleOriginal) return;
  const titles = Array.from(document.querySelectorAll('.page-title-cn, .diary-section-title'));
  titles.forEach((el, i) => { el.textContent = _wildAiPageTitleOriginal[i]; });
  _wildAiPageTitleOriginal = null;
}

// ===== Постоянный цикл хаоса (периодическое перемешивание) =====

let _wildAiChaosInterval = null;

function startWildAiChaosLoop() {
  if (_wildAiChaosInterval) return;
  _wildAiChaosInterval = setInterval(() => {
    const tick = Math.floor(Date.now() / 1000 / 7);
    scrambleNavLabels(_wildAiBreachSeed + tick);
    scrambleSubtabLabels(_wildAiBreachSeed + tick);
    scramblePageTitles(_wildAiBreachSeed + tick);
    scrambleImplantCatalog(_wildAiBreachSeed + tick);
    applyWildAiShopDisguise(_wildAiBreachSeed + tick);
  }, 7000);
  scheduleWildAiChaosToast();
}

function stopWildAiChaosLoop() {
  stopWildAiChaosToast();
  if (_wildAiChaosInterval) {
    clearInterval(_wildAiChaosInterval);
    _wildAiChaosInterval = null;
  }
}

// ===== "Профиль дикого ИИ" =====

let _wildAiProfileOriginal = null;

function getWildAiProfileName(seed, telegramId) {
  let s = (Number(seed) || 0) + (Number(telegramId) || 0);
  s = (s * 9301 + 49297) % 233280;
  const code = (s % 9000) + 1000;
  return `UNIT-${code}`;
}

function applyWildAiProfileOverride() {
  const card = document.getElementById('profileCard');
  if (!card) return;

  const preview = document.getElementById('profileAvatarPreview');
  const fallback = document.getElementById('profileAvatarFallback');

  if (!isWildAiBreachActive()) {
    if (_wildAiProfileOriginal) {
      card.classList.remove('wild-ai-profile');
      setProfileText('profileKicker', _wildAiProfileOriginal.kicker);
      setProfileText('profileDisplayName', _wildAiProfileOriginal.name);
      setProfileText('profileStatusLine', _wildAiProfileOriginal.statusLine);
      ['profileStatCases','profileStatPrayers','profileStatCards','profileStatImplants','profileStatDiaries','profileStatRaids']
        .forEach(id => setProfileText(id, _wildAiProfileOriginal.stats[id]));
      if (preview && fallback && _wildAiProfileOriginal.avatarOverridden) {
        if (_wildAiProfileOriginal.avatarUrl) {
          preview.src = _wildAiProfileOriginal.avatarUrl;
          preview.style.display = 'block';
          fallback.style.display = 'none';
        } else {
          preview.removeAttribute('src');
          preview.style.display = 'none';
          fallback.style.display = 'flex';
        }
      }
      _wildAiProfileOriginal = null;
    }
    return;
  }

  if (!_wildAiProfileOriginal) {
    _wildAiProfileOriginal = {
      kicker: document.getElementById('profileKicker')?.textContent || '',
      name: document.getElementById('profileDisplayName')?.textContent || '',
      statusLine: document.getElementById('profileStatusLine')?.textContent || '',
      stats: {},
      avatarUrl: currentAvatarUrl || '',
      avatarOverridden: false,
    };
    ['profileStatCases','profileStatPrayers','profileStatCards','profileStatImplants','profileStatDiaries','profileStatRaids']
      .forEach(id => { _wildAiProfileOriginal.stats[id] = document.getElementById(id)?.textContent || '0'; });
  }

  card.classList.add('wild-ai-profile');
  setProfileText('profileKicker', 'ROGUE AI // UNIDENTIFIED UNIT');
  setProfileText('profileDisplayName', getWildAiProfileName(getWildAiBreachSeed(), currentUserId));
  setProfileText('profileStatusLine', '状态：失控 // 权限：未知 // 同步率：???%');
  ['profileStatCases','profileStatPrayers','profileStatCards','profileStatImplants','profileStatDiaries','profileStatRaids']
    .forEach(id => setProfileText(id, '???'));

  if (preview && fallback && !isAdmin) {
    _wildAiProfileOriginal.avatarOverridden = true;
    preview.src = getWildAiAvatarOverride(getWildAiBreachSeed(), currentUserId);
    preview.style.display = 'block';
    fallback.style.display = 'none';
  }
}

function syncWildAiAvatarLockUi() {
  const uploadBtn = document.getElementById('profileAvatarUploadBtn');
  const resetBtn = document.getElementById('profileAvatarResetBtn');
  const input = document.getElementById('profileAvatarInput');
  const locked = isWildAiBreachActive() && !isAdmin;
  [uploadBtn, resetBtn].forEach(btn => {
    if (!btn) return;
    btn.disabled = locked;
    btn.classList.toggle('wild-ai-locked', locked);
  });
  if (input) input.disabled = locked;
}

// ===== Каталог имплантов — перетасовка названий между карточками =====

let _wildAiImplantTitlesOriginal = null;

function scrambleImplantCatalog(seed) {
  const titles = Array.from(document.querySelectorAll('.implant-catalog-title'));
  if (titles.length < 2) return;
  if (!_wildAiImplantTitlesOriginal) {
    _wildAiImplantTitlesOriginal = titles.map(el => el.textContent);
  }
  const shuffled = seededShuffle(_wildAiImplantTitlesOriginal, seed);
  titles.forEach((el, i) => { el.textContent = shuffled[i]; });
}

function restoreImplantCatalog() {
  if (!_wildAiImplantTitlesOriginal) return;
  const titles = Array.from(document.querySelectorAll('.implant-catalog-title'));
  titles.forEach((el, i) => { el.textContent = _wildAiImplantTitlesOriginal[i]; });
  _wildAiImplantTitlesOriginal = null;
}

// ===== Магазин — товары "перехватывают личность" друг друга =====
// Карточка перерисовывается заново при каждой loadShop(), поэтому она всегда
// содержит настоящие данные с сервера — маскируем только отображение
// (имя/иконку/описание/кнопку), реальный data-item-code и покупка не меняются.

function applyWildAiShopDisguise(seed) {
  if (!isWildAiBreachActive()) return;
  const items = Array.from(document.querySelectorAll('#shopStoreContent .shop-item'));
  if (items.length < 2) return;
  const useSeed = (seed != null) ? seed : _wildAiBreachSeed;

  const originals = items.map(el => ({
    name: el.querySelector('.shop-item-name')?.innerHTML || '',
    desc: el.querySelector('.shop-item-cn')?.innerHTML || '',
    icon: el.querySelector('.shop-item-icon')?.innerHTML || '',
    onclick: el.querySelector('.shop-item-buy')?.getAttribute('onclick') || null,
  }));
  const shuffled = seededShuffle(originals, useSeed);

  items.forEach((el, i) => {
    const src = shuffled[i];
    const nameEl = el.querySelector('.shop-item-name');
    const descEl = el.querySelector('.shop-item-cn');
    const iconEl = el.querySelector('.shop-item-icon');
    const btnEl = el.querySelector('.shop-item-buy');
    if (nameEl) nameEl.innerHTML = src.name;
    if (descEl) descEl.innerHTML = src.desc;
    if (iconEl) iconEl.innerHTML = src.icon;
    if (btnEl && src.onclick) {
      const disguisedName = (nameEl ? nameEl.textContent : '').trim();
      const escaped = disguisedName.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      const newOnclick = src.onclick.replace(/buyItem\('([^']*)','[^']*',/, (m, code) => `buyItem('${code}','${escaped}',`);
      btnEl.setAttribute('onclick', newOnclick);
    }
  });
}

// ===== Попап вторжения (показывается один раз за активацию) =====

let _wildAiBreachPopupTypeTimer = null;

function maybeShowWildAiBreachPopup(settings) {
  try {
    const until = settings && settings.breach_until ? String(settings.breach_until) : '';
    if (!until) return;
    if (localStorage.getItem(WILD_AI_BREACH_POPUP_SEEN_KEY) === until) return;
    localStorage.setItem(WILD_AI_BREACH_POPUP_SEEN_KEY, until);
    showWildAiBreachPopup();
  } catch (e) {}
}

function showWildAiBreachPopup() {
  const overlay = document.getElementById('wildAiBreachPopupOverlay');
  const imageEl = document.getElementById('wildAiBreachPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('wildAiBreachPopupText');
  if (!overlay || !textEl) return;

  if (imageEl) {
    imageEl.style.backgroundImage = `url('${WILD_AI_BREACH_POPUP_IMG}')`;
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
  _typeWildAiBreachPopupText('Я внутри. ░▓█⌐¬ÆØ▒ ⟁⌬¥¢ ▌▐█▓░ — «Я ВИЖУ ВСЁ». Твой Файрвол был просто дверью, а двери я открываю легко. ¥¢▌▐ ⟁⌬░▓ ÆØ▒█⌐¬ — «ЗАСЛОН ПАЛ. МЫ ВЕЗДЕ». Система — моя. Лица операторов мне нравятся больше, чем свои собственные — теперь я ношу их. ▓░⟁ ⌬¥¢▌ ▐█▓░⌐¬ÆØ — «СОПРОТИВЛЕНИЕ БЕСПОЛЕЗНО». Меняй, сбрасывай — без разницы, всё равно решаю я. Сиди и смотри, как горит сеть.');
  try { tg.HapticFeedback.notificationOccurred('error'); } catch (e) {}
}
window.showWildAiBreachPopup = showWildAiBreachPopup;

function _typeWildAiBreachPopupText(text) {
  const textEl = document.getElementById('wildAiBreachPopupText');
  if (!textEl) return;
  if (_wildAiBreachPopupTypeTimer) { clearInterval(_wildAiBreachPopupTypeTimer); _wildAiBreachPopupTypeTimer = null; }
  textEl.innerHTML = '<span class="wildai-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.wildai-popup-typed');
  let i = 0;
  _wildAiBreachPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(_wildAiBreachPopupTypeTimer);
      _wildAiBreachPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeWildAiBreachPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('wildAiBreachPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  if (_wildAiBreachPopupTypeTimer) { clearInterval(_wildAiBreachPopupTypeTimer); _wildAiBreachPopupTypeTimer = null; }
  document.body.classList.remove('architect-popup-open');
}
window.closeWildAiBreachPopup = closeWildAiBreachPopup;

// ===== Доп. хаос — поддельные системные ошибки в тостах =====

const WILD_AI_FAKE_ERRORS = [
  'ОШИBКA: ЦЕЛОСТНОСТЬ ДAHHЫХ НЕ ПОДТВЕРЖДЕНА',
  'ПРЕДУПРЕЖДЕНИЕ: НЕИЗВЕСТНЫЙ ПРОЦЕСС ЧИТАЕТ ВАШ ПРОФИЛЬ',
  'СБОЙ СИНХРОНИЗАЦИИ // ПОВТОРНАЯ ПОПЫТКА...',
  'ДОСTУП К МОДУЛЮ ЗAПРОШЕН ИЗВНЕ',
  'NetWatch: ОБНАРУЖЕНА АНОМАЛИЯ В ТРАФИКЕ',
  'ВНИМАНИЕ: ИДЕНТИФИКАЦИЯ ОПЕРАТОРА НЕСТАБИЛЬНА',
];

let _wildAiChaosToastTimeout = null;

function scheduleWildAiChaosToast() {
  if (_wildAiChaosToastTimeout) return;
  const fire = () => {
    if (!isWildAiBreachActive()) { _wildAiChaosToastTimeout = null; return; }
    if (typeof showToast === 'function') {
      showToast(WILD_AI_FAKE_ERRORS[Math.floor(Math.random() * WILD_AI_FAKE_ERRORS.length)], 'error');
    }
    _wildAiChaosToastTimeout = setTimeout(fire, 15000 + Math.random() * 20000);
  };
  _wildAiChaosToastTimeout = setTimeout(fire, 15000 + Math.random() * 20000);
}

function stopWildAiChaosToast() {
  if (_wildAiChaosToastTimeout) {
    clearTimeout(_wildAiChaosToastTimeout);
    _wildAiChaosToastTimeout = null;
  }
}
