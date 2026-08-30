(function () {
  const api = window.ZHIDAO_API;
  const state = {
    preview: new URLSearchParams(location.search).has('preview'),
    previewChapter: new URLSearchParams(location.search).get('chapter') || 'form',
    previewUnlockAll: new URLSearchParams(location.search).has('unlock'),
    user: null,
    dashboard: null,
    mission: null,
    stepIndex: 0,
    answers: {},
    writtenAnswer: '',
    voiceBlob: null,
    recorder: null,
    stream: null,
    orderDraft: [],
    writtenTimer: null
  };

  const byId = id => document.getElementById(id);
  const loginScreen = byId('loginScreen');
  const studentApp = byId('studentApp');
  const missionOverlay = byId('missionOverlay');

  const PINYIN_LOOKUP = {
    '你好': 'Nǐ hǎo',
    '我叫': 'Wǒ jiào',
    '你叫': 'Nǐ jiào',
    '再见': 'Zàijiàn',
    '什么': 'shénme',
    '名字': 'míngzi',
    '你叫什么名字': 'Nǐ jiào shénme míngzi',
    '我叫小明': 'Wǒ jiào Xiǎomíng',
    '小明': 'Xiǎomíng',
    '我': 'wǒ',
    '你': 'nǐ',
    '叫': 'jiào',
    '小': 'xiǎo',
    '大': 'dà',
    '长': 'cháng',
    '高': 'gāo',
    '手': 'shǒu',
    '鼻子': 'bízi',
    '耳朵': 'ěrduo',
    '眼睛': 'yǎnjing',
    '头发': 'tóufa',
    '我的': 'wǒ de',
    '很': 'hěn'
  };

  function normalizeHanzi(value) {
    return String(value || '').replace(/[\s！!？?。．…，、:：；;“”«»]/g, '');
  }

  function pinyinFor(value, explicit = '') {
    if (explicit) return explicit;
    const source = String(value || '');
    const normalized = normalizeHanzi(source);
    if (!normalized) return '';
    if (PINYIN_LOOKUP[normalized]) return PINYIN_LOOKUP[normalized];
    const chineseSegments = source.match(/[\u3400-\u9fff]+/g) || [];
    const segment = chineseSegments.find(item => PINYIN_LOOKUP[item]);
    if (segment) return PINYIN_LOOKUP[segment];
    const match = Object.keys(PINYIN_LOOKUP)
      .filter(key => key.length > 1 && normalized.includes(key))
      .sort((a, b) => b.length - a.length)[0];
    return match ? PINYIN_LOOKUP[match] : '';
  }

  function focusStrip(words = [], compact = false) {
    if (!words.length) return '';
    return `<div class="mission-focus ${compact ? 'compact' : ''}">${words.slice(0, 3).map(word => `<span><b>${api.escapeHtml(word.hanzi)}</b><small>${api.escapeHtml(word.pinyin || pinyinFor(word.hanzi))}</small></span>`).join('')}</div>`;
  }

  async function boot() {
    bindEvents();
    if (state.preview) {
      state.user = { id: 'preview', role: 'student', display_name: 'Юный оператор', stars: 15 };
      state.dashboard = previewDashboard();
      loginScreen.classList.add('is-hidden');
      studentApp.classList.remove('is-hidden');
      renderDashboard();
      return;
    }
    try {
      const user = await api.restore();
      if (user.role === 'teacher') { location.href = '/teacher'; return; }
      state.user = user;
      await enterApp();
    } catch (_) {
      loginScreen.classList.remove('is-hidden');
    }
  }

  function bindEvents() {
    byId('loginForm').addEventListener('submit', handleLogin);
    byId('logoutButton').addEventListener('click', handleLogout);
    byId('profileButton').addEventListener('click', () => showView('profileView'));
    document.querySelectorAll('.nav-button').forEach(button => {
      button.addEventListener('click', () => showView(button.dataset.view));
    });
    byId('closeMission').addEventListener('click', closeMission);
    byId('mentorCard').addEventListener('click', openLatestMentorMessage);
    byId('closeArchitect').addEventListener('click', closeArchitect);
    byId('architectConfirm').addEventListener('click', closeArchitect);
    missionOverlay.addEventListener('click', event => { if (event.target === missionOverlay) closeMission(); });
  }

  async function handleLogin(event) {
    event.preventDefault();
    const error = byId('loginError');
    error.textContent = '';
    const button = event.currentTarget.querySelector('button');
    button.disabled = true;
    try {
      const user = await api.login(byId('loginName').value, byId('loginSecret').value);
      if (user.role === 'teacher') { location.href = '/teacher'; return; }
      state.user = user;
      await enterApp();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  }

  async function enterApp() {
    loginScreen.classList.add('is-hidden');
    studentApp.classList.remove('is-hidden');
    await loadDashboard();
  }

  async function handleLogout() {
    await api.logout();
    location.reload();
  }

  async function loadDashboard() {
    try {
      state.dashboard = await api.request('/api/student/dashboard');
      renderDashboard();
    } catch (err) {
      if (err.status === 401) location.reload();
      else api.toast(err.message, 'error');
    }
  }

  function renderDashboard() {
    const data = state.dashboard;
    const profile = data.profile;
    byId('headerName').textContent = data.user.display_name;
    byId('headerXp').textContent = profile.xp;
    byId('headerStars').textContent = data.user.stars;
    byId('levelValue').textContent = profile.level;
    byId('streakValue').textContent = profile.lesson_streak;
    byId('xpFloor').textContent = `${profile.level_floor} XP`;
    byId('xpCeiling').textContent = `${profile.level_ceiling} XP`;
    const progress = ((profile.xp - profile.level_floor) / Math.max(1, profile.level_ceiling - profile.level_floor)) * 100;
    byId('xpTrack').style.width = `${Math.max(0, Math.min(100, progress))}%`;
    byId('chapterKicker').textContent = `ГЛАВА ${String(data.chapter?.order_index || 1).padStart(2, '0')}`;
    byId('chapterTitle').textContent = data.chapter?.title || 'Учебный канал';
    byId('chapterPageTitle').textContent = data.chapter?.title || 'Учебный канал';
    byId('chapterPageSummary').textContent = data.chapter?.subtitle || `${data.missions.length} учебных узла`;
    byId('missionCountChip').textContent = `${data.missions.length} занятия`;

    const latest = data.messages[0];
    if (latest) {
      byId('mentorTitle').textContent = latest.author_name || 'Архитектор';
      byId('mentorText').textContent = latest.text;
    }

    byId('missionList').innerHTML = data.missions.map(missionCard).join('');
    byId('chapterMissionList').innerHTML = data.missions.map(timelineCard).join('');
    document.querySelectorAll('[data-open-mission]').forEach(button => {
      button.addEventListener('click', () => openMission(button.dataset.openMission));
    });

    byId('rewardList').innerHTML = data.rewards.length
      ? data.rewards.map(reward => `<article class="reward-card"><span>◆</span><b>${api.escapeHtml(reward.reward_title)}</b><small>+${reward.xp} XP · +${reward.stars}★</small></article>`).join('')
      : '<article class="empty-reward"><span>◇</span><p>Первая награда появится после проверки миссии.</p></article>';

    const phraseWords = [];
    const seenHanzi = new Set();
    data.missions.flatMap(mission => mission.focus_words || []).forEach(word => {
      if (!word?.hanzi || seenHanzi.has(word.hanzi)) return;
      seenHanzi.add(word.hanzi);
      phraseWords.push(word);
    });
    byId('phraseGrid').innerHTML = phraseWords.map(word => `<div><b>${api.escapeHtml(word.hanzi)}</b><span>${api.escapeHtml(word.pinyin || pinyinFor(word.hanzi))}</span><small>${api.escapeHtml(word.translation || 'учебный сигнал')}</small></div>`).join('');

    byId('profileName').textContent = data.user.display_name;
    byId('profileLevel').textContent = profile.level;
    byId('profileXp').textContent = `${profile.xp} XP`;
    byId('profileStars').textContent = `${data.user.stars} ★`;
    byId('profileStreak').textContent = `${profile.lesson_streak} ⚡`;
  }

  function statusMeta(status) {
    return {
      locked: ['ЗАБЛОКИРОВАНО', 'locked'],
      assigned: ['ДОСТУПНО', 'available'],
      in_progress: ['В ПРОЦЕССЕ', 'progress'],
      submitted: ['НА ПРОВЕРКЕ', 'review'],
      revision_requested: ['НУЖНА ПРАВКА', 'revision'],
      approved: ['ВЫПОЛНЕНО', 'done']
    }[status] || [status, 'locked'];
  }

  function missionCard(mission) {
    const [label, cls] = statusMeta(mission.status);
    const disabled = mission.status === 'locked' || mission.status === 'submitted' || mission.status === 'approved';
    const action = mission.status === 'approved' ? 'ПРОЙДЕНО ✓' : mission.status === 'submitted' ? 'ЖДЁМ АРХИТЕКТОРА' : mission.status === 'locked' ? 'ЗАКРЫТО' : mission.status === 'revision_requested' ? 'ИСПРАВИТЬ' : 'НАЧАТЬ МИССИЮ';
    return `<article class="mission-card ${cls} theme-${api.escapeHtml(mission.signal_code || 'core')}">
      <div class="mission-index"><span>${String(mission.order_index).padStart(2, '0')}</span><i></i></div>
      <div class="mission-card-main">
        <div class="mission-status ${cls}">${label}</div>
        <h3>${api.escapeHtml(mission.title)}</h3><p>${api.escapeHtml(mission.subtitle)}</p>
        ${focusStrip(mission.focus_words || [])}
        ${mission.feedback && mission.status === 'revision_requested' ? `<div class="feedback-note">Архитектор: ${api.escapeHtml(mission.feedback)}</div>` : ''}
        <div class="mission-reward"><span>+${mission.reward_xp} XP</span><span>+${mission.reward_stars}★</span></div>
        <button class="mission-action" data-open-mission="${mission.id}" ${disabled ? 'disabled' : ''}>${action}</button>
      </div>
      <div class="mission-glyph">${mission.status === 'locked' ? '锁' : mission.status === 'approved' ? '✓' : api.escapeHtml(mission.glyph || '任')}</div>
    </article>`;
  }

  function timelineCard(mission) {
    const [label, cls] = statusMeta(mission.status);
    return `<article class="timeline-card ${cls}"><span class="timeline-node"></span><div><small>${label}</small><h3>${api.escapeHtml(mission.title)}</h3><p>${api.escapeHtml(mission.subtitle)}</p>${focusStrip(mission.focus_words || [], true)}</div><b>${String(mission.order_index).padStart(2, '0')}</b></article>`;
  }

  function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => view.classList.toggle('active-view', view.id === viewId));
    document.querySelectorAll('.nav-button').forEach(button => button.classList.toggle('active', button.dataset.view === viewId));
    scrollTo({ top: 0, behavior: 'smooth' });
  }

  function openLatestMentorMessage() {
    const latest = state.dashboard?.messages?.[0];
    showArchitect(latest?.text || 'Оператор, учебный канал активирован. Выбери доступную миссию и двигайся короткими шагами.', 'explaining');
  }

  function showArchitect(text, image = 'explaining', title = 'Сообщение Архитектора') {
    byId('architectPopupText').textContent = text;
    byId('architectPopupTitle').textContent = title;
    byId('architectImage').src = `/media/architect/${image}`;
    byId('architectPopup').classList.remove('is-hidden');
    document.body.classList.add('modal-open');
  }

  function closeArchitect() {
    byId('architectPopup').classList.add('is-hidden');
    if (missionOverlay.classList.contains('is-hidden')) document.body.classList.remove('modal-open');
  }

  async function openMission(missionId) {
    try {
      if (state.preview) {
        state.mission = previewMission(missionId);
        if (!state.mission) throw new Error('Миссия пока заблокирована');
        state.stepIndex = 0;
        state.answers = {};
        state.writtenAnswer = '';
        state.voiceBlob = null;
        byId('missionTitle').textContent = state.mission.mission.title;
        byId('missionLabel').textContent = state.mission.mission.content.lesson_label;
        missionOverlay.classList.remove('is-hidden');
        document.body.classList.add('modal-open');
        renderMissionStep();
        return;
      }
      await api.request(`/api/student/missions/${missionId}/start`, { method: 'POST' });
      state.mission = await api.request(`/api/student/missions/${missionId}`);
      state.stepIndex = 0;
      state.answers = Object.fromEntries(Object.entries(state.mission.attempts || {}).map(([id, value]) => [id, value.answer]));
      const writtenTask = state.mission.mission.content.tasks.find(task => task.type === 'written');
      state.writtenAnswer = state.mission.submission?.written_answer || (writtenTask ? state.mission.attempts?.[writtenTask.id]?.answer : '') || '';
      state.voiceBlob = null;
      byId('missionTitle').textContent = state.mission.mission.title;
      byId('missionLabel').textContent = state.mission.mission.content.lesson_label || 'УЧЕБНАЯ МИССИЯ';
      missionOverlay.classList.remove('is-hidden');
      document.body.classList.add('modal-open');
      renderMissionStep();
    } catch (err) { api.toast(err.message, 'error'); }
  }

  function closeMission() {
    stopRecording();
    missionOverlay.classList.add('is-hidden');
    document.body.classList.remove('modal-open');
    if (!state.preview) loadDashboard();
  }

  function allMissionSteps() {
    if (!state.mission) return [];
    return [
      { id: '__briefing', type: 'briefing' },
      { id: '__lesson', type: 'lesson' },
      ...state.mission.mission.content.tasks,
      { id: '__submit', type: 'submit' }
    ];
  }

  function renderMissionStep() {
    const steps = allMissionSteps();
    const step = steps[state.stepIndex];
    byId('missionStepCount').textContent = `${state.stepIndex + 1}/${steps.length}`;
    byId('missionProgress').style.width = `${((state.stepIndex + 1) / steps.length) * 100}%`;
    const content = byId('missionContent');
    const footer = byId('missionFooter');
    if (step.type === 'briefing') {
      content.innerHTML = `<article class="briefing-step"><div class="briefing-glyph">${api.escapeHtml(state.mission.mission.content.glyph || '构')}</div><small>ЗАДАНИЕ АРХИТЕКТОРА</small><h2>${api.escapeHtml(state.mission.mission.title)}</h2><p>${api.escapeHtml(state.mission.mission.lore)}</p><div class="reward-preview"><span>НАГРАДА</span><b>+${state.mission.mission.reward_xp} XP</b><b>+${state.mission.mission.reward_stars}★</b></div></article>`;
      footer.innerHTML = nextButton('ПРИНЯТЬ МИССИЮ');
    } else if (step.type === 'lesson') {
      content.innerHTML = `<article class="lesson-step"><small>ПАКЕТ ЗНАНИЙ</small><h2>Изучи новые сигналы</h2><div class="pinyin-banner"><span>拼音</span><div><b>ПИНЬИНЬ АКТИВЕН</b><small>Читай произношение под иероглифами</small></div></div><div class="word-list">${state.mission.mission.content.words.map((word, index) => `<div class="word-card"><i>${String(index + 1).padStart(2, '0')}</i><b>${api.escapeHtml(word.hanzi)}</b><span>${api.escapeHtml(word.pinyin || pinyinFor(word.hanzi))}</span><small>${api.escapeHtml(word.translation)}</small></div>`).join('')}</div></article>`;
      footer.innerHTML = navButtons(true);
    } else if (step.type === 'choice') {
      const selected = state.answers[step.id];
      content.innerHTML = taskHeader(step) + `<div class="choice-grid">${step.options.map(option => {
        const optionPinyin = pinyinFor(option, step.option_pinyin?.[option]);
        return `<button class="choice-button ${selected === option ? 'selected' : ''}" data-choice="${api.escapeHtml(option)}"><span class="choice-main">${api.escapeHtml(option)}</span>${optionPinyin ? `<span class="choice-pinyin">${api.escapeHtml(optionPinyin)}</span>` : ''}</button>`;
      }).join('')}</div><div id="taskFeedback" class="task-feedback"></div>`;
      content.querySelectorAll('[data-choice]').forEach(button => button.addEventListener('click', () => saveChoice(step, button.dataset.choice)));
      footer.innerHTML = navButtons(Boolean(selected));
    } else if (step.type === 'order') {
      state.orderDraft = Array.isArray(state.answers[step.id]) ? [...state.answers[step.id]] : [];
      renderOrderTask(step);
      footer.innerHTML = navButtons(state.orderDraft.length === step.options.length);
    } else if (step.type === 'written') {
      content.innerHTML = taskHeader(step) + `<textarea id="writtenAnswer" class="answer-area" maxlength="1000" placeholder="${api.escapeHtml(step.placeholder || '')}">${api.escapeHtml(state.writtenAnswer)}</textarea><p class="input-hint">Ответ увидит только Архитектор.</p>`;
      byId('writtenAnswer').addEventListener('input', event => {
        state.writtenAnswer = event.target.value;
        updateMissionFooter();
        clearTimeout(state.writtenTimer);
        state.writtenTimer = setTimeout(() => saveWrittenDraft(step), 500);
      });
      footer.innerHTML = navButtons(Boolean(state.writtenAnswer.trim()));
    } else if (step.type === 'voice') {
      const uploaded = state.mission.submission?.voice_filename;
      const coach = step.coach ? `<div class="voice-coach"><small>ШПАРГАЛКА ДЛЯ ОТВЕТА</small><b>${api.escapeHtml(step.coach.hanzi)}</b><span>${api.escapeHtml(step.coach.pinyin)}</span></div>` : '';
      content.innerHTML = taskHeader(step) + coach + `<div class="voice-recorder"><div id="voicePulse" class="voice-pulse"><span>声</span></div><p id="voiceStatus">${uploaded ? 'Запись уже загружена. Можно сделать новую.' : 'Нажми кнопку и произнеси фразу.'}</p><audio id="voicePreview" controls class="is-hidden"></audio><button id="recordVoice" class="record-button" type="button">● НАЧАТЬ ЗАПИСЬ</button></div>`;
      byId('recordVoice').addEventListener('click', toggleRecording);
      footer.innerHTML = navButtons(Boolean(uploaded));
    } else if (step.type === 'submit') {
      const tasks = state.mission.mission.content.tasks;
      const completed = tasks.filter(task => task.type === 'written' ? state.writtenAnswer.trim() : task.type === 'voice' ? (state.mission.submission?.voice_filename || state.voiceBlob) : state.answers[task.id]).length;
      content.innerHTML = `<article class="submit-step"><div class="submit-orbit">✓</div><small>ПРОВЕРКА ПАКЕТА</small><h2>Миссия готова к отправке</h2><p>Выполнено заданий: <b>${completed}/${tasks.length}</b></p><div class="submit-summary"><span>Архитектор проверит письменный или голосовой ответ.</span><span>После проверки ты получишь XP, ★ и награду.</span></div></article>`;
      footer.innerHTML = `<button class="secondary-button" data-prev>НАЗАД</button><button class="primary-button" id="submitMission">ОТПРАВИТЬ АРХИТЕКТОРУ</button>`;
      byId('submitMission').addEventListener('click', submitMission);
    }
    bindFooterNavigation();
    content.scrollTop = 0;
  }

  function taskHeader(step) {
    // Never reveal task.focus here: for choice tasks it can contain the answer.
    // Pinyin is shown only when the Chinese text is already part of the prompt.
    const promptPinyin = pinyinFor(step.prompt, step.prompt_pinyin || '');
    return `<article class="task-heading"><small>КОРОТКОЕ ЗАДАНИЕ</small><h2>${api.escapeHtml(step.prompt)}</h2>${promptPinyin ? `<div class="task-pinyin">拼音 // ${api.escapeHtml(promptPinyin)}</div>` : ''}</article>`;
  }

  function nextButton(label) {
    return `<button class="primary-button full-button" data-next>${label} →</button>`;
  }

  function navButtons(canContinue) {
    return `<button class="secondary-button" data-prev>НАЗАД</button><button class="primary-button" data-next ${canContinue ? '' : 'disabled'}>ДАЛЬШЕ →</button>`;
  }

  function bindFooterNavigation() {
    byId('missionFooter').querySelector('[data-prev]')?.addEventListener('click', () => { state.stepIndex = Math.max(0, state.stepIndex - 1); renderMissionStep(); });
    byId('missionFooter').querySelector('[data-next]')?.addEventListener('click', () => { state.stepIndex = Math.min(allMissionSteps().length - 1, state.stepIndex + 1); renderMissionStep(); });
  }

  function updateMissionFooter() {
    const step = allMissionSteps()[state.stepIndex];
    const button = byId('missionFooter').querySelector('[data-next]');
    if (!button) return;
    if (step.type === 'written') button.disabled = !state.writtenAnswer.trim();
    if (step.type === 'voice') button.disabled = !(state.voiceBlob || state.mission.submission?.voice_filename);
    if (step.type === 'order') button.disabled = state.orderDraft.length !== step.options.length;
  }

  async function saveChoice(step, answer) {
    try {
      if (state.preview) {
        state.answers[step.id] = answer;
        renderMissionStep();
        const previewFeedback = byId('taskFeedback');
        const previewCorrect = String(answer) === String(step.correct);
        previewFeedback.className = `task-feedback show ${previewCorrect ? 'correct' : 'wrong'}`;
        previewFeedback.textContent = `${previewCorrect ? '✓ Верно. ' : '↻ Попробуй ещё. '}${step.explanation || ''}`;
        return;
      }
      const result = await api.request(`/api/student/missions/${state.mission.mission.id}/answer`, { method: 'POST', body: JSON.stringify({ step_id: step.id, answer }) });
      state.answers[step.id] = answer;
      renderMissionStep();
      const feedback = byId('taskFeedback');
      if (feedback) {
        feedback.className = `task-feedback show ${result.is_correct ? 'correct' : 'wrong'}`;
        feedback.textContent = `${result.is_correct ? '✓ Верно. ' : '↻ Попробуй ещё. '}${result.explanation || ''}`;
      }
    } catch (err) { api.toast(err.message, 'error'); }
  }

  function renderOrderTask(step) {
    const content = byId('missionContent');
    const tokenMarkup = token => {
      const pinyin = pinyinFor(token, step.token_pinyin?.[token]);
      return `<b>${api.escapeHtml(token)}</b>${pinyin ? `<small>${api.escapeHtml(pinyin)}</small>` : ''}`;
    };
    content.innerHTML = taskHeader(step) + `<div class="order-zone">${state.orderDraft.length ? state.orderDraft.map((token, index) => `<button data-remove-order="${index}">${tokenMarkup(token)}</button>`).join('') : '<span>Нажимай на части фразы по порядку</span>'}</div><div class="token-grid">${step.options.map((option, index) => `<button data-order-index="${index}" ${state.orderDraft.filter(x => x === option).length >= step.options.filter(x => x === option).length ? 'disabled' : ''}>${tokenMarkup(option)}</button>`).join('')}</div><div id="taskFeedback" class="task-feedback"></div>`;
    content.querySelectorAll('[data-order-index]').forEach(button => button.addEventListener('click', () => { state.orderDraft.push(step.options[Number(button.dataset.orderIndex)]); renderOrderTask(step); updateMissionFooter(); }));
    content.querySelectorAll('[data-remove-order]').forEach(button => button.addEventListener('click', () => { state.orderDraft.splice(Number(button.dataset.removeOrder), 1); renderOrderTask(step); updateMissionFooter(); }));
    if (state.orderDraft.length === step.options.length) saveOrder(step);
  }

  async function saveOrder(step) {
    try {
      if (state.preview) {
        state.answers[step.id] = [...state.orderDraft];
        const previewFeedback = byId('taskFeedback');
        const previewCorrect = JSON.stringify(state.orderDraft) === JSON.stringify(step.correct);
        previewFeedback.className = `task-feedback show ${previewCorrect ? 'correct' : 'wrong'}`;
        previewFeedback.textContent = `${previewCorrect ? '✓ Последовательность верна. ' : '↻ Порядок можно изменить. '}${step.explanation || ''}`;
        return;
      }
      const result = await api.request(`/api/student/missions/${state.mission.mission.id}/answer`, { method: 'POST', body: JSON.stringify({ step_id: step.id, answer: state.orderDraft }) });
      state.answers[step.id] = [...state.orderDraft];
      const feedback = byId('taskFeedback');
      feedback.className = `task-feedback show ${result.is_correct ? 'correct' : 'wrong'}`;
      feedback.textContent = `${result.is_correct ? '✓ Последовательность верна. ' : '↻ Порядок можно изменить. '}${result.explanation || ''}`;
    } catch (err) { api.toast(err.message, 'error'); }
  }

  async function saveWrittenDraft(step) {
    if (state.preview || !state.mission) return;
    try {
      await api.request(`/api/student/missions/${state.mission.mission.id}/answer`, {
        method: 'POST',
        body: JSON.stringify({ step_id: step.id, answer: state.writtenAnswer })
      });
    } catch (err) {
      api.toast(`Черновик не сохранён: ${err.message}`, 'error');
    }
  }

  async function toggleRecording() {
    if (state.recorder?.state === 'recording') { state.recorder.stop(); return; }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      api.toast('На этом устройстве запись недоступна', 'error'); return;
    }
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferred = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      state.recorder = new MediaRecorder(state.stream, preferred ? { mimeType: preferred } : undefined);
      const chunks = [];
      state.recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      state.recorder.onstop = async () => {
        const mime = state.recorder.mimeType.split(';')[0] || 'audio/webm';
        state.voiceBlob = new Blob(chunks, { type: mime });
        const audio = byId('voicePreview');
        audio.src = URL.createObjectURL(state.voiceBlob);
        audio.classList.remove('is-hidden');
        byId('voiceStatus').textContent = 'Запись готова. Загружаю в защищённый канал…';
        byId('recordVoice').textContent = '● ЗАПИСАТЬ ЕЩЁ РАЗ';
        byId('voicePulse').classList.remove('recording');
        stopStream();
        try {
          await api.request(`/api/student/missions/${state.mission.mission.id}/voice`, { method: 'POST', headers: { 'Content-Type': mime, 'X-Audio-Mime': mime }, body: state.voiceBlob });
          state.mission.submission = { ...(state.mission.submission || {}), voice_filename: 'uploaded' };
          byId('voiceStatus').textContent = '✓ Голосовой сигнал загружен.';
          updateMissionFooter();
        } catch (err) { api.toast(err.message, 'error'); }
      };
      state.recorder.start();
      byId('voicePulse').classList.add('recording');
      byId('voiceStatus').textContent = 'ИДЁТ ЗАПИСЬ… Произнеси фразу спокойно.';
      byId('recordVoice').textContent = '■ ОСТАНОВИТЬ';
    } catch (_) { api.toast('Разреши доступ к микрофону для голосового ответа', 'error'); }
  }

  function stopStream() { state.stream?.getTracks().forEach(track => track.stop()); state.stream = null; }
  function stopRecording() { if (state.recorder?.state === 'recording') state.recorder.stop(); stopStream(); }

  async function submitMission() {
    const button = byId('submitMission');
    button.disabled = true;
    try {
      if (state.preview) {
        closeMission();
        showArchitect('Демо-пакет принят. В настоящем режиме я проверю ответ, начислю XP и открою следующий узел.', 'happy', 'Ответ отправлен');
        return;
      }
      const result = await api.request(`/api/student/missions/${state.mission.mission.id}/submit`, { method: 'POST', body: JSON.stringify({ written_answer: state.writtenAnswer }) });
      closeMission();
      showArchitect(`Пакет принят системой. Автоматическая проверка: ${result.auto_score}%. Я изучу ответ и открою следующий узел.`, 'thinking', 'Ответ отправлен');
    } catch (err) { api.toast(err.message, 'error'); button.disabled = false; }
  }

  function previewDashboard() {
    if (state.previewChapter === 'greetings') {
      return {
        user: { id: 'preview', display_name: 'Юный оператор', avatar_code: 'operator', stars: 15 },
        profile: { xp: 80, level: 1, lesson_streak: 1, level_floor: 0, level_ceiling: 200 },
        chapter: { id: 'chapter-greetings', order_index: 1, title: 'Приветствие и знакомство', subtitle: 'Глава 01 // Первый сигнал' },
        missions: [
          { id: 'mission-first-contact', assignment_id: 'preview-a1', order_index: 1, title: 'Первый контакт', subtitle: 'Установи безопасное соединение', reward_xp: 80, reward_stars: 15, status: 'assigned', feedback: '', glyph: '任', signal_code: 'core', focus_words: [{ hanzi: '你好', pinyin: 'Nǐ hǎo', translation: 'привет' }, { hanzi: '我叫……', pinyin: 'Wǒ jiào…', translation: 'меня зовут…' }] },
          { id: 'mission-handshake', assignment_id: null, order_index: 2, title: 'Протокол рукопожатия', subtitle: 'Заверши первый диалог', reward_xp: 120, reward_stars: 20, status: 'locked', feedback: '', glyph: '联', signal_code: 'core', focus_words: [{ hanzi: '你叫什么名字？', pinyin: 'Nǐ jiào shénme míngzi?', translation: 'как тебя зовут?' }, { hanzi: '再见', pinyin: 'Zàijiàn', translation: 'до свидания' }] }
        ],
        rewards: [{ reward_code: 'first_signal', reward_title: 'Тестовый знак связи', xp: 80, stars: 15, awarded_at: new Date().toISOString() }],
        messages: [{ id: 'preview-message', text: 'Канал активен. Первая учебная миссия уже ждёт тебя, оператор.', author_name: 'Марк Альбертович' }]
      };
    }
    return {
      user: { id: 'preview', display_name: 'Юный оператор', avatar_code: 'operator', stars: 35 },
      profile: { xp: 200, level: 2, lesson_streak: 2, level_floor: 200, level_ceiling: 400 },
      chapter: { id: 'chapter-form-scan', order_index: 2, title: 'Форма и биометрия', subtitle: 'Глава 02 // Контур объекта' },
      missions: [
        { id: 'mission-scale-protocol', assignment_id: 'preview-scale', order_index: 1, title: 'Протокол масштаба', subtitle: 'Калибруй признаки объектов', reward_xp: 100, reward_stars: 18, status: 'assigned', feedback: '', glyph: '尺', signal_code: 'scale', focus_words: [{ hanzi: '小', pinyin: 'xiǎo', translation: 'маленький' }, { hanzi: '大', pinyin: 'dà', translation: 'большой' }, { hanzi: '长', pinyin: 'cháng', translation: 'длинный' }] },
        { id: 'mission-biometric-scan', assignment_id: state.previewUnlockAll ? 'preview-body' : null, order_index: 2, title: 'Биометрический скан', subtitle: 'Собери контур киберзверя', reward_xp: 130, reward_stars: 24, status: state.previewUnlockAll ? 'assigned' : 'locked', feedback: '', glyph: '体', signal_code: 'body', focus_words: [{ hanzi: '眼睛', pinyin: 'yǎnjing', translation: 'глаза' }, { hanzi: '鼻子', pinyin: 'bízi', translation: 'нос' }, { hanzi: '耳朵', pinyin: 'ěrduo', translation: 'ухо' }] }
      ],
      rewards: [{ reward_code: 'handshake_complete', reward_title: 'Ключ рукопожатия', xp: 120, stars: 20, awarded_at: new Date().toISOString() }],
      messages: [{ id: 'preview-message', text: 'Оператор, запускаю сканирование формы. Калибруй четыре сигнала и не доверяй очевидным подсказкам.', author_name: 'Марк Альбертович' }]
    };
  }

  function previewMission(missionId) {
    if (missionId === 'mission-biometric-scan' && state.previewUnlockAll) {
      return {
        assignment_id: 'preview-body', status: 'assigned', feedback: '', attempts: {}, submission: null,
        mission: {
          id: missionId, title: 'Биометрический скан', lore: 'В архив поступил неизвестный киберзверь. Восстанови его биометрический профиль по частям тела и отправь Архитектору голосовое описание.', reward_xp: 130, reward_stars: 24,
          content: {
            lesson_label: 'ЗАНЯТИЕ 04 // BIOMETRIC SCAN', glyph: '体', signal_code: 'body',
            words: [
              { hanzi: '手', pinyin: 'shǒu', translation: 'рука' },
              { hanzi: '鼻子', pinyin: 'bízi', translation: 'нос' },
              { hanzi: '耳朵', pinyin: 'ěrduo', translation: 'ухо' },
              { hanzi: '眼睛', pinyin: 'yǎnjing', translation: 'глаза' },
              { hanzi: '头发', pinyin: 'tóufa', translation: 'волосы' }
            ],
            tasks: [
              { id: 'body-eyes', type: 'choice', prompt: 'Что означает 眼睛?', options: ['глаза', 'уши', 'волосы'], correct: 'глаза', explanation: '眼睛 — глаза.' },
              { id: 'body-nose', type: 'choice', prompt: 'Как передать сигнал «нос»?', options: ['手', '鼻子', '耳朵'], option_pinyin: { '手': 'shǒu', '鼻子': 'bízi', '耳朵': 'ěrduo' }, correct: '鼻子', explanation: '鼻子 — нос.' },
              { id: 'body-hair', type: 'choice', prompt: 'Как передать сигнал «волосы»?', options: ['眼睛', '头发', '手'], option_pinyin: { '眼睛': 'yǎnjing', '头发': 'tóufa', '手': 'shǒu' }, correct: '头发', explanation: '头发 — волосы.' },
              { id: 'body-order', type: 'order', prompt: 'Собери фразу: «У меня большие глаза»', options: ['我的', '眼睛', '很', '大'], token_pinyin: { '我的': 'wǒ de', '眼睛': 'yǎnjing', '很': 'hěn', '大': 'dà' }, correct: ['我的', '眼睛', '很', '大'], explanation: '我的眼睛很大 — у меня большие глаза.' },
              { id: 'body-voice', type: 'voice', prompt: 'Опиши киберзверя двумя фразами: какие у него глаза и какой нос?', coach: { hanzi: '它的眼睛很……。它的鼻子很……。', pinyin: 'Tā de yǎnjing hěn… Tā de bízi hěn…' }, required: true }
            ]
          }
        }
      };
    }
    if (missionId === 'mission-scale-protocol') {
      return {
        assignment_id: 'preview-scale', status: 'assigned', feedback: '', attempts: {}, submission: null,
        mission: {
          id: missionId, title: 'Протокол масштаба', lore: 'Сканеры Неон-Сити потеряли масштаб. Архитектор передаёт четыре сигнала: определи, что большое, маленькое, длинное и высокое.', reward_xp: 100, reward_stars: 18,
          content: {
            lesson_label: 'ЗАНЯТИЕ 03 // SCALE PROTOCOL', glyph: '尺', signal_code: 'scale',
            words: [
              { hanzi: '小', pinyin: 'xiǎo', translation: 'маленький' },
              { hanzi: '大', pinyin: 'dà', translation: 'большой' },
              { hanzi: '长', pinyin: 'cháng', translation: 'длинный' },
              { hanzi: '高', pinyin: 'gāo', translation: 'высокий' }
            ],
            tasks: [
              { id: 'scale-big', type: 'choice', prompt: 'Что означает 大?', options: ['большой', 'маленький', 'длинный'], correct: 'большой', explanation: '大 — большой.' },
              { id: 'scale-small', type: 'choice', prompt: 'Как передать сигнал «маленький»?', options: ['大', '小', '高'], option_pinyin: { '大': 'dà', '小': 'xiǎo', '高': 'gāo' }, correct: '小', explanation: '小 — маленький.' },
              { id: 'scale-giraffe', type: 'choice', prompt: 'Какой сигнал подходит для высокого жирафа?', options: ['长', '高', '小'], option_pinyin: { '长': 'cháng', '高': 'gāo', '小': 'xiǎo' }, correct: '高', explanation: '高 описывает высокий рост.' },
              { id: 'scale-snake', type: 'choice', prompt: 'Какой сигнал подходит для длинной змеи?', options: ['大', '长', '高'], option_pinyin: { '大': 'dà', '长': 'cháng', '高': 'gāo' }, correct: '长', explanation: '长 — длинный.' },
              { id: 'scale-voice', type: 'voice', prompt: 'Передай четыре сигнала по-китайски: большой, маленький, длинный, высокий.', required: true }
            ]
          }
        }
      };
    }
    if (missionId !== 'mission-first-contact') return null;
    return {
      assignment_id: 'preview-a1', status: 'assigned', feedback: '', attempts: {}, submission: null,
      mission: {
        id: missionId, title: 'Первый контакт', lore: 'В городском секторе замечен новый оператор. Архитектор поручает тебе передать первый дружественный сигнал.', reward_xp: 80, reward_stars: 15,
        content: {
          lesson_label: 'ЗАНЯТИЕ 01 // CONTACT NODE',
          words: [{ hanzi: '你好', pinyin: 'Nǐ hǎo', translation: 'привет' }, { hanzi: '我叫……', pinyin: 'Wǒ jiào…', translation: 'меня зовут…' }],
          tasks: [
            { id: 'm1-meaning', type: 'choice', prompt: 'Что означает 你好?', focus: { hanzi: '你好', pinyin: 'Nǐ hǎo' }, options: ['Привет', 'Спасибо', 'До свидания'], correct: 'Привет', explanation: '你好 — привет или здравствуй.' },
            { id: 'm1-signal', type: 'choice', prompt: 'Как передать: «Меня зовут…»?', focus: { hanzi: '我叫……', pinyin: 'Wǒ jiào…' }, options: ['你叫……', '我叫……', '再见'], option_pinyin: { '你叫……': 'Nǐ jiào…', '我叫……': 'Wǒ jiào…', '再见': 'Zàijiàn' }, correct: '我叫……', explanation: '我 — я, 叫 — называться.' },
            { id: 'm1-order', type: 'order', prompt: 'Собери фразу в правильном порядке', options: ['我', '叫', '小明'], token_pinyin: { '我': 'wǒ', '叫': 'jiào', '小明': 'Xiǎomíng' }, correct: ['我', '叫', '小明'], explanation: 'Сначала 我, затем 叫 и имя.' },
            { id: 'm1-write', type: 'written', prompt: 'Напиши своё имя по формуле: 我叫……', focus: { hanzi: '我叫……', pinyin: 'Wǒ jiào…' }, placeholder: '我叫……', required: true }
          ]
        }
      }
    };
  }

  boot();
})();
