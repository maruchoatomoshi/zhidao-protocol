function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function isLaunchGateActive() {
  return !!window.APP_LAUNCH_LOCK_ENABLED && !!currentUserId && !isAdmin && !isArchitect;
}

function getLaunchGateTargetDate() {
  const value = window.APP_LAUNCH_TARGET_AT || '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatLaunchGateCountdown() {
  const target = getLaunchGateTargetDate();
  if (!target) return 'Ожидаем дату запуска';

  const diff = target.getTime() - Date.now();
  if (diff <= 0) return 'Ожидаем официальный запуск';

  const totalSeconds = Math.floor(diff / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return `${days}д ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function updateLaunchGateCountdowns() {
  const text = formatLaunchGateCountdown();
  document.querySelectorAll('[data-launch-countdown]').forEach(el => {
    el.textContent = text;
  });
  const freezeText = formatFeatureFreezeCountdown();
  document.querySelectorAll('[data-freeze-countdown]').forEach(el => {
    el.textContent = freezeText;
  });
  const shopResetText = formatShopResetCountdown();
  document.querySelectorAll('[data-shop-reset-countdown]').forEach(el => {
    el.textContent = shopResetText;
  });
}

// Дневные лимиты магазина сбрасываются в полночь по Пекину (UTC+8).
function formatShopResetCountdown() {
  const now = new Date();
  const beijingMs = now.getTime() + 8 * 3600 * 1000;
  const beijingDate = new Date(beijingMs);
  const msIntoDay = beijingDate.getUTCHours() * 3600000
    + beijingDate.getUTCMinutes() * 60000
    + beijingDate.getUTCSeconds() * 1000
    + beijingDate.getUTCMilliseconds();
  const msLeft = 24 * 3600000 - msIntoDay;
  const totalSeconds = Math.floor(msLeft / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function syncLaunchGateVisibility() {
  const active = isLaunchGateActive();
  document.body.classList.toggle('launch-locked', active);

  const card = document.getElementById('launchGateCard');
  if (card) card.style.display = active ? 'block' : 'none';

  updateLaunchGateCountdowns();
}

function showLaunchGateOverlay() {
  syncLaunchGateVisibility();
  const overlay = document.getElementById('launchGateOverlay');
  if (!overlay) return;

  overlay.classList.add('show');
  try { tg.HapticFeedback.notificationOccurred('warning'); } catch(e) {}
}

function closeLaunchGateOverlay() {
  const overlay = document.getElementById('launchGateOverlay');
  if (overlay) overlay.classList.remove('show');
}

// === ЗАМОРОЗКА ОТДЕЛЬНЫХ РАЗДЕЛОВ ===
// Ключи совпадают с именами страниц (showPage) и секций (openMore).
const FEATURE_FREEZE_LABELS = {
  casino:        'КЕЙСЫ / МОЛИТВЫ',
  shop:          'МАГАЗИН',
  implants:      'ИМПЛАНТЫ / КАРТОЧКИ',
  laundry:       'СТИРКА / ВОДА',
  achievements:  'АЧИВКИ',
  'diary-stars': 'ДНЕВНИК ★',
  rating:        'РЕЙТИНГ',
};

function isFeatureFrozen(name) {
  if (!window.APP_FEATURE_FREEZE_ENABLED) return false;
  if (!currentUserId || isAdmin || isArchitect) return false;
  return !!(window.APP_FROZEN_FEATURES || {})[name];
}

function formatFeatureFreezeCountdown() {
  const target = new Date(window.APP_FREEZE_TARGET_AT || '');
  if (Number.isNaN(target.getTime())) return '';
  const diff = target.getTime() - Date.now();
  if (diff <= 0) return 'Скоро открытие';
  const totalSeconds = Math.floor(diff / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return `${days}д ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

function showFeatureFreezeOverlay(name) {
  const overlay = document.getElementById('featureFreezeOverlay');
  if (!overlay) return;
  const titleEl = document.getElementById('featureFreezeTitle');
  if (titleEl) titleEl.textContent = FEATURE_FREEZE_LABELS[name] || 'ЭТОТ РАЗДЕЛ';
  const cd = formatFeatureFreezeCountdown();
  const timerEl = document.getElementById('featureFreezeTimer');
  if (timerEl) { timerEl.textContent = cd; timerEl.style.display = cd ? 'block' : 'none'; }
  overlay.classList.add('show');
  try { tg.HapticFeedback.notificationOccurred('warning'); } catch(e) {}
}

function closeFeatureFreezeOverlay() {
  const overlay = document.getElementById('featureFreezeOverlay');
  if (overlay) overlay.classList.remove('show');
}

// Помечает замочком пункты навигации/меню с data-feature, если раздел заморожен.
function syncFeatureFreezeBadges() {
  document.querySelectorAll('[data-feature]').forEach(el => {
    el.classList.toggle('feature-frozen', isFeatureFrozen(el.getAttribute('data-feature')));
  });
}

let _currentPage = 'home';

function showPage(name, btn) {
  if (isLaunchGateActive() && name !== 'home') {
    showLaunchGateOverlay();
    return;
  }

  if (isFeatureFrozen(name)) {
    showFeatureFreezeOverlay(name);
    return;
  }

  if (name === 'diary' && !isAdmin) {
    if (typeof syncDiaryAccessVisibility === 'function') syncDiaryAccessVisibility();
    try { showToast('Архив дневника доступен только администраторам.'); } catch(e) {}
    return;
  }

  const alreadyActive = _currentPage === name;
  _currentPage = name;
  if (name !== 'contracts' && typeof stopContractsAutoRefresh === 'function') {
    stopContractsAutoRefresh();
  }

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  // Clear stale DOM content BEFORE .active is set so old cards don't animate
  if (!alreadyActive) {
    const clearMap = {
      shop:     ['shopStoreContent'],
      rating:   ['leaderboardContent'],
    };
    (clearMap[name] || []).forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });
  }

  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');

  // Pages that always refresh (live data)
  if (name === 'schedule') { loadAnnouncements(); loadSchedule(); }
  // Pages that load only once per visit
  if (name === 'implants') {
    loadImplants(currentUserId);
    if (typeof loadCasinoStatus === 'function') loadCasinoStatus();
    if (isDemoMode && typeof installDemoCatalogLocks === 'function') installDemoCatalogLocks();
  }
  if (name === 'shop' && !alreadyActive) loadShop();
  if (name === 'rating') { loadLeaderboard(); updateRatingPoints(); }
  if (name === 'diary') loadDiaryPage();
  if (name === 'diary-stars') initDiaryStarsPage();
  if (name === 'contracts') { if (typeof openContractsPage === 'function') openContractsPage(); }
  if (name === 'casino') {
    fetch(`${API_URL}/api/settings`).then(r => r.json()).then(settings => {
      if (settings.blackwall && !isAdmin) {
        setCasinoBlackwallState(true);
      } else {
        setCasinoBlackwallState(false);
        if (currentThemePath === 'genshin') {
          document.getElementById('casinoPlayContent').style.display = 'none';
          const gcEl = document.getElementById('casinoGenshinContent');
          if (gcEl) gcEl.style.display = 'flex';
        } else {
          document.getElementById('casinoPlayContent').style.display = 'flex';
          setTimeout(initRoulette, 50);
        }
        setTimeout(() => loadPoints(currentUserId), 300);
        if (typeof loadCasinoStatus === 'function') setTimeout(loadCasinoStatus, 350);
      }
    }).catch(() => { setTimeout(initRoulette, 50); });
  }
}

