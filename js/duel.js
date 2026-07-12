// ===== PvP ДУЭЛИ (Tekken-style live quiz battle) =====
// Async challenge -> accept -> ready-check -> live polled rounds.
// Admin/flag-gated on the backend (DUELS_PUBLIC=False); the UI tab is also
// admin-only via CSS (body.is-admin .duel-tab-btn).

let duelOpponents = [];
let duelOpponentsMessage = '';
let duelSelectedStake = 25;
let duelPollTimer = null;       // polls /state while overlay is open
let duelTimerInterval = null;   // local 1s countdown ticker
let duelCurrentId = null;
let duelLastQuestionId = null;
let duelAnsweredThisRound = false;
let duelSelectedAnswer = null;

// --- Tekken-style анимации: отслеживаем предыдущее состояние между рендерами ---
let duelPrevYouHp = null;
let duelPrevOppHp = null;
let duelPrevStatus = null;
let duelPrevRound = null;
let duelFinishShown = false;
let duelRoundIntroKey = null;
let duelAnnounceTimers = [];
let duelComboCount = 0;      // серия ударов подряд по сопернику (комбо)

const DUEL_STAKES = [10, 25, 50, 100];
const DUEL_GROUP_LABELS = {
  A0: '1班 · A0',
  'A普': '2班 · A普',
  'A+': '3班 · A+',
  'B普': '4班 · B普',
  SUPER: '5班 · SUPER',
};

function duelStudyGroupLabel(value) {
  if (!value) return '';
  const code = typeof value === 'object' ? String(value.code || '').trim() : String(value || '').trim();
  if (!code) return '';
  if (typeof value === 'object' && value.label) return String(value.label);
  return DUEL_GROUP_LABELS[code] || code;
}

function duelHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (typeof currentUserId !== 'undefined' && currentUserId) h['X-Telegram-Id'] = String(currentUserId);
  return h;
}

// ---------- Хаб ----------
async function loadDuelHub() {
  loadDuelLeaderboard();
  await refreshDuelHubStatus(true);
}

async function refreshDuelHubStatus(allowAutoOpen) {
  const statusWrap = document.getElementById('duelStatusWrap');
  const incomingWrap = document.getElementById('duelIncomingWrap');
  if (!statusWrap || !incomingWrap) return;
  try {
    const [curR, incR] = await Promise.all([
      fetch(`${API_URL}/api/duel/current/${currentUserId}`, { headers: duelHeaders() }),
      fetch(`${API_URL}/api/duel/incoming/${currentUserId}`, { headers: duelHeaders() })
    ]);
    const cur = curR.ok ? await curR.json() : {};
    const inc = incR.ok ? await incR.json() : { challenges: [] };

    // Активная дуэль (accepted/ready/active) — кнопка войти в бой
    if (cur.active_duel_id) {
      statusWrap.innerHTML =
        `<div class="duel-card duel-card-live">
           <div class="duel-card-title">⚔ У тебя активная дуэль</div>
           <button class="btn btn-primary" onclick="openDuelOverlay(${cur.active_duel_id})">ВОЙТИ В БОЙ</button>
         </div>`;
      // Автооткрытие боя только при заходе на вкладку (не после ручного закрытия)
      if (allowAutoOpen) openDuelOverlay(cur.active_duel_id);
    } else if (cur.pending_sent) {
      statusWrap.innerHTML =
        `<div class="duel-card">
           <div class="duel-card-title">⏳ Вызов отправлен (${cur.pending_sent.stake}★)</div>
           <div class="duel-card-sub">Ждём ответа соперника…</div>
           <button class="btn duel-btn-secondary" onclick="cancelDuel(${cur.pending_sent.duel_id})">Отменить вызов</button>
         </div>`;
    } else {
      statusWrap.innerHTML = '';
    }

    // Входящие вызовы
    const list = inc.challenges || [];
    if (list.length) {
      incomingWrap.innerHTML =
        `<div class="cn-divider">📥 ВХОДЯЩИЕ ВЫЗОВЫ</div>` +
        list.map(ch => {
          const groupLabel = duelStudyGroupLabel(ch.study_group);
          return `<div class="duel-card">
             <div class="duel-card-title">${escapeDuel(ch.challenger_name)} вызывает тебя</div>
             <div class="duel-card-sub">Ставка: ${ch.stake}★${groupLabel ? ` · ${escapeDuel(groupLabel)}` : ''}</div>
             <div class="duel-card-actions">
               <button class="btn btn-primary" onclick="acceptDuel(${ch.duel_id})">Принять</button>
               <button class="btn duel-btn-secondary" onclick="declineDuel(${ch.duel_id})">Отклонить</button>
             </div>
           </div>`;
        }).join('');
    } else {
      incomingWrap.innerHTML = '';
    }
  } catch (e) {
    statusWrap.innerHTML = '';
  }
}

