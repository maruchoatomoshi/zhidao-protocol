function openDiaryPage() {
  if (!isAdmin) {
    syncDiaryAccessVisibility();
    try { showToast('Архив дневника доступен только администраторам.'); } catch(e) {}
    return;
  }
  showPage('diary');
  const moreBtn = document.getElementById('nav-more-btn');
  if (moreBtn) moreBtn.classList.add('active');
}

function syncDiaryAccessVisibility() {
  const archiveItem = document.getElementById('diaryArchiveItem');
  if (archiveItem) archiveItem.style.display = isAdmin ? '' : 'none';

  const diaryPage = document.getElementById('page-diary');
  if (!isAdmin && diaryPage && diaryPage.classList.contains('active')) {
    showPage('more', document.getElementById('nav-more-btn'));
  }
}

const DIARY_WORD_ROWS = 15;
const DIARY_WEATHER_OPTIONS = [
  '',
  '晴天 / солнечно',
  '多云 / облачно',
  '阴天 / пасмурно',
  '小雨 / небольшой дождь',
  '大雨 / ливень',
  '有风 / ветрено',
  '闷热 / душно',
  '凉爽 / прохладно'
];

// ============================================================
// ZHIDAO Diary — API Integration Patch
// Replaces: from "let diaryInitialized = false;"
//           to end of "

// ── ДНЕВНИК ★ — Оценка дневников ─────────────────────────────

let diaryStarsCurrentStudent = null;

function initDiaryStarsPage() {
  const dateInput = document.getElementById('diaryStarsDate');
  if (dateInput && !dateInput.value) {
    dateInput.value = getShanghaiDateString();
  }
  loadDiaryStarsList();
}

async function loadDiaryStarsList() {
  const date = document.getElementById('diaryStarsDate').value || getShanghaiDateString();
  const list = document.getElementById('diaryStarsList');
  if (!list) return;
  list.innerHTML = '<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Загрузка...</div>';

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (currentUserId) headers['X-Telegram-Id'] = String(currentUserId);
    if (isAdmin) headers['X-Admin-Id'] = String(currentUserId);
    const r = await fetch(`${API_URL}/api/diary/stars/overview?entry_date=${date}`, {
      headers
    });
    if (!r.ok) {
      let detail = '';
      try { const d = await r.json(); if (d.detail) detail = ': ' + d.detail; } catch(e) {}
      list.innerHTML = `<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Ошибка загрузки (${r.status}${detail})</div>`;
      return;
    }
    const data = await r.json();
    renderDiaryStarsList(data.entries || [], date);
  } catch(e) {
    list.innerHTML = '<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Нет соединения</div>';
  }
}

function renderDiaryStarsList(entries, date) {
  const list = document.getElementById('diaryStarsList');
  if (!entries.length) {
    list.innerHTML = '<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Нет студентов в базе</div>';
    return;
  }

  const STAR_POINTS = { 1: 15, 2: 30, 3: 50 };

  const rows = entries.map(entry => {
    const stars = entry.stars || 0;
    const bonus = entry.bonus || false;
    const starsHtml = stars ? '⭐'.repeat(stars) : '—';
    const bonusHtml = bonus ? ' <span style="color:#2ecc71;font-size:10px;">+✨</span>' : '';
    const pointsEarned = stars ? STAR_POINTS[stars] + (bonus ? 20 : 0) : 0;
    const canRate = isAdmin;
    const isMe = entry.telegram_id === currentUserId;
    if (!isAdmin && !isMe) return '';

    const safeName = escapeHtml(entry.full_name);
    const onclickAttr = canRate
      ? `onclick="openDiaryStarsPopup(${entry.telegram_id}, &quot;${safeName}&quot;, '${date}')"`
      : '';
    return `<div class="diary-card" style="margin-bottom:8px;cursor:${canRate?'pointer':'default'};"
      ${onclickAttr}>
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="flex:1;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">${safeName}${isMe && !isAdmin ? ' 👈' : ''}</div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace;margin-top:2px;">
            ${stars ? starsHtml + bonusHtml + ' · +' + pointsEarned + '★' : 'ещё не оценено'}
          </div>
        </div>
        ${canRate ? `<div style="font-size:20px;color:var(--text3);">›</div>` : ''}
      </div>
    </div>`;
  });
  const html = rows.join('');
  list.innerHTML = html.trim()
    ? html
    : '<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Нет записей за этот день</div>';
}

