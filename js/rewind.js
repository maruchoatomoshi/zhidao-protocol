/**
 * ZHIDAO Protocol — Trip Rewind (Spotify-Wrapped-style end-of-trip summary)
 *
 * Pulls real data from GET /api/rewind/{telegram_id} (read-only aggregation
 * over existing tables, see CLAUDE.md). Falls back to REWIND_DEMO_DATA if
 * the request fails (e.g. previewing before any real trip activity exists).
 *
 * Trigger: window.showRewind()  (admin-panel preview button / console).
 */

const REWIND_RARITY_COLOR = {
  legendary: '#ffd24a',
  epic:      '#c98bff',
  rare:      '#6aa0d4',
  common:    '#8fa6bd'
};
const REWIND_RARITY_LABEL = {
  legendary: 'ЛЕГЕНДАРНЫЙ',
  epic:      'ЭПИЧЕСКИЙ',
  rare:      'РЕДКИЙ',
  common:    'ОБЫЧНЫЙ'
};

// Per-slide flair: a Tabler icon (consistent with the rest of the app — no
// emoji) plus a single oversized hanzi character drifting in the background,
// each picked to echo that slide's theme (信 for credit/points, 勤 for
// attendance discipline, etc.) rather than being purely decorative.
const REWIND_SLIDE_META = {
  intro:      { icon: 'ti-sparkles',     hanzi: '智道' },
  earned:     { icon: 'ti-coin',         hanzi: '信' },
  spent:      { icon: 'ti-shopping-cart',hanzi: '耗' },
  cases:      { icon: 'ti-box',          hanzi: '箱' },
  drop:       { icon: 'ti-diamond',      hanzi: '运' },
  attendance: { icon: 'ti-shield-check', hanzi: '勤' },
  diary:      { icon: 'ti-book',         hanzi: '记' },
  events:     { icon: 'ti-bolt',         hanzi: '盾' },
  role:       { icon: 'ti-crown',        hanzi: '命' },
  card:       { icon: 'ti-share',        hanzi: '协议' },
  timeline:   { icon: 'ti-chart-bar',    hanzi: '迹' },
  compare:    { icon: 'ti-trophy',       hanzi: '比' },
  antirecord: { icon: 'ti-mood-confuzed',hanzi: '囧' }
};

