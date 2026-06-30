const user = tg.initDataUnsafe?.user;
if (user) {
  currentUserId = user.id;
  isAdmin = ADMIN_IDS.includes(user.id);
  loadUserData(user.id);
  loadPoints(user.id);
  startGlobalAlertPolling();
  if (typeof syncAdminUiVisibility === 'function') syncAdminUiVisibility();
} else {
  // Telegram не передал данные пользователя (нестандартный клиент/прокси,
  // открыто вне Telegram, и т.п.) — явно показываем причину вместо
  // пустого "Загрузка..." навсегда.
  if (typeof zSetText === 'function') {
    zSetText('status', '● НЕТ ДАННЫХ TELEGRAM');
    zSetText('username', 'Откройте приложение через кнопку бота в официальном Telegram');
  }
  if (typeof zSetStyle === 'function') zSetStyle('status', 'color', '#dbb165');
  if (typeof hideStartupCover === 'function') hideStartupCover();
}

loadSavedTheme();
loadLiteMode();
loadWeather();
loadYuanRate();
loadSchedule();
loadAnnouncements();
loadAchievements();
initLaundry();

window.setInterval(() => {
  if (typeof updateLaunchGateCountdowns === 'function') updateLaunchGateCountdowns();
}, 1000);

// ===== НАВИГАЦИЯ =====

document.addEventListener('DOMContentLoaded', () => {
  if (typeof syncLaunchGateVisibility === 'function') syncLaunchGateVisibility();
  if (typeof loadArchitectEventAvailability === 'function') loadArchitectEventAvailability();

  // Deep-link: ссылка вида t.me/<bot>/<app>?startapp=news открывает раздел НОВОСТИ сразу при старте.
  try {
    const startParam = tg.initDataUnsafe?.start_param;
    if (startParam === 'news') {
      const newsBtn = document.querySelector('.nav-item[onclick*="showPage(\'schedule\'"]');
      showPage('schedule', newsBtn);
    }
  } catch (e) {}

  const screen = document.getElementById('gsPrayScreen');
  if (screen) screen.addEventListener('click', () => {
    if (gsAnimating || gsCardFlipped) return;
    gsCardFlipped = true;
    document.getElementById('gsCard3dNew').style.transform = 'rotateY(180deg)';
    document.getElementById('gsTapHint').style.display = 'none';
    setTimeout(() => {
      const info = document.getElementById('gsResultInfo');
      info.style.opacity = '1';
      info.style.animation = 'fadeUpAnim 0.4s ease-out forwards';
    }, 600);
  });
});

// Переключатель табов импланты/карточки

document.addEventListener('click', function(e) {
  const btn = e.target.closest('.btn, .btn-primary, .shop-item-buy, .subtab, .nav-item');
  if (!btn) return;
  const ripple = document.createElement('div');
  ripple.className = 'ripple';
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  ripple.style.width = ripple.style.height = size + 'px';
  ripple.style.left = (e.clientX - rect.left - size/2) + 'px';
  ripple.style.top = (e.clientY - rect.top - size/2) + 'px';
  btn.appendChild(ripple);
  setTimeout(() => ripple.remove(), 500);
});

window.addEventListener('load', buildMatrixRain);
let _matrixRainTimer;
window.addEventListener('resize', () => { clearTimeout(_matrixRainTimer); _matrixRainTimer = setTimeout(buildMatrixRain, 200); });
