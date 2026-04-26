const ARCHITECT_PHASE_IMAGES = {
  1: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase1.png',
  2: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase2.png',
  3: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase3.png'
};

const ARCHITECT_TERMINAL_IMAGES = {
  FINISHED: 'architect_ivent_win.png',
  FAILED: 'architect_ivent_lose.png'
};

const ARCHITECT_PHASE_VIDEOS = {
  1: 'architect_phase1.mp4',
  2: 'architect_phase2.mp4',
  3: 'architect_phase3.mp4'
};

const ARCHITECT_PHASE_MUSIC = {
  1: 'architect_phase1_music.mp3',
  2: 'architect_phase2_music.mp3',
  3: 'architect_phase3_music.mp3'
};

const ARCHITECT_MUSIC_TARGET_VOLUME = 0.58;
const ARCHITECT_MUSIC_FADE_MS = 1400;
let architectMusicUnlocked = false;
let architectMusicCurrentTrack = '';
let architectMusicActiveDeck = 'a';
let architectMusicFadeFrame = null;
let architectLastRenderedPhase = null;
let architectActionFxTimer = null;
let architectPhaseFxTimer = null;
let architectFinalTimerHandle = null;
let architectQuestionAutoCloseTimer = null;
const ARCHITECT_ANSWER_FEEDBACK_MS = 1800;

function getArchitectPhaseImage(eventData) {
  if (!eventData) return ARCHITECT_PHASE_IMAGES[1];
  const state = String(eventData.state || '').toUpperCase();
  if (ARCHITECT_TERMINAL_IMAGES[state]) return ARCHITECT_TERMINAL_IMAGES[state];
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return ARCHITECT_PHASE_IMAGES[2];
  if (phase >= 3) return ARCHITECT_PHASE_IMAGES[3];
  return ARCHITECT_PHASE_IMAGES[1];
}

function getArchitectPhaseVideo(eventData) {
  if (!eventData) return '';
  const state = String(eventData.state || '').toUpperCase();
  if (state === 'FINISHED' || state === 'FAILED') return '';
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return ARCHITECT_PHASE_VIDEOS[2] || '';
  if (phase >= 3) return ARCHITECT_PHASE_VIDEOS[3] || '';
  return ARCHITECT_PHASE_VIDEOS[1] || '';
}

function getArchitectPhaseMusic(eventData) {
  if (!eventData) return '';
  if (String(eventData.state || '').toUpperCase() !== 'ACTIVE') return '';
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return ARCHITECT_PHASE_MUSIC[2] || '';
  if (phase >= 3) return ARCHITECT_PHASE_MUSIC[3] || '';
  return ARCHITECT_PHASE_MUSIC[1] || '';
}

function getArchitectMusicPlayers() {
  return {
    a: document.getElementById('architectMusicA'),
    b: document.getElementById('architectMusicB')
  };
}

function stopArchitectMusicFade() {
  if (architectMusicFadeFrame) {
    cancelAnimationFrame(architectMusicFadeFrame);
    architectMusicFadeFrame = null;
  }
}

function fadeArchitectMusic(fromAudio, toAudio, targetVolume = ARCHITECT_MUSIC_TARGET_VOLUME, duration = ARCHITECT_MUSIC_FADE_MS) {
  stopArchitectMusicFade();

  const fromStart = fromAudio ? Number(fromAudio.volume || 0) : 0;
  const toStart = toAudio ? Number(toAudio.volume || 0) : 0;
  const startedAt = performance.now();

  function tick(now) {
    const progress = Math.min(1, (now - startedAt) / duration);

    if (fromAudio) {
      fromAudio.volume = Math.max(0, fromStart * (1 - progress));
    }

    if (toAudio) {
      toAudio.volume = Math.min(targetVolume, toStart + (targetVolume - toStart) * progress);
    }

    if (progress < 1) {
      architectMusicFadeFrame = requestAnimationFrame(tick);
      return;
    }

    if (fromAudio) {
      fromAudio.volume = 0;
      try {
        fromAudio.pause();
        fromAudio.currentTime = 0;
      } catch (e) {}
    }

    if (toAudio) {
      toAudio.volume = targetVolume;
    }

    architectMusicFadeFrame = null;
  }

  architectMusicFadeFrame = requestAnimationFrame(tick);
}

