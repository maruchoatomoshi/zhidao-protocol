async function loadPoints(telegramId) {
  if (!telegramId) return;
  try {
    const r = await fetch(`${API_URL}/api/points/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      currentPoints = data.points || 0;
      updatePoints();

      const b = document.getElementById('casinoBonusBanner');
      if (b) {
        if (data.double_win) {
          b.style.display = 'block';
          b.textContent = '🃏 УДВОЕНИЕ АКТИВНО!';
        } else {
          b.style.display = 'none';
          b.textContent = '';
        }
      }

      // Применяем путь (Киберпанк / Геншин).
      // loadPoints() is polled after almost every action (raids, casino, admin
      // adjustments). Only re-trigger the path-choice screen from a *missing*
      // theme_path when we genuinely don't have one yet this session — otherwise
      // a single transient/empty response would re-show the "first open" chooser
      // on top of an already-confirmed path.
      if (!isAdmin && (data.theme_path || !currentThemePath)) applyThemePath(data.theme_path || null);
      loadProfileDossier();
    }
  } catch(e) {}
}

function updatePoints() {
  const star = ' ★';
  const myPointsEl = document.getElementById('myPoints');
  const myPointsBigEl = document.getElementById('myPointsBig');
  const casinoPointsEl = document.getElementById('casinoPoints');
  const shopPointsEl = document.getElementById('shopPoints');
  if (myPointsEl) myPointsEl.textContent = currentPoints + star;
  if (myPointsBigEl) myPointsBigEl.textContent = currentPoints;
  if (casinoPointsEl) casinoPointsEl.textContent = currentPoints + star;
  if (shopPointsEl) shopPointsEl.textContent = currentPoints + star;
}

function updateRatingPoints() {
  if (currentUserId) loadPoints(currentUserId);
}

// ===== КОНФИГ =====

function getProfileInitial(name, fallbackId) {
  const raw = String(name || fallbackId || '?').trim();
  return raw ? raw[0].toUpperCase() : '?';
}

function avatarMarkup(avatarUrl, name, fallbackId, className = 'profile-avatar-img') {
  const initial = escapeHtml(getProfileInitial(name, fallbackId));
  if (avatarUrl) {
    return `<img class="${className}" src="${escapeHtml(avatarUrl)}" alt="${escapeHtml(name || 'avatar')}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"><span class="lb-avatar-fallback" style="display:none;">${initial}</span>`;
  }
  return `<span class="lb-avatar-fallback">${initial}</span>`;
}

function renderProfileAvatarCard(profile = {}) {
  const preview = document.getElementById('profileAvatarPreview');
  const fallback = document.getElementById('profileAvatarFallback');
  const nameEl = document.getElementById('profileDisplayName');
  const statusEl = document.getElementById('profileAvatarStatus');
  if (!preview || !fallback || !nameEl || !statusEl) return;

  const tgUser = tg && tg.initDataUnsafe ? tg.initDataUnsafe.user : null;
  const displayName = profile.full_name || tgUser?.first_name || profile.username || currentUserId || 'ZHIDAO';
  const avatarUrl = profile.avatar_url || currentAvatarUrl || tgUser?.photo_url || '';
  currentAvatarUrl = avatarUrl || null;

  nameEl.textContent = displayName;
  fallback.textContent = getProfileInitial(displayName, currentUserId);
  if (avatarUrl) {
    preview.src = avatarUrl;
    preview.style.display = 'block';
    fallback.style.display = 'none';
    statusEl.textContent = 'Аватар активен в профиле и рейтинге';
  } else {
    preview.removeAttribute('src');
    preview.style.display = 'none';
    fallback.style.display = 'flex';
    statusEl.textContent = 'Загрузи аватар, чтобы оживить рейтинг';
  }
}

const FRAME_IDS = ['bronze','silver','gold','diamond','dragon','netwatch-legend','zhongli','raider','scholar','path-netwatch','path-genshin'];

function applyAvatarFrame(el, frameId) {
  if (!el) return;
  el.classList.remove('has-frame', ...FRAME_IDS.map(f => `frame-${f}`));
  if (frameId && FRAME_IDS.includes(frameId)) {
    el.classList.add('has-frame', `frame-${frameId}`);
  }
}

function updateProfilePathBadge(path = currentThemePath) {
  const badge = document.getElementById('profilePathBadge');
  if (!badge) return;
  if (path === 'genshin') {
    badge.textContent = 'GENSHIN';
  } else if (path === 'cyberpunk') {
    badge.textContent = 'NETWATCH';
  } else {
    badge.textContent = 'SYNC';
  }
}

function setProfileText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

let lastProfileDossier = null;

function renderProfileDossier(profile = {}) {
  lastProfileDossier = profile;
  const stats = profile.stats || {};
  const showcase = profile.showcase || null;
  const place = profile.leaderboard_rank ? '#' + profile.leaderboard_rank : '—';

  setProfileText('myRankSub', (profile.rank || 'D') + '-RANK');
  setProfileText('profileLeaderboardPlace', place);
  updateProfilePathBadge(profile.theme_path || currentThemePath);

  applyAvatarFrame(document.getElementById('profileAvatarWrap'), profile.equipped_frame);

  setProfileText('profileStatusLine', profile.status_line || '状态：在线 // 权限：学生节点 // 同步率：0%');
  setProfileText('profileTitleBadge', profile.title || '协议执行者 / Исполнитель');
  setProfileText('profileStatCases', stats.case_opens || 0);
  setProfileText('profileStatPrayers', stats.prayers || 0);
  setProfileText('profileStatCards', stats.cards || 0);
  setProfileText('profileStatImplants', stats.implants || 0);
  setProfileText('profileStatDiaries', stats.diaries || 0);
  setProfileText('profileStatRaids', stats.raids || 0);

  const showcaseBox = document.getElementById('profileShowcase');
  const showcaseIcon = showcaseBox ? showcaseBox.querySelector('.profile-showcase-icon') : null;
  if (showcaseIcon) {
    showcaseIcon.textContent = showcase && showcase.glyph ? showcase.glyph : '?';
    showcaseIcon.dataset.kind = showcase ? (showcase.kind || '') : '';
    showcaseIcon.dataset.source = showcase ? (showcase.source || 'auto') : '';
  }
  if (showcase) {
    const sourceTag = showcase.source === 'manual' ? ' · ★' : '';
    setProfileText('profileShowcaseText', `${showcase.name || showcase.code || '—'} · ${showcase.detail || 'активно'}${sourceTag}`);
  } else {
    setProfileText('profileShowcaseText', 'ВИТРИНА: АВТО // нет активного предмета');
  }

  if (typeof applyWildAiProfileOverride === 'function') applyWildAiProfileOverride();
}

const RANK_TIERS = [
  { code: 'D',  min: 0 },
  { code: 'C',  min: 180 },
  { code: 'B',  min: 420 },
  { code: 'A',  min: 760 },
  { code: 'S',  min: 1150 },
  { code: 'SS', min: 1650 },
];

function computeReputationBreakdown(profile) {
  const stats = profile.stats || {};
  const points = profile.points || 0;
  const items = [
    { label: 'Очки (потолок 1000)', value: Math.min(points, 1000) },
    { label: 'Записи дневника', count: stats.diaries || 0, per: 35 },
    { label: 'Импланты', count: stats.implants || 0, per: 45 },
    { label: 'Карточки', count: stats.cards || 0, per: 35 },
    { label: 'Рейды', count: stats.raids || 0, per: 25 },
    { label: 'Победы в рейдах', count: stats.raid_wins || 0, per: 45 },
    { label: 'Открытия кейсов', count: stats.case_opens || 0, per: 4 },
    { label: 'Молитвы', count: stats.prayers || 0, per: 4 },
  ].map(i => ({ ...i, value: i.value !== undefined ? i.value : i.count * i.per }));
  const total = items.reduce((sum, i) => sum + i.value, 0);
  return { items, total };
}

function renderRankBreakdown(profile) {
  const box = document.getElementById('rankBreakdownContent');
  if (!box) return;
  const { items, total } = computeReputationBreakdown(profile);
  let tierIdx = 0;
  RANK_TIERS.forEach((t, i) => { if (total >= t.min) tierIdx = i; });
  const current = RANK_TIERS[tierIdx];
  const next = RANK_TIERS[tierIdx + 1];
  const progressPct = next ? Math.min(100, Math.round(((total - current.min) / (next.min - current.min)) * 100)) : 100;

  const rows = items.map(i => `
    <div class="rank-breakdown-row">
      <span class="rank-breakdown-label">${escapeHtml(i.label)}${i.count !== undefined ? ` <em>×${i.count}</em>` : ''}</span>
      <span class="rank-breakdown-value">+${i.value}</span>
    </div>
  `).join('');

  box.innerHTML = `
    <div class="rank-breakdown-total">ИНДЕКС РАНГА: <strong>${total}</strong></div>
    ${rows}
    <div class="rank-breakdown-progress">
      <div class="rank-breakdown-progress-head">
        <span>${current.code}-RANK</span>
        <span>${next ? next.code + '-RANK' : 'МАКСИМУМ'}</span>
      </div>
      <div class="rank-breakdown-progress-bar"><div class="rank-breakdown-progress-fill" style="width:${progressPct}%"></div></div>
      <div class="rank-breakdown-progress-note">${next ? `Нужно ещё ${next.min - total} к индексу ранга до ${next.code}-RANK` : 'Максимальный ранг достигнут'}</div>
    </div>
  `;
}

async function openRankBreakdownModal() {
  const modal = document.getElementById('rankBreakdownModal');
  const box = document.getElementById('rankBreakdownContent');
  if (!modal || !box) return;
  modal.style.display = 'flex';
  let profile = lastProfileDossier;
  if (!profile && currentUserId) {
    box.innerHTML = '<div class="empty-state">Загрузка...</div>';
    try {
      const r = await fetch(`${API_URL}/api/profile/${currentUserId}`);
      profile = r.ok ? await r.json() : null;
    } catch (e) {}
  }
  if (!profile) {
    box.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
    return;
  }
  renderRankBreakdown(profile);
}

function closeRankBreakdownModal() {
  const modal = document.getElementById('rankBreakdownModal');
  if (modal) modal.style.display = 'none';
}

async function loadProfileDossier() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/profile/${currentUserId}`);
    const data = await r.json();
    if (!r.ok) return;
    renderProfileDossier(data);
  } catch (e) {}
}

