/**
 * ZHIDAO Protocol — Trip Rewind (Spotify-Wrapped-style end-of-trip summary)
 *
 * PROTOTYPE STATE (2026-06-21): runs on REWIND_DEMO_DATA so the visual can be
 * previewed before the backend exists. The backend endpoint
 * `/api/rewind/{telegram_id}` (read-only aggregation over existing tables, see
 * CLAUDE.md) will later replace the demo object via loadRewindData().
 *
 * Trigger: window.showRewind()  (currently console / temporary launch only).
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

// --- DEMO DATA (placeholder until /api/rewind/{telegram_id}) ---
const REWIND_DEMO_DATA = {
  name: 'ОПЕРАТОР',
  date_range: '01.07 — 14.07.2026',
  points_earned: 1840,
  points_spent: 1230,
  final_balance: 610,
  cases_opened: 27,
  best_drop: { name: 'КРАСНЫЙ ДРАКОН', rarity: 'legendary' },
  attendance_pct: 96,
  diary_entries: 11,
  diary_avg_stars: 4.3,
  events_repelled: 6,
  event_accuracy: 78,
  gifts_given: 3,
  role: {
    title: 'ЛЮБИМЕЦ РАНДОМА',
    subtitle: 'единственный, кто выбил легендарный имплант за поездку'
  }
};

let _rewindSlides = [];
let _rewindIndex = 0;
let _rewindTimer = null;

function _rewindBuildSlides(d) {
  const dropColor = REWIND_RARITY_COLOR[d.best_drop && d.best_drop.rarity] || '#00ff66';
  const dropLabel = REWIND_RARITY_LABEL[d.best_drop && d.best_drop.rarity] || '';
  return [
    { type: 'intro', accent: '#00ff66',
      kicker: 'ZHIDAO PROTOCOL', big: 'REWIND', bigClass: 'text',
      label: d.date_range, sub: 'твоя поездка в цифрах' },

    { type: 'stat', accent: '#00ff66',
      kicker: 'за эту поездку ты заработал', value: d.points_earned, count: true,
      label: '信用 баллов', sub: 'каждый — за реальное действие' },

    { type: 'stat', accent: '#ff4d6d',
      kicker: '…и не побоялся потратить', value: d.points_spent, count: true,
      label: 'баллов на кейсы, магазин и события' },

    { type: 'stat', accent: '#6aa0d4',
      kicker: 'ты открыл', value: d.cases_opened, count: true,
      label: 'кейсов и молитв', sub: 'азарт — это тоже стратегия' },

    { type: 'stat', accent: dropColor,
      kicker: 'твой лучший дроп', big: d.best_drop ? d.best_drop.name : '—', bigClass: 'text',
      label: dropLabel, sub: 'не каждому так везёт' },

    { type: 'stat', accent: '#00ff66',
      kicker: 'дисциплина отметок', value: d.attendance_pct, suffix: '%', count: true,
      label: 'ты почти не пропускал сбор', sub: 'Михаил Юрьевич это заметил' },

    { type: 'stat', accent: '#ffd24a',
      kicker: 'дневник оператора', value: d.diary_entries, count: true,
      label: 'записей сдано',
      sub: 'средняя оценка ' + (d.diary_avg_stars || 0).toFixed(1) + ' ★' },

    { type: 'stat', accent: '#00ff66',
      kicker: 'ты отражал атаки Архитектора и WildAI', value: d.events_repelled, count: true,
      label: 'раз спасал протокол',
      sub: 'точность ответов ' + (d.event_accuracy || 0) + '%' },

    { type: 'role', accent: '#00ff66',
      kicker: 'твоя роль в протоколе',
      title: d.role ? d.role.title : '—',
      subtitle: d.role ? d.role.subtitle : '' },

    { type: 'card', accent: '#00ff66', data: d }
  ];
}

function showRewind(data) {
  const d = data || REWIND_DEMO_DATA;
  _rewindSlides = _rewindBuildSlides(d);
  _rewindIndex = 0;
  const overlay = document.getElementById('rewindOverlay');
  if (!overlay) return;
  overlay.style.display = 'block';
  document.body.classList.add('architect-popup-open');
  _rewindRender();
}
window.showRewind = showRewind;

function _rewindRender() {
  const overlay = document.getElementById('rewindOverlay');
  if (!overlay) return;
  const slide = _rewindSlides[_rewindIndex];
  if (!slide) { closeRewind(); return; }

  const bars = _rewindSlides.map((s, i) => {
    const cls = i < _rewindIndex ? 'done' : (i === _rewindIndex ? 'active' : '');
    return `<div class="rewind-bar ${cls}"><div class="rewind-bar-fill"></div></div>`;
  }).join('');

  const isLast = _rewindIndex === _rewindSlides.length - 1;
  const dur = slide.type === 'card' ? 0 : (slide.type === 'intro' ? 3200 : 4500);

  overlay.innerHTML = `
    <div class="rewind-bg" style="--accent:${slide.accent}"></div>
    <div class="rewind-bars">${bars}</div>
    <button class="rewind-close" onclick="closeRewind()">✕</button>
    <div class="rewind-stage rewind-slide-enter" style="--accent:${slide.accent};--dur:${dur}ms"
         onclick="_rewindTap(event)">
      ${_rewindSlideHtml(slide)}
    </div>`;

  // start count-up + bar timer
  const bigEl = overlay.querySelector('.rewind-big.is-count');
  if (bigEl && slide.count) {
    _rewindCountUp(bigEl, slide.value, 1100, slide.suffix || '');
  }
  const activeFill = overlay.querySelector('.rewind-bar.active .rewind-bar-fill');
  if (activeFill && dur > 0) {
    activeFill.style.animation = `rewindBarFill ${dur}ms linear forwards`;
  }
  if (_rewindTimer) clearTimeout(_rewindTimer);
  if (dur > 0 && !isLast) {
    _rewindTimer = setTimeout(() => _rewindNext(), dur);
  }
  try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}
}

function _rewindSlideHtml(slide) {
  if (slide.type === 'card') return _rewindCardHtml(slide.data);

  if (slide.type === 'role') {
    return `
      <div class="rewind-kicker">${escapeHtml(slide.kicker)}</div>
      <div class="rewind-role-badge">★</div>
      <div class="rewind-big text">${escapeHtml(slide.title)}</div>
      <div class="rewind-label">${escapeHtml(slide.subtitle)}</div>`;
  }

  const big = slide.count
    ? `<div class="rewind-big is-count">0${slide.suffix || ''}</div>`
    : `<div class="rewind-big ${slide.bigClass === 'text' ? 'text' : ''}">${escapeHtml(String(slide.big))}</div>`;

  return `
    <div class="rewind-kicker">${escapeHtml(slide.kicker)}</div>
    ${big}
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
      <div class="rewind-card-foot">智能电子解决方案 · сделай скриншот ↗</div>
    </div>
    <div class="rewind-sub" style="margin-top:18px;">нажми, чтобы закрыть</div>`;
}

function _rewindCountUp(el, to, dur, suffix) {
  const start = performance.now();
  const from = 0;
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    const val = Math.round(from + (to - from) * eased);
    el.textContent = val + (suffix || '');
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
