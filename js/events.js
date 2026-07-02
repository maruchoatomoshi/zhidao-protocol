let architectEventPublicEnabled = !!window.ARCHITECT_EVENT_ENABLED;
let wildAiEventPublicEnabled = !!window.WILDAI_EVENT_ENABLED;
let mjuEventPublicEnabled = !!window.MJU_EVENT_ENABLED;
let eventLobbyTabHint = 'architect';

function isArchitectEventPublicEnabled() {
  return !!architectEventPublicEnabled;
}

function isWildAiEventPublicEnabled() {
  return !!wildAiEventPublicEnabled;
}

function isMjuEventPublicEnabled() {
  return !!mjuEventPublicEnabled;
}

function canOpenArchitectEvent() {
  return isAdmin || isArchitect || isArchitectEventPublicEnabled();
}

function canOpenWildAiEvent() {
  const wildAiBreach = typeof isWildAiBreachActive === 'function' && isWildAiBreachActive();
  return isAdmin || isArchitect || isWildAiEventPublicEnabled() || wildAiBreach;
}

function canOpenMjuEvent() {
  return isAdmin || isArchitect || isMjuEventPublicEnabled();
}

function syncArchitectEventAvailability(enabled) {
  if (typeof enabled === 'boolean') {
    architectEventPublicEnabled = enabled;
    window.ARCHITECT_EVENT_ENABLED = enabled;
  }

  const visible = canOpenArchitectEvent();
  const card = document.getElementById('homeArchitectEventCard');
  if (card) {
    card.style.display = visible ? 'block' : 'none';
    card.classList.toggle('event-disabled-admin-view', !isArchitectEventPublicEnabled() && (isAdmin || isArchitect));
  }

  const status = document.getElementById('adminArchitectEventStatus');
  if (status) {
    status.textContent = isArchitectEventPublicEnabled()
      ? 'STATUS // PUBLIC ACCESS ENABLED'
      : 'STATUS // HIDDEN FROM STUDENTS';
    status.classList.toggle('enabled', isArchitectEventPublicEnabled());
  }
}

function syncWildAiEventAvailability(enabled) {
  if (typeof enabled === 'boolean') {
    wildAiEventPublicEnabled = enabled;
    window.WILDAI_EVENT_ENABLED = enabled;
  }

  const visible = canOpenWildAiEvent();
  const wildAiCard = document.getElementById('homeWildAiEventCard');
  if (wildAiCard) {
    wildAiCard.style.display = visible ? 'block' : 'none';
    wildAiCard.classList.toggle('event-disabled-admin-view', !isWildAiEventPublicEnabled() && (isAdmin || isArchitect));
  }

  const status = document.getElementById('adminWildAiEventStatus');
  if (status) {
    status.textContent = isWildAiEventPublicEnabled()
      ? 'STATUS // PUBLIC ACCESS ENABLED'
      : 'STATUS // HIDDEN FROM STUDENTS';
    status.classList.toggle('enabled', isWildAiEventPublicEnabled());
  }
}

function syncMjuEventAvailability(enabled) {
  if (typeof enabled === 'boolean') {
    mjuEventPublicEnabled = enabled;
    window.MJU_EVENT_ENABLED = enabled;
  }

  const visible = canOpenMjuEvent();
  const mjuCard = document.getElementById('homeMjuEventCard');
  if (mjuCard) {
    mjuCard.style.display = visible ? 'block' : 'none';
    mjuCard.classList.toggle('event-disabled-admin-view', !isMjuEventPublicEnabled() && (isAdmin || isArchitect));
  }

  const status = document.getElementById('adminMjuEventStatus');
  if (status) {
    status.textContent = isMjuEventPublicEnabled()
      ? 'STATUS // PUBLIC ACCESS ENABLED'
      : 'STATUS // HIDDEN FROM STUDENTS';
    status.classList.toggle('enabled', isMjuEventPublicEnabled());
  }
}

