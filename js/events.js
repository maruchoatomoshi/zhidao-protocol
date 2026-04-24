function openEventOverlay() {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  overlay.style.display = 'block';

  const nav = document.querySelector('.bottom-nav');
  if (nav) nav.style.display = 'none';

  document.body.style.overflow = 'hidden';
  setArchitectAmbientVisibility(false);
  architectMusicUnlocked = true;
  openArchitectEventEntryBanner();

  const log = document.getElementById('eventLog');
  if (log) {
    log.innerHTML = `<div class="event-log-empty">Загрузка состояния ивента...</div>`;
  }

  setEventExplanation('');
  loadCurrentArchitectEvent();
}

function closeEventOverlay() {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  overlay.style.display = 'none';

  const nav = document.querySelector('.bottom-nav');
  if (nav) nav.style.display = '';

  document.body.style.overflow = '';
  setArchitectAmbientVisibility(true);
  closeArchitectEventEntryBanner();

  const bossVideo = document.getElementById('eventBossVideo');
  if (bossVideo) {
    bossVideo.pause();
  }

  stopArchitectMusic();
}

let architectEventEntryBannerTimer = null;

function openArchitectEventEntryBanner() {
  const overlay = document.getElementById('architectEventEntryBanner');
  const audio = document.getElementById('architectEventEntryAudio');
  if (!overlay) return;

  overlay.classList.add('show');

  if (architectEventEntryBannerTimer) {
    clearTimeout(architectEventEntryBannerTimer);
  }

  if (audio) {
    try {
      audio.pause();
      audio.currentTime = 0;
      audio.volume = 0.95;
      const maybePromise = audio.play();
      if (maybePromise && typeof maybePromise.catch === 'function') {
        maybePromise.catch(() => {});
      }
    } catch (e) {}
  }

  try { tg.HapticFeedback.notificationOccurred('warning'); } catch (e) {}

  architectEventEntryBannerTimer = setTimeout(() => {
    closeArchitectEventEntryBanner();
  }, 5200);
}

function closeArchitectEventEntryBanner() {
  const overlay = document.getElementById('architectEventEntryBanner');
  const audio = document.getElementById('architectEventEntryAudio');

  if (architectEventEntryBannerTimer) {
    clearTimeout(architectEventEntryBannerTimer);
    architectEventEntryBannerTimer = null;
  }

  if (overlay) {
    overlay.classList.remove('show');
  }

  if (audio) {
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (e) {}
  }
}

async function loadCurrentEvent() {
  try {
    setEventLoading(true);

    const r = await fetch(`${API_URL}/api/events/current`);
    const data = await r.json();

    if (!r.ok || !data.event) {
      const log = document.getElementById('eventLog');
      if (log) {
        log.innerHTML = `<div class="event-log-empty">Не удалось загрузить ивент</div>`;
      }
      return;
    }

    renderEventOverlay(data.event);
  } catch (e) {
    console.error('Не удалось загрузить ивент', e);

    const log = document.getElementById('eventLog');
    if (log) {
      log.innerHTML = `<div class="event-log-empty">Ошибка соединения с ивентом</div>`;
    }
  } finally {
    setEventLoading(false);
  }
}

function renderEventOverlay(event) {
  if (!event) return;

  if (typeof event.id === 'number') {
    currentEventId = event.id;
  }

  if (typeof event.max_hp === 'number') {
    currentEventMaxHp = event.max_hp;
  }

  applyArchitectMedia(event);
}

let currentEventId = 1;
let currentEventAction = null;
let currentEventQuestion = null;
let currentEventMaxHp = 1000;

async function eventAction(actionType) {
  currentEventAction = actionType;

  if (!currentUserId) {
    tg.showAlert('Откройте приложение через Telegram бота');
    return;
  }

  if (actionType === 'sync') {
    await submitEventAction({ action_type: 'sync' });
    return;
  }

  await loadEventQuestion(actionType);
}

async function loadEventQuestion(actionType) {
  try {
    const r = await fetch(`${API_URL}/api/events/${currentEventId}/question?telegram_id=${currentUserId}&action_type=${actionType}`);
    const data = await r.json();

    if (!r.ok || !data.question) {
      tg.showAlert('Не удалось получить вопрос для действия');
      return;
    }

    currentEventQuestion = data.question;
    renderEventQuestion(data.question);
  } catch (e) {
    console.error('Ошибка загрузки вопроса ивента', e);
    tg.showAlert('Ошибка загрузки вопроса');
  }
}