function stopArchitectMusic(immediate = false) {
  const players = getArchitectMusicPlayers();
  const allPlayers = [players.a, players.b].filter(Boolean);

  stopArchitectMusicFade();

  if (immediate) {
    allPlayers.forEach((audio) => {
      try {
        audio.pause();
        audio.currentTime = 0;
        audio.volume = 0;
      } catch (e) {}
    });
    architectMusicCurrentTrack = '';
    return;
  }

  const activePlayer = players[architectMusicActiveDeck];
  if (!activePlayer) {
    architectMusicCurrentTrack = '';
    return;
  }

  fadeArchitectMusic(activePlayer, null, 0, 700);
  architectMusicCurrentTrack = '';
}

function switchArchitectMusic(trackUrl) {
  const players = getArchitectMusicPlayers();
  const activePlayer = players[architectMusicActiveDeck];
  const nextDeck = architectMusicActiveDeck === 'a' ? 'b' : 'a';
  const nextPlayer = players[nextDeck];

  if (!architectMusicUnlocked || !activePlayer || !nextPlayer) {
    return;
  }

  if (!trackUrl) {
    stopArchitectMusic();
    return;
  }

  if (architectMusicCurrentTrack === trackUrl && activePlayer.dataset.currentTrack === trackUrl) {
    if (activePlayer.paused) {
      const resumePromise = activePlayer.play();
      if (resumePromise && typeof resumePromise.catch === 'function') {
        resumePromise.catch(() => {});
      }
    }
    activePlayer.volume = ARCHITECT_MUSIC_TARGET_VOLUME;
    return;
  }

  stopArchitectMusicFade();

  nextPlayer.loop = true;
  nextPlayer.preload = 'auto';
  nextPlayer.volume = 0;

  if (nextPlayer.dataset.currentTrack !== trackUrl) {
    nextPlayer.src = trackUrl;
    nextPlayer.dataset.currentTrack = trackUrl;
    nextPlayer.load();
  } else {
    try {
      nextPlayer.currentTime = 0;
    } catch (e) {}
  }

  const playPromise = nextPlayer.play();
  if (playPromise && typeof playPromise.catch === 'function') {
    playPromise.catch(() => {});
  }

  fadeArchitectMusic(activePlayer, nextPlayer);
  architectMusicActiveDeck = nextDeck;
  architectMusicCurrentTrack = trackUrl;
}

function syncArchitectMusic(eventData) {
  switchArchitectMusic(getArchitectPhaseMusic(eventData));
}

function clearArchitectFxTimer(timer) {
  if (timer) {
    clearTimeout(timer);
  }
}

function triggerArchitectPhaseShift(phase) {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  clearArchitectFxTimer(architectPhaseFxTimer);
  overlay.classList.remove('event-phase-shift', 'event-phase-shift-2', 'event-phase-shift-3');
  void overlay.offsetWidth;
  overlay.classList.add('event-phase-shift');

  if (phase === 2) {
    overlay.classList.add('event-phase-shift-2');
  } else if (phase >= 3) {
    overlay.classList.add('event-phase-shift-3');
  }

  architectPhaseFxTimer = setTimeout(() => {
    overlay.classList.remove('event-phase-shift', 'event-phase-shift-2', 'event-phase-shift-3');
    architectPhaseFxTimer = null;
  }, 1100);
}

function triggerArchitectActionFx(actionType, isCorrect = true) {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay || !actionType) return;

  clearArchitectFxTimer(architectActionFxTimer);
  overlay.classList.remove(
    'event-action-fx',
    'event-action-fx-attack',
    'event-action-fx-protocol',
    'event-action-fx-sync',
    'event-action-fx-stabilize',
    'event-action-fx-miss'
  );

  document.querySelectorAll('.event-action.is-firing').forEach((node) => {
    node.classList.remove('is-firing');
  });

  void overlay.offsetWidth;
  overlay.classList.add('event-action-fx', `event-action-fx-${actionType}`);

  if (!isCorrect) {
    overlay.classList.add('event-action-fx-miss');
  }

  const button = document.querySelector(`.event-action.${actionType}`);
  if (button) {
    button.classList.add('is-firing');
  }

  architectActionFxTimer = setTimeout(() => {
    overlay.classList.remove(
      'event-action-fx',
      'event-action-fx-attack',
      'event-action-fx-protocol',
      'event-action-fx-sync',
      'event-action-fx-stabilize',
      'event-action-fx-miss'
    );
    if (button) {
      button.classList.remove('is-firing');
    }
    architectActionFxTimer = null;
  }, 760);
}

