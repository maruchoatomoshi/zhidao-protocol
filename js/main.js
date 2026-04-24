const user = tg.initDataUnsafe?.user;
if (user) {
  currentUserId = user.id;
  isAdmin = ADMIN_IDS.includes(user.id);
  loadUserData(user.id);
  loadPoints(user.id);
  loadImplants(user.id);
  startGlobalAlertPolling();
  if (isAdmin) {
    document.getElementById('adminMoreBtn').style.display = 'block';
    document.getElementById('shopResetBtn').style.display = 'block';
  }
}

loadSavedTheme();
// genshinTabBtn управляется через applyThemePath
loadWeather();
loadYuanRate();
loadSchedule();
loadAnnouncements();
loadLeaderboard();
loadAchievements();
initLaundry();

// ===== НАВИГАЦИЯ =====

document.addEventListener('DOMContentLoaded', () => {
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
window.addEventListener('resize', buildMatrixRain);