async function loadDuelLeaderboard() {
  const el = document.getElementById('duelLeaderboard');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const r = await fetch(`${API_URL}/api/duel/leaderboard`, { headers: duelHeaders() });
    const data = r.ok ? await r.json() : { leaderboard: [] };
    const board = data.leaderboard || [];
    if (!board.length) {
      el.innerHTML = '<div class="empty-state">Пока никто не дрался. Будь первым ⚔</div>';
      return;
    }
    el.innerHTML = board.map((p, i) =>
      `<div class="duel-lb-row">
         <div class="duel-lb-rank">${i + 1}</div>
         <div class="duel-lb-name">${escapeDuel(p.name)}</div>
         <div class="duel-lb-record"><span class="duel-w">${p.wins}</span>/<span class="duel-l">${p.losses}</span></div>
       </div>`
    ).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

// ---------- Вызов соперника ----------
async function openDuelChallenge() {
  const modal = document.getElementById('duelChallengeModal');
  if (!modal) return;
  duelSelectedStake = 25;
  renderDuelStakeRow();
  modal.classList.add('show');
  const listEl = document.getElementById('duelOpponentList');
  listEl.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const r = await fetch(`${API_URL}/api/duel/opponents/${currentUserId}`, { headers: duelHeaders() });
    const data = r.ok ? await r.json() : { opponents: [] };
    duelOpponents = data.opponents || [];
    duelOpponentsMessage = data.message || '';
    renderDuelOpponentList();
  } catch (e) {
    duelOpponentsMessage = '';
    listEl.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

function closeDuelChallenge() {
  const modal = document.getElementById('duelChallengeModal');
  if (modal) modal.classList.remove('show');
}

function renderDuelStakeRow() {
  const row = document.getElementById('duelStakeRow');
  if (!row) return;
  row.innerHTML = DUEL_STAKES.map(s =>
    `<button class="duel-stake-btn ${s === duelSelectedStake ? 'active' : ''}" onclick="selectDuelStake(${s})">${s}★</button>`
  ).join('');
}

function selectDuelStake(s) {
  duelSelectedStake = s;
  renderDuelStakeRow();
}

function renderDuelOpponentList() {
  const listEl = document.getElementById('duelOpponentList');
  if (!listEl) return;
  const q = (document.getElementById('duelOpponentSearch')?.value || '').trim().toLowerCase();
  const filtered = duelOpponents.filter(o => !q || (o.name || '').toLowerCase().includes(q));
  if (!filtered.length) {
    listEl.innerHTML = `<div class="empty-state">${escapeDuel(duelOpponentsMessage || 'Никого не найдено')}</div>`;
    return;
  }
  listEl.innerHTML = filtered.map(o => {
    const groupLabel = duelStudyGroupLabel(o.study_group);
    return `<div class="duel-opp-row" onclick="confirmDuelChallenge(${o.telegram_id})">
       <div class="duel-opp-name">${escapeDuel(o.name)}</div>
       <div class="duel-opp-rep">${groupLabel ? `${escapeDuel(groupLabel)} · ` : ''}${o.rep}★</div>
     </div>`;
  }).join('');
}

async function confirmDuelChallenge(opponentId) {
  const opp = duelOpponents.find(o => o.telegram_id === opponentId);
  const name = opp ? opp.name : 'соперника';
  if (typeof showConfirmDialog === 'function') {
    const ok = await showConfirmDialog({
      title: '⚔ Вызов на дуэль',
      message: `Вызвать ${name} на дуэль со ставкой ${duelSelectedStake}★?`,
      confirmText: 'Вызвать'
    });
    if (!ok) return;
  }
  sendDuelChallenge(opponentId);
}

async function sendDuelChallenge(opponentId) {
  try {
    const r = await fetch(`${API_URL}/api/duel/challenge`, {
      method: 'POST',
      headers: duelHeaders(),
      body: JSON.stringify({ challenger_id: currentUserId, opponent_id: opponentId, stake: duelSelectedStake })
    });
    if (r.ok) {
      closeDuelChallenge();
      showToast('⚔ Вызов отправлен!');
      refreshDuelHubStatus();
    } else {
      const d = await r.json().catch(() => ({}));
      showToast(d.detail || 'Не удалось отправить вызов');
    }
  } catch (e) {
    showToast('Нет соединения');
  }
}

// ---------- Принять / отклонить / отменить ----------
async function acceptDuel(duelId) {
  await duelAction(duelId, 'accept', '✅ Вызов принят! Жми «Готов».');
}
async function declineDuel(duelId) {
  await duelAction(duelId, 'decline', 'Вызов отклонён');
}
async function cancelDuel(duelId) {
  await duelAction(duelId, 'cancel', 'Вызов отменён');
}

async function duelAction(duelId, action, okMsg) {
  try {
    const r = await fetch(`${API_URL}/api/duel/${duelId}/${action}`, {
      method: 'POST',
      headers: duelHeaders(),
      body: JSON.stringify({ telegram_id: currentUserId })
    });
    if (r.ok) {
      if (okMsg) showToast(okMsg);
      if (action === 'accept') {
        openDuelOverlay(duelId);
      } else if (duelCurrentId === duelId) {
        closeDuelOverlay();
      } else {
        refreshDuelHubStatus();
      }
    } else {
      const d = await r.json().catch(() => ({}));
      showToast(d.detail || 'Ошибка');
      refreshDuelHubStatus();
    }
  } catch (e) {
    showToast('Нет соединения');
  }
}

// ---------- Полноэкранный бой ----------
function openDuelOverlay(duelId) {
  duelCurrentId = duelId;
  duelLastQuestionId = null;
  duelAnsweredThisRound = false;
  duelSelectedAnswer = null;
  duelPrevYouHp = null;
  duelPrevOppHp = null;
  duelPrevStatus = null;
  duelPrevRound = null;
  duelFinishShown = false;
  duelRoundIntroKey = null;
  duelComboCount = 0;
  clearDuelAnnounceQueue();
  const ov = document.getElementById('duel-overlay');
  if (ov) {
    ov.classList.remove('duel-finish-win', 'duel-finish-lose', 'duel-finish-draw', 'duel-hitstop');
    ov.classList.add('show');
  }
  startDuelPolling();
}

function closeDuelOverlay() {
  stopDuelPolling();
  duelCurrentId = null;
  const ov = document.getElementById('duel-overlay');
  if (ov) ov.classList.remove('show');
  refreshDuelHubStatus();
  loadDuelLeaderboard();
}

function startDuelPolling() {
  stopDuelPolling();
  pollDuelState();
  duelPollTimer = setInterval(pollDuelState, 1200);
}

function stopDuelPolling() {
  if (duelPollTimer) { clearInterval(duelPollTimer); duelPollTimer = null; }
  if (duelTimerInterval) { clearInterval(duelTimerInterval); duelTimerInterval = null; }
}

async function pollDuelState() {
  if (!duelCurrentId) return;
  try {
    const r = await fetch(`${API_URL}/api/duel/${duelCurrentId}/state?telegram_id=${currentUserId}`, { headers: duelHeaders() });
    if (!r.ok) return;
    const st = await r.json();
    renderDuelState(st);
  } catch (e) { /* keep polling */ }
}

function renderDuelState(st) {
  if (!st || !st.exists) return;
  const youName = document.getElementById('duelYouName');
  const oppName = document.getElementById('duelOppName');
  const youAv = document.getElementById('duelYouAvatar');
  const oppAv = document.getElementById('duelOppAvatar');
  const oppNm = (st.opponent && st.opponent.name) || 'СОПЕРНИК';
  if (oppName) oppName.textContent = oppNm;
  setDuelAvatar(oppAv, st.opponent && st.opponent.avatar_url, oppNm);
  if (youName) youName.textContent = 'ТЫ';
  setDuelAvatar(youAv, st.you && st.you.avatar_url, (st.you && st.you.name) || 'Я');
  const ov = document.getElementById('duel-overlay');

  const maxHp = st.max_hp || 100;
  const youHp = st.you ? st.you.hp : maxHp;
  const oppHp = st.opponent ? st.opponent.hp : maxHp;

  // --- Анонсы: смена статуса/раунда (ROUND / FINAL ROUND / FIGHT) ---
  if (st.status === 'active') {
    const introKey = `${st.id || duelCurrentId}:${st.round_no}`;
    if (duelPrevStatus !== 'active' || introKey !== duelRoundIntroKey) {
      duelRoundIntroKey = introKey;
      playDuelRoundIntro(st.round_no, st.max_rounds);
    }
    duelPrevRound = st.round_no;
  }

  // --- Детект урона: HP упал => удар попал. Анимируем ту сторону, кому досталось. ---
  if (duelPrevOppHp !== null && oppHp < duelPrevOppHp) {
    triggerDuelHit('opp', duelPrevOppHp - oppHp, oppHp <= 0);
  }
  if (duelPrevYouHp !== null && youHp < duelPrevYouHp) {
    triggerDuelHit('you', duelPrevYouHp - youHp, youHp <= 0);
  }
  duelPrevYouHp = youHp;
  duelPrevOppHp = oppHp;
  duelPrevStatus = st.status;

  setDuelHp('duelYouHp', 'duelYouHpText', youHp, maxHp);
  setDuelHp('duelOppHp', 'duelOppHpText', oppHp, maxHp);
  setDuelFighterCritical('duelYouFighter', youHp, maxHp);
  setDuelFighterCritical('duelOppFighter', oppHp, maxHp);

  const roundLabel = document.getElementById('duelRoundLabel');
  const timer = document.getElementById('duelTimer');
  const qEl = document.getElementById('duelQuestion');
  const aEl = document.getElementById('duelAnswers');
  const statusLine = document.getElementById('duelStatusLine');

  if (st.status === 'accepted' || st.status === 'ready') {
    if (roundLabel) roundLabel.textContent = 'Подготовка';
    if (timer) timer.textContent = '';
    if (qEl) qEl.innerHTML = '';
    const youReady = st.you && st.you.ready;
    const oppReady = st.opponent && st.opponent.ready;
    if (aEl) {
      aEl.innerHTML = youReady
        ? `<div class="duel-ready-wait">Ты готов. Ждём соперника…</div>
           <button class="btn duel-btn-secondary duel-ready-btn" onclick="declineDuel(${duelCurrentId})">ОТКАЗАТЬСЯ</button>`
        : `<button class="btn btn-primary duel-ready-btn" onclick="readyDuel()">Я ГОТОВ</button>
           <button class="btn duel-btn-secondary duel-ready-btn" onclick="declineDuel(${duelCurrentId})">ОТКАЗАТЬСЯ</button>`;
    }
    if (statusLine) statusLine.textContent = `Соперник: ${oppReady ? 'готов ✅' : 'ещё не готов…'}`;
    if (duelTimerInterval) { clearInterval(duelTimerInterval); duelTimerInterval = null; }
    return;
  }

  if (st.status === 'active') {
    if (roundLabel) roundLabel.textContent = `Раунд ${st.round_no} / ${st.max_rounds}`;
    // Новый раунд -> сбросить состояние ответа
    const qid = st.question ? st.question.id : null;
    if (qid !== duelLastQuestionId) {
      duelLastQuestionId = qid;
      duelAnsweredThisRound = false;
      duelSelectedAnswer = null;
    }
    if (st.you && st.you.answered) duelAnsweredThisRound = true;

    if (qEl && st.question) qEl.textContent = st.question.prompt;
    if (aEl && st.question) {
      const opts = st.question.options || {};
      const locked = duelAnsweredThisRound;
      aEl.innerHTML = ['a', 'b', 'c'].map(k =>
        `<button class="duel-answer-btn ${duelSelectedAnswer === k ? 'duel-answer-selected' : ''}" ${locked ? 'disabled' : ''} onclick="submitDuelAnswer('${k}')">${escapeDuel(opts[k] || '')}</button>`
      ).join('');
    }
    if (statusLine) {
      const oppAns = st.opponent && st.opponent.answered;
      statusLine.textContent = duelAnsweredThisRound
        ? (oppAns ? 'Оба ответили — раунд считается…' : 'Ответ принят. Ждём соперника…')
        : (oppAns ? '⚠ Соперник уже ответил! Быстрее!' : 'Отвечай первым, чтобы ударить!');
    }
    startDuelCountdown(st.seconds_left);
    return;
  }

  if (st.status === 'finished') {
    if (duelTimerInterval) { clearInterval(duelTimerInterval); duelTimerInterval = null; }
    if (duelPollTimer) { clearInterval(duelPollTimer); duelPollTimer = null; }
    clearDuelAnnounceQueue();
    if (roundLabel) roundLabel.textContent = 'Бой окончен';
    if (timer) timer.textContent = '';
    // Финишер: K.O.-вспышка + баннер один раз
    if (!duelFinishShown) {
      duelFinishShown = true;
      if (!st.draw) {
        if (ov) ov.classList.add(st.you_won ? 'duel-finish-win' : 'duel-finish-lose');
        flashDuelScreen('strong');
        try { tg.HapticFeedback.notificationOccurred(st.you_won ? 'success' : 'error'); } catch (e) {}
        announceDuel('K.O.', 'duel-announce-ko');
        const winnerHp = st.you_won ? youHp : oppHp;
        if (winnerHp >= maxHp) queueDuelAnnouncement('PERFECT', 'duel-announce-perfect', 950);
      } else {
        if (ov) ov.classList.add('duel-finish-draw');
        announceDuel('НИЧЬЯ', '');
      }
    }
    if (qEl) {
      qEl.innerHTML = st.draw
        ? `<div class="duel-result duel-result-draw">НИЧЬЯ</div>`
        : (st.you_won
            ? `<div class="duel-result duel-result-win">ПОБЕДА! +${st.stake}★</div>`
            : `<div class="duel-result duel-result-lose">ПОРАЖЕНИЕ −${st.stake}★</div>`);
    }
    if (aEl) aEl.innerHTML = `<button class="btn btn-primary" onclick="closeDuelOverlay()">ЗАКРЫТЬ</button>`;
    if (statusLine) statusLine.textContent = '';
    return;
  }

  // declined/cancelled/expired
  if (qEl) qEl.innerHTML = `<div class="duel-result">Дуэль завершена</div>`;
  if (aEl) aEl.innerHTML = `<button class="btn btn-primary" onclick="closeDuelOverlay()">ЗАКРЫТЬ</button>`;
  if (duelPollTimer) { clearInterval(duelPollTimer); duelPollTimer = null; }
}

function setDuelHp(fillId, textId, hp, maxHp) {
  const fill = document.getElementById(fillId);
  const txt = document.getElementById(textId);
  const pct = Math.max(0, Math.min(100, Math.round((hp / maxHp) * 100)));
  if (fill) {
    fill.style.width = pct + '%';
    fill.classList.toggle('duel-hp-low', pct <= 34);
    // «Призрачный» chip-бар: жёлтая полоса за основной, оседает с задержкой —
    // фирменный приём файтингов (видно, сколько урона только что прошло).
    const ghost = document.getElementById(fillId + 'Ghost');
    if (ghost) ghost.style.width = pct + '%';
  }
  if (txt) txt.textContent = hp;
}

function setDuelFighterCritical(fighterId, hp, maxHp) {
  const fighter = document.getElementById(fighterId);
  if (!fighter) return;
  const pct = maxHp ? (hp / maxHp) * 100 : 100;
  fighter.classList.toggle('duel-fighter-critical', pct > 0 && pct <= 34);
  fighter.classList.toggle('duel-fighter-ko', hp <= 0);
}

function startDuelCountdown(secondsLeft) {
  if (duelTimerInterval) { clearInterval(duelTimerInterval); duelTimerInterval = null; }
  let left = (typeof secondsLeft === 'number') ? secondsLeft : null;
  const timer = document.getElementById('duelTimer');
  const paint = () => {
    if (!timer) return;
    if (left === null) { timer.textContent = ''; return; }
    timer.textContent = left + 'с';
    timer.classList.toggle('duel-timer-urgent', left <= 5);
  };
  paint();
  if (left === null) return;
  duelTimerInterval = setInterval(() => {
    left = Math.max(0, left - 1);
    paint();
    if (left <= 0 && duelTimerInterval) { clearInterval(duelTimerInterval); duelTimerInterval = null; }
  }, 1000);
}

async function readyDuel() {
  if (!duelCurrentId) return;
  try {
    const r = await fetch(`${API_URL}/api/duel/${duelCurrentId}/ready`, {
      method: 'POST',
      headers: duelHeaders(),
      body: JSON.stringify({ telegram_id: currentUserId })
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      showToast(d.detail || 'Ошибка');
    }
    pollDuelState();
  } catch (e) {
    showToast('Нет соединения');
  }
}

async function submitDuelAnswer(option) {
  if (!duelCurrentId || duelAnsweredThisRound) return;
  duelAnsweredThisRound = true; // оптимистично — блокируем повторный тап
  duelSelectedAnswer = option;
  // блокируем кнопки сразу
  document.querySelectorAll('#duelAnswers .duel-answer-btn').forEach(b => {
    if (b.getAttribute('onclick') && b.getAttribute('onclick').includes(`'${option}'`)) {
      b.classList.add('duel-answer-selected');
    }
    b.disabled = true;
  });
  const statusLine = document.getElementById('duelStatusLine');
  if (statusLine) statusLine.textContent = 'INPUT LOCKED // ждём результат...';
  try {
    const r = await fetch(`${API_URL}/api/duel/${duelCurrentId}/answer`, {
      method: 'POST',
      headers: duelHeaders(),
      body: JSON.stringify({ telegram_id: currentUserId, option, question_id: duelLastQuestionId })
    });
    if (r.ok) {
      const st = await r.json();
      renderDuelState(st);
    } else {
      const d = await r.json().catch(() => ({}));
      showToast(d.detail || 'Ошибка ответа');
      duelAnsweredThisRound = false;
      duelSelectedAnswer = null;
      document.querySelectorAll('#duelAnswers .duel-answer-btn').forEach(b => {
        b.disabled = false;
        b.classList.remove('duel-answer-selected');
      });
    }
  } catch (e) {
    showToast('Нет соединения');
    duelAnsweredThisRound = false;
    duelSelectedAnswer = null;
    document.querySelectorAll('#duelAnswers .duel-answer-btn').forEach(b => {
      b.disabled = false;
      b.classList.remove('duel-answer-selected');
    });
  }
}

// ---------- Tekken-style анимации ----------
// Аватар: если есть картинка — показываем её фоном, иначе первую букву имени.
function setDuelAvatar(el, avatarUrl, name) {
  if (!el) return;
  if (avatarUrl) {
    if (el.dataset.avatarUrl !== avatarUrl) {
      el.dataset.avatarUrl = avatarUrl;
      el.style.backgroundImage = `url('${String(avatarUrl).replace(/'/g, "%27")}')`;
      el.classList.add('duel-avatar-img');
      el.textContent = '';
    }
  } else {
    if (el.dataset.avatarUrl) {
      el.dataset.avatarUrl = '';
      el.style.backgroundImage = '';
      el.classList.remove('duel-avatar-img');
    }
    el.textContent = ((name || '?')[0] || '?').toUpperCase();
  }
}

// Удар попал: тряска экрана, вспышка, всплывающее число урона, дрожь аватара.
function triggerDuelHit(side, dmg, isKo) {
  const ov = document.getElementById('duel-overlay');
  const avatar = document.getElementById(side === 'opp' ? 'duelOppAvatar' : 'duelYouAvatar');
  const striker = document.getElementById(side === 'opp' ? 'duelYouAvatar' : 'duelOppAvatar');
  const dmgEl = document.getElementById(side === 'opp' ? 'duelOppDmg' : 'duelYouDmg');
  const hitWord = isKo ? 'K.O.' : 'CLEAN HIT';

  applyDuelHitStop(isKo ? 190 : 120);
  flashDuelScreen('hit');
  if (ov) {
    ov.classList.remove('duel-shake');
    void ov.offsetWidth; // рестарт анимации
    ov.classList.add('duel-shake');
    setTimeout(() => ov.classList.remove('duel-shake'), 420);
  }
  if (striker) {
    striker.classList.remove('duel-avatar-strike', 'duel-avatar-strike-you', 'duel-avatar-strike-opp');
    void striker.offsetWidth;
    striker.classList.add('duel-avatar-strike', side === 'opp' ? 'duel-avatar-strike-you' : 'duel-avatar-strike-opp');
    setTimeout(() => striker.classList.remove('duel-avatar-strike', 'duel-avatar-strike-you', 'duel-avatar-strike-opp'), 360);
  }
  if (avatar) {
    avatar.classList.remove('duel-avatar-hit');
    void avatar.offsetWidth;
    avatar.classList.add('duel-avatar-hit');
    setTimeout(() => avatar.classList.remove('duel-avatar-hit'), 500);
  }
  if (dmgEl && dmg > 0) {
    dmgEl.innerHTML = `<span>${hitWord}</span><strong>-${dmg}</strong>`;
    dmgEl.classList.remove('duel-dmg-show');
    void dmgEl.offsetWidth;
    dmgEl.classList.add('duel-dmg-show');
    setTimeout(() => { dmgEl.classList.remove('duel-dmg-show'); dmgEl.textContent = ''; }, 900);
  }
  spawnDuelSparks(side);
  // Комбо: серия ударов по сопернику подряд. Получил сам — серия сбрасывается.
  if (side === 'opp') {
    duelComboCount += 1;
    if (duelComboCount >= 2 && !isKo) showDuelCombo(duelComboCount);
  } else {
    duelComboCount = 0;
  }
  try { tg.HapticFeedback.impactOccurred(side === 'opp' ? 'heavy' : 'medium'); } catch (e) {}
}

function showDuelCombo(n) {
  const el = document.getElementById('duelCombo');
  if (!el) return;
  el.innerHTML = `<strong>${n}</strong><span>COMBO</span>`;
  el.classList.remove('duel-combo-show');
  void el.offsetWidth;
  el.classList.add('duel-combo-show');
  clearTimeout(el._hideTimer);
  el._hideTimer = setTimeout(() => el.classList.remove('duel-combo-show'), 1200);
}

function applyDuelHitStop(ms) {
  const ov = document.getElementById('duel-overlay');
  if (!ov) return;
  ov.classList.remove('duel-hitstop');
  void ov.offsetWidth;
  ov.classList.add('duel-hitstop');
  clearTimeout(ov._hitStopTimer);
  ov._hitStopTimer = setTimeout(() => ov.classList.remove('duel-hitstop'), ms || 120);
}

function spawnDuelSparks(side) {
  const ov = document.getElementById('duel-overlay');
  if (!ov) return;
  const burst = document.createElement('div');
  burst.className = `duel-spark-burst duel-spark-${side}`;
  for (let i = 0; i < 10; i += 1) {
    const spark = document.createElement('i');
    const angle = (Math.PI * 2 * i) / 10;
    const dist = 34 + (i % 4) * 10;
    spark.style.setProperty('--dx', `${Math.cos(angle) * dist}px`);
    spark.style.setProperty('--dy', `${Math.sin(angle) * dist}px`);
    spark.style.setProperty('--rot', `${angle}rad`);
    burst.appendChild(spark);
  }
  ov.appendChild(burst);
  setTimeout(() => burst.remove(), 620);
}

// Кратковременная вспышка экрана: 'hit' слабее, 'strong' для финишера.
function flashDuelScreen(kind) {
  const flash = document.getElementById('duelFlash');
  if (!flash) return;
  flash.classList.remove('duel-flash-hit', 'duel-flash-strong');
  void flash.offsetWidth;
  flash.classList.add(kind === 'strong' ? 'duel-flash-strong' : 'duel-flash-hit');
  setTimeout(() => flash.classList.remove('duel-flash-hit', 'duel-flash-strong'),
    kind === 'strong' ? 650 : 320);
}

function playDuelRoundIntro(roundNo, maxRounds) {
  clearDuelAnnounceQueue();
  const isFinal = maxRounds && roundNo >= maxRounds;
  announceDuel(isFinal ? 'FINAL ROUND' : 'ROUND ' + roundNo, isFinal ? 'duel-announce-final' : '');
  queueDuelAnnouncement('FIGHT!', 'duel-announce-fight', 760);
}

function queueDuelAnnouncement(text, cls, delay) {
  const t = setTimeout(() => announceDuel(text, cls), delay || 0);
  duelAnnounceTimers.push(t);
}

function clearDuelAnnounceQueue() {
  duelAnnounceTimers.forEach(t => clearTimeout(t));
  duelAnnounceTimers = [];
}

// Большой баннер по центру (БОЙ! / РАУНД X / K.O.).
function announceDuel(text, cls) {
  const el = document.getElementById('duelAnnounce');
  if (!el) return;
  el.className = 'duel-announce';
  el.textContent = text;
  void el.offsetWidth;
  el.classList.add('duel-announce-show');
  if (cls) el.classList.add(cls);
  clearTimeout(el._hideTimer);
  el._hideTimer = setTimeout(() => el.classList.remove('duel-announce-show'),
    cls === 'duel-announce-ko' ? 1600 : 1100);
}

// ---------- утилиты ----------
function escapeDuel(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
