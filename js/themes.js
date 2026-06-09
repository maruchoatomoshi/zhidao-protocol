function applyThemePath(path) {
  currentThemePath = path;
  if (typeof updateProfilePathBadge === 'function') updateProfilePathBadge(path);

  const nwCards    = ['theme-btn-default', 'theme-btn-nw-light'];
  const gsCards    = ['theme-btn-genshin-light', 'theme-btn-genshin-dark'];

  if (path === 'cyberpunk') {
    nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    if (!isAdmin) {
      gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    } else {
      // Admins always see both path catalogs regardless of current path
      gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    }
    // Admins may use any theme regardless of path — don't force their theme back.
    if (!isAdmin) {
      const t = localStorage.getItem('zhidao_theme') || '';
      if (t.startsWith('genshin')) setTheme('');
    }
    // Показываем импланты, скрываем карточки
    const implTab = document.getElementById('implants-tab'); if (implTab) implTab.style.display = 'block';
    const cardTab = document.getElementById('cards-tab'); if (cardTab) cardTab.style.display = 'none';
    const implCat = document.getElementById('implants-catalog'); if (implCat) implCat.style.display = 'block';
    // Кейсы — показываем рулетку
    const cp = document.getElementById('casinoPlayContent'); if (cp) cp.style.display = 'flex';
    const gc = document.getElementById('casinoGenshinContent'); if (gc) gc.style.display = 'none';
    const genshinTabBtn = document.getElementById('genshinTabBtn'); if (genshinTabBtn) genshinTabBtn.style.display = 'none';
    const playBtn = document.getElementById('casinoPlayBtn'); if (playBtn) playBtn.textContent = '🎰 ИГРАТЬ';
  } else if (path === 'genshin') {
    if (!isAdmin) nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    // Admins may use any theme regardless of path — don't force their theme.
    if (!isAdmin) {
      const t = localStorage.getItem('zhidao_theme') || '';
      if (!t.startsWith('genshin')) setTheme('genshin-light');
    }
    // Показываем карточки, скрываем импланты
    const implTab = document.getElementById('implants-tab'); if (implTab) implTab.style.display = 'none';
    const cardTab = document.getElementById('cards-tab'); if (cardTab) cardTab.style.display = 'block';
    const implCat = document.getElementById('implants-catalog'); if (implCat) implCat.style.display = 'none';
    // Молитвы — показываем Геншин
    const cp = document.getElementById('casinoPlayContent'); if (cp) cp.style.display = 'none';
    const gc = document.getElementById('casinoGenshinContent'); if (gc) gc.style.display = 'flex';
    const playBtn = document.getElementById('casinoPlayBtn'); if (playBtn) playBtn.textContent = '✦ МОЛИТВЫ';
  } else {
    // path = null — первый вход, показываем экран выбора
    showPathChoiceScreen();
  }
}

function showPathChoiceScreen() {
  const overlay = document.getElementById('overlay-path-choice');
  if (overlay) overlay.style.display = 'flex';
}

async function chooseThemePath(path) {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/user/set_path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: currentUserId, path })
    });
    if (r.ok) {
      const overlay = document.getElementById('overlay-path-choice');
      if (overlay) overlay.style.display = 'none';
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      applyThemePath(path);
    } else if (r.status === 401) {
      showToast('Открой приложение заново через Telegram.');
    } else {
      showToast('Ошибка. Попробуй ещё раз.');
    }
  } catch(e) {
    showToast('Нет соединения.');
  }
}

function syncAdminThemeMode(theme) {
  if (!isAdmin) return;

  const isGenshinTheme = theme === 'genshin-light' || theme === 'genshin-dark';
  currentThemePath = isGenshinTheme ? 'genshin' : 'cyberpunk';
  if (typeof updateProfilePathBadge === 'function') updateProfilePathBadge(currentThemePath);

  const casinoCases = document.getElementById('casinoPlayContent');
  const casinoPrayers = document.getElementById('casinoGenshinContent');
  const playBtn = document.getElementById('casinoPlayBtn');

  if (casinoCases) casinoCases.style.display = isGenshinTheme ? 'none' : 'flex';
  if (casinoPrayers) casinoPrayers.style.display = isGenshinTheme ? 'flex' : 'none';
  if (playBtn) playBtn.textContent = isGenshinTheme ? '✦ МОЛИТВЫ' : '🎰 ИГРАТЬ';

  const implTab = document.getElementById('implants-tab');
  const cardTab = document.getElementById('cards-tab');
  const implCat = document.getElementById('implants-catalog');
  if (implTab) implTab.style.display = isGenshinTheme ? 'none' : 'block';
  if (cardTab) cardTab.style.display = isGenshinTheme ? 'block' : 'none';
  if (implCat) implCat.style.display = isGenshinTheme ? 'none' : 'block';

  if (!isGenshinTheme && casinoCases && casinoCases.style.display !== 'none') {
    setTimeout(initRoulette, 50);
  }
}

