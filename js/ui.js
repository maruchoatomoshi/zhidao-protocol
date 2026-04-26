function showPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');

  if (name === 'schedule') { loadAnnouncements(); loadSchedule(); }
  if (name === 'implants') loadImplants(currentUserId);
  if (name === 'shop') loadShop();
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
      }
    }).catch(() => { setTimeout(initRoulette, 50); });
  }
}

function openMore(section) {
  // Скрываем все субстраницы
  ['themes','weather','laundry','news','achievements','team','admin'].forEach(s => {
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
      if (isAdmin && typeof syncAdminThemeMode === 'function') {
        syncAdminThemeMode(localStorage.getItem('zhidao_theme') || '');
      }
      userConfig = data.link;
      currentAvatarUrl = data.avatar_url || null;
      if (typeof renderProfileAvatarCard === 'function') {
        renderProfileAvatarCard(data);
      }
      document.getElementById('status').textContent = '● АКТИВЕН';
      document.getElementById('status').style.color = '#cc4444';
      document.getElementById('username').textContent = data.username;
      document.getElementById('serverTag').textContent = 'HK NODE // ' + ((data.used_traffic || 0) / 1024/1024/1024).toFixed(2) + ' GB';
      const used = data.used_traffic || 0;
      const usedGB = (used / 1024/1024/1024).toFixed(2);
      document.getElementById('trafficValue').textContent = usedGB + ' GB';
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

// ── THEME PATH LOGIC ──────────────────────────────────────────

function getConfig() {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  if (userConfig) {
    document.getElementById('configBox').textContent = userConfig;
    document.getElementById('configBox').style.display = 'block';
    document.getElementById('copyBtn').style.display = 'block';
  } else { tg.showAlert('Конфиг не найден. Активируйте код через /start КОД в боте.'); }
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
  if (!text) { tg.showAlert('Напиши вопрос!'); return; }
  try {
    const r = await fetch(`${API_URL}/api/question`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,telegram_id:currentUserId})});
    if (r.ok) { closeQuestion(); tg.showAlert('✅ Вопрос отправлен анонимно!'); try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} }
    else tg.showAlert('Ошибка отправки');
  } catch(e) { tg.showAlert('Ошибка соединения'); }
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