function renderEventQuestion(question) {
  const box = document.getElementById('eventQuestionBox');
  const prompt = document.getElementById('eventQuestionPrompt');
  const options = document.getElementById('eventOptions');

  if (!box || !prompt || !options) return;

  prompt.textContent = question.prompt || 'Вопрос';

  const entries = Object.entries(question.options || {});
  options.innerHTML = entries.map(([key, value]) => `
    <button class="event-option-btn" onclick="submitEventAnswer('${key}')">
      <strong>${key.toUpperCase()}.</strong> ${value}
    </button>
  `).join('');

  box.style.display = 'block';
}

async function submitEventAnswer(answerOption) {
  if (!currentEventQuestion || !currentEventAction) return;

  await submitEventAction({
    action_type: currentEventAction,
    question_id: currentEventQuestion.id,
    answer_option: answerOption
  });

  const box = document.getElementById('eventQuestionBox');
  if (box) box.style.display = 'none';

  currentEventQuestion = null;
  currentEventAction = null;
}

async function submitEventAction({ action_type, question_id = null, answer_option = null }) {
  try {
    setEventLoading(true);

    const payload = {
      event_id: currentEventId,
      telegram_id: currentUserId,
      action_type,
      use_active_modifier: false
    };

    if (question_id !== null) payload.question_id = question_id;
    if (answer_option !== null) payload.answer_option = answer_option;

    const r = await fetch(`${API_URL}/api/events/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await r.json();

    if (!r.ok) {
      tg.showAlert(data.detail || 'Не удалось выполнить действие');
      return;
    }

    renderEventActionResult(data);
  } catch (e) {
    console.error('Ошибка действия ивента', e);
    tg.showAlert('Ошибка соединения с ивентом');
  } finally {
    setEventLoading(false);
  }
}

function renderEventActionResult(data) {
  const hpFill = document.getElementById('eventHpFill');
  const hpText = document.getElementById('eventHpText');
  const phaseText = document.getElementById('eventPhaseText');
  const phaseLabel = document.getElementById('eventPhaseLabel');
  const bossImage = document.getElementById('eventBossImage');
  const log = document.getElementById('eventLog');
  const stateBadge = document.getElementById('eventStateBadge');

  const vulnerabilityBadge = document.getElementById('eventVulnerabilityBadge');
  const overloadBadge = document.getElementById('eventOverloadBadge');

  if (hpFill && typeof data.current_hp === 'number') {
    hpFill.style.width = `${Math.max(0, Math.min(100, (data.current_hp / currentEventMaxHp) * 100))}%`;
  }

  if (hpText && typeof data.current_hp === 'number') {
    hpText.textContent = `${data.current_hp} / ${currentEventMaxHp}`;
  }

  if (phaseText && data.phase) {
    phaseText.textContent = `PHASE ${data.phase}`;
  }

  if (phaseLabel && data.phase) {
    const roman = {1: 'I', 2: 'II', 3: 'III'};
    phaseLabel.textContent = `ФАЗА ${roman[data.phase] || data.phase}`;
  }

  if (stateBadge && data.state) {
    const state = String(data.state || '').toUpperCase();
    stateBadge.textContent = state || 'UNKNOWN';
    stateBadge.className = 'event-status-badge';
    if (state === 'ACTIVE') stateBadge.classList.add('green');
    if (state === 'REGISTRATION') stateBadge.classList.add('gold');
    if (state === 'FAILED' || state === 'FINISHED') stateBadge.classList.add('hot');
  }

  if (vulnerabilityBadge) {
    const vulnerable = !!data.vulnerability_active;
    vulnerabilityBadge.textContent = vulnerable ? 'VULNERABLE' : 'SHIELDED';
    vulnerabilityBadge.className = 'event-status-badge';
    vulnerabilityBadge.classList.add(vulnerable ? 'gold' : 'hot');
  }

  if (overloadBadge) {
    overloadBadge.textContent = `OVR ${data.overload_pressure ?? 0}`;
  }

  if (bossImage && data.phase) {
    if (data.phase === 1) {
      bossImage.src = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase1.png';
    } else if (data.phase === 2) {
      bossImage.src = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase2.png';
    } else {
      bossImage.src = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/Architect_phase3.png';
    }
  }

  if (log && Array.isArray(data.logs)) {
    log.innerHTML = data.logs.map(item => `
      <div class="event-log-item">${item.message}</div>
    `).join('');
    log.scrollTop = 0;
  }
}

function setEventLoading(isLoading) {
  const shell = document.querySelector('#eventOverlay .event-shell');

  if (shell) {
    shell.classList.toggle('event-loading', !!isLoading);
  }
}

function setEventExplanation(text) {
  const box = document.getElementById('eventExplanation');
  if (!box) return;

  if (text && String(text).trim()) {
    box.style.display = 'block';
    box.textContent = text;
  } else {
    box.style.display = 'none';
    box.textContent = '';
  }
}
