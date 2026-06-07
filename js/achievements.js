const ACHIEVEMENT_IMAGES = {
  early_bird: 'ach_early_bird.png',
  iron_mode: 'ach_iron_mode.png',
  legend: 'ach_protocol_legend.png',
  curious: 'ach_explorer.png',
  polyglot: 'ach_polyglot.png',
  explorer: 'ach_guide.png',
  brave: 'ach_bold_move.png',
  exemplary: 'ach_model_participant.png',
  helper: 'ach_group_helper.png',
  dragon: 'ach_dragon_trace.png',
  night_watch: 'ach_night_watch.png',
  master: 'ach_summon_master.png',
  gambler: 'ach_probability_player.png',
  lucky: 'ach_lucky_signal.png'
};

function achIcon(filename) {
  return `<div class="achievement-icon-wrap"><img src="${filename}" alt=""></div>`;
}

const ACHIEVEMENT_ICONS = {};
Object.keys(ACHIEVEMENT_IMAGES).forEach(code => {
  ACHIEVEMENT_ICONS[code] = achIcon(ACHIEVEMENT_IMAGES[code]);
});

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
      const svgIcon = ACHIEVEMENT_ICONS[a.code] || `<div class="achievement-icon-wrap"><i class="ti ti-award"></i></div>`;
      const badge = a.earned
        ? `<div class="achievement-earned-badge" title="Получено">${ACHIEVEMENT_BADGE_DONE}</div>`
        : `<div class="achievement-locked-badge" title="Закрыто">${ACHIEVEMENT_BADGE_LOCK}</div>`;
      html += `<div class="achievement-card ${a.earned?'':'locked'}" onclick='showAchievementInfo(${JSON.stringify(a.code)},${JSON.stringify(a.name)},${JSON.stringify(a.description)},${Boolean(a.earned)})'>
        ${badge}
        <div class="achievement-svg">${svgIcon}</div>
        <div class="achievement-name">${a.name}</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function ensureAchievementModal() {
  let modal = document.getElementById('achievementModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'achievementModal';
  modal.className = 'achievement-modal';
  modal.innerHTML = `
    <div class="achievement-modal-sheet">
      <div class="achievement-modal-img-wrap" id="achievementModalImgWrap">
        <img id="achievementModalImg" src="" alt="">
      </div>
      <div class="achievement-modal-status" id="achievementModalStatus"></div>
      <div class="achievement-modal-title" id="achievementModalTitle"></div>
      <div class="achievement-modal-desc" id="achievementModalDesc"></div>
      <button class="achievement-modal-close" type="button" data-role="close">Закрыть</button>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (event) => {
    if (event.target === modal || event.target.dataset.role === 'close') {
      modal.style.display = 'none';
    }
  });
  return modal;
}

function showAchievementInfo(code, name, description, earned) {
  const modal = ensureAchievementModal();
  const imgWrap = modal.querySelector('#achievementModalImgWrap');
  const img = modal.querySelector('#achievementModalImg');
  const statusEl = modal.querySelector('#achievementModalStatus');
  const titleEl = modal.querySelector('#achievementModalTitle');
  const descEl = modal.querySelector('#achievementModalDesc');

  img.src = ACHIEVEMENT_IMAGES[code] || '';
  imgWrap.classList.toggle('locked', !earned);
  statusEl.textContent = earned ? '✓ ПОЛУЧЕНО' : '🔒 НЕДОСТУПНО';
  statusEl.className = 'achievement-modal-status ' + (earned ? 'earned' : 'locked');
  titleEl.textContent = name;
  descEl.textContent = earned ? description : 'Эта ачивка ещё не открыта. Условие получения скрыто, пока ты её не заработаешь.';

  modal.style.display = 'flex';
}

// ===== АНОНИМНЫЙ ВОПРОС =====
