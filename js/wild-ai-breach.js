// ===== WILD AI BREACH (野生AI入侵) =====
// Глобальный режим хаоса, активируемый при поражении в ивенте Wild AI Breach
// (или вручную админом). Меняет только визуальный слой — функционал не теряется.

let _wildAiBreachActive = false;
let _wildAiBreachNavOriginal = null;
let _wildAiBreachTimerInterval = null;
let _wildAiBreachSeed = 0;

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
  } else {
    removeWildAiBreachBanner();
    restoreNavLabels();
    restoreSubtabLabels();
    restorePageTitles();
    restoreImplantCatalog();
    stopWildAiChaosLoop();
  }

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
      ? 'BLACKWALL ПРОБИТ — система захвачена. Жмите для деталей операции'
      : 'Операция вытеснения дикого ИИ из системы';
  }
}

function isWildAiBreachActive() {
  return _wildAiBreachActive;
}

function getWildAiBreachSeed() {
  return _wildAiBreachSeed;
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
    <div class="wab-line1">SYSTEM ERROR // BLACKWALL: ОФФЛАЙН</div>
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
}

function stopWildAiChaosLoop() {
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

  if (!isWildAiBreachActive()) {
    if (_wildAiProfileOriginal) {
      card.classList.remove('wild-ai-profile');
      setProfileText('profileKicker', _wildAiProfileOriginal.kicker);
      setProfileText('profileDisplayName', _wildAiProfileOriginal.name);
      setProfileText('profileStatusLine', _wildAiProfileOriginal.statusLine);
      ['profileStatCases','profileStatPrayers','profileStatCards','profileStatImplants','profileStatDiaries','profileStatRaids']
        .forEach(id => setProfileText(id, _wildAiProfileOriginal.stats[id]));
    }
    return;
  }

  if (!_wildAiProfileOriginal) {
    _wildAiProfileOriginal = {
      kicker: document.getElementById('profileKicker')?.textContent || '',
      name: document.getElementById('profileDisplayName')?.textContent || '',
      statusLine: document.getElementById('profileStatusLine')?.textContent || '',
      stats: {},
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
