(function () {
  const api = window.ZHIDAO_API;
  const state = { preview: new URLSearchParams(location.search).has('preview'), user: null, data: null, selectedStudentId: null };
  const byId = id => document.getElementById(id);

  async function boot() {
    bindEvents();
    if (state.preview) {
      state.user = { id: 'preview-teacher', role: 'teacher', display_name: 'Марк Альбертович' };
      state.data = previewData();
      byId('teacherLogin').classList.add('is-hidden');
      byId('teacherApp').classList.remove('is-hidden');
      byId('teacherName').textContent = state.user.display_name;
      render();
      return;
    }
    try {
      const user = await api.restore();
      if (user.role !== 'teacher') { location.href = '/'; return; }
      state.user = user;
      await enterConsole();
    } catch (_) { byId('teacherLogin').classList.remove('is-hidden'); }
  }

  function bindEvents() {
    byId('teacherLoginForm').addEventListener('submit', handleLogin);
    byId('teacherLogout').addEventListener('click', async () => { await api.logout(); location.reload(); });
    byId('refreshTeacher').addEventListener('click', loadOverview);
    byId('mentorMessageForm').addEventListener('submit', sendMessage);
    byId('createMissionButton').addEventListener('click', () => openEditor());
    byId('closeEditor').addEventListener('click', closeEditor);
    byId('missionEditorForm').addEventListener('submit', saveMission);
    document.querySelectorAll('.teacher-tab').forEach(tab => tab.addEventListener('click', () => showPanel(tab.dataset.panel)));
  }

  async function handleLogin(event) {
    event.preventDefault();
    const error = byId('teacherLoginError'); error.textContent = '';
    try {
      const user = await api.login(byId('teacherLoginName').value, byId('teacherLoginSecret').value);
      if (user.role !== 'teacher') { await api.logout(); throw new Error('Этот аккаунт не имеет доступа к консоли'); }
      state.user = user; await enterConsole();
    } catch (err) { error.textContent = err.message; }
  }

  async function enterConsole() {
    byId('teacherLogin').classList.add('is-hidden');
    byId('teacherApp').classList.remove('is-hidden');
    byId('teacherName').textContent = state.user.display_name;
    await loadOverview();
  }

  async function loadOverview() {
    try { state.data = await api.request('/api/teacher/overview'); render(); }
    catch (err) { if (err.status === 401) location.reload(); else api.toast(err.message, 'error'); }
  }

  function render() {
    state.selectedStudentId = state.selectedStudentId || state.data.students[0]?.id || null;
    byId('reviewCount').textContent = state.data.submissions.filter(item => item.status === 'submitted').length;
    renderStudents(); renderSubmissions(); renderMissions();
  }

  function renderStudents() {
    const container = byId('studentOverview');
    if (!state.data.students.length) { container.innerHTML = '<div class="console-empty">Ученик ещё не создан.</div>'; return; }
    container.innerHTML = state.data.students.map(student => `<article class="student-dossier glass-panel ${student.id === state.selectedStudentId ? 'selected' : ''}" data-student="${student.id}">
      <div class="dossier-avatar">操</div><div class="dossier-main"><small>OPERATOR // ${api.escapeHtml(student.username)}</small><h2>${api.escapeHtml(student.display_name)}</h2><div class="dossier-stats"><span><b>${student.level || 1}</b> уровень</span><span><b>${student.xp || 0}</b> XP</span><span><b>${student.stars || 0}</b> ★</span><span><b>${student.lesson_streak || 0}</b> серия</span></div></div>
      <div class="dossier-signal"><span>${student.assignment_counts?.submitted || 0}</span><small>на проверке</small></div>
    </article>`).join('');
    container.querySelectorAll('[data-student]').forEach(card => card.addEventListener('click', () => { state.selectedStudentId = card.dataset.student; renderStudents(); }));
  }

  function renderSubmissions() {
    const items = state.data.submissions;
    const container = byId('submissionList');
    if (!items.length) { container.innerHTML = '<div class="console-empty">Ответов пока нет. Канал ожидания активен.</div>'; return; }
    container.innerHTML = items.map(item => `<article class="submission-card glass-panel ${item.status}">
      <header><div><small>${api.escapeHtml(item.student_name)} // ${statusLabel(item.status)}</small><h3>${api.escapeHtml(item.mission_title)}</h3></div><div class="score-orb">${item.auto_score ?? 0}<small>%</small></div></header>
      ${item.written_answer ? `<div class="answer-box"><small>ПИСЬМЕННЫЙ ОТВЕТ</small><p>${api.escapeHtml(item.written_answer)}</p></div>` : ''}
      ${item.voice_filename ? `<div class="answer-box"><small>ГОЛОСОВОЙ ОТВЕТ</small><audio controls preload="none" src="/api/teacher/audio/${encodeURIComponent(item.voice_filename)}"></audio></div>` : ''}
      ${item.feedback ? `<div class="feedback-note">Последний комментарий: ${api.escapeHtml(item.feedback)}</div>` : ''}
      ${item.status === 'submitted' ? `<div class="review-controls"><textarea data-feedback="${item.assignment_id}" maxlength="600" placeholder="Сообщение ученику..."></textarea><div><label>XP<input data-xp="${item.assignment_id}" type="number" min="0" max="1000" placeholder="по миссии"></label><label>★<input data-stars="${item.assignment_id}" type="number" min="0" max="500" placeholder="по миссии"></label></div><div><button class="secondary-button revision-button" data-review="revise" data-assignment="${item.assignment_id}">ВЕРНУТЬ</button><button class="primary-button" data-review="approve" data-assignment="${item.assignment_id}">ПРИНЯТЬ + НАГРАДА</button></div></div>` : ''}
    </article>`).join('');
    container.querySelectorAll('[data-review]').forEach(button => button.addEventListener('click', () => review(button.dataset.assignment, button.dataset.review)));
  }

  function statusLabel(status) {
    return ({ submitted: 'ЖДЁТ ПРОВЕРКИ', revision_requested: 'ВОЗВРАЩЕНО', approved: 'ПРИНЯТО' })[status] || status;
  }

  async function review(assignmentId, decision) {
    const feedback = document.querySelector(`[data-feedback="${assignmentId}"]`)?.value || '';
    const xpRaw = document.querySelector(`[data-xp="${assignmentId}"]`)?.value;
    const starsRaw = document.querySelector(`[data-stars="${assignmentId}"]`)?.value;
    try {
      const result = await api.request(`/api/teacher/assignments/${assignmentId}/review`, { method: 'POST', body: JSON.stringify({ decision, feedback, xp: xpRaw === '' ? null : Number(xpRaw), stars: starsRaw === '' ? null : Number(starsRaw), unlock_next: true }) });
      api.toast(decision === 'approve' ? `Миссия принята: +${result.xp} XP, +${result.stars}★` : 'Ответ возвращён ученику');
      await loadOverview();
    } catch (err) { api.toast(err.message, 'error'); }
  }

  function renderMissions() {
    const studentId = state.selectedStudentId;
    byId('teacherMissionList').innerHTML = state.data.missions.map(mission => `<article class="teacher-mission-card glass-panel">
      <div class="teacher-mission-number">${String(mission.order_index).padStart(2, '0')}</div><div><small>VERSION ${mission.version}</small><h3>${api.escapeHtml(mission.title)}</h3><p>${api.escapeHtml(mission.subtitle)}</p><div class="teacher-mission-focus">${(mission.content?.words || []).slice(0, 3).map(word => `<span><b>${api.escapeHtml(word.hanzi)}</b><small>${api.escapeHtml(word.pinyin || '')}</small></span>`).join('')}</div><div class="mission-reward"><span>+${mission.reward_xp} XP</span><span>+${mission.reward_stars}★</span></div></div>
      <div class="teacher-card-actions"><button class="secondary-button" data-edit="${mission.id}">РЕДАКТИРОВАТЬ</button><button class="primary-button" data-assign="${mission.id}" ${studentId ? '' : 'disabled'}>НАЗНАЧИТЬ</button></div>
    </article>`).join('');
    document.querySelectorAll('[data-edit]').forEach(button => button.addEventListener('click', () => openEditor(state.data.missions.find(item => item.id === button.dataset.edit))));
    document.querySelectorAll('[data-assign]').forEach(button => button.addEventListener('click', () => assignMission(button.dataset.assign)));
  }

  async function assignMission(missionId) {
    if (!state.selectedStudentId) return;
    try { await api.request(`/api/teacher/missions/${missionId}/assign`, { method: 'POST', body: JSON.stringify({ student_id: state.selectedStudentId }) }); api.toast('Миссия назначена'); await loadOverview(); }
    catch (err) { api.toast(err.message, 'error'); }
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (!state.selectedStudentId) { api.toast('Сначала выбери ученика', 'error'); return; }
    try { await api.request(`/api/teacher/messages/${state.selectedStudentId}`, { method: 'POST', body: JSON.stringify({ text: byId('mentorMessageText').value }) }); byId('mentorMessageText').value = ''; api.toast('Сообщение отправлено в штаб ученика'); }
    catch (err) { api.toast(err.message, 'error'); }
  }

  function showPanel(panelId) {
    document.querySelectorAll('.teacher-panel').forEach(panel => panel.classList.toggle('active-panel', panel.id === panelId));
    document.querySelectorAll('.teacher-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.panel === panelId));
  }

  function openEditor(mission = null) {
    byId('editorMissionId').value = mission?.id || '';
    byId('editorMissionTitle').value = mission?.title || '';
    byId('editorMissionOrder').value = mission?.order_index || (state.data.missions.length + 1);
    byId('editorMissionSubtitle').value = mission?.subtitle || '';
    byId('editorMissionLore').value = mission?.lore || '';
    byId('editorMissionXp').value = mission?.reward_xp ?? 50;
    byId('editorMissionStars').value = mission?.reward_stars ?? 10;
    byId('editorRewardCode').value = mission?.reward_code || `reward_${Date.now()}`;
    byId('editorRewardTitle').value = mission?.reward_title || 'Новая награда';
    byId('editorMissionContent').value = JSON.stringify(mission?.content || { lesson_label: 'НОВАЯ МИССИЯ', words: [], tasks: [] }, null, 2);
    byId('editorError').textContent = '';
    byId('missionEditor').classList.remove('is-hidden'); document.body.classList.add('modal-open');
  }

  function closeEditor() { byId('missionEditor').classList.add('is-hidden'); document.body.classList.remove('modal-open'); }

  async function saveMission(event) {
    event.preventDefault();
    let content;
    try { content = JSON.parse(byId('editorMissionContent').value); } catch (_) { byId('editorError').textContent = 'JSON содержит ошибку'; return; }
    const id = byId('editorMissionId').value;
    const payload = { title: byId('editorMissionTitle').value, subtitle: byId('editorMissionSubtitle').value, lore: byId('editorMissionLore').value, order_index: Number(byId('editorMissionOrder').value), reward_xp: Number(byId('editorMissionXp').value), reward_stars: Number(byId('editorMissionStars').value), reward_code: byId('editorRewardCode').value, reward_title: byId('editorRewardTitle').value, content };
    try { await api.request(id ? `/api/teacher/missions/${id}` : '/api/teacher/missions', { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) }); closeEditor(); api.toast('Blueprint сохранён'); await loadOverview(); }
    catch (err) { byId('editorError').textContent = err.message; }
  }

  function previewData() {
    const content = { lesson_label: 'ЗАНЯТИЕ 01 // CONTACT NODE', words: [{ hanzi: '你好', pinyin: 'Nǐ hǎo', translation: 'привет' }], tasks: [{ id: 'preview-task', type: 'choice', prompt: 'Что означает 你好?', options: ['Привет', 'Пока'], correct: 'Привет' }] };
    return {
      teacher: { display_name: 'Марк Альбертович' },
      students: [{ id: 'preview-student', username: 'operator', display_name: 'Юный оператор', stars: 15, xp: 80, level: 1, lesson_streak: 1, assignment_counts: { submitted: 1 } }],
      missions: [
        { id: 'mission-first-contact', order_index: 1, title: 'Первый контакт', subtitle: 'Установи безопасное соединение', lore: 'Первый дружественный сигнал.', reward_xp: 80, reward_stars: 15, reward_code: 'first_contact', reward_title: 'Знак первого контакта', version: 1, content },
        { id: 'mission-handshake', order_index: 2, title: 'Протокол рукопожатия', subtitle: 'Заверши первый диалог', lore: 'Продолжение контакта.', reward_xp: 120, reward_stars: 20, reward_code: 'handshake_complete', reward_title: 'Ключ рукопожатия', version: 1, content }
      ],
      submissions: [{ assignment_id: 'preview-assignment', status: 'submitted', submitted_at: new Date().toISOString(), feedback: '', mission_id: 'mission-first-contact', mission_title: 'Первый контакт', student_id: 'preview-student', student_name: 'Юный оператор', written_answer: '我叫Лёша', voice_filename: null, auto_score: 100, updated_at: new Date().toISOString() }]
    };
  }

  boot();
})();