// --- DEMO DATA (placeholder until /api/rewind/{telegram_id}) ---
const REWIND_DEMO_DATA = {
  name: 'ОПЕРАТОР',
  date_range: '01.07 — 14.07.2026',
  points_earned: 1840,
  points_spent: 1230,
  final_balance: 610,
  cases_opened: 27,
  best_drop: { name: 'КРАСНЫЙ ДРАКОН', rarity: 'legendary', image_url: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true' },
  attendance_pct: 96,
  diary_entries: 11,
  diary_avg_stars: 4.3,
  events_repelled: 6,
  event_accuracy: 78,
  gifts_given: 3,
  role: {
    title: 'ЛЮБИМЕЦ РАНДОМА',
    subtitle: 'единственный, кто выбил легендарный имплант за поездку'
  },
  timeline: [
    { label: 'Нед. 1', value: 420 },
    { label: 'Нед. 2', value: 610 },
    { label: 'Нед. 3', value: 540 },
    { label: 'Нед. 4', value: 270 }
  ],
  percentile: 12,
  beaten_count: 58,
  antirecord: { label: 'самый дорогой порыв', value: '-180', sub: 'потрачено за один раз' }
};

let _rewindSlides = [];
let _rewindIndex = 0;
let _rewindTimer = null;

function _rewindBuildSlides(d) {
  const dropColor = REWIND_RARITY_COLOR[d.best_drop && d.best_drop.rarity] || '#00ff66';
  const dropLabel = REWIND_RARITY_LABEL[d.best_drop && d.best_drop.rarity] || '';
  const slides = [
    { type: 'intro', key: 'intro', accent: '#00ff66',
      kicker: 'ZHIDAO PROTOCOL', big: 'REWIND', bigClass: 'text',
      label: d.date_range, sub: 'твоя поездка в цифрах' },

    { type: 'stat', key: 'earned', accent: '#00ff66',
      kicker: 'за эту поездку ты заработал', value: d.points_earned, count: true,
      label: '信用 баллов', sub: 'каждый — за реальное действие' },

    { type: 'stat', key: 'spent', accent: '#ff4d6d',
      kicker: '…и не побоялся потратить', value: d.points_spent, count: true,
      label: 'баллов на кейсы, магазин и события' },

    { type: 'stat', key: 'cases', accent: '#6aa0d4',
      kicker: 'ты открыл', value: d.cases_opened, count: true,
      label: 'кейсов и молитв', sub: 'азарт — это тоже стратегия' }
  ];

  if (d.timeline && d.timeline.length) {
    slides.push({ type: 'timeline', key: 'timeline', accent: '#6aa0d4',
      kicker: 'твоя активность по неделям', timeline: d.timeline,
      sub: 'баллы, заработанные за каждую неделю' });
  }

  slides.push(
    { type: 'stat', key: 'drop', accent: dropColor, rays: true, dropRarity: d.best_drop ? d.best_drop.rarity : null,
      kicker: 'твой лучший дроп', big: d.best_drop ? d.best_drop.name : '—', bigClass: 'text',
      dropImage: d.best_drop ? d.best_drop.image_url : null,
      label: dropLabel, sub: 'не каждому так везёт' }
  );

  if (d.percentile) {
    slides.push({ type: 'stat', key: 'compare', accent: '#ffd24a',
      kicker: 'по баллам за поездку ты вошёл', big: 'ТОП-' + d.percentile + '%', bigClass: 'text',
      label: d.beaten_count ? 'обогнал ' + d.beaten_count + ' операторов' : 'среди всех операторов поездки' });
  }

  slides.push(
    { type: 'stat', key: 'attendance', accent: '#00ff66',
      kicker: 'дисциплина отметок', value: d.attendance_pct, suffix: '%', count: true,
      label: 'ты почти не пропускал сбор', sub: 'Михаил Юрьевич это заметил' },

    { type: 'stat', key: 'diary', accent: '#ffd24a',
      kicker: 'дневник оператора', value: d.diary_entries, count: true,
      label: 'записей сдано',
      sub: 'средняя оценка ' + (d.diary_avg_stars || 0).toFixed(1) + ' ★' }
  );

  if (d.antirecord) {
    slides.push({ type: 'stat', key: 'antirecord', accent: '#ff7a45',
      kicker: 'и для баланса — антирекорд', big: d.antirecord.value, bigClass: 'text',
      label: d.antirecord.label, sub: d.antirecord.sub });
  }

  slides.push(
    { type: 'stat', key: 'events', accent: '#00ff66',
      kicker: 'ты отражал атаки Архитектора и WildAI', value: d.events_repelled, count: true,
      label: 'раз спасал протокол',
      sub: 'точность ответов ' + (d.event_accuracy || 0) + '%' },

    { type: 'role', key: 'role', accent: '#00ff66',
      kicker: 'твоя роль в протоколе',
      title: d.role ? d.role.title : '—',
      subtitle: d.role ? d.role.subtitle : '' },

    { type: 'card', key: 'card', accent: '#00ff66', data: d }
  );

  return slides;
}

async function loadRewindData() {
  try {
    const { response, data } = await apiGetJsonSafe(`/api/rewind/${currentUserId}`);
    if (response.ok && data) return data;
  } catch (e) {}
  return REWIND_DEMO_DATA;
}

async function showRewind(data) {
  const d = data || await loadRewindData();
  _rewindSlides = _rewindBuildSlides(d);
  _rewindIndex = 0;
  const overlay = document.getElementById('rewindOverlay');
  if (!overlay) return;

  // Persistent ambient shell — built once so background motion / particles
  // keep running smoothly instead of restarting on every slide change.
  overlay.innerHTML = `
    <div class="rewind-bg"></div>
    <div class="rewind-grid"></div>
    <div class="rewind-particles" id="rewindParticles"></div>
    <div class="rewind-scanlines"></div>
    <div class="rewind-flash" id="rewindFlash"></div>
    <div class="rewind-bars" id="rewindBars"></div>
    <button class="rewind-close" onclick="closeRewind()">✕</button>
    <div class="rewind-stage" id="rewindStage" onclick="_rewindTap(event)"></div>`;
  _rewindSpawnParticles(document.getElementById('rewindParticles'), 16);

  overlay.style.display = 'block';
  document.body.classList.add('architect-popup-open');
  _rewindRender();
}
window.showRewind = showRewind;

function _rewindSpawnParticles(host, n) {
  if (!host) return;
  let html = '';
  for (let i = 0; i < n; i++) {
    const left = Math.random() * 100;
    const size = 2 + Math.random() * 3;
    const dur = 6 + Math.random() * 7;
    const delay = -Math.random() * 12;
    html += `<div class="rewind-particle" style="left:${left}%;width:${size}px;height:${size}px;animation-duration:${dur}s;animation-delay:${delay}s;"></div>`;
  }
  host.innerHTML = html;
}

function _rewindRender() {
  const overlay = document.getElementById('rewindOverlay');
  const stage = document.getElementById('rewindStage');
  const barsEl = document.getElementById('rewindBars');
  if (!overlay || !stage) return;
  const slide = _rewindSlides[_rewindIndex];
  if (!slide) { closeRewind(); return; }

  // accent drives every ambient layer via CSS var on the root
  overlay.style.setProperty('--accent', slide.accent);

  if (barsEl) {
    barsEl.innerHTML = _rewindSlides.map((s, i) => {
      const cls = i < _rewindIndex ? 'done' : (i === _rewindIndex ? 'active' : '');
      return `<div class="rewind-bar ${cls}"><div class="rewind-bar-fill"></div></div>`;
    }).join('');
  }

  const isLast = _rewindIndex === _rewindSlides.length - 1;
  const dur = slide.type === 'card' ? 0 : (slide.type === 'intro' ? 3200 : 4500);

  // re-trigger entrance animation
  stage.classList.remove('rewind-slide-enter');
  void stage.offsetWidth;
  stage.innerHTML = _rewindSlideHtml(slide);
  stage.classList.add('rewind-slide-enter');

  // transition flash
  const flash = document.getElementById('rewindFlash');
  if (flash) { flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go'); }

  // count-up
  const bigEl = stage.querySelector('.rewind-big.is-count');
  if (bigEl && slide.count) _rewindCountUp(bigEl, slide.value, 1200, slide.suffix || '');

  // progress bar fill timer
  const activeFill = barsEl ? barsEl.querySelector('.rewind-bar.active .rewind-bar-fill') : null;
  if (activeFill && dur > 0) activeFill.style.animation = `rewindBarFill ${dur}ms linear forwards`;
  if (_rewindTimer) clearTimeout(_rewindTimer);
  if (dur > 0 && !isLast) _rewindTimer = setTimeout(() => _rewindNext(), dur);

  // stinger on the two "wow" moments: a legendary best-drop and the final card
  if (slide.key === 'card' || (slide.key === 'drop' && slide.dropRarity === 'legendary')) {
    _rewindPlayStinger();
  }

  try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}
}

function _rewindPlayStinger() {
  const audio = document.getElementById('rewindStingerAudio');
  if (!audio) return;
  try {
    audio.currentTime = 0;
    audio.volume = 0.55;
    const stopAt = setTimeout(() => { try { audio.pause(); } catch (e) {} }, 2500);
    audio.play().catch(() => clearTimeout(stopAt));
  } catch (e) {}
}

function _rewindHanziBg(key) {
  const meta = REWIND_SLIDE_META[key];
  return meta ? `<div class="rewind-hanzi-bg">${meta.hanzi}</div>` : '';
}

function _rewindIconHtml(key) {
  const meta = REWIND_SLIDE_META[key];
  return meta ? `<div class="rewind-icon"><i class="ti ${meta.icon}"></i></div>` : '';
}

function _rewindSlideHtml(slide) {
  if (slide.type === 'card') return _rewindHanziBg(slide.key) + _rewindCardHtml(slide.data);

  if (slide.type === 'role') {
    return `
      ${_rewindHanziBg(slide.key)}
      <div class="rewind-kicker">${escapeHtml(slide.kicker)}</div>
      <div class="rewind-role-badge"><i class="ti ${REWIND_SLIDE_META.role.icon}"></i></div>
      <div class="rewind-big text">${escapeHtml(slide.title)}</div>
      <div class="rewind-label">${escapeHtml(slide.subtitle)}</div>`;
  }

  if (slide.type === 'timeline') {
    const maxVal = Math.max(1, ...slide.timeline.map(t => t.value));
    const bars = slide.timeline.map(t => {
      const pct = Math.max(4, Math.round(100 * t.value / maxVal));
      return `
        <div class="rewind-tl-col">
          <div class="rewind-tl-val">${escapeHtml(String(t.value))}</div>
          <div class="rewind-tl-bar-wrap"><div class="rewind-tl-bar" style="height:${pct}%;"></div></div>
          <div class="rewind-tl-label">${escapeHtml(t.label)}</div>
        </div>`;
    }).join('');
    return `
      ${_rewindHanziBg(slide.key)}
      ${_rewindIconHtml(slide.key)}
      <div class="rewind-kicker">${escapeHtml(slide.kicker)}</div>
      <div class="rewind-timeline">${bars}</div>
      ${slide.sub ? `<div class="rewind-sub">${escapeHtml(slide.sub)}</div>` : ''}`;
  }

  const rays = slide.rays ? '<div class="rewind-rays"></div>' : '';
  const dropImg = slide.dropImage ? `<img class="rewind-drop-img" src="${escapeHtml(slide.dropImage)}" alt="" oncontextmenu="return false">` : '';
  const big = slide.count
    ? `<div class="rewind-big is-count">0${slide.suffix || ''}</div>`
    : `<div class="rewind-big ${slide.bigClass === 'text' ? 'text' : ''} ${dropImg ? 'with-img' : ''}">${escapeHtml(String(slide.big))}</div>`;

  return `
    ${_rewindHanziBg(slide.key)}
    ${_rewindIconHtml(slide.key)}
    <div class="rewind-kicker">${escapeHtml(slide.kicker)}</div>
    <div class="rewind-big-wrap">${rays}${dropImg}${big}</div>
    ${slide.label ? `<div class="rewind-label">${escapeHtml(slide.label)}</div>` : ''}
    ${slide.sub ? `<div class="rewind-sub">${escapeHtml(slide.sub)}</div>` : ''}`;
}

function _rewindCardHtml(d) {
  const row = (label, val) =>
    `<div class="rewind-card-row"><span>${escapeHtml(label)}</span><b>${escapeHtml(String(val))}</b></div>`;
  return `
    <div class="rewind-card">
      <div class="rewind-card-head">
        <div class="rewind-card-title">ZHIDAO REWIND</div>
        <div class="rewind-card-sub">${escapeHtml(d.date_range)}</div>
      </div>
      <div class="rewind-card-role">${escapeHtml(d.role ? d.role.title : '—')}</div>
      <div class="rewind-card-stats">
        ${row('Заработано', d.points_earned)}
        ${row('Кейсов открыто', d.cases_opened)}
        ${row('Дисциплина', d.attendance_pct + '%')}
        ${row('Спасений протокола', d.events_repelled)}
      </div>
      <div class="rewind-card-foot">智能电子解决方案</div>
    </div>
    <button class="rewind-share-btn" onclick="event.stopPropagation(); _rewindShareCard();"><i class="ti ti-download"></i> сохранить картинку</button>
    <div class="rewind-sub" style="margin-top:10px;">нажми мимо кнопки, чтобы закрыть</div>`;
}

function _rewindShareCard() {
  const cardSlide = _rewindSlides[_rewindSlides.length - 1];
  const d = cardSlide ? cardSlide.data : null;
  if (!d) return;
  const accent = '#00ff66';
  const w = 720, h = 1080;
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');

  const bg = ctx.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, '#0a0f0a');
  bg.addColorStop(1, '#040604');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = accent;
  ctx.lineWidth = 5;
  ctx.strokeRect(18, 18, w - 36, h - 36);

  ctx.textAlign = 'center';
  ctx.fillStyle = accent;
  ctx.font = '900 46px sans-serif';
  ctx.fillText('ZHIDAO REWIND', w / 2, 130);

  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.font = '24px sans-serif';
  ctx.fillText(d.date_range || '', w / 2, 170);

  ctx.fillStyle = '#ffffff';
  ctx.font = '900 34px sans-serif';
  ctx.fillText(d.role ? d.role.title : '—', w / 2, 260);

  const rows = [
    ['Заработано', d.points_earned],
    ['Кейсов открыто', d.cases_opened],
    ['Дисциплина', (d.attendance_pct || 0) + '%'],
    ['Спасений протокола', d.events_repelled]
  ];
  let y = 380;
  rows.forEach(([label, val]) => {
    ctx.textAlign = 'left';
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '26px sans-serif';
    ctx.fillText(label, 70, y);
    ctx.textAlign = 'right';
    ctx.fillStyle = accent;
    ctx.font = '900 30px sans-serif';
    ctx.fillText(String(val), w - 70, y);
    y += 90;
  });

  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.font = '18px sans-serif';
  ctx.fillText('智能电子解决方案', w / 2, h - 60);

  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'zhidao_rewind.png';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  });
}
window._rewindShareCard = _rewindShareCard;

function _rewindCountUp(el, to, dur, suffix) {
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(to * eased) + (suffix || '');
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function _rewindTap(e) {
  const stage = e.currentTarget;
  const rect = stage.getBoundingClientRect();
  const x = e.clientX - rect.left;
  if (x < rect.width * 0.28) _rewindPrev();
  else _rewindNext();
}

function _rewindNext() {
  if (_rewindIndex >= _rewindSlides.length - 1) { closeRewind(); return; }
  _rewindIndex++;
  _rewindRender();
}

function _rewindPrev() {
  if (_rewindIndex <= 0) return;
  _rewindIndex--;
  _rewindRender();
}

function closeRewind() {
  if (_rewindTimer) clearTimeout(_rewindTimer);
  const overlay = document.getElementById('rewindOverlay');
  if (overlay) { overlay.style.display = 'none'; overlay.innerHTML = ''; }
  document.body.classList.remove('architect-popup-open');
}
window.closeRewind = closeRewind;