function syncAdminUiVisibility() {
  document.body.classList.toggle('is-admin', !!isAdmin);
  syncLaunchGateVisibility();
  syncFeatureFreezeBadges();
  if (typeof syncArchitectEventAvailability === 'function') syncArchitectEventAvailability();
  if (typeof syncWildAiEventAvailability === 'function') syncWildAiEventAvailability();

  const shopReset = document.getElementById('shopResetBtn');
  if (shopReset) shopReset.style.display = isAdmin ? 'block' : 'none';

  const adminThemeBtn = document.getElementById('theme-btn-admin');
  if (adminThemeBtn) adminThemeBtn.style.display = isAdmin ? '' : 'none';

  const architectThemeBtn = document.getElementById('theme-btn-architect');
  if (architectThemeBtn) architectThemeBtn.style.display = isArchitect ? '' : 'none';
}

function openMore(section) {
  if (isLaunchGateActive()) {
    showLaunchGateOverlay();
    return;
  }

  if (isFeatureFrozen(section)) {
    showFeatureFreezeOverlay(section);
    return;
  }

  // Скрываем все субстраницы
  ['themes','map','weather','laundry','news','achievements','team','admin','stats'].forEach(s => {
    const el = document.getElementById('more-' + s);
    if (el) el.style.display = 'none';
  });
  const el = document.getElementById('more-' + section);
  if (!el) return;
  if (currentMoreSection === section) {
    el.style.display = 'none';
    currentMoreSection = null;
  } else {
    el.style.display = 'block';
    currentMoreSection = section;
    if (section === 'themes' && isAdmin) {
      ['theme-btn-genshin-light', 'theme-btn-genshin-dark'].forEach(id => {
        const cardEl = document.getElementById(id);
        if (cardEl) cardEl.style.display = '';
      });
    }
    if (section === 'achievements') {
      loadAchievements();
      if (typeof renderArchitectDiary === 'function') renderArchitectDiary();
    }
    if (section === 'news') loadAnnouncements();
    if (section === 'laundry') { initLaundry(); }
    if (section === 'team' && typeof renderTeamCards === 'function') renderTeamCards();
    if (section === 'map' && typeof initCampusMap === 'function') initCampusMap();
  }
}

// ===== ДАННЫЕ =====
// loadUserData() живёт ниже как обёртка с ретраями над zFetchUserProfile /
// zApplyUserProfile. Старая inline-реализация удалена как мёртвый код:
// две function-декларации с одним именем — побеждала вторая.

// ── ADMIN EXCLUSIVE INTRO VIDEOS ─────────────────────────────

const ADMIN_INTRO_ASSETS = {
  cyberpunk: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/cyberpunktheme_intro.mp4',
  genshin: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/genshin_intro.mp4',
};

const ADMIN_INTRO_CAPTIONS = {
  cyberpunk: 'NETWATCH ADMIN ACCESS',
  genshin: 'GENSHIN ADMIN ACCESS',
};