function normalizeArchitectDeadline(value) {
  if (!value) return null;
  const raw = String(value);
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? raw : `${raw}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatArchitectCountdown(ms) {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function stopArchitectFinalTimer() {
  if (architectFinalTimerHandle) {
    clearInterval(architectFinalTimerHandle);
    architectFinalTimerHandle = null;
  }
}

function updateArchitectFinalTimer(eventData) {
  const timer = document.getElementById('eventFinalTimer');
  if (!timer) return;

  stopArchitectFinalTimer();

  const isFinalPhase = !!eventData &&
    eventData.state === 'ACTIVE' &&
    Number(eventData.phase || 1) >= 3 &&
    !!eventData.final_phase_deadline;

  if (!isFinalPhase) {
    timer.style.display = 'none';
    timer.textContent = 'FINAL T-00:00';
    return;
  }

  const deadline = normalizeArchitectDeadline(eventData.final_phase_deadline);
  if (!deadline) {
    timer.style.display = 'none';
    return;
  }

  function renderTimer() {
    const remaining = deadline.getTime() - Date.now();
    timer.textContent = `FINAL WINDOW T-${formatArchitectCountdown(remaining)}`;
    timer.style.display = remaining > 0 ? 'block' : 'none';
    if (remaining <= 0) {
      stopArchitectFinalTimer();
    }
  }

  renderTimer();
  architectFinalTimerHandle = setInterval(renderTimer, 500);
}

function updateArchitectPhaseFxState(eventData) {
  const overlay = document.getElementById('eventOverlay');
  const warning = document.getElementById('eventPhaseWarning');
  if (!overlay) return;

  overlay.classList.remove(
    'event-state-active',
    'event-state-registration',
    'event-state-terminal',
    'event-state-finished',
    'event-state-failed',
    'event-phase-1',
    'event-phase-2',
    'event-phase-3',
    'event-overload-high',
    'event-overload-critical'
  );

  if (!eventData) {
    architectLastRenderedPhase = null;
    updateArchitectFinalTimer(null);
    if (warning) warning.style.display = 'none';
    return;
  }

  const state = String(eventData.state || '').toUpperCase();
  const isActive = state === 'ACTIVE';
  const isTerminal = state === 'FAILED' || state === 'FINISHED';
  const phase = Math.max(1, Math.min(3, Number(eventData.phase || 1)));
  const overload = Number(eventData.overload_pressure || 0);

  overlay.classList.toggle('event-state-active', isActive);
  overlay.classList.toggle('event-state-registration', state === 'REGISTRATION');
  overlay.classList.toggle('event-state-terminal', isTerminal);
  overlay.classList.toggle('event-state-finished', state === 'FINISHED');
  overlay.classList.toggle('event-state-failed', state === 'FAILED');

  if (isActive) {
    overlay.classList.add(`event-phase-${phase}`);

    if (architectLastRenderedPhase !== null && architectLastRenderedPhase !== phase) {
      triggerArchitectPhaseShift(phase);
    }

    architectLastRenderedPhase = phase;
  } else {
    architectLastRenderedPhase = null;
  }

  const overloadHigh = isActive && phase >= 3 && overload >= 12;
  const overloadCritical = isActive && phase >= 3 && overload >= 20;
  overlay.classList.toggle('event-overload-high', overloadHigh);
  overlay.classList.toggle('event-overload-critical', overloadCritical);

  if (warning) {
    warning.textContent = overloadCritical ? 'OVERLOAD CRITICAL' : 'OVERLOAD WARNING';
    warning.style.display = overloadHigh ? 'block' : 'none';
  }

  updateArchitectFinalTimer(eventData);
}

function setArchitectAmbientVisibility(isVisible) {
  const matrix = document.getElementById('matrixRain');
  if (matrix) {
    matrix.style.display = isVisible ? '' : 'none';
  }

  document.querySelectorAll('.bg-kanji').forEach((node) => {
    node.style.display = isVisible ? '' : 'none';
  });
}

function applyArchitectMedia(eventData) {
  const bossImage = document.getElementById('eventBossImage');
  const bossVideo = document.getElementById('eventBossVideo');
  const hudAvatar = document.getElementById('eventHudAvatar');
  const videoSrc = getArchitectPhaseVideo(eventData);
  const imageSrc = getArchitectPhaseImage(eventData);

  if (bossVideo) {
    bossVideo.loop = true;
    bossVideo.muted = true;
    bossVideo.playsInline = true;
    if (videoSrc) {
      if (bossVideo.dataset.currentSrc !== videoSrc) {
        bossVideo.src = videoSrc;
        bossVideo.dataset.currentSrc = videoSrc;
        bossVideo.load();
      }
      bossVideo.style.display = 'block';
      const maybePromise = bossVideo.play();
      if (maybePromise && typeof maybePromise.catch === 'function') {
        maybePromise.catch(() => {});
      }
    } else {
      bossVideo.pause();
      bossVideo.removeAttribute('src');
      bossVideo.dataset.currentSrc = '';
      bossVideo.style.display = 'none';
      bossVideo.load();
    }
  }

  if (bossImage) {
    bossImage.src = imageSrc;
    bossImage.style.display = videoSrc ? 'none' : 'block';
  }

  if (hudAvatar) {
    hudAvatar.style.backgroundImage = `url('${imageSrc}')`;
  }

  syncArchitectMusic(eventData);
}

async function loadCurrentArchitectEvent() {
  try {
    const res = await fetch(`${API_URL}/api/events/current`);
    const data = await res.json();

    currentArchitectEvent = data.event || null;
    currentArchitectEventId = currentArchitectEvent ? currentArchitectEvent.id : null;

    renderArchitectLobby(currentArchitectEvent);
  } catch (e) {
    renderArchitectLobby(null, 'Не удалось загрузить событие.');
  }
}

function renderArchitectLobby(eventData, errorText = '') {
  const lobbyCard = document.getElementById('eventLobbyCard');
  const overlay = document.getElementById('eventOverlay');
  const statusEl = document.getElementById('eventStatusText');
  const rewardEl = document.getElementById('eventRewardText');
  const teamCountEl = document.getElementById('eventTeamCount');
  const teamListEl = document.getElementById('eventTeamList');
  const createBtn = document.getElementById('eventCreateBtn');
  const joinBtn = document.getElementById('eventJoinBtn');
  const leaveBtn = document.getElementById('eventLeaveBtn');
  const startBtn = document.getElementById('eventStartBtn');
  const kickerEl = lobbyCard ? lobbyCard.querySelector('.event-lobby-kicker') : null;
  const labelEls = lobbyCard ? lobbyCard.querySelectorAll('.event-lobby-label') : [];

  if (!lobbyCard || !statusEl || !rewardEl || !teamCountEl || !teamListEl || !createBtn || !joinBtn || !leaveBtn || !startBtn) {
    return;
  }

  if (!eventData) {
    if (overlay) {
      overlay.classList.remove('event-terminal');
    }
    lobbyCard.classList.remove('event-result-card', 'event-result-win', 'event-result-lose');

    lobbyCard.style.display = 'block';
    if (kickerEl) kickerEl.textContent = 'КОМАНДА';
    if (labelEls[0]) labelEls[0].textContent = 'ПРИЗ';
    if (labelEls[1]) labelEls[1].textContent = 'СОСТАВ КОМАНДЫ';
    statusEl.textContent = errorText || 'Ивент не создан';
    rewardEl.textContent = '—';
    teamCountEl.textContent = '0 / 0';
    teamListEl.innerHTML = '<div class="event-team-empty">Нет активного ивента</div>';

    createBtn.style.display = isAdmin ? 'inline-flex' : 'none';
    joinBtn.style.display = 'none';
    leaveBtn.style.display = 'none';
    startBtn.style.display = 'none';
    updateArchitectBattleVisibility(null);
    return;
  }

  const stateMap = {
    REGISTRATION: 'Набор команды',
    ACTIVE: 'Идёт бой',
    FINISHED: 'Победа',
    FAILED: 'Поражение'
  };

  statusEl.textContent = stateMap[eventData.state] || eventData.state || '—';
  rewardEl.textContent = eventData.reward_text || 'Приз не указан';

  const minPlayers = eventData.min_players || 0;
  const maxPlayers = eventData.max_players || 0;
  const teamMembers = Array.isArray(eventData.team_members) ? eventData.team_members : [];
  const teamCount = typeof eventData.team_count === 'number' ? eventData.team_count : teamMembers.length;
  const hasReward = !!(eventData.reward_text && String(eventData.reward_text).trim());
  const isTerminal = eventData.state === 'FAILED' || eventData.state === 'FINISHED';
  const showLobbyCard = eventData.state === 'REGISTRATION' || (isTerminal && (teamCount > 0 || hasReward || isAdmin));

  if (overlay) {
    overlay.classList.toggle('event-terminal', isTerminal);
  }

  lobbyCard.classList.toggle('event-result-card', isTerminal);
  lobbyCard.classList.toggle('event-result-win', eventData.state === 'FINISHED');
  lobbyCard.classList.toggle('event-result-lose', eventData.state === 'FAILED');
  lobbyCard.style.display = showLobbyCard ? 'block' : 'none';

  if (kickerEl) {
    kickerEl.textContent = isTerminal
      ? (eventData.state === 'FINISHED' ? 'RESULT // WIN' : 'RESULT // FAIL')
      : 'КОМАНДА';
  }
  if (labelEls[0]) labelEls[0].textContent = isTerminal ? 'НАГРАДА' : 'ПРИЗ';
  if (labelEls[1]) labelEls[1].textContent = isTerminal ? 'MVP / УРОН' : 'СОСТАВ КОМАНДЫ';

  if (eventData.state === 'REGISTRATION') {
    teamCountEl.textContent = `${teamCount} / ${maxPlayers}`;
  } else if (isTerminal) {
    teamCountEl.textContent = `${teamCount} бойц.`;
  } else {
    teamCountEl.textContent = `${teamCount} чел.`;
  }

  if (isTerminal) {
    renderArchitectResultPanel(eventData);
    loadArchitectResultStats(eventData);
  } else if (!teamMembers.length) {
    teamListEl.innerHTML = '<div class="event-team-empty">Пока никто не вступил</div>';
  } else {
    teamListEl.innerHTML = teamMembers.map(member => {
      const name = escapeHtml(member.full_name || 'Аноним');
      return `<div class="event-team-member">${name}</div>`;
    }).join('');
  }

  const isMember = teamMembers.some(member => Number(member.telegram_id) === Number(currentUserId));
  const canJoin = eventData.state === 'REGISTRATION' && !isMember && teamCount < maxPlayers;
  const canLeave = eventData.state === 'REGISTRATION' && isMember;
  const canStart = eventData.state === 'REGISTRATION' &&
                   typeof isAdmin !== 'undefined' && isAdmin &&
                   teamCount >= minPlayers;

  createBtn.style.display = (isAdmin && isTerminal) ? 'inline-flex' : 'none';
  joinBtn.style.display = canJoin ? 'inline-flex' : 'none';
  leaveBtn.style.display = canLeave ? 'inline-flex' : 'none';
  startBtn.style.display = canStart ? 'inline-flex' : 'none';

  updateArchitectBattleVisibility(eventData);
}

function getArchitectTeamNameMap(eventData) {
  const result = new Map();
  const members = Array.isArray(eventData && eventData.team_members) ? eventData.team_members : [];

  members.forEach((member) => {
    result.set(Number(member.telegram_id), member.full_name || 'Аноним');
  });

  return result;
}

function renderArchitectResultPanel(eventData, leaderboard = null) {
  const rewardEl = document.getElementById('eventRewardText');
  const teamListEl = document.getElementById('eventTeamList');
  if (!rewardEl || !teamListEl || !eventData) return;

  const rewardText = eventData.reward_text || 'Приз не указан';
  const totalDamage = Number(eventData.total_damage || 0);
  const totalActions = Number(eventData.total_actions || 0);
  const state = String(eventData.state || '').toUpperCase();
  const resultLabel = state === 'FINISHED' ? 'Награда разблокирована' : 'Протокол не пробит';

  rewardEl.innerHTML = `
    <span class="event-result-reward-main">${escapeHtml(rewardText)}</span>
    <span class="event-result-reward-sub">${resultLabel} · урон команды ${totalDamage} · действий ${totalActions}</span>
  `;

  const names = getArchitectTeamNameMap(eventData);
  const rows = Array.isArray(leaderboard) ? leaderboard.slice() : [];
  rows.sort((a, b) => {
    const damageDiff = Number(b.total_damage || 0) - Number(a.total_damage || 0);
    if (damageDiff) return damageDiff;
    return Number(b.total_support || 0) - Number(a.total_support || 0);
  });

  if (!rows.length) {
    const members = Array.isArray(eventData.team_members) ? eventData.team_members : [];
    teamListEl.innerHTML = members.length
      ? members.map((member, index) => {
          const name = escapeHtml(member.full_name || 'Аноним');
          const tag = index === 0 ? '<span class="event-result-mvp">MVP?</span>' : '';
          return `<div class="event-result-row"><span>${tag}${name}</span><strong>—</strong></div>`;
        }).join('')
      : '<div class="event-team-empty">Команда не найдена</div>';
    return;
  }

  const mvpId = Number(rows[0].telegram_id);
  teamListEl.innerHTML = rows.map((row) => {
    const telegramId = Number(row.telegram_id);
    const name = escapeHtml(names.get(telegramId) || `ID ${telegramId}`);
    const damage = Number(row.total_damage || 0);
    const support = Number(row.total_support || 0);
    const mvp = telegramId === mvpId ? '<span class="event-result-mvp">MVP</span>' : '';
    return `
      <div class="event-result-row">
        <span>${mvp}${name}</span>
        <strong>${damage} dmg / ${support} sup</strong>
      </div>
    `;
  }).join('');
}

async function loadArchitectResultStats(eventData) {
  if (!eventData || !eventData.id || (eventData.state !== 'FAILED' && eventData.state !== 'FINISHED')) return;

  try {
    const res = await fetch(`${API_URL}/api/events/${eventData.id}/leaderboard`);
    if (!res.ok) return;

    const data = await res.json();
    if (!currentArchitectEvent || Number(currentArchitectEvent.id) !== Number(eventData.id)) return;

    renderArchitectResultPanel(eventData, data.leaderboard || []);
  } catch (e) {}
}

function updateArchitectBattleVisibility(eventData) {
  const actions = document.querySelector('.event-actions');
  const bossImage = document.getElementById('eventBossImage');
  const log = document.getElementById('eventLog');
  const hud = document.querySelector('.event-hud');
  const hpText = document.getElementById('eventHpText');
  const hpFill = document.getElementById('eventHpFill');
  const phaseText = document.getElementById('eventPhaseText');
  const phaseLabel = document.getElementById('eventPhaseLabel');
  const stateBadge = document.getElementById('eventStateBadge');
  const vulnerabilityBadge = document.getElementById('eventVulnerabilityBadge');
  const overloadBadge = document.getElementById('eventOverloadBadge');


  if (!actions || !log || !hpText || !hpFill || !phaseText || !phaseLabel) {
    return;
  }

  updateArchitectPhaseFxState(eventData);

  const isActive = !!eventData && eventData.state === 'ACTIVE';
  const isTerminal = !!eventData && (eventData.state === 'FAILED' || eventData.state === 'FINISHED');

  actions.style.display = isActive ? 'grid' : 'none';
  if (hud) {
    hud.style.display = isTerminal ? 'none' : 'flex';
  }
  if (!isActive) {
  closeArchitectQuestion();
}

  if (!eventData) {
    hpText.textContent = '-- / ----';
    hpFill.style.width = '0%';
    phaseText.textContent = 'NO SIGNAL';
    phaseLabel.textContent = '—';
    log.innerHTML = '<div class="event-log-empty">Лог ивента появится здесь</div>';

      if (stateBadge) {
      stateBadge.textContent = '—';
      stateBadge.className = 'event-status-badge';
    }

    if (vulnerabilityBadge) {
      vulnerabilityBadge.textContent = '—';
      vulnerabilityBadge.className = 'event-status-badge';
    }

    if (overloadBadge) {
      overloadBadge.textContent = 'OVR 0';
    }
    return;
  }

  const maxHp = eventData.max_hp || 1;
  const currentHp = Math.max(0, eventData.current_hp || 0);
  const hpPercent = Math.max(0, Math.min(100, (currentHp / maxHp) * 100));

  applyArchitectMedia(eventData);

  hpText.textContent = `${currentHp} / ${maxHp}`;
  hpFill.style.width = `${hpPercent}%`;
  phaseText.textContent = eventData.state === 'ACTIVE'
    ? `PHASE ${eventData.phase || 1}`
    : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');
  phaseLabel.textContent = eventData.state === 'ACTIVE'
    ? `ФАЗА ${eventData.phase || 1}`
    : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');

     if (stateBadge) {
    const state = String(eventData.state || '').toUpperCase();
    stateBadge.textContent = state || 'UNKNOWN';
    stateBadge.className = 'event-status-badge';

    if (state === 'ACTIVE') stateBadge.classList.add('green');
    if (state === 'REGISTRATION') stateBadge.classList.add('gold');
    if (state === 'FAILED' || state === 'FINISHED') stateBadge.classList.add('hot');
  }

  if (vulnerabilityBadge) {
    const vulnerable = !!eventData.vulnerability_active && eventData.state === 'ACTIVE';
    vulnerabilityBadge.textContent = vulnerable ? 'VULNERABLE' : 'SHIELDED';
    vulnerabilityBadge.className = 'event-status-badge';
    vulnerabilityBadge.classList.add(vulnerable ? 'gold' : 'hot');
  }

  if (overloadBadge) {
    const overload = Number(eventData.overload_pressure || 0);
    overloadBadge.textContent = `OVR ${overload}`;
  }

  const logs = Array.isArray(eventData.logs) ? eventData.logs : [];
  if (!logs.length) {
    log.innerHTML = '<div class="event-log-empty">Лог ивента появится здесь</div>';
  } else {
    log.innerHTML = logs.map(item => {
      return `<div class="event-log-line">${escapeHtml(item.message || '')}</div>`;
    }).join('');
    log.scrollTop = log.scrollHeight;
  }
}

async function joinArchitectTeam() {
  if (!currentArchitectEventId || !currentUserId) return;

  try {
    const res = await fetch(`${API_URL}/api/events/${currentArchitectEventId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: currentUserId })
    });

    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось вступить в команду');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}