function getProfileShowcaseGlyph(kind, code, fallback) {
  if (fallback) return fallback;
  if (kind === 'card') return code === 'card_moon' ? '月' : '卡';
  const map = {
    implant_red_dragon: '龍',
    implant_netwatch: '衛',
    implant_qilin: '麒',
    implant_caishen: '财',
    implant_terracota: '兵',
    implant_guanxi: '关',
    implant_panda: '熊',
    implant_shaolin: '武',
    implant_linguasoft: '言',
  };
  return map[code] || '芯';
}

function renderProfileShowcaseOptions(options) {
  const box = document.getElementById('profileShowcaseOptions');
  if (!box) return;
  if (!options.length) {
    box.innerHTML = '<div class="empty-state">No active cards or implants</div>';
    return;
  }
  box.innerHTML = options.map(item => {
    const art = item.img
      ? `<img src="${escapeHtml(item.img)}" alt="${escapeHtml(item.name)}">`
      : `<span>${escapeHtml(item.glyph)}</span>`;
    return `
    <button class="profile-showcase-card profile-showcase-card-${item.rarityClass} ${item.equipped ? 'equipped' : ''}" onclick="selectProfileShowcase('${item.kind}', '${escapeHtml(item.code)}')">
      <span class="profile-showcase-card-art">${art}</span>
      <span class="profile-showcase-card-label">${escapeHtml(item.label)}</span>
      <span class="profile-showcase-card-name">${escapeHtml(item.name)}</span>
      <span class="profile-showcase-card-detail">${escapeHtml(item.detail)}</span>
      ${item.equipped ? '<span class="profile-showcase-card-equipped">★ АКТИВНО</span>' : ''}
    </button>`;
  }).join('');
}