function openDiaryStarsPopup(telegramId, name, date) {
  if (!isAdmin) return;
  diaryStarsCurrentStudent = { telegramId, name, date };
  document.getElementById('diaryStarsPopupName').textContent = name;
  document.getElementById('diaryStarsPopupDate').textContent = date;
  const popup = document.getElementById('diaryStarsPopup');
  popup.style.display = 'flex';
}

function closeDiaryStarsPopup() {
  const popup = document.getElementById('diaryStarsPopup');
  popup.style.display = 'none';
  diaryStarsCurrentStudent = null;
}

async function submitDiaryStars(value) {
  if (!diaryStarsCurrentStudent || !isAdmin) return;
  const { telegramId, name, date } = diaryStarsCurrentStudent;

  const isBonus = value === 'bonus';
  const payload = {
    telegram_id: telegramId,
    entry_date: date,
    stars: isBonus ? null : value,
    bonus: isBonus
  };

  try {
    const r = await fetch(`${API_URL}/api/diary/stars/rate`, {
      method: 'POST',
      headers: diaryHeaders(),
      body: JSON.stringify(payload)
    });
    if (r.ok) {
      const data = await r.json();
      closeDiaryStarsPopup();
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      showToast(`✅ ${name}: ${data.points_delta >= 0 ? '+' : ''}${data.points_delta}★`);
      loadDiaryStarsList();
    } else {
      let errorText = 'Ошибка при начислении.';
      try {
        const data = await r.json();
        if (data.detail) errorText = data.detail;
      } catch(e) {}
      showToast(errorText);
    }
  } catch(e) {
    showToast('Нет соединения.');
  }
}

// ── ADMIN OVERVIEW ────────────────────────────────────────────

function diaryStatusLabel(status) {
  switch (status) {
    case 'draft':     return { icon: '📝', text: 'черновик',  cls: 'draft' };
    case 'submitted': return { icon: '✅', text: 'сдано',     cls: 'submitted' };
    case 'locked':    return { icon: '🔒', text: 'закрыто',   cls: 'locked' };
    default:          return { icon: '💾', text: 'нет записи',cls: 'missing' };
  }
}

async function loadDiaryOverview(dateOverride) {
  const dateInput = document.getElementById('diaryAdminDate');
  const date = dateOverride || (dateInput && dateInput.value) || getShanghaiDateString();
  if (dateInput) dateInput.value = date;

  const list = document.getElementById('diaryStudentList');
  if (!list) return;
  list.innerHTML = '<div class="diary-day-chip-empty">Загрузка...</div>';

  try {
    const r = await fetch(`${API_URL}/api/diary/admin/overview?entry_date=${date}`, {
      headers: diaryHeaders()
    });
    if (!r.ok) { list.innerHTML = '<div class="diary-day-chip-empty">Ошибка загрузки.</div>'; return; }
    const data = await r.json();
    const entries = data.entries || [];
    if (!entries.length) {
      list.innerHTML = '<div class="diary-day-chip-empty">Нет студентов в базе.</div>';
      return;
    }
    renderDiaryStudentList(entries);
  } catch(e) {
    list.innerHTML = '<div class="diary-day-chip-empty">Нет соединения.</div>';
  }
}

function renderDiaryStudentList(entries) {
  const list = document.getElementById('diaryStudentList');
  if (!list) return;

  list.innerHTML = entries.map(entry => {
    const { icon, text, cls } = diaryStatusLabel(entry.status);
    const words = entry.has_entry ? `${entry.words_filled}/15` : '—';
    const isActive = diaryViewedUserId === entry.telegram_id;
    const scoreText = (entry.lesson_score || entry.diary_score)
      ? ` · 📚${entry.lesson_score || '?'} 📓${entry.diary_score || '?'}` : '';

    return `
      <div class="diary-student-row ${isActive ? 'active' : ''}"
        onclick="openStudentDiary(${entry.telegram_id}, '${escapeHtml(entry.full_name || 'Студент')}')">
        <span class="diary-student-icon">${icon}</span>
        <span class="diary-student-name">${escapeHtml(entry.full_name || 'Студент')}</span>
        <span class="diary-student-words">${words}${scoreText}</span>
        <span class="diary-student-badge ${cls}">${text}</span>
      </div>`;
  }).join('');
}