async function leaveArchitectTeam() {
  if (!currentArchitectEventId || !currentUserId) return;

  try {
    const res = await fetch(`${API_URL}/api/events/${currentArchitectEventId}/leave`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: currentUserId })
    });

    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось покинуть команду');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('warning'); } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}

async function createArchitectEvent() {
  if (!currentUserId || !isAdmin) return;

  const rewardInput = window.prompt('Приз для команды', 'Поход в ТЦ');
  if (rewardInput === null) return;

  const rewardText = rewardInput.trim() || 'Приз не указан';

  try {
    const res = await fetch(`${API_URL}/api/events/architect/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Id': String(currentUserId || 0)
      },
      body: JSON.stringify({
        telegram_id: currentUserId,
        reward_text: rewardText,
        min_players: 3,
        max_players: 5
      })
    });

    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось создать ивент');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}

async function startArchitectEvent() {
  if (!currentArchitectEventId) return;

  try {
    const res = await fetch(`${API_URL}/api/events/${currentArchitectEventId}/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Id': String(currentUserId || 0)
      },
      body: JSON.stringify({ telegram_id: currentUserId })
    });

    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось запустить ивент');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}

let pendingEventActionType = null;
let pendingEventQuestionId = null;
let pendingEventQuestion = null;
let isArchitectQuestionLoading = false;

