function achIcon(name) {
  return `<div class="achievement-icon-wrap"><i class="ti ti-${name}"></i></div>`;
}

const ACHIEVEMENT_ICONS = {
  early_bird: achIcon('sunrise'),
  iron_mode: achIcon('shield-check'),
  legend: achIcon('trophy'),
  curious: achIcon('search'),
  polyglot: achIcon('language'),
  explorer: achIcon('compass'),
  brave: achIcon('sword'),
  exemplary: achIcon('rosette-discount-check'),
  helper: achIcon('heart-handshake'),
  dragon: achIcon('flame'),
  night_watch: achIcon('moon-stars'),
  master: achIcon('school'),
  gambler: achIcon('cards'),
  lucky: achIcon('clover')
};

const ACHIEVEMENT_BADGE_DONE = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9"/></svg>`;
const ACHIEVEMENT_BADGE_LOCK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;
const ACHIEVEMENT_DIVIDER_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="15" r="5"/><path d="M9.5 10.5L7.5 3h2l2.5 5 2.5-5h2l-2 7.5"/></svg>`;

// Инициализация пользователя

async function loadAchievements() {
  if (!currentUserId) return;
  const container = document.getElementById('achievementsContent');
  if (!container) return;
  try {
    const r = await fetch(`${API_URL}/api/achievements/${currentUserId}`);
    const data = await r.json();
    if (!Array.isArray(data) || !data.length) {
      container.innerHTML = `<div class="empty-state" style="padding:16px;">
        Каталог достижений пока не загружен<br>
        <span style="font-size:10px;font-family:monospace;color:var(--text3);">После обновления API раздел появится автоматически</span>
      </div>`;
      return;
    }
    const earned = data.filter(a => a.earned).length;
    let html = `<div class="achievement-count">// Получено: <b style="color:var(--gold)">${earned}</b> из ${data.length}</div><div class="achievements-grid">`;
    data.forEach(a => {
      const svgIcon = ACHIEVEMENT_ICONS[a.code] || achIcon('award');
      const badge = a.earned
        ? `<div class="achievement-earned-badge" title="Получено">${ACHIEVEMENT_BADGE_DONE}</div>`
        : `<div class="achievement-locked-badge" title="Закрыто">${ACHIEVEMENT_BADGE_LOCK}</div>`;
      html += `<div class="achievement-card ${a.earned?'':'locked'}" onclick='showAchievementInfo(${JSON.stringify(a.name)},${JSON.stringify(a.description)},${Boolean(a.earned)})'>
        ${badge}
        <div class="achievement-svg">${svgIcon}</div>
        <div class="achievement-name">${a.name}</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function showAchievementInfo(name, description, earned) {
  tg.showPopup({title:earned?'✅ '+name:'🔒 '+name,message:description+(earned?'\n\n✨ Получено!':'\n\n❌ Ещё не получено'),buttons:[{type:'ok'}]});
}

// ===== АНОНИМНЫЙ ВОПРОС =====