let adminIntroPlaying = false;
let adminIntroDoneCallback = null;

function resolveAdminIntroVariant(profile = {}) {
  if (!isAdmin || !currentUserId) return null;
  return ADMIN_INTRO_ASSETS[profile.admin_intro_variant] ? profile.admin_intro_variant : null;
}

function playAdminIntroIfNeeded(profile = {}, done) {
  const variant = resolveAdminIntroVariant(profile);
  if (!variant) return false;
  const sessionKey = `zhidao_admin_intro_${variant}_done`;
  if (sessionStorage.getItem(sessionKey)) return false;

  const overlay = document.getElementById('adminIntroOverlay');
  const video = document.getElementById('adminIntroVideo');
  const caption = document.getElementById('adminIntroCaption');
  if (!overlay || !video) return false;

  adminIntroPlaying = true;
  adminIntroDoneCallback = typeof done === 'function' ? done : null;
  sessionStorage.setItem(sessionKey, '1');

  if (caption) caption.textContent = ADMIN_INTRO_CAPTIONS[variant] || 'ADMIN ACCESS';
  overlay.classList.toggle('genshin', variant === 'genshin');
  overlay.classList.toggle('cyberpunk', variant === 'cyberpunk');
  overlay.style.display = 'flex';
  overlay.classList.remove('closing');
  hideStartupCover();

  video.pause();
  video.src = ADMIN_INTRO_ASSETS[variant];
  video.currentTime = 0;
  video.onended = finishAdminIntro;
  video.onerror = finishAdminIntro;

  const playPromise = video.play();
  if (playPromise && typeof playPromise.catch === 'function') {
    playPromise.catch(() => {
      setTimeout(finishAdminIntro, 1200);
    });
  }
  return true;
}

function finishAdminIntro() {
  if (!adminIntroPlaying) return;
  adminIntroPlaying = false;
  const overlay = document.getElementById('adminIntroOverlay');
  const video = document.getElementById('adminIntroVideo');
  if (video) {
    video.onended = null;
    video.onerror = null;
    video.pause();
  }
  if (overlay) {
    overlay.classList.add('closing');
    setTimeout(() => {
      overlay.style.display = 'none';
      overlay.classList.remove('closing');
      if (video) video.removeAttribute('src');
      const cb = adminIntroDoneCallback;
      adminIntroDoneCallback = null;
      if (cb) cb();
    }, 420);
  } else if (adminIntroDoneCallback) {
    const cb = adminIntroDoneCallback;
    adminIntroDoneCallback = null;
    cb();
  }
}

function skipAdminIntro() {
  finishAdminIntro();
}

// ── THEME SELECTION SPLASH (для всех игроков) ────────────────
// При первом входе после выбора темы NetWatch/Genshin показываем
// соответствующую видео-заставку (тот же ролик, что у admin intro).
// Для Михаил Юрьевича (Альфабосс, 244487659) NetWatch-заставка
// показывается при каждом запуске приложения.

const THEME_INTRO_ASSETS = {
  cyberpunk: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/cyberpunktheme_intro.mp4',
  genshin: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/genshin_intro.mp4',
};

const THEME_INTRO_CAPTIONS = {
  cyberpunk: 'NETWATCH ACCESS',
  genshin: 'GENSHIN ACCESS',
};

const PERMANENT_THEME_INTRO_IDS = {
  cyberpunk: [244487659], // Михаил Юрьевич // Альфабосс
};

let themeIntroPlaying = false;
let themeIntroDoneCallback = null;

function themeIntroVariant(theme) {
  if (theme === 'genshin-light' || theme === 'genshin-dark') return 'genshin';
  if (theme === '' || theme === 'nw-light') return 'cyberpunk';
  return null;
}

// Вызывается из setTheme(), когда тему меняет сам игрок.
function markThemeIntroPending(theme) {
  const variant = themeIntroVariant(theme);
  if (!variant) return;
  try { localStorage.setItem('zhidao_theme_intro_pending', variant); } catch(e) {}
}

function playThemeIntroIfNeeded(done) {
  if (adminIntroPlaying || themeIntroPlaying) return false;

  const theme = localStorage.getItem('zhidao_theme') || '';
  const variant = themeIntroVariant(theme);
  if (!variant || !THEME_INTRO_ASSETS[variant]) return false;

  let shouldPlay = false;
  try {
    if (localStorage.getItem('zhidao_theme_intro_pending') === variant) {
      shouldPlay = true;
      localStorage.removeItem('zhidao_theme_intro_pending');
    }
  } catch(e) {}

  if (!shouldPlay && (PERMANENT_THEME_INTRO_IDS[variant] || []).includes(currentUserId)) {
    shouldPlay = true;
  }

  if (!shouldPlay) return false;

  const overlay = document.getElementById('adminIntroOverlay');
  const video = document.getElementById('adminIntroVideo');
  const caption = document.getElementById('adminIntroCaption');
  if (!overlay || !video) return false;

  themeIntroPlaying = true;
  themeIntroDoneCallback = typeof done === 'function' ? done : null;

  if (caption) caption.textContent = THEME_INTRO_CAPTIONS[variant] || '';
  overlay.classList.toggle('genshin', variant === 'genshin');
  overlay.classList.toggle('cyberpunk', variant === 'cyberpunk');
  overlay.style.display = 'flex';
  overlay.classList.remove('closing');
  hideStartupCover();

  video.pause();
  video.src = THEME_INTRO_ASSETS[variant];
  video.currentTime = 0;
  video.onended = finishThemeIntro;
  video.onerror = finishThemeIntro;

  const playPromise = video.play();
  if (playPromise && typeof playPromise.catch === 'function') {
    playPromise.catch(() => {
      setTimeout(finishThemeIntro, 1200);
    });
  }
  return true;
}