async function requestArchitectQuestion(actionType) {
  if (!currentArchitectEventId || !currentUserId) return;

  const box = document.getElementById('eventQuestionBox');
  if (
    box &&
    box.style.display !== 'none' &&
    box.querySelector('.event-answer-feedback')
  ) {
    return;
  }

  if (
    pendingEventQuestion &&
    pendingEventActionType &&
    box &&
    box.style.display !== 'none'
  ) {
    showArchitectQuestion(pendingEventQuestion);
    return;
  }

  if (isArchitectQuestionLoading) return;

  try {
    isArchitectQuestionLoading = true;

    const res = await fetch(
      `${API_URL}/api/events/${currentArchitectEventId}/question?telegram_id=${encodeURIComponent(currentUserId)}&action_type=${encodeURIComponent(actionType)}`
    );
    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось получить вопрос');
      return;
    }

    pendingEventActionType = actionType;

    if (actionType === 'sync') {
      pendingEventQuestionId = null;
      await submitArchitectAnswer(null);
      return;
    }

    const question = data.question;
    if (!question) {
      tg.showAlert('Вопрос не найден');
      return;
    }

    pendingEventQuestionId = question.id;
    pendingEventQuestion = question;
    showArchitectQuestion(question);
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  } finally {
    isArchitectQuestionLoading = false;
  }
}

