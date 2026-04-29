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

      // Применяем путь (Киберпанк / Геншин)
      if (!isAdmin) applyThemePath(data.theme_path || null);
      loadProfileDossier();
    }
  } catch(e) {}
}

function updatePoints() {
  const star = ' \u2605';
  const myPointsEl = document.getElementById('myPoints');
  const myPointsBigEl = document.getElementById('myPointsBig');
  const casinoPointsEl = document.getElementById('casinoPoints');
  const shopPointsEl = document.getElementById('shopPoints');
  const profilePointsEl = document.getElementById('myPointsRating');
  if (myPointsEl) myPointsEl.textContent = currentPoints + star;
  if (myPointsBigEl) myPointsBigEl.textContent = currentPoints;
  if (casinoPointsEl) casinoPointsEl.textContent = currentPoints + star;
  if (shopPointsEl) shopPointsEl.textContent = currentPoints + star;
  if (profilePointsEl) profilePointsEl.textContent = currentPoints + star;
}

function updateRatingPoints() {
  const profilePointsEl = document.getElementById('myPointsRating');
  if (profilePointsEl) profilePointsEl.textContent = currentPoints + ' \u2605';
}

// ===== КОНФИГ =====

function getProfileInitial(name, fallbackId) {
  const raw = String(name || fallbackId || '?').trim();
  return raw ? raw[0].toUpperCase() : '?';
}