async function openStudentDiary(telegramId, name) {
  diaryViewedUserId = telegramId;

  // Show viewing banner
  const banner = document.getElementById('diaryViewingBanner');
  const bannerName = document.getElementById('diaryViewingName');
  if (banner) banner.style.display = 'flex';
  if (bannerName) bannerName.textContent = `👁 Просматриваешь: ${name}`;

  // Refresh student list to highlight active row
  await loadDiaryOverview();

  // Load that student's diary for the current overview date
  const dateInput = document.getElementById('diaryAdminDate');
  const date = (dateInput && dateInput.value) || getShanghaiDateString();

  // Load into the diary form below
  diaryCurrentDate = date;
  document.getElementById('diaryDate').value = date;

  const server = await loadDiaryFromAPI(telegramId, date);
  if (server) {
    const merged = { ...createEmptyDiaryEntry(date), ...server };
    fillDiaryForm(merged);
    applyDiaryRoleUX(server.status || 'draft');
  } else {
    fillDiaryForm(createEmptyDiaryEntry(date));
    applyDiaryRoleUX(null);
  }
}

function diaryBackToSelf() {
  diaryViewedUserId = currentUserId;

  const banner = document.getElementById('diaryViewingBanner');
  if (banner) banner.style.display = 'none';

  loadDiaryPage(getShanghaiDateString());
  loadDiaryOverview();
}

// ============================================================

// ── STATE ────────────────────────────────────────────────────
let diaryInitialized  = false;
let diaryAutosaveTimer = null;
let diaryCurrentDate  = null;
let diaryServerStatus = null;   // null | 'draft' | 'submitted' | 'locked'
let diaryViewedUserId = null;   // whose diary is open (null = currentUserId)
let diaryIsSaving     = false;

// ── UTILS ─────────────────────────────────────────────────────

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;');
}

function getDiaryStorageKey() {
  return `zhidao_diary_v1_${currentUserId || 'guest'}`;
}

function getDiaryStore() {
  try { return JSON.parse(localStorage.getItem(getDiaryStorageKey()) || '{}'); }
  catch (e) { return {}; }
}

function setDiaryStore(store) {
  localStorage.setItem(getDiaryStorageKey(), JSON.stringify(store));
}

function getShanghaiDateString() {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
  });
  const parts = formatter.formatToParts(new Date())
    .reduce((acc, p) => { acc[p.type] = p.value; return acc; }, {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function getDiaryWeekday(dateString) {
  if (!dateString) return '';
  const date = new Date(`${dateString}T00:00:00`);
  return ['Воскресенье','Понедельник','Вторник','Среда','Четверг','Пятница','Суббота'][date.getDay()] || '';
}

function createEmptyDiaryWords() {
  return Array.from({ length: 15 }, () => ({ hanzi: '', pinyin: '', translation: '' }));
}

function createEmptyDiaryEntry(dateString) {
  const date = dateString || getShanghaiDateString();
  return {
    date, weekday: getDiaryWeekday(date), weather: '',
    words: createEmptyDiaryWords(),
    discussion_rating: 0, discussion_person: '', discussion_topic: '',
    story: '', lesson_score: '', diary_score: '', updated_at: null
  };
}

function getDiaryEntryFromCache(dateString) {
  const store = getDiaryStore();
  return store[dateString] || createEmptyDiaryEntry(dateString);
}

function countDiaryWords(entry) {
  if (!entry || !entry.words) return 0;
  return entry.words.filter(w =>
    (w.hanzi || '').trim() ||
    (w.pinyin || '').trim() ||
    (w.translation || '').trim()
  ).length;
}

// Headers for all diary API calls
function diaryHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (currentUserId) {
    h['X-Telegram-Id'] = String(currentUserId);
    if (isAdmin) h['X-Admin-Id'] = String(currentUserId);
  }
  return h;
}

// ── API CALLS ─────────────────────────────────────────────────

async function loadDiaryFromAPI(targetUserId, date) {
  if (!targetUserId) return null;
  try {
    const r = await fetch(`${API_URL}/api/diary/${targetUserId}/${date}`, {
      headers: diaryHeaders()
    });
    if (!r.ok) return null;
    const data = await r.json();

    // Support both indexed rows and a plain ordered array from the API.
    const wordArr = createEmptyDiaryWords();
    if (Array.isArray(data.words)) {
      data.words.forEach((w, index) => {
        const idx = Number.isInteger(w?.row_number) ? w.row_number - 1 : index;
        if (idx >= 0 && idx < 15)
          wordArr[idx] = { hanzi: w.hanzi || '', pinyin: w.pinyin || '', translation: w.translation || '' };
      });
    }
    data.words = wordArr;

    // Flatten scores to top level
    if (data.scores) {
      data.lesson_score = data.scores.lesson_score || '';
      data.diary_score  = data.scores.diary_score  || '';
    }
    return data;
  } catch (e) {
    return null;
  }
}

async function loadDiaryListFromAPI(targetUserId) {
  if (!targetUserId) return [];
  try {
    const r = await fetch(`${API_URL}/api/diary/${targetUserId}`, {
      headers: diaryHeaders()
    });
    if (!r.ok) return [];
    const data = await r.json();
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.entries)) return data.entries;
    return [];
  } catch (e) {
    return [];
  }
}