function showArchitectQuestion(question) {
  const box = document.getElementById('eventQuestionBox');
  const prompt = document.getElementById('eventQuestionPrompt');
  const options = document.getElementById('eventOptions');

  if (!box || !prompt || !options) return;
  clearArchitectQuestionAutoClose();

  prompt.textContent = question.prompt || 'Вопрос не загружен';

  const opts = question.options || {};
  options.innerHTML = `
    <button class="event-option-btn" data-option="a" onclick="submitArchitectAnswer('a')">${escapeHtml(opts.a || '')}</button>
    <button class="event-option-btn" data-option="b" onclick="submitArchitectAnswer('b')">${escapeHtml(opts.b || '')}</button>
    <button class="event-option-btn" data-option="c" onclick="submitArchitectAnswer('c')">${escapeHtml(opts.c || '')}</button>
  `;

  box.querySelectorAll('.event-answer-feedback').forEach((node) => {
    node.remove();
  });
  box.style.display = 'block';
}

function clearArchitectQuestionAutoClose() {
  if (architectQuestionAutoCloseTimer) {
    clearTimeout(architectQuestionAutoCloseTimer);
    architectQuestionAutoCloseTimer = null;
  }
}

function scheduleArchitectQuestionAutoClose() {
  clearArchitectQuestionAutoClose();
  architectQuestionAutoCloseTimer = setTimeout(() => {
    architectQuestionAutoCloseTimer = null;
    closeArchitectQuestion();
  }, ARCHITECT_ANSWER_FEEDBACK_MS);
}