function avatarMarkup(avatarUrl, name, fallbackId, className = 'profile-avatar-img') {
  const initial = escapeHtml(getProfileInitial(name, fallbackId));
  if (avatarUrl) {
    return `<img class="${className}" src="${avatarUrl}" alt="${escapeHtml(name || 'avatar')}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"><span class="lb-avatar-fallback" style="display:none;">${initial}</span>`;
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

function renderProfileDossier(profile = {}) {
  const stats = profile.stats || {};
  const showcase = profile.showcase || null;
  const place = profile.leaderboard_rank ? '#' + profile.leaderboard_rank : '\u2014';

  if (typeof profile.points === 'number') {
    setProfileText('myPointsRating', profile.points + ' \u2605');
  }
  setProfileText('myRankSub', (profile.rank || 'D') + '-RANK');
  setProfileText('profileLeaderboardPlace', place);
  updateProfilePathBadge(profile.theme_path || currentThemePath);

  setProfileText('profileStatusLine', profile.status_line || '\u72b6\u6001\uff1a\u5728\u7ebf // \u6743\u9650\uff1a\u5b66\u751f\u8282\u70b9 // \u540c\u6b65\u7387\uff1a0%');
  setProfileText('profileTitleBadge', profile.title || '\u534f\u8bae\u6267\u884c\u8005 / \u0418\u0441\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c');
  setProfileText('profileStatCases', stats.case_opens || 0);
  setProfileText('profileStatPrayers', stats.prayers || 0);
  setProfileText('profileStatCards', stats.cards || 0);
  setProfileText('profileStatImplants', stats.implants || 0);
  setProfileText('profileStatDiaries', stats.diaries || 0);
  setProfileText('profileStatRaids', stats.raids || 0);

  const showcaseBox = document.getElementById('profileShowcase');
  const showcaseIcon = showcaseBox ? showcaseBox.querySelector('.profile-showcase-icon') : null;
  if (showcaseIcon) showcaseIcon.textContent = showcase && showcase.glyph ? showcase.glyph : '?';
  if (showcase) {
    setProfileText('profileShowcaseText', `${showcase.kind || 'item'}: ${showcase.name || showcase.code || 'AUTO'} // ${showcase.detail || 'active'}`);
  } else {
    setProfileText('profileShowcaseText', 'SHOWCASE: AUTO // no active item');
  }
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
  if (kind === 'card') return code === 'card_moon' ? '\u6708' : '\u5361';
  const map = {
    implant_red_dragon: '\u9f8d',
    implant_netwatch: '\u885b',
    implant_qilin: '\u9e92',
    implant_caishen: '\u8d22',
    implant_terracota: '\u5175',
    implant_guanxi: '\u5173',
    implant_panda: '\u718a',
    implant_shaolin: '\u6b66',
    implant_linguasoft: '\u8a00',
  };
  return map[code] || '\u82af';
}

function renderProfileShowcaseOptions(options) {
  const box = document.getElementById('profileShowcaseOptions');
  if (!box) return;
  if (!options.length) {
    box.innerHTML = '<div class="empty-state">No active cards or implants</div>';
    return;
  }
  box.innerHTML = options.map(item => `
    <button class="profile-showcase-option" onclick="selectProfileShowcase('${item.kind}', '${escapeHtml(item.code)}')">
      <span class="profile-showcase-option-icon">${escapeHtml(item.glyph)}</span>
      <span class="profile-showcase-option-copy">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.name)}</strong>
        <em>${escapeHtml(item.detail)}</em>
      </span>
    </button>
  `).join('');
}

async function openProfileShowcaseModal() {
  const modal = document.getElementById('profileShowcaseModal');
  const box = document.getElementById('profileShowcaseOptions');
  if (!modal || !box || !currentUserId) return;
  modal.style.display = 'flex';
  box.innerHTML = '<div class="empty-state">Loading...</div>';
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
      label: 'AUTO MODE',
      name: 'Automatic showcase',
      detail: 'System selects the strongest active item',
    }];
    (Array.isArray(implants) ? implants : []).forEach(item => {
      options.push({
        kind: 'implant',
        code: item.implant_id,
        glyph: getProfileShowcaseGlyph('implant', item.implant_id, item.icon),
        label: 'IMPLANT',
        name: item.name || item.implant_id,
        detail: item.desc || `durability ${item.durability || 0}`,
      });
    });
    (Array.isArray(cards) ? cards : []).forEach(item => {
      options.push({
        kind: 'card',
        code: item.card_id,
        glyph: getProfileShowcaseGlyph('card', item.card_id),
        label: `${item.rarity || 4}\u2605 CARD`,
        name: item.name || item.card_id,
        detail: item.passive || `durability ${item.durability || 0}`,
      });
    });
    renderProfileShowcaseOptions(options);
  } catch (e) {
    box.innerHTML = '<div class="empty-state">Showcase loading error</div>';
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
  container.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const headers = {'Content-Type': 'application/json'};
    if (currentUserId) headers['X-Telegram-Id'] = String(currentUserId);
    if (isAdmin) headers['X-Admin-Id'] = String(currentUserId);
    const r = await fetch(`${API_URL}/api/diary/stars/leaderboard`, {headers});
    if (!r.ok) {
      let detail = '';
      try { const d = await r.json(); if (d.detail) detail = ': ' + d.detail; } catch(e) {}
      container.innerHTML = `<div class="empty-state">Ошибка загрузки (${r.status}${detail})</div>`;
      return;
    }
    const data = await r.json();
    if (!Array.isArray(data)) { container.innerHTML = '<div class="empty-state">Ошибка формата данных</div>'; return; }
    if (!data.length) { container.innerHTML = '<div class="empty-state">Пока нет данных</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    container.innerHTML = data.map((row, i) => {
      const medal = medals[i] || `${i+1}.`;
      const isMe = row.telegram_id === currentUserId;
      const topClass = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
      const pathLabel = row.theme_path === 'genshin' ? 'GENSHIN' : row.theme_path === 'cyberpunk' ? 'NETWATCH' : 'SYNC';
      const pathClass = row.theme_path === 'genshin' ? 'genshin' : row.theme_path === 'cyberpunk' ? 'netwatch' : 'sync';
      const status = row.days_rated > 0 ? `${row.days_rated} DAYS // +${row.total_points || 0}\u2605` : 'NOT RATED YET';
      const stars = row.total_stars || 0;
      return `<div class="diary-rank-card ${topClass} ${isMe ? 'me' : ''}" style="animation-delay:${i*0.05}s">
        <div class="diary-rank-place">${medal}</div>
        <div class="lb-avatar">${avatarMarkup(row.avatar_url, row.name, row.telegram_id, 'lb-avatar-img')}</div>
        <div class="diary-rank-main">
          <div class="diary-rank-name-row">
            <span class="diary-rank-name">${escapeHtml(row.name)}${isMe?' \ud83d\udc48':''}</span>
            <span class="lb-path-badge ${pathClass}">${pathLabel}</span>
          </div>
          <div class="diary-rank-sub">
            <span>日记节点</span>
            <span>${status}</span>
            ${row.total_bonus ? `<span>BONUS x${row.total_bonus}</span>` : ''}
          </div>
        </div>
        <div class="diary-rank-score">${stars} ⭐</div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = '<div class="empty-state">Нет соединения</div>';
  }
}

async function loadLeaderboard() {
  const IMPLANT_GLYPHS = {
    'implant_red_dragon':   ['\u9f8d', '#cc2200', 'RED DRAGON'],
    'implant_netwatch':     ['\u885b', '#cc2200', 'NETWATCH'],
    'implant_guanxi':       ['\u7fa9', '#9b59b6', 'GUANXI'],
    'implant_terracota':    ['\u5175', '#9b59b6', 'TERRACOTA'],
    'implant_panda':        ['\u718a', '#9b59b6', 'PANDA'],
    'implant_shaolin':      ['\u6b66', '#9b59b6', 'SHAOLIN'],
    'implant_linguasoft':   ['\u8a00', '#9b59b6', 'LINGUASOFT'],
    'implant_caishen':      ['\u8ca1', '#9b59b6', 'CAISHEN'],
    'implant_qilin':        ['\u9e9f', '#9b59b6', 'QILIN'],
  };
  const CARD_GLYPHS = {
    'card_zhongli':    ['\u5ca9', '#d4af37', 'ZHONGLI'],
    'card_star':       ['\u7d2b', '#9b59b6', 'STAR'],
    'card_pyro':       ['\u7130', '#e74c3c', 'PYRO'],
    'card_fox':        ['\u72d0', '#e67e22', 'FOX'],
    'card_fairy':      ['\u6843', '#e91e8c', 'FAIRY'],
    'card_literature': ['\u6587', '#3498db', 'LITERATURE'],
    'card_forest':     ['\u6728', '#2ecc71', 'FOREST'],
    'card_sea':        ['\u6d77', '#1abc9c', 'SEA'],
    'card_moon':       ['\u6708', '#b0c4de', 'MOON'],
  };
  const TOP_COLORS = [
    'linear-gradient(90deg,#d4af37,#f5e070)',
    'linear-gradient(90deg,#b0b0b0,#e8e8e8)',
    'linear-gradient(90deg,#b87333,#e8a050)',
    '#e8c84a','#e8c84a','#c8a830','#c8a830','#a88820','#a88820','#887010'
  ];
  try {
    const r = await fetch(`${API_URL}/api/leaderboard`);
    const data = await r.json();
    const container = document.getElementById('leaderboardContent');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Рейтинг пока пуст</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    let myRank = '—', html = '';

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

      // Иероглиф импланта
      let glyphHtml = '';
      let signalLabel = 'NO IMPLANT';
      if (item.implant && IMPLANT_GLYPHS[item.implant]) {
        const [glyph, color, label] = IMPLANT_GLYPHS[item.implant];
        signalLabel = label;
        glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
      } else if (item.card) {
        if (CARD_GLYPHS[item.card]) {
          const [glyph, color, label] = CARD_GLYPHS[item.card];
          signalLabel = label;
          glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
        }
      }

      // Титул
      const titleHtml = item.has_title ? '<span style="font-size:12px;margin-left:3px;">👑</span>' : '';

      // Прогресс до следующего места
      let progressHtml = '';
      let deltaHtml = i === 0 ? '<span>LEADER NODE</span>' : '';
      if (i > 0 && data[i-1]) {
        const prev = data[i-1].points;
        const curr = item.points;
        const delta = Math.max(0, prev - curr);
        const pct = prev > 0 ? Math.round((curr / prev) * 100) : 100;
        const barColor = isLegendary ? 'rgba(200,34,0,0.5)' : i < 3 ? 'rgba(212,175,55,0.4)' : 'rgba(150,150,150,0.2)';
        progressHtml = `<div class="lb-progress" style="width:${pct}%;background:${barColor};max-width:100%;"></div>`;
        deltaHtml = `<span>${delta} \u2605 TO NEXT</span>`;
      }

      // Разделитель после топ-3
      const divider = i === 3 ? '<div class="lb-divider">— — — ТОП 3 — — —</div>' : '';

      html += `${divider}<div class="lb-item ${topClass} ${isMe?'me':''}" style="${animDelay}">
        <div class="lb-rank">${medal}</div>
        <div class="lb-avatar">${avatarMarkup(item.avatar_url, item.name, item.telegram_id, 'lb-avatar-img')}</div>
        <div class="lb-name-wrap">
          <div class="lb-name-row">
            <div class="lb-name" style="${nameStyle}">${escapeHtml(item.name)}${titleHtml}${glyphHtml}${isMe?' \ud83d\udc48':''}</div>
            <span class="lb-path-badge ${pathClass}">${pathLabel}</span>
          </div>
          <div class="lb-subline">
            <span>${rankSignal}</span>
            <span>${signalLabel}</span>
            ${deltaHtml}
          </div>
          ${progressHtml}
        </div>
        <div class="lb-points">${item.points} ★</div>
      </div>`;
    });
    container.innerHTML = html;
    const placeEl = document.getElementById('profileLeaderboardPlace');
    if (placeEl) placeEl.textContent = String(myRank).startsWith('#') ? myRank : (Number(myRank) > 0 ? '#' + myRank : '\u2014');
  } catch(e) { document.getElementById('leaderboardContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

// ===== МАГАЗИН =====
