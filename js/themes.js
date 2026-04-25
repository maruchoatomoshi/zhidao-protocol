function applyThemePath(path) {
  currentThemePath = path;

  const nwCards    = ['theme-btn-default', 'theme-btn-nw-light'];
  const gsCards    = ['theme-btn-genshin-light', 'theme-btn-genshin-dark'];

  if (path === 'cyberpunk') {
    nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    const t = localStorage.getItem('zhidao_theme') || '';
    if (t.startsWith('genshin')) setTheme('');
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
    nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    const t = localStorage.getItem('zhidao_theme') || '';
    if (!t.startsWith('genshin')) setTheme('genshin-light');
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
    } else {
      tg.showAlert('Ошибка. Попробуй ещё раз.');
    }
  } catch(e) {
    tg.showAlert('Нет соединения.');
  }
}

function syncAdminThemeMode(theme) {
  if (!isAdmin) return;

  const isGenshinTheme = theme === 'genshin-light' || theme === 'genshin-dark';
  currentThemePath = isGenshinTheme ? 'genshin' : 'cyberpunk';

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
  const logoImg = document.querySelector('.main-logo img');
  const isG = theme === 'genshin-light' || theme === 'genshin-dark';
  document.body.classList.toggle('theme-genshin', isG);
  if (logoImg) {
    logoImg.src = isG
      ? 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo_genshintheme_nobackground.png'
      : 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/logo.png?raw=true';
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