function renderArchitectAnswerFeedback(answerOption, isCorrect, explanation) {
  const box = document.getElementById('eventQuestionBox');
  const options = document.getElementById('eventOptions');
  if (!box || !options) return;

  options.querySelectorAll('.event-option-btn').forEach((button) => {
    const selected = button.dataset.option === answerOption;
    button.disabled = true;
    button.classList.toggle('is-selected', selected);
    button.classList.toggle('is-correct', selected && isCorrect);
    button.classList.toggle('is-wrong', selected && !isCorrect);
  });

  box.querySelectorAll('.event-answer-feedback').forEach((node) => {
    node.remove();
  });

  if (explanation && String(explanation).trim()) {
    const feedback = document.createElement('div');
    feedback.className = 'event-answer-feedback';
    feedback.textContent = explanation;
    box.appendChild(feedback);
  }

  scheduleArchitectQuestionAutoClose();
}

function closeArchitectQuestion() {
  const box = document.getElementById('eventQuestionBox');
  const options = document.getElementById('eventOptions');
  const prompt = document.getElementById('eventQuestionPrompt');

  clearArchitectQuestionAutoClose();
  if (box) box.style.display = 'none';
  if (box) {
    box.querySelectorAll('.event-answer-feedback').forEach((node) => {
      node.remove();
    });
  }
  if (options) options.innerHTML = '';
  if (prompt) prompt.textContent = 'Вопрос появится здесь';

  pendingEventActionType = null;
  pendingEventQuestionId = null;
  pendingEventQuestion = null;
}