function finishThemeIntro() {
  if (!themeIntroPlaying) return;
  themeIntroPlaying = false;
  const overlay = document.getElementById('adminIntroOverlay');
  const video = document.getElementById('adminIntroVideo');
  if (video) {
    video.onended = null;
    video.onerror = null;
    video.pause();
  }
  if (overlay) {
    overlay.classList.add('closing');
    setTimeout(() => {
      overlay.style.display = 'none';
      overlay.classList.remove('closing');
      if (video) video.removeAttribute('src');
      const cb = themeIntroDoneCallback;
      themeIntroDoneCallback = null;
      if (cb) cb();
    }, 420);
  } else if (themeIntroDoneCallback) {
    const cb = themeIntroDoneCallback;
    themeIntroDoneCallback = null;
    cb();
  }
}

function skipThemeIntro() {
  finishThemeIntro();
}

function hideStartupCover() {
  const cover = document.getElementById('startupCover');
  if (!cover || cover.classList.contains('hidden')) return;
  cover.classList.add('hidden');
  setTimeout(() => cover.remove(), 240);
}

// ── ARCHITECT WOW ANIMATIONS ─────────────────────────────────

function cipherDecode(el) {
  if (!el) return;
  const GLYPHS = '智道龙福网络协议数据流天命链接黑墙信义勇ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789◆◈▓░▒■□';
  const final = el.textContent;
  const len = final.length;
  let frame = 0;
  const revealAt = 10; // frames before first char resolves
  const framesPerChar = 4;
  const totalFrames = revealAt + len * framesPerChar + 6;

  function tick() {
    frame++;
    let result = '';
    const revealed = Math.max(0, Math.floor((frame - revealAt) / framesPerChar));
    for (let i = 0; i < len; i++) {
      if (i < revealed) {
        result += final[i];
      } else {
        result += GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
      }
    }
    el.textContent = result;
    if (frame < totalFrames) {
      requestAnimationFrame(tick);
    } else {
      el.textContent = final;
    }
  }
  setTimeout(tick, 800);
}

let _bootRunning = false;
let _bootCbs = [];

function startBlackwallBoot(cb) {
  // Already finished this session — fire callback immediately
  if (sessionStorage.getItem('bw_boot_done')) { if (cb) cb(); return; }
  if (cb) _bootCbs.push(cb);
  // Already running — callback queued, will fire on completion
  if (_bootRunning) return;
  _bootRunning = true;

  const overlay = document.getElementById('blackwall-boot');
  const linesEl = document.getElementById('bootLines');
  if (!overlay || !linesEl) {
    _bootCbs.forEach(f => f()); _bootCbs = []; return;
  }

  linesEl.innerHTML = '';
  overlay.style.display = 'flex';
  hideStartupCover();

  const LINES = [
    { text: '> ZHIDAO PROTOCOL v3.0.0', delay: 0 },
    { text: '> INITIALIZING BLACKWALL...', delay: 260 },
    { text: '> ARCHITECT ACCESS CONFIRMED', delay: 280 },
    { text: '> CLEARANCE LEVEL: OMEGA', delay: 240 },
    { text: '> LOADING NEURAL MESH... [████████] 100%', delay: 380 },
    { text: '> THREAT MATRIX: NOMINAL', delay: 220 },
    { text: '> 智道黑壁 — ONLINE', delay: 300 },
    { text: '欢迎回来, 架构师', delay: 420, gold: true },
  ];

  let elapsed = 80;
  LINES.forEach((l, i) => {
    elapsed += l.delay;
    setTimeout(() => {
      const span = document.createElement('span');
      span.className = l.gold ? 'bw-gold' : 'bw-current';
      span.textContent = l.text;
      linesEl.appendChild(span);
      linesEl.querySelectorAll('span.bw-current').forEach((s, si, arr) => {
        if (si < arr.length - 1) s.className = '';
      });

      if (i === LINES.length - 1) {
        setTimeout(() => {
          const cursor = document.getElementById('bootCursor');
          if (cursor) cursor.style.display = 'none';
          overlay.classList.add('bw-fadeout');
          setTimeout(() => {
            overlay.style.display = 'none';
            overlay.classList.remove('bw-fadeout');
            linesEl.innerHTML = '';
            sessionStorage.setItem('bw_boot_done', '1');
            _bootRunning = false;
            _bootCbs.forEach(f => f());
            _bootCbs = [];
          }, 900);
        }, 900);
      }
    }, elapsed);
  });
}