async function saveDiaryToAPI(entry, targetUserId) {
  if (!currentUserId || !targetUserId) return false;
  try {
    const r = await fetch(`${API_URL}/api/diary/save`, {
      method: 'POST',
      headers: diaryHeaders(),
      body: JSON.stringify({
        telegram_id:       targetUserId,
        entry_date:        entry.date,
        weekday:           entry.weekday,
        weather:           entry.weather,
        words:             entry.words,
        discussion_rating: entry.discussion_rating,
        discussion_person: entry.discussion_person,
        discussion_topic:  entry.discussion_topic,
        story:             entry.story
      })
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

// ── RENDER ────────────────────────────────────────────────────

function renderDiaryWeatherOptions() {
  const sel = document.getElementById('diaryWeather');
  if (!sel) return;
  ['','☀️ Солнечно','⛅ Облачно','🌧 Дождь','🌩 Гроза','❄️ Снег','🌫 Туман'].forEach(o => {
    const opt = document.createElement('option');
    opt.value = o; opt.textContent = o || '— Погода —';
    sel.appendChild(opt);
  });
}

function renderDiaryStars(rating) {
  const container = document.getElementById('diaryStars');
  if (!container) return;
  container.innerHTML = [1,2,3,4,5].map(i =>
    `<button type="button" class="diary-star ${i <= rating ? 'active' : ''}"
      onclick="setDiaryDiscussionRating(${i})">★</button>`
  ).join('');
}

function renderDiaryWordRows(words) {
  const container = document.getElementById('diaryWordsRows');
  if (!container) return;
  const list = (words && words.length) ? words : createEmptyDiaryWords();
  container.innerHTML = list.map((word, index) => `
    <div class="diary-word-row">
      <div class="diary-word-index">${index + 1}</div>
      <input class="diary-input diary-word-input" data-word-index="${index}" data-word-field="hanzi"
        value="${escapeHtml(word.hanzi)}" placeholder="汉字">
      <input class="diary-input diary-word-input" data-word-index="${index}" data-word-field="pinyin"
        value="${escapeHtml(word.pinyin)}" placeholder="pīn yīn">
      <input class="diary-input diary-word-input" data-word-index="${index}" data-word-field="translation"
        value="${escapeHtml(word.translation)}" placeholder="перевод">
    </div>`
  ).join('');
}

function updateDiaryStatus(entry, status) {
  const badge = document.getElementById('diaryStatusBadge');
  const meta  = document.getElementById('diarySaveMeta');
  if (!badge || !meta) return;

  const wordsFilled = countDiaryWords(entry);
  const s = status || diaryServerStatus;

  if (s === 'locked') {
    badge.textContent = '🔒 заблокировано';
    badge.style.cssText = 'background:rgba(255,200,50,0.18)';
    meta.textContent = 'Запись заблокирована. Оценки финальные.';
  } else if (s === 'submitted') {
    badge.textContent = '✅ сдано на проверку';
    badge.style.cssText = 'background:rgba(50,200,100,0.18)';
    meta.textContent = 'День сдан. Ожидай оценки от вожатых.';
  } else {
    badge.textContent = currentUserId
      ? `📝 черновик: ${wordsFilled}/15 слов`
      : `💾 локальный черновик: ${wordsFilled}/15`;
    badge.style.cssText = '';
    meta.textContent = currentUserId
      ? 'Черновик сохраняется автоматически. Нажми «СДАТЬ ДЕНЬ» когда закончишь.'
      : 'Открой через Telegram-бота — данные будут сохраняться на сервере.';
  }
}

async function renderDiarySavedDays() {
  const container = document.getElementById('diarySavedDays');
  if (!container) return;

  const tid = diaryViewedUserId || currentUserId;
  const serverList = await loadDiaryListFromAPI(tid);
  const localDates  = Object.keys(getDiaryStore());
  const serverDates = new Set(serverList.map(e => e.entry_date));
  const allDates    = [...new Set([...serverList.map(e => e.entry_date), ...localDates])]
    .sort((a, b) => b.localeCompare(a));

  if (!allDates.length) {
    container.innerHTML = '<div class="diary-day-chip-empty">Записей пока нет. Начни с текущего дня.</div>';
    return;
  }

  const byDate = Object.fromEntries(serverList.map(e => [e.entry_date, e]));
  container.innerHTML = allDates.map(date => {
    const active     = date === diaryCurrentDate ? 'active' : '';
    const srv        = byDate[date];
    const local      = getDiaryEntryFromCache(date);
    const wordCount  = srv ? (srv.words_filled ?? srv.word_count ?? 0) : countDiaryWords(local);
    const icon       = srv
      ? (srv.status === 'locked' ? '🔒' : srv.status === 'submitted' ? '✅' : '📝')
      : '💾';
    return `<button type="button" class="diary-day-chip ${active}"
      onclick="loadDiaryPage('${date}')">${icon} ${date}<span>${wordCount}/15</span></button>`;
  }).join('');
}

// ── ROLE UX ───────────────────────────────────────────────────

function applyDiaryRoleUX(status) {
  diaryServerStatus = status || null;
  const isLocked    = status === 'locked';
  const isSubmitted = status === 'submitted';
  const studentLock = isLocked || isSubmitted;

  // Admins can edit their OWN diary; readonly only when viewing someone else's
  const viewingOther   = isAdmin && diaryViewedUserId && diaryViewedUserId !== currentUserId;
  const contentReadonly = viewingOther || studentLock;

  // Content fields
  const contentIds = ['diaryWeekday','diaryWeather','diaryDiscussPerson','diaryDiscussTopic','diaryStory'];
  contentIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.readOnly = contentReadonly;
  });
  document.querySelectorAll('.diary-word-input').forEach(el => {
    el.readOnly = contentReadonly;
  });

  // Stars: disabled when content is readonly
  const canClickStars = !contentReadonly;
  document.querySelectorAll('.diary-star').forEach(el => {
    el.disabled = !canClickStars;
    el.style.opacity = canClickStars ? '1' : '0.5';
    el.style.cursor  = canClickStars ? 'pointer' : 'default';
  });

  // Score fields: editable only by admin when NOT locked yet
  ['diaryLessonScore','diaryDiaryScore'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.readOnly = !(isAdmin && !isLocked);
  });

  // Buttons — show/hide based on role + status
  const show = (id, visible) => {
    const el = document.getElementById(id);
    if (el) el.style.display = visible ? '' : 'none';
  };
  show('diaryBtnSave',   !isAdmin && !studentLock);
  show('diaryBtnSubmit', !isAdmin && !studentLock);
  show('diaryBtnScore',  isAdmin && isSubmitted && !isLocked);
  show('diaryBtnLock',   isAdmin && isSubmitted && !isLocked);
  show('diaryBtnUnlock', isAdmin && isLocked);
  show('diaryBtnReset',  !isAdmin && !studentLock);

  updateDiaryStatus(collectDiaryFormData(), status);
}

// ── FORM ──────────────────────────────────────────────────────

function fillDiaryForm(entry) {
  document.getElementById('diaryDate').value              = entry.date || '';
  document.getElementById('diaryWeekday').value           = entry.weekday || getDiaryWeekday(entry.date);
  document.getElementById('diaryWeather').value           = entry.weather || '';
  document.getElementById('diaryDiscussionRating').value  = entry.discussion_rating || 0;
  document.getElementById('diaryDiscussPerson').value     = entry.discussion_person || '';
  document.getElementById('diaryDiscussTopic').value      = entry.discussion_topic || '';
  document.getElementById('diaryStory').value             = entry.story || '';
  document.getElementById('diaryLessonScore').value       = entry.lesson_score || '';
  document.getElementById('diaryDiaryScore').value        = entry.diary_score || '';
  renderDiaryStars(entry.discussion_rating || 0);
  renderDiaryWordRows(entry.words);
}

function collectDiaryFormData() {
  const date  = document.getElementById('diaryDate').value || getShanghaiDateString();
  const words = createEmptyDiaryWords().map((_, i) => ({
    hanzi:       document.querySelector(`[data-word-index="${i}"][data-word-field="hanzi"]`)?.value  || '',
    pinyin:      document.querySelector(`[data-word-index="${i}"][data-word-field="pinyin"]`)?.value || '',
    translation: document.querySelector(`[data-word-index="${i}"][data-word-field="translation"]`)?.value || ''
  }));
  return {
    date, weekday: getDiaryWeekday(date),
    weather:           document.getElementById('diaryWeather').value || '',
    words,
    discussion_rating: parseInt(document.getElementById('diaryDiscussionRating').value || '0', 10),
    discussion_person: document.getElementById('diaryDiscussPerson').value.trim(),
    discussion_topic:  document.getElementById('diaryDiscussTopic').value.trim(),
    story:             document.getElementById('diaryStory').value.trim(),
    lesson_score:      document.getElementById('diaryLessonScore').value.trim(),
    diary_score:       document.getElementById('diaryDiaryScore').value.trim(),
    updated_at:        new Date().toISOString()
  };
}

// ── ACTIONS ───────────────────────────────────────────────────

async function saveDiaryDraft(showFeedback = false) {
  if (diaryIsSaving) return;
  diaryIsSaving = true;
  try {
    const entry = collectDiaryFormData();
    const tid   = diaryViewedUserId || currentUserId;

    // Always write to localStorage cache first
    const store = getDiaryStore();
    store[entry.date] = entry;
    diaryCurrentDate = entry.date;
    setDiaryStore(store);
    document.getElementById('diaryWeekday').value = entry.weekday;

    // Try API save (students only — admins don't save student content)
    let saved = false;
    if (!isAdmin) saved = await saveDiaryToAPI(entry, tid);

    updateDiaryStatus(entry, diaryServerStatus);
    renderDiarySavedDays();

    if (showFeedback) {
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      showToast(saved
        ? '✅ День сохранён на сервере.'
        : '💾 Сохранено локально (сервер недоступен).');
    }
  } finally {
    diaryIsSaving = false;
  }
}

// ── DIARY VALIDATION ──────────────────────────────────────────

function isChineseChar(ch) {
  const code = ch.codePointAt(0);
  return (code >= 0x4e00 && code <= 0x9fff)
      || (code >= 0x3400 && code <= 0x4dbf)
      || (code >= 0x20000 && code <= 0x2a6df);
}

function countChineseChars(str) {
  return [...(str || '')].filter(isChineseChar).length;
}

const PINYIN_SYLLABLE = /^(zh|ch|sh|[bpmfdtnlgkhjqxrzcsyw])?([aeiouuv]+(?:ng?|n)?|[mn])[1-5]$/i;

function validatePinyinToken(token) {
  return PINYIN_SYLLABLE.test(token);
}

function validateDiary(entry) {
  const warnings = [];

  entry.words.forEach((w, i) => {
    const row   = i + 1;
    const hanzi = (w.hanzi || '').trim();
    const pinyin= (w.pinyin || '').trim();
    const trans = (w.translation || '').trim();
    if (!hanzi && !pinyin && !trans) return;

    if (hanzi) {
      const cnCount = countChineseChars(hanzi);
      if (cnCount === 0)
        warnings.push('Строка ' + row + ': в поле иероглифов нет китайских символов');
      else if ([...hanzi].some(c => /[a-zA-Z]/.test(c)))
        warnings.push('Строка ' + row + ': в иероглифах есть латинские буквы');
    } else {
      warnings.push('Строка ' + row + ': поле иероглифов пустое');
    }

    if (pinyin) {
      const tokens = pinyin.trim().toLowerCase().split(/\s+/);
      const bad = tokens.filter(t => !validatePinyinToken(t));
      if (bad.length)
        warnings.push('Строка ' + row + ': пиньинь — «' + bad.join(', ') + '» не похоже на формат ni3 hao3');
    } else if (hanzi) {
      warnings.push('Строка ' + row + ': пиньинь не заполнен');
    }

    if (!trans && hanzi)
      warnings.push('Строка ' + row + ': перевод не заполнен');
  });

  const cnInStory = countChineseChars(entry.story || '');
  if ((entry.story || '').trim() && cnInStory < 10)
    warnings.push('Текст дня: маловато иероглифов (' + cnInStory + ') — проверь, всё ли написано');

  return warnings;
}

async function submitDiary() {
  if (!currentUserId) { showToast('Открой через бота.'); return; }
  const entry     = collectDiaryFormData();
  const wordCount = countDiaryWords(entry);
  const hasStory  = entry.story.trim().length > 0;

  if (wordCount < 1 && !hasStory) {
    showToast('Заполни хотя бы несколько слов или напиши текст дня перед сдачей.');
    return;
  }

  const warnings = validateDiary(entry);
  const popupMsg = warnings.length
    ? '\u26a0\ufe0f Найдены замечания:\n' + warnings.slice(0,5).map(w => '\u2022 ' + w).join('\n') + (warnings.length > 5 ? '\n...и ещё ' + (warnings.length - 5) : '') + '\n\nВсё равно сдать?'
    : 'Слов: ' + wordCount + '/15. После сдачи редактирование будет закрыто до разблокировки.';

  tg.showPopup({
    title: warnings.length ? '\u26a0\ufe0f Проверь дневник' : 'Сдать день?',
    message: popupMsg,
    buttons: [{ id: 'yes', type: 'default', text: warnings.length ? 'Всё равно сдать' : '\u2705 Сдать' }, { type: 'cancel', text: warnings.length ? 'Исправить' : 'Отмена' }]
  }, async (btnId) => {
    if (btnId !== 'yes') return;
    await saveDiaryDraft(false);
    try {
      const r = await fetch(`${API_URL}/api/diary/submit`, {
        method: 'POST',
        headers: diaryHeaders(),
        body: JSON.stringify({ telegram_id: currentUserId, entry_date: entry.date })
      });
      if (r.ok) {
        try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
        applyDiaryRoleUX('submitted');
        renderDiarySavedDays();
        showToast('✅ День сдан на проверку!');
      } else {
        showToast('Ошибка при сдаче. Попробуй ещё раз.');
      }
    } catch(e) {
      showToast('Нет соединения с сервером.');
    }
  });
}

async function scoreDiary() {
  if (!isAdmin) return;
  const date   = document.getElementById('diaryDate').value || getShanghaiDateString();
  const lesson = document.getElementById('diaryLessonScore').value.trim();
  const diary  = document.getElementById('diaryDiaryScore').value.trim();
  const tid    = diaryViewedUserId || currentUserId;
  try {
    const r = await fetch(`${API_URL}/api/diary/score`, {
      method: 'POST',
      headers: diaryHeaders(),
      body: JSON.stringify({ telegram_id: tid, entry_date: date, lesson_score: lesson, diary_score: diary })
    });
    if (r.ok) {
      const data = await r.json();
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      showToast('⭐ Оценки выставлены.');
      if (data.entry) {
        const merged = { ...createEmptyDiaryEntry(date), ...data.entry };
        fillDiaryForm(merged);
        applyDiaryRoleUX(merged.status || 'reviewed');
      }
      loadDiaryOverview(date);
    } else {
      let errorText = 'Ошибка при сохранении оценки.';
      try {
        const data = await r.json();
        if (data.detail) errorText = data.detail;
      } catch(e) {}
      showToast(errorText);
    }
  } catch(e) {
    showToast('Нет соединения.');
  }
}

async function lockDiaryEntry(locked) {
  if (!isAdmin) return;
  const date = document.getElementById('diaryDate').value || getShanghaiDateString();
  const tid  = diaryViewedUserId || currentUserId;
  try {
    const r = await fetch(`${API_URL}/api/diary/lock`, {
      method: 'POST',
      headers: diaryHeaders(),
      body: JSON.stringify({ telegram_id: tid, entry_date: date, locked })
    });
    if (r.ok) {
      applyDiaryRoleUX(locked ? 'locked' : 'submitted');
      renderDiarySavedDays();
      showToast(locked ? '🔒 Запись заблокирована.' : '🔓 Запись разблокирована.');
    }
  } catch(e) {
    showToast('Нет соединения.');
  }
}

function queueDiaryAutosave() {
  if (!diaryInitialized || isAdmin) return;
  clearTimeout(diaryAutosaveTimer);
  diaryAutosaveTimer = setTimeout(() => saveDiaryDraft(false), 700);
}

function setDiaryDiscussionRating(value) {
  document.getElementById('diaryDiscussionRating').value = value;
  renderDiaryStars(value);
  queueDiaryAutosave();
}

async function loadDiaryPage(dateOverride = '') {
  initDiaryPage();
  const date = dateOverride
    || document.getElementById('diaryDate').value
    || diaryCurrentDate
    || getShanghaiDateString();

  diaryCurrentDate  = date;
  diaryViewedUserId = diaryViewedUserId || currentUserId;
  document.getElementById('diaryDate').value = date;

  // 1. Immediate paint from cache
  const cached = getDiaryEntryFromCache(date);
  fillDiaryForm(cached);
  applyDiaryRoleUX(diaryServerStatus);
  renderDiarySavedDays();

  // 2. Async server fetch — update over the top
  const server = await loadDiaryFromAPI(diaryViewedUserId, date);
  if (server) {
    const merged = { ...cached, ...server };
    const store  = getDiaryStore();
    store[date]  = merged;
    setDiaryStore(store);
    fillDiaryForm(merged);
    applyDiaryRoleUX(server.status || 'draft');
  } else {
    applyDiaryRoleUX(null);
  }
  renderDiarySavedDays();
}

function resetDiaryForCurrentDate() {
  const date = document.getElementById('diaryDate').value || diaryCurrentDate || getShanghaiDateString();
  tg.showPopup({
    title: 'Очистить черновик?',
    message: 'Удалить локальную копию для этой даты? Данные на сервере останутся.',
    buttons: [{ id: 'yes', type: 'destructive', text: 'Очистить' }, { type: 'cancel' }]
  }, (btnId) => {
    if (btnId !== 'yes') return;
    const store = getDiaryStore();
    delete store[date];
    setDiaryStore(store);
    fillDiaryForm(createEmptyDiaryEntry(date));
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
  });
}

function initDiaryPage() {
  if (diaryInitialized) return;
  diaryInitialized = true;
  renderDiaryWeatherOptions();

  const diaryPage = document.getElementById('page-diary');
  const dateInput = document.getElementById('diaryDate');
  if (dateInput) {
    dateInput.value = getShanghaiDateString();
    dateInput.addEventListener('change', () => loadDiaryPage(dateInput.value));
  }

  diaryPage.addEventListener('input', (event) => {
    if (event.target.id === 'diaryDate') return;
    queueDiaryAutosave();
  });
  diaryPage.addEventListener('change', (event) => {
    if (event.target.id === 'diaryDate') return;
    queueDiaryAutosave();
  });

  // Show admin panel for admins
  if (isAdmin) {
    const panel = document.getElementById('diaryAdminPanel');
    if (panel) panel.style.display = 'block';
    const adminDate = document.getElementById('diaryAdminDate');
    if (adminDate) adminDate.value = getShanghaiDateString();
    loadDiaryOverview();
  }

  loadDiaryPage(getShanghaiDateString());
}
