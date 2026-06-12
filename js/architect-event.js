const WILD_AI_BREACH_INFECTION_THRESHOLD = 100;
const WILD_AI_BREACH_INFECTION_STABILIZE_REDUCTION = 5;
const WILD_AI_BREACH_INFECTION_SYNC_REDUCTION = 2;

const ARCHITECT_LOBBY_IMAGE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architect_ivent_lobby.png';
const WILD_AI_BREACH_LOBBY_IMAGE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/wild_ai_lobby_picture.png';

const ARCHITECT_PHASE_IMAGES = {
  1: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase1.png',
  2: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase2.png',
  3: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase3.png'
};

const ARCHITECT_TERMINAL_IMAGES = {
  FINISHED: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architect_ivent_win.png',
  FAILED: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/architect_ivent_lose.png'
};

const WILD_AI_BREACH_TERMINAL_IMAGES = {
  FINISHED: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/wildai_win.png',
  FAILED: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/wildai_lose.png'
};

const ARCHITECT_PHASE_VIDEOS = {
  1: 'architect_phase1.mp4',
  2: 'architect_phase2.mp4',
  3: 'architect_phase3.mp4'
};

const WILD_AI_BREACH_PHASE_VIDEOS = {
  1: 'wildai_phase1_cut.mp4',
  2: 'wildai_phase2.mp4',
  3: 'wildai_phase3.mp4'
};

const WILD_AI_BREACH_LOSE_VIDEO = 'wildai-lose_w2xvaPOC.mp4';
// Defeat sting: upload a file with this exact name to the repo root and it
// will play automatically when the loss video starts. Missing file = silent no-op.
const WILD_AI_BREACH_LOSE_SOUND = 'wildai_losetheme.mp3';
let wildAiLoseSoundPlayedFor = null;

const ARCHITECT_PHASE_MUSIC = {
  1: 'architect_phase1_music.mp3',
  2: 'architect_phase2_music.mp3',
  3: 'architect_phase3_music.mp3'
};
const ARCHITECT_LOBBY_MUSIC = 'architector_ivent_lobby_theme.mp3';

const WILD_AI_BREACH_PHASE_MUSIC = {
  1: 'wildai_phase1_theme.mp3',
  2: 'wildai_phase2_theme.mp3',
  3: 'wildai_phase3_theme.mp3'
};
const WILD_AI_BREACH_LOBBY_MUSIC = 'wildai_lobbytheme.mp3';

const ARCHITECT_MUSIC_TARGET_VOLUME = 0.58;
const ARCHITECT_MUSIC_FADE_MS = 1400;
let architectMusicUnlocked = false;
let architectMusicCurrentTrack = '';
let architectMusicActiveDeck = 'a';
let architectMusicFadeFrame = null;
let architectMusicPendingTrack = '';
let architectMusicRetryTimer = null;
let architectMusicRetryAttempts = 0;
let architectLastRenderedPhase = null;
let architectLastLogCount = 0;
let architectActionFxTimer = null;
let architectPhaseFxTimer = null;
let architectFinalTimerHandle = null;
let architectQuestionAutoCloseTimer = null;
let architectResultRevealTimer = null;
let architectResultRevealEventKey = null;
let architectVideoStartTimer = null;
let architectActionResultTimer = null;
const ARCHITECT_ANSWER_FEEDBACK_MS = 1800;
const ARCHITECT_RESULT_REVEAL_DELAY = 4500;
// WildAI loss video runs ~10s; reveal the defeat banner right after it ends
const WILD_AI_LOSE_REVEAL_DELAY = 10500;

function getArchitectPhaseImage(eventData) {
  if (!eventData) {
    return (typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach')
      ? WILD_AI_BREACH_LOBBY_IMAGE
      : ARCHITECT_LOBBY_IMAGE;
  }
  const isWildAi = eventData.code === 'wildai_breach';
  const state = String(eventData.state || '').toUpperCase();
  if (state === 'REGISTRATION') return isWildAi ? WILD_AI_BREACH_LOBBY_IMAGE : ARCHITECT_LOBBY_IMAGE;
  const terminalImages = isWildAi ? WILD_AI_BREACH_TERMINAL_IMAGES : ARCHITECT_TERMINAL_IMAGES;
  if (terminalImages[state]) return terminalImages[state];
  if (isWildAi) return WILD_AI_BREACH_LOBBY_IMAGE;
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return ARCHITECT_PHASE_IMAGES[2];
  if (phase >= 3) return ARCHITECT_PHASE_IMAGES[3];
  return ARCHITECT_PHASE_IMAGES[1];
}

function getArchitectPhaseVideo(eventData) {
  if (!eventData) return '';
  const isWildAi = eventData.code === 'wildai_breach';
  const state = String(eventData.state || '').toUpperCase();
  if (state === 'REGISTRATION') return '';
  if (state === 'FAILED') return isWildAi ? WILD_AI_BREACH_LOSE_VIDEO : '';
  if (state === 'FINISHED') return '';
  const videos = isWildAi ? WILD_AI_BREACH_PHASE_VIDEOS : ARCHITECT_PHASE_VIDEOS;
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return videos[2] || '';
  if (phase >= 3) return videos[3] || '';
  return videos[1] || '';
}

function getArchitectPhaseMusic(eventData) {
  const hintIsWildAi = typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach';
  const isWildAi = eventData ? eventData.code === 'wildai_breach' : hintIsWildAi;
  const state = eventData ? String(eventData.state || '').toUpperCase() : '';
  if (state === 'REGISTRATION' || (!eventData && ARCHITECT_LOBBY_MUSIC)) {
    return isWildAi ? WILD_AI_BREACH_LOBBY_MUSIC : ARCHITECT_LOBBY_MUSIC;
  }
  if (!eventData || state !== 'ACTIVE') return '';
  const music = isWildAi ? WILD_AI_BREACH_PHASE_MUSIC : ARCHITECT_PHASE_MUSIC;
  const phase = Number(eventData.phase || 1);
  if (phase === 2) return music[2] || '';
  if (phase >= 3) return music[3] || '';
  return music[1] || '';
}

function getArchitectMusicPlayers() {
  return {
    a: document.getElementById('architectMusicA'),
    b: document.getElementById('architectMusicB')
  };
}

function clearArchitectMusicRetry() {
  if (architectMusicRetryTimer) {
    clearTimeout(architectMusicRetryTimer);
    architectMusicRetryTimer = null;
  }
}

function isArchitectOverlayVisible() {
  const overlay = document.getElementById('eventOverlay');
  return !!overlay && overlay.style.display !== 'none';
}

function stopArchitectMusicFade() {
  if (architectMusicFadeFrame) {
    cancelAnimationFrame(architectMusicFadeFrame);
    architectMusicFadeFrame = null;
  }
}

function armArchitectMusicGestureRetry() {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay || overlay.dataset.musicRetryArmed === '1') return;

  overlay.dataset.musicRetryArmed = '1';
  const retry = () => {
    overlay.dataset.musicRetryArmed = '';
    if (architectMusicPendingTrack && isArchitectOverlayVisible()) {
      switchArchitectMusic(architectMusicPendingTrack, true);
    }
  };

  overlay.addEventListener('pointerdown', retry, { once: true, passive: true });
  overlay.addEventListener('touchstart', retry, { once: true, passive: true });
  overlay.addEventListener('click', retry, { once: true });
}