let _profileTiltBound = false;
function setupProfileTilt() {
  const card = document.getElementById('profileCard');
  if (!card) return;
  // The card is a singleton element; binding listeners more than once (e.g. on
  // every profile reload for an architect) would stack duplicate pointer and
  // global deviceorientation handlers. Bind exactly once.
  if (_profileTiltBound) return;
  _profileTiltBound = true;
  const MAX = 10;

  function applyTilt(rx, ry) {
    card.classList.add('tilt-move');
    card.classList.remove('tilt-reset');
    card.style.transform = `perspective(700px) rotateX(${rx}deg) rotateY(${ry}deg)`;
  }
  function resetTilt() {
    card.classList.remove('tilt-move');
    card.classList.add('tilt-reset');
    card.style.transform = '';
  }

  // Desktop pointer tilt
  card.addEventListener('pointermove', (e) => {
    const r = card.getBoundingClientRect();
    const rx = (((e.clientY - r.top) / r.height) - 0.5) * -MAX;
    const ry = (((e.clientX - r.left) / r.width) - 0.5) * MAX;
    applyTilt(rx, ry);
  });
  card.addEventListener('pointerleave', resetTilt);

  // Mobile gyroscope tilt
  if (window.DeviceOrientationEvent) {
    window.addEventListener('deviceorientation', (e) => {
      if (e.beta == null) return;
      const rx = Math.max(-MAX, Math.min(MAX, (e.beta - 45) * 0.25));
      const ry = Math.max(-MAX, Math.min(MAX, (e.gamma || 0) * 0.25));
      applyTilt(rx, ry);
    }, { passive: true });
  }
}

// ── THEME PATH LOGIC ──────────────────────────────────────────

function getConfig() {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  if (userConfig) {
    document.getElementById('configBox').textContent = userConfig;
    document.getElementById('configBox').style.display = 'block';
    document.getElementById('copyBtn').style.display = 'block';
  } else { showToast('VPN-конфиг не привязан. Mini App доступен без VPN.'); }
}

function copyConfig() {
  if (userConfig) {
    navigator.clipboard.writeText(userConfig);
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ СКОПИРОВАНО!';
    setTimeout(() => { btn.textContent = '📋 СКОПИРОВАТЬ'; }, 2000);
  }
}

function showHelp() {
  tg.showPopup({ title: '📖 Инструкция', message: '1. Нажми "КОНФИГ"\n2. Нажми "СКОПИРОВАТЬ"\n3. Открой Happ → + → вставь ссылку\n4. Подключись!', buttons: [{type:'ok'}] });
}



async function loadWeather() {
  try {
    const r = await fetch(`${API_URL}/api/weather/beijing`);
    if (!r.ok) throw new Error('Weather unavailable');
    const data = await r.json();
    document.getElementById('weatherTemp').innerHTML = `${Math.round(data.main.temp)}<span>°C</span>`;
    document.getElementById('weatherDesc').textContent = data.weather[0].description.charAt(0).toUpperCase() + data.weather[0].description.slice(1);
    document.getElementById('weatherHumidity').textContent = data.main.humidity;
    document.getElementById('weatherWind').textContent = data.wind.speed;
    document.getElementById('weatherFeels').textContent = Math.round(data.main.feels_like);
    document.getElementById('weatherIcon').textContent = getWeatherIcon(data.weather[0].id);
  } catch(e) { document.getElementById('weatherDesc').textContent = 'Недоступно'; }
}

async function loadYuanRate() {
  try {
    const r = await fetch('https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/cny.json');
    const data = await r.json();
    const rub = data.cny.rub;
    if (rub) {
      document.getElementById('yuanRate').innerHTML = `${rub.toFixed(2)}<span> ₽</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    }
  } catch(e) {
    try {
      const r2 = await fetch('https://open.er-api.com/v6/latest/CNY');
      const data2 = await r2.json();
      document.getElementById('yuanRate').innerHTML = `${data2.rates.RUB.toFixed(2)}<span> ₽</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    } catch(e2) { document.getElementById('yuanRate').innerHTML = `—<span> ₽</span>`; }
  }
}

function getWeatherIcon(id) {
  if (id >= 200 && id < 300) return '⛈'; if (id >= 300 && id < 400) return '🌦';
  if (id >= 500 && id < 600) return '🌧'; if (id >= 600 && id < 700) return '❄️';
  if (id >= 700 && id < 800) return '🌫'; if (id === 800) return '☀️';
  if (id === 801) return '🌤'; if (id === 802) return '⛅'; return '☁️';
}

// ===== СТИРКА =====

function askAnonymous() { document.getElementById('questionModal').classList.add('show'); document.getElementById('questionText').value=''; }
function closeQuestion() { document.getElementById('questionModal').classList.remove('show'); }

async function submitQuestion() {
  const text = document.getElementById('questionText').value.trim();
  if (!text) { showToast('Напиши вопрос!'); return; }
  try {
    const r = await fetch(`${API_URL}/api/question`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,telegram_id:currentUserId})});
    if (r.ok) { closeQuestion(); showToast('✅ Вопрос отправлен анонимно!'); try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} }
    else showToast('Ошибка отправки');
  } catch(e) { showToast('Ошибка соединения'); }
}

// ===== АДМИН =====