async function loadArchitectEventAvailability() {
  try {
    const r = await fetch(`${API_URL}/api/settings`);
    if (!r.ok) throw new Error('settings');
    const settings = await r.json();
    syncArchitectEventAvailability(!!settings.architect_event);
    syncWildAiEventAvailability(!!settings.wildai_event);
    syncMjuEventAvailability(!!settings.mju_event);
    if (typeof applyWildAiBreachState === 'function') applyWildAiBreachState(settings);
  } catch (e) {
    syncArchitectEventAvailability(!!window.ARCHITECT_EVENT_ENABLED);
    syncWildAiEventAvailability(!!window.WILDAI_EVENT_ENABLED);
    syncMjuEventAvailability(!!window.MJU_EVENT_ENABLED);
  }
}

function openEventOverlay(tabHint) {
  if (typeof isLaunchGateActive === 'function' && isLaunchGateActive()) {
    showLaunchGateOverlay();
    return;
  }

  const requestedCode = tabHint === 'wildai_breach'
    ? 'wildai_breach'
    : (tabHint === 'mju_protocol_boss' ? 'mju_protocol_boss' : 'architect');
  const allowed = requestedCode === 'wildai_breach'
    ? canOpenWildAiEvent()
    : (requestedCode === 'mju_protocol_boss' ? canOpenMjuEvent() : canOpenArchitectEvent());
  if (!allowed) {
    const closedText = requestedCode === 'wildai_breach'
      ? 'WILD AI BREACH пока закрыт.'
      : (requestedCode === 'mju_protocol_boss' ? 'Босс Протокола пока закрыт.' : 'Architect Protocol пока закрыт.');
    showToast(closedText);
    return;
  }

  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  eventLobbyTabHint = requestedCode;

  if (typeof closeCreateEventModal === 'function') {
    closeCreateEventModal();
  }

  overlay.style.display = 'block';

  const nav = document.querySelector('.bottom-nav');
  if (nav) nav.style.display = 'none';

  document.body.style.overflow = 'hidden';
  setArchitectAmbientVisibility(false);
  if (typeof primeArchitectMusicUnlock === 'function') {
    primeArchitectMusicUnlock();
  } else {
    architectMusicUnlocked = true;
  }
  // Start lobby music synchronously in gesture context — iOS blocks autoplay on async calls
  const lobbyMusic = eventLobbyTabHint === 'wildai_breach' && typeof WILD_AI_BREACH_LOBBY_MUSIC !== 'undefined'
    ? WILD_AI_BREACH_LOBBY_MUSIC
    : (eventLobbyTabHint === 'mju_protocol_boss' && typeof MJU_LOBBY_MUSIC !== 'undefined'
      ? MJU_LOBBY_MUSIC
      : (typeof ARCHITECT_LOBBY_MUSIC !== 'undefined' ? ARCHITECT_LOBBY_MUSIC : ''));
  if (typeof switchArchitectMusic === 'function' && lobbyMusic) {
    switchArchitectMusic(lobbyMusic);
  }
  openArchitectEventEntryBanner();

  const log = document.getElementById('eventLog');
  if (log) {
    log.innerHTML = `<div class="event-log-empty">Загрузка состояния ивента...</div>`;
  }

  setEventExplanation('');
  loadCurrentArchitectEvent();
  if (typeof loadEventActiveBonuses === 'function') loadEventActiveBonuses();
  startArchitectLobbyPoll();
}

function closeEventOverlay() {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  stopArchitectLobbyPoll();
  overlay.style.display = 'none';

  const nav = document.querySelector('.bottom-nav');
  if (nav) nav.style.display = '';

  document.body.style.overflow = '';
  setArchitectAmbientVisibility(true);
  closeArchitectEventEntryBanner();
  if (typeof updateArchitectPhaseFxState === 'function') {
    updateArchitectPhaseFxState(null);
  }

  if (typeof architectVideoStartTimer !== 'undefined' && architectVideoStartTimer) {
    clearTimeout(architectVideoStartTimer);
    architectVideoStartTimer = null;
  }

  const bossVideo = document.getElementById('eventBossVideo');
  if (bossVideo) {
    bossVideo.pause();
  }

  if (typeof stopArchitectMusicOnClose === 'function') {
    stopArchitectMusicOnClose();
  } else {
    stopArchitectMusic(true);
  }

  // Clear question auto-close timer so it can't fire and corrupt state on re-entry
  if (typeof clearArchitectQuestionAutoClose === 'function') {
    clearArchitectQuestionAutoClose();
  }
  if (typeof closeArchitectQuestion === 'function') {
    closeArchitectQuestion();
  }

  // Cancel pending result banner reveal timer
  if (typeof architectResultRevealTimer !== 'undefined' && architectResultRevealTimer) {
    clearTimeout(architectResultRevealTimer);
    architectResultRevealTimer = null;
    architectResultRevealEventKey = null;
  }

  if (typeof flushPendingArchitectOutcomePopup === 'function') {
    flushPendingArchitectOutcomePopup();
  }
}

