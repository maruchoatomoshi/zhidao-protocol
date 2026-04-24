const ARCHITECT_PHASE_IMAGES = {
  1: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase1.png',
  2: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase2.png',
  3: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase3.png'
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

function getArchitectPhaseImage(eventData) {
  if (!eventData) return ARCHITECT_PHASE_IMAGES[1];
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return ARCHITECT_PHASE_IMAGES[2];
  if (phase >= 3) return ARCHITECT_PHASE_IMAGES[3];
  return ARCHITECT_PHASE_IMAGES[1];
}

function getArchitectPhaseVideo(eventData) {
  if (!eventData) return '';
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
  const statusEl = document.getElementById('eventStatusText');
  const rewardEl = document.getElementById('eventRewardText');
  const teamCountEl = document.getElementById('eventTeamCount');
  const teamListEl = document.getElementById('eventTeamList');
  const createBtn = document.getElementById('eventCreateBtn');
  const joinBtn = document.getElementById('eventJoinBtn');
  const leaveBtn = document.getElementById('eventLeaveBtn');
  const startBtn = document.getElementById('eventStartBtn');

  if (!lobbyCard || !statusEl || !rewardEl || !teamCountEl || !teamListEl || !createBtn || !joinBtn || !leaveBtn || !startBtn) {
    return;
  }

  if (!eventData) {
    lobbyCard.style.display = 'block';
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
  const showLobbyCard = eventData.state === 'REGISTRATION' || teamCount > 0 || hasReward || (isAdmin && isTerminal);

  lobbyCard.style.display = showLobbyCard ? 'block' : 'none';

  if (eventData.state === 'REGISTRATION') {
    teamCountEl.textContent = `${teamCount} / ${maxPlayers}`;
  } else {
    teamCountEl.textContent = `${teamCount} чел.`;
  }

  if (!teamMembers.length) {
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

function updateArchitectBattleVisibility(eventData) {
  const actions = document.querySelector('.event-actions');
  const bossImage = document.getElementById('eventBossImage');
  const log = document.getElementById('eventLog');
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

  const isActive = !!eventData && eventData.state === 'ACTIVE';

  actions.style.display = isActive ? 'grid' : 'none';
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

async function requestArchitectQuestion(actionType) {
  if (!currentArchitectEventId || !currentUserId) return;

  try {
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
    showArchitectQuestion(question);
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}

function showArchitectQuestion(question) {
  const box = document.getElementById('eventQuestionBox');
  const prompt = document.getElementById('eventQuestionPrompt');
  const options = document.getElementById('eventOptions');

  if (!box || !prompt || !options) return;

  prompt.textContent = question.prompt || 'Вопрос не загружен';

  const opts = question.options || {};
  options.innerHTML = `
    <button class="event-option-btn" onclick="submitArchitectAnswer('a')">${escapeHtml(opts.a || '')}</button>
    <button class="event-option-btn" onclick="submitArchitectAnswer('b')">${escapeHtml(opts.b || '')}</button>
    <button class="event-option-btn" onclick="submitArchitectAnswer('c')">${escapeHtml(opts.c || '')}</button>
  `;

  box.style.display = 'block';
}

function closeArchitectQuestion() {
  const box = document.getElementById('eventQuestionBox');
  const options = document.getElementById('eventOptions');
  const prompt = document.getElementById('eventQuestionPrompt');

  if (box) box.style.display = 'none';
  if (options) options.innerHTML = '';
  if (prompt) prompt.textContent = 'Вопрос появится здесь';

  pendingEventQuestionId = null;
}

async function submitArchitectAnswer(answerOption) {
  if (!currentArchitectEventId || !currentUserId || !pendingEventActionType) return;

  try {
    const payload = {
      event_id: currentArchitectEventId,
      telegram_id: currentUserId,
      action_type: pendingEventActionType,
      use_active_modifier: false
    };

    if (pendingEventActionType !== 'sync') {
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

    closeArchitectQuestion();
    pendingEventActionType = null;

    if (data.is_correct === false && data.question_explanation) {
      setEventExplanation(`Неверно. ${data.question_explanation}`);
    } else if (data.question_explanation) {
      setEventExplanation(data.question_explanation);
    } else {
      setEventExplanation('');
    }

    await loadCurrentArchitectEvent();

    try {
      tg.HapticFeedback.notificationOccurred(data.is_correct === false ? 'error' : 'success');
    } catch (e) {}
  } catch (e) {
    tg.showAlert('Ошибка соединения');
  }
}
