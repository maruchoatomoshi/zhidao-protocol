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
    }
  } catch(e) {}
}

function updatePoints() {
  document.getElementById('myPoints').textContent = currentPoints + ' ★';
  document.getElementById('myPointsBig').textContent = currentPoints;
  document.getElementById('casinoPoints').textContent = currentPoints + ' ★';
  document.getElementById('shopPoints').textContent = currentPoints + ' ★';
  document.getElementById('myPointsRating').textContent = currentPoints;
}

function updateRatingPoints() {
  document.getElementById('myPointsRating').textContent = currentPoints;
}

// ===== КОНФИГ =====

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
    const data = await r.json();
    if (!data.length) { container.innerHTML = '<div class="empty-state">Пока нет данных</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    container.innerHTML = data.map((row, i) => {
      const medal = medals[i] || `${i+1}.`;
      const isMe = row.telegram_id === currentUserId;
      return `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
        <div style="font-size:16px;min-width:28px;text-align:center;">${medal}</div>
        <div style="flex:1;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">${row.name}${isMe?' 👈':''}</div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace;">Дней оценено: ${row.days_rated}</div>
        </div>
        <div style="font-size:13px;font-weight:700;color:var(--gold);">${row.total_stars} ⭐</div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function loadLeaderboard() {
  const IMPLANT_GLYPHS = {
    'implant_red_dragon':   ['龍', '#cc2200'],
    'implant_netwatch':     ['衛', '#cc2200'],
    'implant_guanxi':       ['義', '#9b59b6'],
    'implant_terracota':    ['兵', '#9b59b6'],
    'implant_panda':        ['熊', '#9b59b6'],
    'implant_shaolin':      ['武', '#9b59b6'],
    'implant_linguasoft':   ['言', '#9b59b6'],
    'implant_caishen':      ['財', '#9b59b6'],
    'implant_qilin':        ['麟', '#9b59b6'],
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

      // Иероглиф импланта
      let glyphHtml = '';
      if (item.implant && IMPLANT_GLYPHS[item.implant]) {
        const [glyph, color] = IMPLANT_GLYPHS[item.implant];
        glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
      } else if (item.card) {
        const CARD_GLYPHS = {
          'card_zhongli':    ['岩', '#d4af37'],
          'card_star':       ['紫', '#9b59b6'],
          'card_pyro':       ['焰', '#e74c3c'],
          'card_fox':        ['狐', '#e67e22'],
          'card_fairy':      ['桃', '#e91e8c'],
          'card_literature': ['文', '#3498db'],
          'card_forest':     ['木', '#2ecc71'],
          'card_sea':        ['海', '#1abc9c'],
          'card_moon':       ['月', '#b0c4de'],
        };
        if (CARD_GLYPHS[item.card]) {
          const [glyph, color] = CARD_GLYPHS[item.card];
          glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
        }
      }

      // Титул
      const titleHtml = item.has_title ? '<span style="font-size:12px;margin-left:3px;">👑</span>' : '';

      // Прогресс до следующего места
      let progressHtml = '';
      if (i > 0 && data[i-1]) {
        const prev = data[i-1].points;
        const curr = item.points;
        const pct = prev > 0 ? Math.round((curr / prev) * 100) : 100;
        const barColor = isLegendary ? 'rgba(200,34,0,0.5)' : i < 3 ? 'rgba(212,175,55,0.4)' : 'rgba(150,150,150,0.2)';
        progressHtml = `<div class="lb-progress" style="width:${pct}%;background:${barColor};max-width:100%;"></div>`;
      }

      // Разделитель после топ-3
      const divider = i === 3 ? '<div class="lb-divider">— — — ТОП 3 — — —</div>' : '';

      html += `${divider}<div class="lb-item ${topClass} ${isMe?'me':''}" style="${animDelay}">
        <div class="lb-rank">${medal}</div>
        <div class="lb-name-wrap">
          <div class="lb-name" style="${nameStyle}">${item.name}${titleHtml}${glyphHtml}${isMe?' 👈':''}</div>
          ${progressHtml}
        </div>
        <div class="lb-points">${item.points} ★</div>
      </div>`;
    });
    container.innerHTML = html;
    document.getElementById('myRankSub').textContent = myRank !== '—' ? `// Место в рейтинге: #${myRank}` : '// Участвуй чтобы попасть в рейтинг!';
  } catch(e) { document.getElementById('leaderboardContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

// ===== МАГАЗИН =====