function scheduleArchitectMusicRetry(trackUrl) {
  if (!trackUrl || !isArchitectOverlayVisible()) return;
  architectMusicPendingTrack = trackUrl;
  clearArchitectMusicRetry();
  armArchitectMusicGestureRetry();

  if (architectMusicRetryAttempts >= 4) return;
  architectMusicRetryAttempts += 1;
  architectMusicRetryTimer = setTimeout(() => {
    architectMusicRetryTimer = null;
    if (architectMusicPendingTrack && isArchitectOverlayVisible()) {
      switchArchitectMusic(architectMusicPendingTrack, true);
    }
  }, 260 + architectMusicRetryAttempts * 340);
}

function primeArchitectMusicUnlock() {
  stopArchitectMusicFade();
  architectMusicUnlocked = true;
  architectMusicRetryAttempts = 0;

  const players = getArchitectMusicPlayers();
  const audio = players.a || players.b;
  if (!audio) return;

  architectMusicActiveDeck = 'a';

  try {
    audio.loop = true;
    audio.preload = 'auto';
    audio.volume = 0;
    audio.src = ARCHITECT_PHASE_MUSIC[1];
    audio.dataset.currentTrack = ARCHITECT_PHASE_MUSIC[1];
    audio.load();

    const unlockPromise = audio.play();
    if (unlockPromise && typeof unlockPromise.then === 'function') {
      unlockPromise
        .then(() => {
          try { audio.pause(); } catch (e) {}
          try { audio.currentTime = 0; } catch (e) {}
        })
        .catch(() => {
          armArchitectMusicGestureRetry();
        });
    }
  } catch (e) {
    armArchitectMusicGestureRetry();
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
  clearArchitectMusicRetry();
  architectMusicPendingTrack = '';
  architectMusicRetryAttempts = 0;

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

let architectMusicMuted = false;

function toggleArchitectMusicMute() {
  architectMusicMuted = !architectMusicMuted;
  const players = getArchitectMusicPlayers();
  [players.a, players.b].forEach((p) => {
    if (p) p.muted = architectMusicMuted;
  });
  const btn = document.getElementById('eventMuteBtn');
  if (btn) {
    btn.textContent = architectMusicMuted ? '🔇' : '🔊';
    btn.classList.toggle('muted', architectMusicMuted);
  }
}

function stopArchitectMusicOnClose() {
  stopArchitectMusic(true);
  architectMusicUnlocked = false;
  architectMusicCurrentTrack = '';
  architectMusicActiveDeck = 'a';
  architectMusicMuted = false;
  const players = getArchitectMusicPlayers();
  if (players.a) { players.a.dataset.currentTrack = ''; players.a.muted = false; }
  if (players.b) { players.b.dataset.currentTrack = ''; players.b.muted = false; }
  const btn = document.getElementById('eventMuteBtn');
  if (btn) { btn.textContent = '🔊'; btn.classList.remove('muted'); }
}

function switchArchitectMusic(trackUrl, forceRetry = false) {
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

  if (!forceRetry && architectMusicCurrentTrack === trackUrl && activePlayer.dataset.currentTrack === trackUrl) {
    if (activePlayer.paused) {
      const resumePromise = activePlayer.play();
      if (resumePromise && typeof resumePromise.catch === 'function') {
        resumePromise.catch(() => scheduleArchitectMusicRetry(trackUrl));
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
    playPromise
      .then(() => {
        architectMusicPendingTrack = '';
        architectMusicRetryAttempts = 0;
      })
      .catch(() => {
        try {
          nextPlayer.pause();
          nextPlayer.volume = 0;
        } catch (e) {}
        scheduleArchitectMusicRetry(trackUrl);
      });
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

function renderArchitectActionResult(actionType, data) {
  const host = document.getElementById('eventExplanation');
  if (!host || !data) return;

  if (architectActionResultTimer) {
    clearTimeout(architectActionResultTimer);
    architectActionResultTimer = null;
  }

  const isCorrect = data.is_correct !== false;
  const damage = Number(data.damage_dealt || 0);
  const support = Number(data.support_value || 0);
  const hp = Number(data.current_hp || 0);
  const phase = Number(data.phase || 1);
  const pressure = Number(data.overload_pressure || 0);
  const isWildAi = data.code === 'wildai_breach';

  let title = 'ДЕЙСТВИЕ ПРИНЯТО';
  let value = '';
  if (isWildAi) {
    if (!isCorrect) {
      title = 'СБОЙ ОПЕРАЦИИ';
      value = damage > 0 ? `+${damage} ЦЕЛОСТНОСТЬ` : 'эффект не применён';
    } else if (actionType === 'attack' || actionType === 'protocol') {
      title = actionType === 'protocol' ? 'ПРОТОКОЛ СРАБОТАЛ' : 'УЗЕЛ ПОРАЖЁН';
      value = `+${damage} ЦЕЛОСТНОСТЬ`;
    } else if (actionType === 'stabilize') {
      title = 'СЕКТОР ЗАЛАТАН';
      value = `−${WILD_AI_BREACH_INFECTION_STABILIZE_REDUCTION} ЗАРАЖЕНИЕ`;
    } else if (actionType === 'sync') {
      title = 'СКАНИРОВАНИЕ';
      value = `−${WILD_AI_BREACH_INFECTION_SYNC_REDUCTION} ЗАРАЖЕНИЕ`;
    }

    host.className = `event-explanation event-action-result ${isCorrect ? 'is-success' : 'is-fail'}`;
    host.style.display = 'block';
    host.innerHTML = `
      <div class="event-action-result-title">${escapeHtml(title)}</div>
      <div class="event-action-result-value">${escapeHtml(value)}</div>
      <div class="event-action-result-meta">
        <span>ЦЕЛОСТНОСТЬ: ${hp}</span>
        <span>ЗАРАЖЕНИЕ: ${pressure}/${WILD_AI_BREACH_INFECTION_THRESHOLD}</span>
      </div>
    `;
  } else {
    if (!isCorrect) {
      title = 'ОШИБКА ПРОТОКОЛА';
      value = 'урон не прошёл';
    } else if (actionType === 'attack' || actionType === 'protocol') {
      title = actionType === 'protocol' ? 'ПРОТОКОЛ ПРОБИТ' : 'АТАКА ПРОШЛА';
      value = `-${damage} HP`;
    } else if (actionType === 'stabilize') {
      title = 'СТАБИЛИЗАЦИЯ';
      value = `+${support} SUPPORT`;
    } else if (actionType === 'sync') {
      title = 'СИНХРОНИЗАЦИЯ';
      value = `+${support} SUPPORT`;
    }

    host.className = `event-explanation event-action-result ${isCorrect ? 'is-success' : 'is-fail'}`;
    host.style.display = 'block';
    host.innerHTML = `
      <div class="event-action-result-title">${escapeHtml(title)}</div>
      <div class="event-action-result-value">${escapeHtml(value)}</div>
      <div class="event-action-result-meta">
        <span>HP: ${hp}</span>
        <span>PHASE: ${phase}</span>
        <span>OVR: ${pressure}</span>
      </div>
    `;
  }

  architectActionResultTimer = setTimeout(() => {
    if (host.classList.contains('event-action-result')) {
      host.style.display = 'none';
      host.textContent = '';
      host.className = 'event-explanation';
    }
    architectActionResultTimer = null;
  }, 4200);
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
    'event-state-lobby',
    'event-state-active',
    'event-state-registration',
    'event-state-terminal',
    'event-state-finished',
    'event-state-failed',
    'event-wildai-lobby',
    'event-phase-1',
    'event-phase-2',
    'event-phase-3',
    'event-overload-high',
    'event-overload-critical'
  );

  if (!eventData) {
    overlay.classList.add('event-state-lobby');
    if (typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach') {
      overlay.classList.add('event-wildai-lobby');
    }
    const standbyImg = document.getElementById('eventBossImage');
    if (standbyImg) standbyImg.classList.remove('result-image-reveal');
    architectLastRenderedPhase = null;
    architectLastLogCount = 0;
    updateArchitectFinalTimer(null);
    if (warning) warning.style.display = 'none';
    return;
  }

  const state = String(eventData.state || '').toUpperCase();
  const isActive = state === 'ACTIVE';
  const isTerminal = state === 'FAILED' || state === 'FINISHED';
  const phase = Math.max(1, Math.min(3, Number(eventData.phase || 1)));
  const overload = Number(eventData.overload_pressure || 0);

  // The result screen tags the boss image with result-image-reveal whose
  // animation is !important and one-shot — if it lingers into a new lobby it
  // freezes the image and kills the lobby glitch FX. Strip it outside results.
  if (!isTerminal) {
    const bossImg = document.getElementById('eventBossImage');
    if (bossImg) bossImg.classList.remove('result-image-reveal');
  }

  const isWildAi = eventData.code === 'wildai_breach';

  overlay.classList.toggle('event-state-lobby', state === 'REGISTRATION');
  overlay.classList.toggle('event-state-active', isActive);
  overlay.classList.toggle('event-state-registration', state === 'REGISTRATION');
  overlay.classList.toggle('event-state-terminal', isTerminal);
  overlay.classList.toggle('event-state-finished', state === 'FINISHED');
  overlay.classList.toggle('event-state-failed', state === 'FAILED');
  overlay.classList.toggle('event-wildai-lobby', isWildAi && state === 'REGISTRATION');
  overlay.classList.toggle('event-wildai', isWildAi);

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

function playWildAiLoseSound(eventData) {
  if (!eventData || eventData.code !== 'wildai_breach' || eventData.state !== 'FAILED') return;
  const key = `${eventData.id}_${eventData.state}`;
  if (wildAiLoseSoundPlayedFor === key) return;
  try {
    const audio = new Audio(WILD_AI_BREACH_LOSE_SOUND);
    audio.volume = 0.9;
    const maybePromise = audio.play();
    if (maybePromise && typeof maybePromise.then === 'function') {
      maybePromise.then(() => {
        wildAiLoseSoundPlayedFor = key;
      }).catch(() => {
        // playback blocked (e.g. autoplay policy) — retry on next render
      });
    } else {
      wildAiLoseSoundPlayedFor = key;
    }
  } catch (e) {}
}

function applyArchitectMedia(eventData) {
  const bossImage = document.getElementById('eventBossImage');
  const bossVideo = document.getElementById('eventBossVideo');
  const hudAvatar = document.getElementById('eventHudAvatar');
  const videoSrc = getArchitectPhaseVideo(eventData);
  const imageSrc = getArchitectPhaseImage(eventData);

  if (bossImage) {
    bossImage.src = imageSrc;
    // Keep the static image visible until the video actually starts playing —
    // hiding it immediately caused a black-screen flash while the video decoder spins up.
    if (!videoSrc) bossImage.style.display = 'block';
  }

  if (bossVideo) {
    bossVideo.loop = true;
    bossVideo.muted = true;
    bossVideo.playsInline = true;
    if (videoSrc) {
      const isNewSrc = bossVideo.dataset.currentSrc !== videoSrc;
      if (isNewSrc) {
        bossVideo.pause();
        bossVideo.style.display = 'none';
        clearTimeout(architectVideoStartTimer);
        // Stagger the heavy video load/play so it doesn't compete with the
        // entry-banner sting and lobby/phase music starting almost simultaneously —
        // that pile-up of media inits is what crashed the WebView to a black screen.
        architectVideoStartTimer = setTimeout(() => {
          bossVideo.src = videoSrc;
          bossVideo.dataset.currentSrc = videoSrc;
          bossVideo.load();
          const maybePromise = bossVideo.play();
          if (maybePromise && typeof maybePromise.catch === 'function') {
            maybePromise.catch(() => {});
          }
          bossVideo.addEventListener('playing', function onPlaying() {
            bossVideo.removeEventListener('playing', onPlaying);
            bossVideo.style.display = 'block';
            if (bossImage) bossImage.style.display = 'none';
            playWildAiLoseSound(eventData);
          });
        }, 450);
      } else {
        bossVideo.style.display = 'block';
        if (bossImage) bossImage.style.display = 'none';
        const maybePromise = bossVideo.play();
        if (maybePromise && typeof maybePromise.catch === 'function') {
          maybePromise.catch(() => {});
        }
        playWildAiLoseSound(eventData);
      }
    } else {
      clearTimeout(architectVideoStartTimer);
      bossVideo.pause();
      bossVideo.removeAttribute('src');
      bossVideo.dataset.currentSrc = '';
      bossVideo.style.display = 'none';
      bossVideo.load();
    }
  }

  if (hudAvatar) {
    hudAvatar.style.backgroundImage = `url('${imageSrc}')`;
  }

  syncArchitectMusic(eventData);
}

async function loadCurrentArchitectEvent() {
  try {
    const code = (typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach')
      ? 'wildai_breach'
      : 'architect';
    const res = await fetch(`${API_URL}/api/events/current?code=${encodeURIComponent(code)}`);
    const data = await res.json();

    currentArchitectEvent = data.event || null;
    currentArchitectEventId = currentArchitectEvent ? currentArchitectEvent.id : null;

    renderArchitectLobby(currentArchitectEvent);
  } catch (e) {
    renderArchitectLobby(null, 'Не удалось загрузить событие.');
  }
}

function scheduleArchitectResultReveal(lobbyCard, eventData) {
  const revealKey = `arch_result_${eventData.id}_${eventData.state}`;
  const alreadySeen = sessionStorage.getItem(revealKey);

  // Already seen this result — show immediately, no delay
  if (alreadySeen) {
    lobbyCard.style.display = 'block';
    lobbyCard.classList.remove('result-banner-hidden', 'result-banner-reveal');
    return;
  }

  // Timer already running for this key — keep card hidden, don't restart
  if (architectResultRevealEventKey === revealKey) {
    lobbyCard.style.display = 'block';
    lobbyCard.classList.add('result-banner-hidden');
    return;
  }

  // Cancel any previous timer (different event/state)
  if (architectResultRevealTimer) {
    clearTimeout(architectResultRevealTimer);
    architectResultRevealTimer = null;
  }
  architectResultRevealEventKey = revealKey;

  // Show card but invisible — prevents layout flash
  lobbyCard.style.display = 'block';
  lobbyCard.classList.add('result-banner-hidden');
  lobbyCard.classList.remove('result-banner-reveal');

  // Animate result image entrance
  const img = document.getElementById('eventBossImage');
  if (img) {
    img.classList.remove('result-image-reveal');
    void img.offsetWidth;
    img.classList.add('result-image-reveal');
  }

  // Reveal banner after delay; the WildAI defeat plays a ~10s loss video,
  // so the banner waits for it to finish instead of cutting in mid-playback.
  const isWildAiFail = eventData.code === 'wildai_breach' && eventData.state === 'FAILED';
  const revealDelay = isWildAiFail ? WILD_AI_LOSE_REVEAL_DELAY : ARCHITECT_RESULT_REVEAL_DELAY;
  architectResultRevealTimer = setTimeout(() => {
    lobbyCard.classList.remove('result-banner-hidden');
    lobbyCard.classList.add('result-banner-reveal');
    sessionStorage.setItem(revealKey, '1');
    architectResultRevealTimer = null;
    architectResultRevealEventKey = null;
  }, revealDelay);
}

function renderArchitectLobby(eventData, errorText = '') {
  const lobbyCard = document.getElementById('eventLobbyCard');
  const overlay = document.getElementById('eventOverlay');
  if (!lobbyCard) return;

  // The standby screen below replaces lobbyCard.innerHTML and destroys the
  // lobby elements (status, team list, buttons). Keep the original markup so
  // it can be restored when a real event needs to render afterwards.
  if (!window._eventLobbyMarkup && document.getElementById('eventStatusText')) {
    window._eventLobbyMarkup = lobbyCard.innerHTML;
  }

  const hintIsWildAi = typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach';
  if (eventData && (eventData.code === 'wildai_breach') !== hintIsWildAi) {
    eventData = null;
  }

  if (!eventData) {
    if (overlay) overlay.classList.remove('event-terminal');
    lobbyCard.classList.remove('event-result-card', 'event-result-win', 'event-result-lose');
    lobbyCard.style.display = 'block';

    if (hintIsWildAi) {
      lobbyCard.innerHTML = `
        <div class="event-standby-screen">
          <div class="event-standby-kicker">⚠ WILD AI BREACH // STANDBY</div>
          <div class="event-standby-title">${errorText || 'BLACKWALL ОНЛАЙН'}</div>
          <div class="event-standby-sub">Операция не активна. Вторжение Дикого ИИ пока не зафиксировано.</div>
          ${isAdmin ? `<button class="event-standby-create-btn" onclick="createWildAiEvent()">⚠ WILD AI BREACH // ОПЕРАЦИЯ ВЫТЕСНЕНИЯ</button>` : ''}
        </div>`;
    } else {
      lobbyCard.innerHTML = `
        <div class="event-standby-screen">
          <div class="event-standby-kicker">⬡ ARCHITECT PROTOCOL // STANDBY</div>
          <div class="event-standby-title">${errorText || 'СИСТЕМА ГОТОВА'}</div>
          <div class="event-standby-sub">Ивент не активен. Дождитесь запуска Архитектора.</div>
          ${isAdmin ? `<button class="event-standby-create-btn" onclick="createArchitectEvent()">⚡ ИНИЦИИРОВАТЬ ПРОТОКОЛ</button>` : ''}
        </div>`;
    }
    updateArchitectBattleVisibility(null);
    return;
  }

  // Standby screen wiped the lobby markup earlier — restore it before rendering
  if (!document.getElementById('eventStatusText') && window._eventLobbyMarkup) {
    lobbyCard.innerHTML = window._eventLobbyMarkup;
  }

  const statusEl = document.getElementById('eventStatusText');
  const rewardEl = document.getElementById('eventRewardText');
  const teamCountEl = document.getElementById('eventTeamCount');
  const teamListEl = document.getElementById('eventTeamList');
  const createBtn = document.getElementById('eventCreateBtn');
  const joinBtn = document.getElementById('eventJoinBtn');
  const leaveBtn = document.getElementById('eventLeaveBtn');
  const startBtn = document.getElementById('eventStartBtn');
  const kickerEl = lobbyCard.querySelector('.event-lobby-kicker');
  const labelEls = lobbyCard.querySelectorAll('.event-lobby-label');

  if (!statusEl || !rewardEl || !teamCountEl || !teamListEl || !createBtn || !joinBtn || !leaveBtn || !startBtn) {
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
  const showLobbyCard = eventData.state === 'REGISTRATION' || isTerminal;

  if (overlay) {
    overlay.classList.toggle('event-terminal', isTerminal);
  }

  lobbyCard.classList.toggle('event-result-card', isTerminal);
  lobbyCard.classList.toggle('event-result-win', eventData.state === 'FINISHED');
  lobbyCard.classList.toggle('event-result-lose', eventData.state === 'FAILED');

  if (isTerminal && showLobbyCard) {
    scheduleArchitectResultReveal(lobbyCard, eventData);
  } else {
    lobbyCard.style.display = showLobbyCard ? 'block' : 'none';
    lobbyCard.classList.remove('result-banner-hidden', 'result-banner-reveal');
  }

  const isWildAi = eventData.code === 'wildai_breach';
  const verdictEl = document.getElementById('eventResultVerdict');
  const verdictRow = document.getElementById('eventResultHeader');
  const subtextEl = document.getElementById('eventResultSubtext');
  if (verdictEl && verdictRow) {
    if (isTerminal) {
      if (isWildAi) {
        verdictEl.textContent = eventData.state === 'FINISHED' ? 'ЦЕЛОСТНОСТЬ ВОССТАНОВЛЕНА' : 'СИСТЕМА ЗАРАЖЕНА';
      } else {
        verdictEl.textContent = eventData.state === 'FINISHED' ? 'ПРОТОКОЛ ПРОБИТ' : 'МИССИЯ ПРОВАЛЕНА';
      }
      verdictRow.style.display = 'block';

      if (subtextEl) {
        if (isWildAi && eventData.state === 'FAILED') {
          subtextEl.textContent = 'Дикий ИИ прорвал BlackWall. Система перехвачена — приложение временно под контролем ИИ.';
          subtextEl.style.display = 'block';
        } else {
          subtextEl.style.display = 'none';
          subtextEl.textContent = '';
        }
      }
    } else {
      verdictRow.style.display = 'none';
      if (subtextEl) {
        subtextEl.style.display = 'none';
        subtextEl.textContent = '';
      }
    }
  }

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

  // Extra participants section (result only)
  const extraSection = document.getElementById('eventExtraSection');
  const extraList = document.getElementById('eventExtraList');
  const extraInputRow = document.getElementById('eventExtraInputRow');
  if (extraSection) {
    if (isTerminal) {
      extraSection.style.display = 'block';
      const extras = Array.isArray(eventData.extra_participants) ? eventData.extra_participants : [];
      if (extraList) {
        extraList.innerHTML = extras.length
          ? extras.map(n => `<div class="event-extra-item">
              <span>${escapeHtml(n)}</span>
              ${isAdmin ? `<button class="event-extra-remove" onclick="removeEventExtraParticipant(${eventData.id}, '${escapeHtml(n).replace(/'/g,"\\'")}')">✕</button>` : ''}
            </div>`).join('')
          : (isAdmin ? '' : '<div class="event-team-empty">—</div>');
      }
      if (extraInputRow) extraInputRow.style.display = isAdmin ? 'flex' : 'none';
    } else {
      extraSection.style.display = 'none';
    }
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
  const adminSoloReady = typeof isAdmin !== 'undefined' && isAdmin;
  const canJoin = eventData.state === 'REGISTRATION' && !isMember && teamCount < maxPlayers;
  const canLeave = eventData.state === 'REGISTRATION' && isMember;
  const canStart = eventData.state === 'REGISTRATION' &&
                   typeof isAdmin !== 'undefined' && isAdmin &&
                   (teamCount >= minPlayers || adminSoloReady);

  createBtn.style.display = (isAdmin && isTerminal) ? 'inline-flex' : 'none';
  if (isAdmin && isTerminal) {
    // The inline onclick in index.html is hardcoded to createArchitectEvent();
    // on a WildAI result screen it must create a WildAI event instead.
    createBtn.onclick = isWildAi ? createWildAiEvent : createArchitectEvent;
    createBtn.textContent = isWildAi ? 'Новая операция' : 'Создать';
  }
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
  const isWin = state === 'FINISHED';
  const resultLabel = isWin ? 'Награда разблокирована' : 'Протокол не пробит';
  const resultTone = isWin ? 'WIN' : 'FAIL';

  rewardEl.innerHTML = `
    <span class="event-result-reward-main">${escapeHtml(rewardText)}</span>
    <span class="event-result-reward-sub">${resultLabel}</span>
    <span class="event-result-summary">
      <span>${resultTone}</span>
      <span>${totalDamage} DMG</span>
      <span>${totalActions} ACTIONS</span>
    </span>
  `;

  const names = getArchitectTeamNameMap(eventData);
  const rows = Array.isArray(leaderboard) ? leaderboard.slice() : [];
  rows.sort((a, b) => {
    const damageDiff = Number(b.total_damage || 0) - Number(a.total_damage || 0);
    if (damageDiff) return damageDiff;
    return Number(b.total_support || 0) - Number(a.total_support || 0);
  });

  // No participation data — fall back to team roster
  if (!rows.length) {
    const members = Array.isArray(eventData.team_members) ? eventData.team_members : [];
    teamListEl.innerHTML = members.length
      ? `<div class="event-finale-empty">Статистика боя недоступна</div>` +
        members.map((member) => `<div class="event-finale-row event-finale-row-empty">
          <span class="event-finale-row-name">${escapeHtml(member.full_name || 'Аноним')}</span>
          <span class="event-finale-row-stat">—</span>
        </div>`).join('')
      : '<div class="event-team-empty">Команда не найдена</div>';
    return;
  }

  const mvp = rows[0];
  const mvpId = Number(mvp.telegram_id);
  const mvpDamage = Number(mvp.total_damage || 0);
  const mvpSupport = Number(mvp.total_support || 0);
  const mvpName = escapeHtml(names.get(mvpId) || `ID ${mvpId}`);
  const maxDamage = Math.max(1, mvpDamage);
  const hasMvp = mvpDamage > 0 || mvpSupport > 0;

  const mvpCard = hasMvp ? `
    <div class="event-finale-mvp ${isWin ? 'is-win' : 'is-fail'}">
      <div class="event-finale-mvp-crown">${isWin ? '♛' : '☠'}</div>
      <div class="event-finale-mvp-label">MVP // ОПЕРАТОР МИССИИ</div>
      <div class="event-finale-mvp-name">${mvpName}</div>
      <div class="event-finale-mvp-stats">
        <div class="event-finale-mvp-stat"><span>${mvpDamage}</span><label>DMG</label></div>
        <div class="event-finale-mvp-stat"><span>${mvpSupport}</span><label>SUP</label></div>
      </div>
    </div>
  ` : '';

  const board = rows.map((row, idx) => {
    const telegramId = Number(row.telegram_id);
    const name = escapeHtml(names.get(telegramId) || `ID ${telegramId}`);
    const damage = Number(row.total_damage || 0);
    const support = Number(row.total_support || 0);
    const isMvpRow = telegramId === mvpId && hasMvp;
    const pct = Math.round((damage / maxDamage) * 100);
    const place = String(idx + 1).padStart(2, '0');
    return `
      <div class="event-finale-row${isMvpRow ? ' is-mvp' : ''}">
        <div class="event-finale-row-head">
          <span class="event-finale-row-place">#${place}</span>
          <span class="event-finale-row-name">${name}</span>
          <span class="event-finale-row-stat">${damage} <small>DMG</small></span>
        </div>
        <div class="event-finale-row-bar"><div style="width:${pct}%;"></div></div>
        ${support > 0 ? `<div class="event-finale-row-sub">+${support} SUPPORT</div>` : ''}
      </div>
    `;
  }).join('');

  teamListEl.innerHTML = `
    ${mvpCard}
    <div class="event-finale-board-label">ОПЕРАТИВНАЯ СВОДКА</div>
    <div class="event-finale-board">${board}</div>
  `;
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
  const hasEvent = !!eventData;

  actions.style.display = isActive ? 'grid' : 'none';
  if (hud) hud.style.display = isActive ? 'flex' : 'none';
  if (log) log.style.display = isActive ? 'block' : 'none';
  if (bossImage) bossImage.style.display = 'block';
  const bossVideo = document.getElementById('eventBossVideo');
  if (bossVideo && !hasEvent) { bossVideo.pause(); bossVideo.style.display = 'none'; }
  if (!isActive) closeArchitectQuestion();

  if (!eventData) {
    applyArchitectMedia(null);
    const hintIsWildAi = typeof eventLobbyTabHint !== 'undefined' && eventLobbyTabHint === 'wildai_breach';
    const kickerEl = document.getElementById('eventKicker');
    const bossNameEl = document.getElementById('eventBossName');
    if (kickerEl) kickerEl.textContent = hintIsWildAi ? 'WILD AI BREACH' : 'ARCHITECT PROTOCOL';
    if (bossNameEl) bossNameEl.textContent = hintIsWildAi ? 'ДИКИЙ ИИ' : 'АРХИТЕКТОР';
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
  const isWildAi = eventData.code === 'wildai_breach';

  applyArchitectMedia(eventData);

  const kickerEl = document.getElementById('eventKicker');
  const bossNameEl = document.getElementById('eventBossName');
  if (kickerEl) kickerEl.textContent = isWildAi ? 'WILD AI BREACH' : 'ARCHITECT PROTOCOL';
  if (bossNameEl) bossNameEl.textContent = isWildAi ? (eventData.boss_name || 'ДИКИЙ ИИ') : 'АРХИТЕКТОР';

  hpText.textContent = `${currentHp} / ${maxHp}`;
  hpFill.style.width = `${hpPercent}%`;
  if (isWildAi) {
    const roman = {1: 'I', 2: 'II', 3: 'III'};
    const phase = eventData.phase || 1;
    phaseText.textContent = eventData.state === 'ACTIVE'
      ? `BREACH ${phase}`
      : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');
    phaseLabel.textContent = eventData.state === 'ACTIVE'
      ? `ВТОРЖЕНИЕ ${roman[phase] || phase}`
      : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');
  } else {
    phaseText.textContent = eventData.state === 'ACTIVE'
      ? `PHASE ${eventData.phase || 1}`
      : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');
    phaseLabel.textContent = eventData.state === 'ACTIVE'
      ? `ФАЗА ${eventData.phase || 1}`
      : (eventData.state === 'REGISTRATION' ? 'LOBBY' : 'END');
  }

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
    if (isWildAi) {
      vulnerabilityBadge.textContent = vulnerable ? 'НОДА ВСКРЫТА' : 'СКРЫТА';
    } else {
      vulnerabilityBadge.textContent = vulnerable ? 'VULNERABLE' : 'SHIELDED';
    }
    vulnerabilityBadge.className = 'event-status-badge';
    vulnerabilityBadge.classList.add(vulnerable ? 'gold' : 'hot');
  }

  if (overloadBadge) {
    const overload = Number(eventData.overload_pressure || 0);
    overloadBadge.textContent = isWildAi
      ? `ЗАРАЖЕНИЕ ${overload}/${WILD_AI_BREACH_INFECTION_THRESHOLD}`
      : `OVR ${overload}`;
  }

  const logs = Array.isArray(eventData.logs) ? eventData.logs : [];
  if (!logs.length) {
    if (architectLastLogCount !== 0) {
      log.innerHTML = '<div class="event-log-empty">Лог ивента появится здесь</div>';
      architectLastLogCount = 0;
    }
  } else {
    if (architectLastLogCount === 0) {
      log.innerHTML = logs.map(item =>
        `<div class="event-log-line">${escapeHtml(item.message || '')}</div>`
      ).join('');
      architectLastLogCount = logs.length;
    } else if (logs.length > architectLastLogCount) {
      const newItems = logs.slice(architectLastLogCount);
      newItems.forEach(item => {
        const div = document.createElement('div');
        div.className = 'event-log-line';
        div.textContent = item.message || '';
        log.appendChild(div);
      });
      architectLastLogCount = logs.length;
    }
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
      showToast(data.detail || 'Не удалось вступить в команду');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
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
      showToast(data.detail || 'Не удалось покинуть команду');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('warning'); } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

function createArchitectEvent() {
  if (!currentUserId || !isAdmin) return;
  const modal = document.getElementById('eventCreateModal');
  if (modal) {
    const input = document.getElementById('eventCreatePrizeInput');
    if (input) input.value = '';
    modal.style.display = 'flex';
    setTimeout(() => { if (input) input.focus(); }, 120);
    return;
  }
  // Fallback: tg.showPopup if modal not in DOM (old HTML cached)
  tg.showPopup({
    title: '🏆 ПРИЗ ИВЕНТА',
    message: 'Выбери или введи приз',
    buttons: [
      { id: 'ptc',    type: 'default', text: '🛍 Поход в ТЦ' },
      { id: 'cinema', type: 'default', text: '🎬 Кино' },
      { id: 'quest',  type: 'default', text: '🔐 Квест' },
      { type: 'cancel' }
    ]
  }, async (prizeId) => {
    if (!prizeId || prizeId === 'cancel') return;
    const map = { ptc: 'Поход в ТЦ', cinema: 'Поход в кино', quest: 'Квест-комната' };
    await _doCreateArchitectEvent(map[prizeId] || 'Приз не указан');
  });
}

function setCreateEventPreset(text) {
  const input = document.getElementById('eventCreatePrizeInput');
  if (input) { input.value = text; input.focus(); }
}

function closeCreateEventModal() {
  const modal = document.getElementById('eventCreateModal');
  if (modal) modal.style.display = 'none';
}

async function submitCreateArchitectEvent() {
  const input = document.getElementById('eventCreatePrizeInput');
  const rewardText = (input ? input.value : '').trim() || 'Приз не указан';
  closeCreateEventModal();
  await _doCreateArchitectEvent(rewardText);
}

async function _doCreateArchitectEvent(rewardText) {
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
      showToast(data.detail || 'Не удалось создать ивент');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

async function createWildAiEvent() {
  if (!currentUserId || !isAdmin) return;

  try {
    const res = await fetch(`${API_URL}/api/events/wildai/create`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Id': String(currentUserId || 0)
      },
      body: JSON.stringify({ telegram_id: currentUserId })
    });

    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Не удалось создать операцию');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
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
      showToast(data.detail || 'Не удалось запустить ивент');
      return;
    }

    currentArchitectEvent = data;
    currentArchitectEventId = data.id;
    renderArchitectLobby(data);

    try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

let pendingEventActionType = null;
let pendingEventQuestionId = null;
let pendingEventQuestion = null;
let isArchitectQuestionLoading = false;

async function requestArchitectQuestion(actionType) {
  if (!currentArchitectEventId || !currentUserId) return;

  // Immediate haptic so the button always feels responsive
  try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}

  const box = document.getElementById('eventQuestionBox');
  if (
    box &&
    box.style.display !== 'none' &&
    box.querySelector('.event-answer-feedback')
  ) {
    closeArchitectQuestion();
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

  // Show loading state on the button immediately
  const btn = document.querySelector(`.event-action.${actionType}`);
  if (btn) btn.classList.add('is-requesting');

  try {
    isArchitectQuestionLoading = true;

    const res = await fetch(
      `${API_URL}/api/events/${currentArchitectEventId}/question?telegram_id=${encodeURIComponent(currentUserId)}&action_type=${encodeURIComponent(actionType)}`
    );
    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Не удалось получить вопрос');
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
      showToast('Вопрос не найден');
      return;
    }

    pendingEventQuestionId = question.id;
    pendingEventQuestion = question;
    showArchitectQuestion(question);
  } catch (e) {
    showToast('Ошибка соединения');
  } finally {
    isArchitectQuestionLoading = false;
    if (btn) btn.classList.remove('is-requesting');
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
    <button class="event-option-btn" data-option="a" onclick="submitArchitectAnswer('a')"><span class="event-option-mark">01</span><span class="event-option-text">${escapeHtml(opts.a || '')}</span></button>
    <button class="event-option-btn" data-option="b" onclick="submitArchitectAnswer('b')"><span class="event-option-mark">02</span><span class="event-option-text">${escapeHtml(opts.b || '')}</span></button>
    <button class="event-option-btn" data-option="c" onclick="submitArchitectAnswer('c')"><span class="event-option-mark">03</span><span class="event-option-text">${escapeHtml(opts.c || '')}</span></button>
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

  // Capture and clear pending state immediately — prevents stale state if this
  // function is re-entered or if an error/timer fires mid-flight.
  const actionType = pendingEventActionType;
  const questionId = pendingEventQuestionId;
  pendingEventActionType = null;
  pendingEventQuestionId = null;
  pendingEventQuestion = null;

  try {
    const payload = {
      event_id: currentArchitectEventId,
      telegram_id: currentUserId,
      action_type: actionType,
      use_active_modifier: false
    };

    if (actionType !== 'sync') {
      payload.question_id = questionId;
      payload.answer_option = answerOption;
    }

    const res = await fetch(`${API_URL}/api/events/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!res.ok) {
      showToast(data.detail || 'Не удалось отправить действие');
      return;
    }

    triggerArchitectActionFx(actionType, data.is_correct !== false);
    renderArchitectActionResult(actionType, data);

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
    }

    await loadCurrentArchitectEvent();

    try {
      tg.HapticFeedback.notificationOccurred(data.is_correct === false ? 'error' : 'success');
    } catch (e) {}
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

// ── Extra participants (admin adds names to trip list after FINISHED) ───

async function addEventExtraParticipant() {
  const input = document.getElementById('eventExtraInput');
  const name = input ? input.value.trim() : '';
  if (!name) { showToast('Введи имя участника'); return; }
  const eventId = currentArchitectEvent && currentArchitectEvent.id;
  if (!eventId) return;
  try {
    const r = await fetch(`${API_URL}/api/events/${eventId}/extra`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Id': String(currentUserId) },
      body: JSON.stringify({ name, action: 'add' }),
    });
    if (!r.ok) { showToast('Ошибка'); return; }
    const data = await r.json();
    if (input) input.value = '';
    if (currentArchitectEvent) currentArchitectEvent.extra_participants = data.extra_participants;
    renderArchitectLobby(currentArchitectEvent);
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
  } catch(e) { showToast('Ошибка соединения'); }
}

async function removeEventExtraParticipant(eventId, name) {
  try {
    const r = await fetch(`${API_URL}/api/events/${eventId}/extra`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Id': String(currentUserId) },
      body: JSON.stringify({ name, action: 'remove' }),
    });
    if (!r.ok) return;
    const data = await r.json();
    if (currentArchitectEvent) currentArchitectEvent.extra_participants = data.extra_participants;
    renderArchitectLobby(currentArchitectEvent);
  } catch(e) {}
}

// ===== Боевые бонусы имплантов/карточек в ивентах =====

const EVENT_COMBAT_ITEM_CATALOG = {
  implant_red_dragon: { icon: '🐉', name: 'Красный Дракон', desc: '+20% урона на Атаке/Протоколе' },
  implant_shaolin:    { icon: '🥋', name: 'Шаолинь', desc: '+10% урона на Атаке' },
  implant_linguasoft: { icon: '🎙', name: 'Linguasoft', desc: '+10% урона на Протоколе' },
  card_pyro:          { icon: '🔥', name: 'Страж Огня', desc: '+10% урона на Атаке' },
  card_literature:    { icon: '📖', name: 'Звезда Литературы', desc: '+10% урона на Протоколе' },
  card_star:          { icon: '⭐', name: 'Императорская Звезда', desc: '+1 урон при верном ответе' },
  implant_terracota:  { icon: '🗿', name: 'Терракота', desc: '-20% к росту перегрузки/заражения при ошибке' },
  card_forest:        { icon: '🌲', name: 'Дух Леса', desc: '-20% к росту перегрузки/заражения при ошибке' },
  implant_guanxi:     { icon: '🤝', name: 'Гуаньси', desc: '+1 поддержка при Синхронизации' },
  card_sea:           { icon: '🌊', name: 'Дух Морей', desc: '+1 поддержка при Синхронизации' },
  implant_caishen:    { icon: '💰', name: 'Цайшэнь', desc: '+2 поддержка при Стабилизации' },
  card_fairy:         { icon: '🌸', name: 'Небесная Фея', desc: '+2 поддержка при Стабилизации' },
  implant_panda:      { icon: '🐼', name: 'Панда', desc: '+1 поддержка при Синхронизации/Стабилизации' },
  card_fox:           { icon: '🦊', name: 'Лиса-Оборотень', desc: '+1 поддержка при Синхронизации/Стабилизации' },
  implant_qilin:      { icon: '🐲', name: 'Цилинь', desc: '+5% урона команде, если 2+ в команде с этим предметом' },
  card_moon:          { icon: '🌙', name: 'Богиня Луны', desc: '+5% урона команде, если 2+ в команде с этим предметом' },
  card_zhongli:       { icon: '⛰', name: 'Архонт Земли', desc: 'Доп. -1 к перегрузке/заражению при Стабилизации/Синхронизации' },
  implant_netwatch:   { icon: '🔴', name: 'Сетевой Дозор', desc: 'Удачная Синхронизация продлевает окно уязвимости на +30с' },
};

const EVENT_COMBAT_BONUSES_ENABLED = true;

async function loadEventActiveBonuses() {
  const box = document.getElementById('eventActiveBonuses');
  if (!box || !currentUserId) return;

  if (!EVENT_COMBAT_BONUSES_ENABLED ||
      (currentArchitectEvent && currentArchitectEvent.code === 'wildai_breach')) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }

  try {
    const [implantsRes, cardsRes] = await Promise.all([
      fetch(`${API_URL}/api/casino/implants/${currentUserId}`),
      fetch(`${API_URL}/api/cards/${currentUserId}`),
    ]);
    const implants = implantsRes.ok ? await implantsRes.json() : [];
    const cards = cardsRes.ok ? await cardsRes.json() : [];
    const ids = new Set([
      ...(Array.isArray(implants) ? implants.map(i => i.implant_id) : []),
      ...(Array.isArray(cards) ? cards.map(c => c.card_id) : []),
    ]);

    const active = Object.keys(EVENT_COMBAT_ITEM_CATALOG).filter(id => ids.has(id));
    if (!active.length) {
      box.style.display = 'none';
      box.innerHTML = '';
      return;
    }
    box.style.display = 'flex';
    box.innerHTML = active.map(id => {
      const item = EVENT_COMBAT_ITEM_CATALOG[id];
      return `<span class="event-bonus-badge" title="${escapeHtml(item.desc)}">${item.icon} ${escapeHtml(item.name)}</span>`;
    }).join('');
  } catch (e) {
    box.style.display = 'none';
  }
}

function buildEventBonusTableHtml() {
  const rows = Object.values(EVENT_COMBAT_ITEM_CATALOG).map(item =>
    `<tr><td>${item.icon} ${escapeHtml(item.name)}</td><td>${escapeHtml(item.desc)}</td></tr>`
  ).join('');
  return `<table class="event-bonus-table">${rows}</table>`;
}

function openEventInfoModal() {
  const modal = document.getElementById('eventInfoModal');
  const body = document.getElementById('eventInfoModalBody');
  if (!modal || !body) return;

  const isWildAi = currentArchitectEvent && currentArchitectEvent.code === 'wildai_breach';

  let title, intro;
  if (isWildAi) {
    title = '⚠ WILD AI BREACH // СПРАВКА';
    intro = `
      <div class="event-info-text">
        Дикий ИИ прорвался в систему. Команда восстанавливает <b>Целостность системы</b> (атака/протокол)
        и сдерживает <b>Заражение</b> (синхронизация/стабилизация снижают, ошибки и время повышают).<br><br>
        Заражение растёт само по времени. Если оно достигнет 100% или истечёт лимит времени —
        операция провалена и активируется режим Wild AI Breach (хаос на 3 дня).<br>
        Если Целостность дойдёт до 0 — Дикий ИИ вытеснен, команда получает награду.
      </div>`;
  } else {
    title = '⬡ ARCHITECT PROTOCOL // СПРАВКА';
    intro = `
      <div class="event-info-text">
        Командный бой против Архитектора. <b>Атака</b> и <b>Протокол</b> наносят урон,
        <b>Синхронизация</b> открывает окна уязвимости, <b>Стабилизация</b> сдерживает перегрузку.<br><br>
        У Архитектора 3 фазы — с каждой фазой растёт сложность и эффекты перегрузки.
        Если перегрузка достигает критического порога в финальной фазе и не сбита вовремя — миссия провалена.
      </div>`;
  }

  body.innerHTML = `
    <div class="event-info-title">${title}</div>
    ${intro}
    <div class="event-info-section">ИМПЛАНТЫ И КАРТОЧКИ В БОЮ</div>
    <div class="event-info-text">Активные предметы из инвентаря дают пассивные бонусы в бою:</div>
    ${buildEventBonusTableHtml()}
  `;

  modal.style.display = 'flex';
}

function closeEventInfoModal(e) {
  if (e && e.target && e.target.id !== 'eventInfoModal') return;
  const modal = document.getElementById('eventInfoModal');
  if (modal) modal.style.display = 'none';
}