function setTheme(theme) {
  // Убираем все классы тем
  THEMES.forEach(t => {
    if (t) document.body.classList.remove('theme-' + t);
  });
  // Применяем новую
  if (theme) document.body.classList.add('theme-' + theme);

  // Сохраняем
  try {
    localStorage.setItem('zhidao_theme', theme);
    if(window.Telegram?.WebApp?.CloudStorage) tg.CloudStorage.setItem('zhidao_theme', theme, ()=>{});
  } catch(e) {}

  // Обновляем галочки
  THEMES.forEach(t => {
    const key = t || 'default';
    const el = document.getElementById('check-' + key);
    if (el) el.style.display = (t === theme) ? 'block' : 'none';
  });

  // Обновляем логотип под тему
  const logoBg = document.querySelector('.main-logo .no-leak-bg');
  const isG = theme === 'genshin-light' || theme === 'genshin-dark';
  const isA = theme === 'admin' || theme === 'admin-light';
  document.body.classList.toggle('theme-genshin', isG);
  if (logoBg) {
    const logoUrl = isG
      ? 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo_genshintheme_nobackground.png'
      : isA
        ? 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architect_logo.png'
        : 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo.png';
    logoBg.style.backgroundImage = `url('${logoUrl}')`;
  }
  // Переименовываем разделы под тему
  const el = (id) => document.getElementById(id);
  if (el('nav-casino-label'))    el('nav-casino-label').textContent = isG ? '祈愿' : '箱子';
  if (el('nav-casino-icon'))     el('nav-casino-icon').className    = isG ? 'ti ti-sparkles' : 'ti ti-package';
  if (el('nav-implants-label'))  el('nav-implants-label').textContent = isG ? '卡片' : '植入物';
  if (el('nav-implants-icon'))   el('nav-implants-icon').className  = isG ? 'ti ti-cards' : 'ti ti-cpu';
  if (el('casino-page-cn'))      el('casino-page-cn').textContent   = isG ? '祈愿' : '箱子';
  if (el('casino-page-title'))   el('casino-page-title').firstChild.textContent = isG ? 'МОЛИТВЫ ' : 'КЕЙСЫ ';
  if (el('implants-page-cn'))    el('implants-page-cn').textContent = isG ? '卡片' : '植入物';
  if (el('implants-page-title')) el('implants-page-title').firstChild.textContent = isG ? 'КАРТОЧКИ ' : 'ИМПЛАНТЫ ';
  if (el('home-neuro-divider'))  el('home-neuro-divider').textContent = isG ? '✦ 卡片 артефакты ✦' : '🏮 网络链接 нейролинк 🏮';
  syncAdminThemeMode(theme);
  if (typeof buildMatrixRain === 'function') buildMatrixRain();
  try { try{tg.HapticFeedback.impactOccurred('light');}catch(e){} } catch(e) {}
}

function loadSavedTheme() {
  try {
    if(window.Telegram?.WebApp?.CloudStorage) {
      tg.CloudStorage.getItem('zhidao_theme', (err, val) => {
        setTheme(val || localStorage.getItem('zhidao_theme') || '');
      });
    } else {
      setTheme(localStorage.getItem('zhidao_theme') || '');
    }
  } catch(e) { setTheme(''); }
}

function toggleLiteMode() {
  const active = document.body.classList.toggle('lite-mode');
  try {
    localStorage.setItem('zhidao_lite', active ? '1' : '');
    if (window.Telegram?.WebApp?.CloudStorage) tg.CloudStorage.setItem('zhidao_lite', active ? '1' : '', () => {});
  } catch(e) {}
  const btn = document.getElementById('lite-mode-btn');
  if (btn) btn.textContent = active ? '⚡ ВКЛ' : '⚡ ВЫКЛ';
  const label = document.getElementById('lite-mode-label');
  if (label) label.style.opacity = active ? '1' : '0.5';
}

function loadLiteMode() {
  function apply(val) {
    if (val === '1') {
      document.body.classList.add('lite-mode');
      const btn = document.getElementById('lite-mode-btn');
      if (btn) btn.textContent = '⚡ ВКЛ';
      const label = document.getElementById('lite-mode-label');
      if (label) label.style.opacity = '1';
    }
  }
  try {
    if (window.Telegram?.WebApp?.CloudStorage) {
      tg.CloudStorage.getItem('zhidao_lite', (err, val) => apply(val || localStorage.getItem('zhidao_lite') || ''));
    } else {
      apply(localStorage.getItem('zhidao_lite') || '');
    }
  } catch(e) {}
}