async function submitArchitectAnswer(answerOption) {
  if (!currentArchitectEventId || !currentUserId || !pendingEventActionType) return;

  try {
    const actionType = pendingEventActionType;
    const payload = {
      event_id: currentArchitectEventId,
      telegram_id: currentUserId,
      action_type: actionType,
      use_active_modifier: false
    };

    if (actionType !== 'sync') {
      payload.question_id = pendingEventQuestionId;
      payload.answer_option = answerOption;
    }

    const res = await fetch(`${API_URL}/api/events/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!res.ok) {
      tg.showAlert(data.detail || 'Не удалось отправить действие');
      return;
    }

    triggerArchitectActionFx(actionType, data.is_correct !== false);
    pendingEventActionType = null;

    if (data.is_correct === false && data.question_explanation) {
      setEventExplanation(`Неверно. ${data.question_explanation}`);
    } else if (data.question_explanation) {
      setEventExplanation(data.question_explanation);
    } else {
      setEventExplanation('');
    }

    if (actionType === 'sync') {
      closeArchitectQuestion();
    } else {
      const explanation = data.question_explanation
        ? `${data.is_correct === false ? 'Неверно. ' : ''}${data.question_explanation}`
        : '';
      setEventExplanation('');
      renderArchitectAnswerFeedback(answerOption, data.is_correct !== false, explanation);
      pendingEventQuestionId = null;
      pendingEventQuestion = null;
    }

    await loadCurrentArchitectEvent();

    try {
      tg.HapticFeedback.notificationOccurred(data.is_correct === false ? 'error' : 'success');
    } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}
