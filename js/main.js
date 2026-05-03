const user = tg.initDataUnsafe?.user;
if (user) {
  currentUserId = user.id;
  isAdmin = ADMIN_IDS.includes(user.id);
  loadUserData(user.id);
  loadPoints(user.id);
  loadImplants(user.id);
  startGlobalAlertPolling();
  if (typeof syncAdminUiVisibility === 'function') syncAdminUiVisibility();
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

function initBlackwallBootSequence() {
  const overlay = document.getElementById('blackwallBootSequence');
  if (!overlay || overlay.dataset.started === '1') return;

  overlay.dataset.started = '1';
  overlay.classList.add('show');

  window.setTimeout(() => {
    overlay.classList.add('closing');
  }, 2600);

  window.setTimeout(() => {
    overlay.classList.remove('show', 'closing');
    overlay.style.display = 'none';
  }, 3250);
}

// ===== НАВИГАЦИЯ =====

document.addEventListener('DOMContentLoaded', () => {
  initBlackwallBootSequence();

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
