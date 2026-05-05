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

let _currentPage = 'home';

function showPage(name, btn) {
  if (isLaunchGateActive() && name !== 'home') {
    showLaunchGateOverlay();
    return;
  }

  if (name === 'diary' && !isAdmin) {
    if (typeof syncDiaryAccessVisibility === 'function') syncDiaryAccessVisibility();
    try { showToast('Архив дневника доступен только администраторам.'); } catch(e) {}
    return;
  }

  const alreadyActive = _currentPage === name;
  _currentPage = name;

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');

  // Pages that always refresh (live data)
  if (name === 'schedule') { loadAnnouncements(); loadSchedule(); }
  // Pages that load only on first visit or explicit re-tap
  if (name === 'implants' && !alreadyActive) loadImplants(currentUserId);
  if (name === 'shop' && !alreadyActive) loadShop();
  if (name === 'rating') { loadLeaderboard(); updateRatingPoints(); }
  if (name === 'diary') loadDiaryPage();
  if (name === 'diary-stars') initDiaryStarsPage();
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
  if (typeof syncArchitectEventAvailability === 'function') syncArchitectEventAvailability();

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

  // Скрываем все субстраницы
  ['themes','weather','laundry','news','achievements','team','admin','stats'].forEach(s => {
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
    if (section === 'achievements') loadAchievements();
    if (section === 'news') loadAnnouncements();
    if (section === 'laundry') { initLaundry(); }
  }
}

// ===== ДАННЫЕ =====

async function loadUserData(telegramId) {
  try {
    const r = await fetch(`${API_URL}/api/user/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      isAdmin = !!data.is_admin;
      isArchitect = !!data.is_architect;
      document.body.classList.toggle('is-architect', isArchitect);
      if (isArchitect) {
        localStorage.setItem('zhidao_architect', '1');
        const badge = document.querySelector('.profile-admin-badge');
        if (badge) badge.textContent = '架构师 // ARCHITECT';
        const kicker = document.getElementById('profileKicker');
        if (kicker) kicker.textContent = 'ARCHITECT // PROTOCOL';
        startBlackwallBoot(() => {
          const nameEl = document.getElementById('profileDisplayName');
          cipherDecode(nameEl);
        });
        setupProfileTilt();
      } else {
        // Clear flag — not architect (covers account change / stale localStorage)
        localStorage.removeItem('zhidao_architect');
        // Abort boot overlay if it was pre-shown from stale localStorage
        // Also hide overlay if it was pre-shown by inline script (stale localStorage)
        const _ov = document.getElementById('blackwall-boot');
        if (_ov) _ov.style.display = 'none';
        if (_bootRunning) {
          _bootRunning = false;
          _bootCbs = [];
        }
      }
      if (isAdmin && typeof syncAdminThemeMode === 'function') {
        syncAdminThemeMode(localStorage.getItem('zhidao_theme') || '');
      }
      syncAdminUiVisibility();
      userConfig = data.link;
      currentAvatarUrl = data.avatar_url || null;
      if (typeof renderProfileAvatarCard === 'function') {
        renderProfileAvatarCard(data);
      }
      if (typeof syncDiaryAccessVisibility === 'function') {
        syncDiaryAccessVisibility();
      }
      document.getElementById('status').textContent = '● АКТИВЕН';
      document.getElementById('status').style.color = '#cc4444';
      document.getElementById('username').textContent = data.full_name || data.username;
      document.getElementById('serverTag').textContent = data.has_vpn === false
        ? 'STUDENT NODE // VPN не привязан'
        : 'HK NODE // ' + ((data.used_traffic || 0) / 1024/1024/1024).toFixed(2) + ' GB';
      const used = data.used_traffic || 0;
      const usedGB = (used / 1024/1024/1024).toFixed(2);
      document.getElementById('trafficValue').textContent = data.has_vpn === false ? '— GB' : usedGB + ' GB';
      const percent = Math.min((used / (10*1024*1024*1024)) * 100, 100);
      setTimeout(() => { document.getElementById('progressFill').style.width = percent + '%'; }, 300);
    } else {
      document.getElementById('status').textContent = '● НЕ НАЙДЕН';
      document.getElementById('username').textContent = 'Нет подписки';
    }
  } catch(e) {
    document.getElementById('status').textContent = '● ОФЛАЙН';
    document.getElementById('username').textContent = 'Ошибка связи';
  }
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

  // Overlay is already visible (CSS default + inline script logic)
  overlay.style.display = 'flex';

  const LINES = [
    { text: '> ZHIDAO PROTOCOL v2.7.0', delay: 0 },
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

function setupProfileTilt() {
  const card = document.getElementById('profileCard');
  if (!card) return;
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

function contactAdmin() { tg.openTelegramLink('https://t.me/christianpastor'); }

async function loadWeather() {
  try {
    const r = await fetch(`https://api.openweathermap.org/data/2.5/weather?id=1816670&appid=${WEATHER_KEY}&units=metric&lang=ru`);
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
    const r = await fetch('https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@2024-03-28/v1/currencies/cny.json');
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

  const glyphs = ['智','道','龙','福','网','络','协','议','数','据','流','天','命','链','接','红','黑','墙','信','義','勇','中'];
  const columns = Math.max(10, Math.floor(window.innerWidth / 38));

  for (let i = 0; i < columns; i++) {
    const col = document.createElement('div');
    col.className = 'matrix-col';

    const length = 5 + Math.floor(Math.random() * 8);
    const chars = [];

    for (let j = 0; j < length; j++) {
      chars.push(glyphs[Math.floor(Math.random() * glyphs.length)]);
    }

    col.innerHTML = chars.join('<br>');
    col.style.left = `${Math.random() * 100}%`;
    col.style.setProperty('--dur', `${10 + Math.random() * 10}s`);
    col.style.setProperty('--delay', `${-Math.random() * 18}s`);
    col.style.setProperty('--drift', `${-12 + Math.random() * 24}px`);
    col.style.setProperty('--blur', `${Math.random() * 0.6}px`);
    col.style.fontSize = `${12 + Math.random() * 10}px`;
    col.style.opacity = `${0.35 + Math.random() * 0.35}`;

    root.appendChild(col);
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
  msgEl.innerHTML = msg
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