let architectEventEntryBannerTimer = null;
let architectLobbyPollTimer = null;

// Without this, state changes (lobby -> active fight -> finished) only ever
// reach the client when the user opens the overlay or submits an action — if
// they're just sitting in the lobby while the admin starts/finishes the
// event, the client never finds out until they manually leave and come back.
function startArchitectLobbyPoll() {
  stopArchitectLobbyPoll();
  architectLobbyPollTimer = setInterval(() => {
    if (typeof loadCurrentArchitectEvent === 'function') loadCurrentArchitectEvent();
  }, 6000);
}

function stopArchitectLobbyPoll() {
  if (architectLobbyPollTimer) {
    clearInterval(architectLobbyPollTimer);
    architectLobbyPollTimer = null;
  }
}

function openArchitectEventEntryBanner() {
  const overlay = document.getElementById('architectEventEntryBanner');
  const audio = document.getElementById('architectEventEntryAudio');
  if (!overlay) return;

  setEventEntryBannerCopy();
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

function setEventEntryBannerCopy() {
  const overlay = document.getElementById('architectEventEntryBanner');
  if (!overlay) return;

  const code = typeof getEventHintCode === 'function' ? getEventHintCode() : eventLobbyTabHint;
  const isWildAi = code === 'wildai_breach';
  const isMju = code === 'mju_protocol_boss';
  const kicker = overlay.querySelector('.architect-event-entry-kicker');
  const title = overlay.querySelector('.architect-event-entry-title');
  const copy = overlay.querySelector('.architect-event-entry-copy');
  const grid = overlay.querySelector('.architect-event-entry-grid');

  const cfg = isMju
    ? {
        kicker: 'PROTOCOL BOSS // ACCESS CHECK',
        title: 'ПРОВЕРКА ДОПУСКА',
        copy: 'Цензор активировал сетевое сканирование.<br>Команде требуется дисциплина, точность и полный контроль нарушений.',
        grid: ['CHECK // ACTIVE', 'VIOLATIONS // TRACKED', 'BOSS // MJU']
      }
    : (isWildAi
      ? {
          kicker: 'RED FIREWALL SECURITY // INTRUSION ALERT',
          title: 'ВНИМАНИЕ!',
          copy: 'Несанкционированный вход в сеть.<br>Черный Заслон под угрозой вторжения.',
          grid: ['TRACE // ACTIVE', 'FIREWALL // BREACHED', 'THREAT // WILD AI']
        }
      : {
          kicker: 'ARCHITECT PROTOCOL // SYSTEM ALERT',
          title: 'АРХИТЕКТОР В СЕТИ',
          copy: 'Канал протокола открыт.<br>Команде требуется пробить фазы и удержать перегрузку.',
          grid: ['TRACE // ACTIVE', 'PHASES // ARMED', 'BOSS // ARCHITECT']
        });

  if (kicker) kicker.textContent = cfg.kicker;
  if (title) title.textContent = cfg.title;
  if (copy) copy.innerHTML = cfg.copy;
  if (grid) {
    grid.innerHTML = cfg.grid.map(item => `<span>${item}</span>`).join('');
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
    showToast('Откройте приложение через Telegram бота');
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
      showToast('Не удалось получить вопрос для действия');
      return;
    }

    currentEventQuestion = data.question;
    renderEventQuestion(data.question);
  } catch (e) {
    console.error('Ошибка загрузки вопроса ивента', e);
    showToast('Ошибка загрузки вопроса');
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
      showToast(data.detail || 'Не удалось выполнить действие');
      return;
    }

    renderEventActionResult(data);
  } catch (e) {
    console.error('Ошибка действия ивента', e);
    showToast('Ошибка соединения с ивентом');
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