async function openProfileShowcaseModal() {
  const modal = document.getElementById('profileShowcaseModal');
  const box = document.getElementById('profileShowcaseOptions');
  if (!modal || !box || !currentUserId) return;
  modal.style.display = 'flex';
  box.innerHTML = '<div class="empty-state">Loading...</div>';
  const equippedKind = lastProfileDossier?.showcase?.kind || null;
  const equippedCode = lastProfileDossier?.showcase?.code || null;
  const isManual = lastProfileDossier?.showcase?.source === 'manual';
  try {
    const [implantsRes, cardsRes] = await Promise.all([
      fetch(`${API_URL}/api/casino/implants/${currentUserId}`),
      fetch(`${API_URL}/api/cards/${currentUserId}`),
    ]);
    const implants = implantsRes.ok ? await implantsRes.json() : [];
    const cards = cardsRes.ok ? await cardsRes.json() : [];
    const options = [{
      kind: 'auto',
      code: '',
      glyph: '自',
      label: 'АВТО',
      name: 'Автоматическая витрина',
      detail: 'Система сама выбирает самый сильный активный предмет',
      rarityClass: 'auto',
      equipped: !isManual,
    }];
    (Array.isArray(implants) ? implants : []).forEach(item => {
      const isLegendary = Boolean(LEGENDARY_IMPLANT_INFO && LEGENDARY_IMPLANT_INFO[item.implant_id]);
      options.push({
        kind: 'implant',
        code: item.implant_id,
        glyph: getProfileShowcaseGlyph('implant', item.implant_id, item.icon),
        img: typeof IMPLANT_IMGS !== 'undefined' ? IMPLANT_IMGS[item.implant_id] : null,
        label: isLegendary ? 'LEGENDARY ИМПЛАНТ' : 'ИМПЛАНТ',
        name: item.name || item.implant_id,
        detail: item.desc || `прочность ${item.durability || 0}`,
        rarityClass: isLegendary ? 'red' : 'gold',
        equipped: isManual && equippedKind === 'implant' && equippedCode === item.implant_id,
      });
    });
    (Array.isArray(cards) ? cards : []).forEach(item => {
      const rarity = item.rarity || 4;
      options.push({
        kind: 'card',
        code: item.card_id,
        glyph: getProfileShowcaseGlyph('card', item.card_id),
        img: typeof GENSHIN_IMGS !== 'undefined' ? GENSHIN_IMGS[item.card_id] : null,
        label: `${rarity}★ КАРТА`,
        name: item.name || item.card_id,
        detail: item.passive || `прочность ${item.durability || 0}`,
        rarityClass: rarity === 5 ? 'gold' : rarity === 4 ? 'purple' : 'blue',
        equipped: isManual && equippedKind === 'card' && equippedCode === item.card_id,
      });
    });
    renderProfileShowcaseOptions(options);
  } catch (e) {
    box.innerHTML = '<div class="empty-state">Ошибка загрузки витрины</div>';
  }
}