function buildMatrixRain() {
  const root = document.getElementById('matrixRain');
  if (!root) return;
  root.innerHTML = '';

  const isArchitectTheme = document.body.classList.contains('theme-architect');

  if (isArchitectTheme) {
    // Horizontal green data streams — architect only
    const hex = () => Math.floor(Math.random() * 256).toString(16).padStart(2, '0').toUpperCase();
    const id  = () => Math.random().toString(36).slice(2, 7).toUpperCase();
    const coord = () => (Math.random() * 180 - 90).toFixed(4);
    const prefixes = ['SYS', 'NET', 'ARCH', 'SYNC', 'CORE', 'NODE', 'PKT', 'MEM', 'AUTH', 'EXEC', 'INIT', 'LINK'];
    const rowCount = Math.max(12, Math.floor(window.innerHeight / 52));

    for (let i = 0; i < rowCount; i++) {
      const row = document.createElement('div');
      row.className = 'matrix-col';
      const pfx = prefixes[Math.floor(Math.random() * prefixes.length)];
      const chunks = Math.floor(6 + Math.random() * 10);
      const parts = [`${pfx}:${id()}`];
      for (let j = 0; j < chunks; j++) {
        const r = Math.random();
        if (r < 0.4)       parts.push(`0x${hex()}${hex()}`);
        else if (r < 0.65) parts.push(`[${coord()},${coord()}]`);
        else if (r < 0.82) parts.push(id());
        else               parts.push(`${Math.floor(Math.random()*9999).toString().padStart(4,'0')}`);
      }
      row.textContent = parts.join('  ');
      row.style.top = `${(i / rowCount) * 100}%`;
      row.style.opacity = `${0.22 + Math.random() * 0.30}`;
      row.style.fontSize = `${9 + Math.random() * 3}px`;
      const colors = [
        `rgba(0,255,136,${0.30 + Math.random()*0.25})`,
        `rgba(0,229,255,${0.22 + Math.random()*0.22})`,
        `rgba(57,255,20,${0.20 + Math.random()*0.18})`,
      ];
      row.style.color = colors[Math.floor(Math.random() * colors.length)];
      row.style.setProperty('--dur', `${5 + Math.random() * 7}s`);
      row.style.setProperty('--delay', `${-Math.random() * 10}s`);
      root.appendChild(row);
    }
  } else {
    // Vertical falling hieroglyphs — all users (default)
    const KANJI = '智道龙福网络协议数据流天命链接黑墙信义勇力守节命运界限虚空核心阵列节点密钥层';
    const colCount = Math.max(8, Math.floor(window.innerWidth / 28));
    for (let i = 0; i < colCount; i++) {
      const col = document.createElement('div');
      col.className = 'matrix-kanji';
      const len = 8 + Math.floor(Math.random() * 12);
      col.textContent = Array.from({length: len}, () => KANJI[Math.floor(Math.random() * KANJI.length)]).join('\n');
      col.style.left = `${(i / colCount) * 100 + Math.random() * (100 / colCount)}%`;
      col.style.setProperty('--dur', `${6 + Math.random() * 10}s`);
      col.style.setProperty('--delay', `${-Math.random() * 14}s`);
      col.style.opacity = `${0.12 + Math.random() * 0.18}`;
      root.appendChild(col);
    }
  }
}

window.addEventListener('load', buildMatrixRain);
window.addEventListener('resize', buildMatrixRain);

// ===== TOAST NOTIFICATIONS =====

function showToast(msg, type) {
  if (!type) {
    if (/✅/.test(msg)) type = 'success';
    else if (/⛔|❌|Ошибка|ошибка|[Ee]rror|failed|Failed/.test(msg)) type = 'error';
    else if (/Введи|Заполни|Напиши|Выбери|Откройте|недостаточно|Недостаточно/.test(msg)) type = 'warn';
    else type = 'info';
  }

  const icons = { success: '✅', error: '⛔', info: '⚡', warn: '⚠️' };
  const container = document.getElementById('toastContainer');
  if (!container) { console.warn('[toast]', msg); return; }

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;

  const iconEl = document.createElement('span');
  iconEl.className = 'toast-icon';
  iconEl.textContent = icons[type] || '⚡';

  const msgEl = document.createElement('span');
  msgEl.className = 'toast-msg';
  // Strip a leading emoji from the message text — the toast already shows
  // its own type icon on the left, so an embedded emoji would duplicate it.
  const cleanMsg = msg.replace(/^[\p{Extended_Pictographic}‍️]+\s*/u, '');
  msgEl.innerHTML = cleanMsg
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');

  const closeEl = document.createElement('span');
  closeEl.className = 'toast-close';
  closeEl.textContent = '✕';

  el.appendChild(iconEl);
  el.appendChild(msgEl);
  el.appendChild(closeEl);

  const dismiss = () => {
    if (el._gone) return;
    el._gone = true;
    el.classList.add('hiding');
    setTimeout(() => { el.parentElement && el.parentElement.removeChild(el); }, 230);
  };
  el._dismiss = dismiss;
  closeEl.addEventListener('click', dismiss);

  container.appendChild(el);
  setTimeout(dismiss, 3600);

  const toasts = container.querySelectorAll('.toast:not(.hiding)');
  if (toasts.length > 4) toasts[0]._dismiss && toasts[0]._dismiss();
}