function closeProfileShowcaseModal() {
  const modal = document.getElementById('profileShowcaseModal');
  if (modal) modal.style.display = 'none';
}

async function selectProfileShowcase(kind, code) {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/profile/showcase`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, kind, code})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Showcase save failed');
    closeProfileShowcaseModal();
    await loadProfileDossier();
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
  } catch (e) {
    showToast('Showcase save failed');
  }
}

function renderProfileFrameOptions(data) {
  const box = document.getElementById('profileFrameOptions');
  if (!box) return;
  const equipped = data.equipped || null;
  let html = `
    <button class="profile-showcase-option ${!equipped ? 'equipped' : ''}" onclick="selectProfileFrame(null)">
      <span class="profile-frame-swatch frame-none"></span>
      <span class="profile-showcase-option-copy">
        <span>NO FRAME</span>
        <strong>Без рамки</strong>
        <em>Стандартный аватар</em>
      </span>
    </button>`;
  html += (data.frames || []).map(f => `
    <button class="profile-showcase-option ${f.unlocked ? '' : 'locked'} ${equipped === f.id ? 'equipped' : ''}"
      onclick="${f.unlocked ? `selectProfileFrame('${f.id}')` : 'void(0)'}">
      <span class="profile-frame-swatch frame-${f.id}"></span>
      <span class="profile-showcase-option-copy">
        <span>${f.unlocked ? 'РАЗБЛОКИРОВАНО' : 'ЗАБЛОКИРОВАНО'}</span>
        <strong>${escapeHtml(f.name)}</strong>
        <em>${escapeHtml(f.desc)}</em>
      </span>
      ${f.unlocked ? '' : '<span class="profile-frame-lock">🔒</span>'}
    </button>`).join('');
  box.innerHTML = html;
}

async function openProfileFrameModal() {
  const modal = document.getElementById('profileFrameModal');
  const box = document.getElementById('profileFrameOptions');
  if (!modal || !box || !currentUserId) return;
  modal.style.display = 'flex';
  box.innerHTML = '<div class="empty-state">Loading...</div>';
  try {
    const r = await fetch(`${API_URL}/api/frames/${currentUserId}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Frames load failed');
    renderProfileFrameOptions(data);
  } catch (e) {
    box.innerHTML = '<div class="empty-state">Frames loading error</div>';
  }
}