// Telegram's native popup bridge can get stuck "open" if showPopup is invoked
// again before the previous one's callback fires (repeated admin/economy actions
// trigger this after a few uses and require a page reload). Guard against overlap
// and always release the lock, even if the bridge never calls back.
let _tgPopupOpen = false;
let _tgPopupReleaseTimer = null;

function safeShowPopup(options, callback) {
  if (_tgPopupOpen) {
    showToast('Подожди закрытия предыдущего окна');
    return;
  }
  _tgPopupOpen = true;
  clearTimeout(_tgPopupReleaseTimer);
  _tgPopupReleaseTimer = setTimeout(() => { _tgPopupOpen = false; }, 8000);

  const release = () => {
    _tgPopupOpen = false;
    clearTimeout(_tgPopupReleaseTimer);
    _tgPopupReleaseTimer = null;
  };

  try {
    tg.showPopup(options, (buttonId) => {
      release();
      if (typeof callback === 'function') callback(buttonId);
    });
  } catch (e) {
    release();
    if (typeof callback === 'function') callback('cancel');
  }
}

// Some Telegram clients don't implement tg.showPopup at all (it's silently a
// no-op or throws), which made safeShowPopup() look like it "did nothing" —
// no dialog appears, the action quietly cancels. window.confirm() is even worse:
// it can hang the WebView's JS thread entirely. This builds our own modal in the
// DOM, so confirmations always work regardless of the host client's capabilities.
function ensureConfirmDialogModal() {
  let modal = document.getElementById('confirmDialogModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'confirmDialogModal';
  modal.className = 'confirm-dialog-modal';
  modal.style.display = 'none';
  modal.innerHTML = `
    <div class="confirm-dialog-sheet">
      <div class="confirm-dialog-title" id="confirmDialogTitle"></div>
      <div class="confirm-dialog-msg" id="confirmDialogMsg"></div>
      <div class="confirm-dialog-actions">
        <button class="confirm-dialog-btn cancel" type="button" data-role="cancel">Отмена</button>
        <button class="confirm-dialog-btn confirm" type="button" data-role="confirm">Подтвердить</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  return modal;
}

function showConfirmDialog(options) {
  const opts = options || {};
  const modal = ensureConfirmDialogModal();
  const titleEl = modal.querySelector('#confirmDialogTitle');
  const msgEl = modal.querySelector('#confirmDialogMsg');
  const confirmBtn = modal.querySelector('[data-role="confirm"]');
  const cancelBtn = modal.querySelector('[data-role="cancel"]');

  titleEl.textContent = opts.title || 'Подтверди действие';
  msgEl.textContent = opts.message || '';
  confirmBtn.textContent = opts.confirmText || 'Подтвердить';
  cancelBtn.textContent = opts.cancelText || 'Отмена';
  confirmBtn.classList.toggle('danger', !!opts.danger);
  modal.style.display = 'flex';

  return new Promise((resolve) => {
    const close = (result) => {
      modal.style.display = 'none';
      confirmBtn.removeEventListener('click', onConfirm);
      cancelBtn.removeEventListener('click', onCancel);
      modal.removeEventListener('click', onBackdrop);
      resolve(result);
    };
    const onConfirm = () => close(true);
    const onCancel = () => close(false);
    const onBackdrop = (event) => { if (event.target === modal) close(false); };
    confirmBtn.addEventListener('click', onConfirm);
    cancelBtn.addEventListener('click', onCancel);
    modal.addEventListener('click', onBackdrop);
  });
}

function zSetText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function zSetStyle(id, prop, value) {
  const el = document.getElementById(id);
  if (el) el.style[prop] = value;
}

function zSafeUiCall(label, fn) {
  try {
    if (typeof fn === 'function') fn();
  } catch (e) {
    console.warn(`[ZHIDAO UI] ${label} failed`, e);
  }
}

function zCacheUserProfile(telegramId, data) {
  try {
    localStorage.setItem(`zhidao_profile_cache_${telegramId}`, JSON.stringify({
      saved_at: Date.now(),
      data,
    }));
  } catch (e) {}
}

function zReadCachedUserProfile(telegramId) {
  try {
    const raw = localStorage.getItem(`zhidao_profile_cache_${telegramId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && parsed.data ? parsed.data : null;
  } catch (e) {
    return null;
  }
}

async function zFetchUserProfile(telegramId, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_URL}/api/user/${telegramId}`, {
      signal: controller.signal,
      headers: { 'X-Request-ID': `profile-${Date.now().toString(36)}` },
    });
    let data = null;
    try { data = await r.json(); } catch (e) {}
    return { response: r, data };
  } finally {
    window.clearTimeout(timeout);
  }
}

function zApplyUserProfile(telegramId, data, options = {}) {
  isAdmin = !!data.is_admin;
  isArchitect = !!data.is_architect;
  document.body.classList.toggle('is-architect', isArchitect);

  userConfig = data.link;
  currentAvatarUrl = data.avatar_url || null;

  const displayName = data.full_name || data.username || `ID ${telegramId}`;
  zSetText('status', options.fromCache ? '● КЕШ' : '● АКТИВЕН');
  zSetStyle('status', 'color', options.fromCache ? '#dbb165' : '#cc4444');
  zSetText('username', displayName);

  const used = data.used_traffic || 0;
  const usedGB = (used / 1024 / 1024 / 1024).toFixed(2);
  const hasVpn = data.has_vpn !== false;
  zSetText('serverTag', hasVpn ? `HK NODE // ${usedGB} GB` : 'STUDENT NODE // VPN не привязан');
  zSetText('trafficValue', hasVpn ? `${usedGB} GB` : '— GB');
  const percent = Math.min((used / (10 * 1024 * 1024 * 1024)) * 100, 100);
  window.setTimeout(() => {
    const fill = document.getElementById('progressFill');
    if (fill) fill.style.width = `${percent}%`;
  }, 100);

  zSafeUiCall('architect visibility', () => {
    document.querySelectorAll('.architect-only-block').forEach(el => {
      el.style.display = isArchitect ? '' : 'none';
    });
  });

  if (isArchitect) {
    localStorage.setItem('zhidao_architect', '1');
    zSafeUiCall('architect profile labels', () => {
      const badge = document.querySelector('.profile-admin-badge');
      if (badge) badge.textContent = '架构师 // ARCHITECT';
      const kicker = document.getElementById('profileKicker');
      if (kicker) kicker.textContent = 'ARCHITECT // PROTOCOL';
    });
    zSafeUiCall('architect boot', () => {
      const afterIntro = () => cipherDecode(document.getElementById('profileDisplayName'));
      if (!playAdminIntroIfNeeded(data, afterIntro)) startBlackwallBoot(afterIntro);
      setupProfileTilt();
    });
  } else {
    localStorage.removeItem('zhidao_architect');
    zSafeUiCall('hide stale boot', () => {
      const ov = document.getElementById('blackwall-boot');
      if (ov) ov.style.display = 'none';
      if (_bootRunning) {
        _bootRunning = false;
        _bootCbs = [];
      }
    });
  }

  zSafeUiCall('theme guard', () => {
    if (!isArchitect && document.body.classList.contains('theme-architect')) {
      if (typeof setTheme === 'function') setTheme('');
      try { tg.CloudStorage.setItem('zhidao_theme', ''); } catch(e) {}
      localStorage.setItem('zhidao_theme', '');
    }
    if (isAdmin && typeof syncAdminThemeMode === 'function') {
      syncAdminThemeMode(localStorage.getItem('zhidao_theme') || '');
    }
  });

  zSafeUiCall('admin intro', () => {
    if (isAdmin && !isArchitect) {
      const badge = document.querySelector('.profile-admin-badge');
      if (badge) badge.textContent = '系统架构师';
      playAdminIntroIfNeeded(data);
    }
  });

  zSafeUiCall('theme intro', () => {
    playThemeIntroIfNeeded();
  });

  zSafeUiCall('admin visibility', () => syncAdminUiVisibility());
  zSafeUiCall('mvp badge', () => {
    const mvpBadge = document.getElementById('profileMvpBadge');
    if (mvpBadge) mvpBadge.style.display = data.is_last_mvp ? 'inline-flex' : 'none';
  });
  zSafeUiCall('profile avatar', () => {
    if (typeof renderProfileAvatarCard === 'function') renderProfileAvatarCard(data);
  });
  zSafeUiCall('diary access', () => {
    if (typeof syncDiaryAccessVisibility === 'function') syncDiaryAccessVisibility();
  });
  zSafeUiCall('feature freeze', () => {
    if (typeof syncFeatureFreezeBadges === 'function') syncFeatureFreezeBadges();
  });
  zSafeUiCall('architect diary unlocks', () => {
    if (typeof checkArchitectDiaryUnlocks === 'function') checkArchitectDiaryUnlocks();
  });
  zSafeUiCall('gift code poller', () => {
    if (typeof startGiftCodePoller === 'function') startGiftCodePoller();
  });

  if (!adminIntroPlaying && !_bootRunning) hideStartupCover();
}

async function loadUserData(telegramId) {
  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const { response, data } = await zFetchUserProfile(telegramId);
      if (response.ok && data) {
        zCacheUserProfile(telegramId, data);
        zApplyUserProfile(telegramId, data);
        return;
      }
      if (response.status === 404) {
        zSetText('status', '● НЕ НАЙДЕН');
        zSetText('username', 'Нет подписки');
        hideStartupCover();
        return;
      }
      if (response.status === 401 || response.status === 403) {
        zSetText('status', '● НЕТ ДОСТУПА');
        zSetStyle('status', 'color', '#dbb165');
        zSetText('username', 'Открой через Telegram');
        hideStartupCover();
        return;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (e) {
      lastError = e;
    }
    await new Promise(resolve => window.setTimeout(resolve, 700));
  }

  const cached = zReadCachedUserProfile(telegramId);
  if (cached) {
    zApplyUserProfile(telegramId, cached, { fromCache: true });
    showToast('Профиль временно показан из кеша. Проверю соединение позже.');
    return;
  }

  console.warn('[ZHIDAO UI] profile load failed', lastError);
  zSetText('status', '● ОФЛАЙН');
  zSetStyle('status', 'color', '#dbb165');
  zSetText('username', 'Ошибка связи');
  hideStartupCover();
}