function closeProfileFrameModal() {
  const modal = document.getElementById('profileFrameModal');
  if (modal) modal.style.display = 'none';
}

async function selectProfileFrame(frameId) {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/frames/equip`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, frame_id: frameId})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Frame save failed');
    applyAvatarFrame(document.getElementById('profileAvatarWrap'), data.equipped);
    await openProfileFrameModal();
    loadLeaderboard();
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
  } catch (e) {
    showToast('Не удалось сохранить рамку');
  }
}

function compressProfileAvatar(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type || !file.type.startsWith('image/')) {
      reject(new Error('Invalid image'));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Read failed'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('Image failed'));
      img.onload = () => {
        const maxSize = 320;
        const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.76));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

async function saveProfileAvatar(avatarUrl) {
  if (!currentUserId) return;
  const r = await fetch(`${API_URL}/api/user/avatar`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({telegram_id: currentUserId, avatar_url: avatarUrl || ''})
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Avatar save failed');
  currentAvatarUrl = data.avatar_url || null;
  renderProfileAvatarCard({avatar_url: currentAvatarUrl});
  loadLeaderboard();
  loadProfileDossier();
}

async function handleProfileAvatarFile(input) {
  const file = input && input.files ? input.files[0] : null;
  if (!file) return;
  try {
    const avatarUrl = await compressProfileAvatar(file);
    await saveProfileAvatar(avatarUrl);
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
  } catch (e) {
    showToast('Не удалось сохранить аватар');
  } finally {
    if (input) input.value = '';
  }
}

async function removeProfileAvatar() {
  try {
    await saveProfileAvatar('');
    try { tg.HapticFeedback.impactOccurred('light'); } catch(e) {}
  } catch (e) {
    showToast('Не удалось сбросить аватар');
  }
}

function switchRatingTab(tab, btn) {
  document.querySelectorAll('#page-rating .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('rating-main-tab').style.display = tab === 'main' ? 'block' : 'none';
  document.getElementById('rating-diary-tab').style.display = tab === 'diary' ? 'block' : 'none';
  if (tab === 'diary') loadDiaryStarsLeaderboardRating();
}

async function loadDiaryStarsLeaderboardRating() {
  const container = document.getElementById('diaryStarsLeaderboardRating');
  if (!container) return;
  container.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const headers = {'Content-Type': 'application/json'};
    if (currentUserId) headers['X-Telegram-Id'] = String(currentUserId);
    if (isAdmin) headers['X-Admin-Id'] = String(currentUserId);
    let diaryRows = [];
    let userRows = [];
    let warning = '';

    try {
      const diaryResponse = await fetch(`${API_URL}/api/diary/stars/leaderboard`, {headers});
      if (diaryResponse.ok) {
        const parsed = await diaryResponse.json();
        if (Array.isArray(parsed)) diaryRows = parsed;
      } else {
        let detail = '';
        try { const d = await diaryResponse.json(); if (d.detail) detail = `: ${d.detail}`; } catch(e) {}
        warning = `Дневниковый API ответил ${diaryResponse.status}${detail}; показываю общий список.`;
      }
    } catch(e) {
      warning = 'Дневниковый API недоступен; показываю общий список.';
    }

    try {
      const usersResponse = await fetch(`${API_URL}/api/leaderboard`);
      if (usersResponse.ok) {
        const parsed = await usersResponse.json();
        if (Array.isArray(parsed)) userRows = parsed;
      }
    } catch(e) {
      if (!warning) warning = 'Общий рейтинг временно недоступен.';
    }

    if (!diaryRows.length && !userRows.length) {
      container.innerHTML = '<div class="empty-state">Пока нет данных</div>';
      return;
    }

    const rowsById = new Map();
    userRows.forEach(row => {
      rowsById.set(row.telegram_id, {
        telegram_id: row.telegram_id,
        name: row.name || 'Аноним',
        avatar_url: row.avatar_url || null,
        theme_path: row.theme_path || null,
        total_stars: 0,
        total_bonus: 0,
        total_points: 0,
        days_rated: 0
      });
    });
    diaryRows.forEach(row => {
      rowsById.set(row.telegram_id, {
        ...(rowsById.get(row.telegram_id) || {}),
        telegram_id: row.telegram_id,
        name: row.name || rowsById.get(row.telegram_id)?.name || 'Аноним',
        avatar_url: row.avatar_url || rowsById.get(row.telegram_id)?.avatar_url || null,
        theme_path: row.theme_path || rowsById.get(row.telegram_id)?.theme_path || null,
        total_stars: Number(row.total_stars || 0),
        total_bonus: Number(row.total_bonus || 0),
        total_points: Number(row.total_points || 0),
        days_rated: Number(row.days_rated || 0)
      });
    });

    const data = Array.from(rowsById.values()).sort((a, b) =>
      (b.total_points || 0) - (a.total_points || 0)
      || (b.total_stars || 0) - (a.total_stars || 0)
      || (b.days_rated || 0) - (a.days_rated || 0)
      || String(a.name || '').localeCompare(String(b.name || ''), 'ru')
    );

    const medals = ['🥇','🥈','🥉'];
    const cards = data.map((row, i) => {
      const medal = medals[i] || `${i+1}.`;
      const isMe = row.telegram_id === currentUserId;
      const topClass = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
      const pathLabel = row.theme_path === 'genshin' ? 'GENSHIN' : row.theme_path === 'cyberpunk' ? 'NETWATCH' : 'SYNC';
      const pathClass = row.theme_path === 'genshin' ? 'genshin' : row.theme_path === 'cyberpunk' ? 'netwatch' : 'sync';
      const status = row.days_rated > 0 ? `${row.days_rated} DAYS // +${row.total_points || 0}★` : 'ОЖИДАЕТ ОЦЕНКИ';
      const stars = row.total_stars || 0;
      return `<div class="diary-rank-card ${topClass} ${isMe ? 'me' : ''}" style="animation-delay:${i*0.05}s">
        <div class="diary-rank-place">${medal}</div>
        <div class="lb-avatar">${avatarMarkup(row.avatar_url, row.name, row.telegram_id, 'lb-avatar-img')}</div>
        <div class="diary-rank-main">
          <div class="diary-rank-name-row">
            <span class="diary-rank-name">${escapeHtml(row.name)}</span>
            <span class="lb-path-badge ${pathClass}">${pathLabel}</span>
          </div>
          <div class="diary-rank-sub">
            <span>日记节点</span>
            <span>${status}</span>
            ${row.total_bonus ? `<span>BONUS x${row.total_bonus}</span>` : ''}
          </div>
        </div>
        <div class="diary-rank-score">${stars} 💎</div>
      </div>`;
    }).join('');
    container.innerHTML = `${warning ? `<div class="diary-rank-note">${escapeHtml(warning)}</div>` : ''}${cards}`;
  } catch(e) {
    container.innerHTML = '<div class="empty-state">Нет соединения</div>';
  }
}

async function loadLeaderboard() {
  const IMPLANT_GLYPHS = {
    'implant_red_dragon':   ['龍', '#cc2200', 'RED DRAGON'],
    'implant_netwatch':     ['衛', '#cc2200', 'NETWATCH'],
    'implant_guanxi':       ['義', '#9b59b6', 'GUANXI'],
    'implant_terracota':    ['兵', '#9b59b6', 'TERRACOTA'],
    'implant_panda':        ['熊', '#9b59b6', 'PANDA'],
    'implant_shaolin':      ['武', '#9b59b6', 'SHAOLIN'],
    'implant_linguasoft':   ['言', '#9b59b6', 'LINGUASOFT'],
    'implant_caishen':      ['財', '#9b59b6', 'CAISHEN'],
    'implant_qilin':        ['麟', '#9b59b6', 'QILIN'],
  };
  const CARD_GLYPHS = {
    'card_zhongli':    ['岩', '#d4af37', 'ZHONGLI'],
    'card_star':       ['紫', '#9b59b6', 'STAR'],
    'card_pyro':       ['焰', '#e74c3c', 'PYRO'],
    'card_fox':        ['狐', '#e67e22', 'FOX'],
    'card_fairy':      ['桃', '#e91e8c', 'FAIRY'],
    'card_literature': ['文', '#3498db', 'LITERATURE'],
    'card_forest':     ['木', '#2ecc71', 'FOREST'],
    'card_sea':        ['海', '#1abc9c', 'SEA'],
    'card_moon':       ['月', '#b0c4de', 'MOON'],
  };
  const TOP_COLORS = [
    'linear-gradient(90deg,#d4af37,#f5e070)',
    'linear-gradient(90deg,#b0b0b0,#e8e8e8)',
    'linear-gradient(90deg,#b87333,#e8a050)',
    '#e8c84a','#e8c84a','#c8a830','#c8a830','#a88820','#a88820','#887010'
  ];
  try {
    const r = await fetch(`${API_URL}/api/leaderboard`);
    const container = document.getElementById('leaderboardContent');
    if (!r.ok) {
      let detail = '';
      try { const d = await r.json(); if (d.detail) detail = `: ${d.detail}`; } catch(e) {}
      container.innerHTML = `<div class="empty-state">Ошибка загрузки (${r.status}${detail})</div>`;
      return;
    }
    let data = await r.json();
    if (!data.length) { container.innerHTML = '<div class="empty-state">Рейтинг пока пуст</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    let myRank = '—', html = '';

    // Wild AI Breach: личности (имя/аватар/титул) перемешаны между местами рейтинга
    const breachActive = typeof isWildAiBreachActive === 'function' && isWildAiBreachActive();
    if (breachActive && typeof seededShuffle === 'function') {
      const identities = data.map(item => ({
        name: item.name,
        avatar_url: item.avatar_url,
        telegram_id: item.telegram_id,
        has_title: item.has_title,
      }));
      const shuffled = seededShuffle(identities, getWildAiBreachSeed());
      data = data.map((item, i) => ({ ...item, ...shuffled[i] }));
      html += '<div class="lb-corrupted-badge">⚠ ДАННЫЕ ПОВРЕЖДЕНЫ // ОТОБРАЖЕНИЕ НЕДОСТОВЕРНО</div>';
    }

    data.forEach((item, i) => {
      const medal = medals[i] || (i+1)+'.';
      const isMe = currentUserId && item.telegram_id === currentUserId;
      if (isMe) myRank = i+1;
      const topClass = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
      const animDelay = `animation-delay:${i*0.06}s`;

      // Цвет ника — топ-10 градиент
      const nameColor = i < 10 ? TOP_COLORS[i] : '';
      const isGradient = nameColor && nameColor.startsWith('linear');
      let nameStyle = isGradient
        ? `background:${nameColor};-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-weight:700;`
        : nameColor ? `color:${nameColor};font-weight:700;` : '';

      // Свечение топ-3
      if (i === 0) nameStyle += 'filter:drop-shadow(0 0 8px rgba(212,175,55,0.6));';
      else if (i === 1) nameStyle += 'filter:drop-shadow(0 0 6px rgba(200,200,200,0.4));';
      else if (i === 2) nameStyle += 'filter:drop-shadow(0 0 6px rgba(184,115,51,0.4));';

      // Легендарные импланты — красный ник поверх всего
      const isLegendary = item.implant === 'implant_red_dragon' || item.implant === 'implant_netwatch';
      if (isLegendary) {
        nameStyle = 'color:#cc2200;text-shadow:0 0 10px rgba(200,0,0,0.5);font-weight:700;';
      }

      const pathLabel = item.theme_path === 'genshin' ? 'GENSHIN' : item.theme_path === 'cyberpunk' ? 'NETWATCH' : 'SYNC';
      const pathClass = item.theme_path === 'genshin' ? 'genshin' : item.theme_path === 'cyberpunk' ? 'netwatch' : 'sync';
      const rankSignal = i === 0 ? 'ALPHA' : i < 3 ? 'ELITE' : i < 10 ? 'TOP-10' : 'OPERATOR';

      // Сигнал импланта/карты для подстроки
      let signalLabel = 'NO IMPLANT';
      if (item.implant && IMPLANT_GLYPHS[item.implant]) {
        signalLabel = IMPLANT_GLYPHS[item.implant][2];
      } else if (item.card && CARD_GLYPHS[item.card]) {
        signalLabel = CARD_GLYPHS[item.card][2];
      }

      // Титул — раньше тут была корона рядом с ником, убрали: статус "титула дня"
      // уже передаётся через title-glow подсветку всей строки (title_style выше).
      const titleHtml = '';

      // Прогресс до следующего места
      let progressHtml = '';
      let deltaHtml = i === 0 ? '<span>LEADER NODE</span>' : '';
      if (i > 0 && data[i-1]) {
        const prev = data[i-1].rep;
        const curr = item.rep;
        const delta = Math.max(0, prev - curr);
        const pct = prev > 0 ? Math.round((curr / prev) * 100) : 100;
        const barColor = isLegendary ? 'rgba(200,34,0,0.5)' : i < 3 ? 'rgba(212,175,55,0.4)' : 'rgba(150,150,150,0.2)';
        progressHtml = `<div class="lb-progress" style="width:${pct}%;background:${barColor};max-width:100%;"></div>`;
        deltaHtml = `<span>${delta} REP TO NEXT</span>`;
      }

      // Разделитель после топ-3
      const divider = i === 3 ? '<div class="lb-divider">— — — ТОП 3 — — —</div>' : '';

      // Рамка аватара — за топ-3 фиксированная, для остальных по выбору пользователя
      const frameClass = (!topClass && item.equipped_frame) ? `has-frame frame-${item.equipped_frame}` : '';

      // Титул дня с подсветкой — выделяет всю строку игрока целиком (рамка + ник + статус)
      const titleGlowClass = item.title_style ? `title-glow title-${item.title_style}` : '';

      // Динамика места в рейтинге со вчера
      let rankChangeHtml = '';
      if (item.rank_delta > 0) {
        rankChangeHtml = `<span class="lb-rank-change up">▲${item.rank_delta}</span>`;
      } else if (item.rank_delta < 0) {
        rankChangeHtml = `<span class="lb-rank-change down">▼${Math.abs(item.rank_delta)}</span>`;
      }

      html += `${divider}<div class="lb-item ${topClass} ${isMe?'me':''} ${titleGlowClass}" style="${animDelay}">
        <div class="lb-rank">${medal}${rankChangeHtml}</div>
        <div class="lb-avatar ${frameClass}">${avatarMarkup(item.avatar_url, item.name, item.telegram_id, 'lb-avatar-img')}</div>
        <div class="lb-name-wrap">
          <div class="lb-name-row">
            <div class="lb-name" style="${nameStyle}">${escapeHtml(item.name)}${titleHtml}</div>
            <span class="lb-path-badge ${pathClass}">${pathLabel}</span>
          </div>
          <div class="lb-subline">
            <span>${rankSignal}</span>
            <span>${signalLabel}</span>
            ${deltaHtml}
          </div>
          ${progressHtml}
        </div>
        <div class="lb-points">${item.rep} REP</div>
      </div>`;
    });
    container.innerHTML = html;
    const placeEl = document.getElementById('profileLeaderboardPlace');
    if (placeEl) placeEl.textContent = String(myRank).startsWith('#') ? myRank : (Number(myRank) > 0 ? '#' + myRank : '—');
    if (typeof checkMjuTopRank === 'function') checkMjuTopRank(Number(myRank) || 0);
  } catch(e) { document.getElementById('leaderboardContent').innerHTML = '<div class="empty-state">Нет соединения</div>'; }
}

// ===== МАГАЗИН =====
