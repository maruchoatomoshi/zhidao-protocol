/**
 * ZHIDAO Protocol — Дневник Архитектора
 * Лог-записи, открывающиеся по мере прогресса оператора.
 */

const ARCHITECT_DIARY_AUTHORS = {
  architect: { name: 'АРХИТЕКТОР',       image: 'architect_happy.png', color: '#00ff66' },
  olga:      { name: 'ОЛЬГА МИХАЙЛОВНА', image: 'olga.png',            color: '#ffd23f' },
  wunan:     { name: 'ВУ НАН',           image: 'wungan.png',          color: '#9b6bff' }
};

const ARCHITECT_DIARY_ENTRIES = [
  {
    code: "intro",
    title: "ЗАПИСЬ #000 // ИНИЦИАЛИЗАЦИЯ",
    who: "olga",
    text: "Привет! Это дневник вожатых — мы будем иногда оставлять здесь заметки о том, что происходит. Сегодня заметила, что вы быстро втянулись в баллы и кейсы. Это хорошо, только не забывайте и про сон — я буду напоминать",
    image: "olga.png"
  },
  {
    code: "first_spin",
    title: "ЗАПИСЬ #001 // ПЕРВАЯ КРУТКА",
    who: "wunan",
    text: "Слышала, что кто-то уже открыл свой первый кейс! Повезло не так, как хотелось — бывает. Следующий раз обязательно будет удачнее, 加油 (надо стараться)!",
    image: "wungan.png"
  },
  {
    code: "first_item",
    title: "ЗАПИСЬ #002 // ПЕРВЫЙ ТРОФЕЙ",
    who: "olga",
    text: "О, у тебя появился первый предмет в инвентаре! Поздравляю. Совет от меня: не продавай его сразу на эмоциях — потом обычно жалеют",
    image: "olga.png"
  },
  {
    code: "first_raid",
    title: "ЗАПИСЬ #003 // ПЕРВЫЙ РЕЙД",
    who: "wunan",
    text: "Вы присоединились к рейду — отлично, вместе веселее и быстрее! Шум и движение — это нормально, тишина у нас обычно значит, что кто-то проспал расписание",
    image: "wungan.png"
  },
  {
    code: "first_economy",
    title: "ЗАПИСЬ #004 // ПЕРВАЯ КОРРЕКЦИЯ БАЛАНСА",
    who: "wunan",
    text: "Твой баланс баллов поправили вручную. Заслуженно или нет — решали без меня, но в журнал я это всё равно записываю",
    image: "wungan.png"
  },
  {
    code: "first_achievement",
    title: "ЗАПИСЬ #005 // ПЕРВОЕ ДОСТИЖЕНИЕ",
    who: "architect",
    text: "Получено первое достижение! Система поздравляет вас сухим текстом, потому что других эмоций у системы пока нет. Но если бы были, то это были бы гордость и легкое недоверие, что вы справились сами",
    image: "architect_happy.png"
  },
  {
    code: "first_laundry",
    title: "ЗАПИСЬ #006 // ПЕРВАЯ ЗАПИСЬ НА СТИРКУ",
    who: "olga",
    text: "Видела, что ты записался на стирку. Мелочь на первый взгляд, а на деле именно из таких привычек складывается порядок в комнате и в голове",
    image: "olga.png"
  },
  {
    code: "first_shop_tx",
    title: "ЗАПИСЬ #007 // ПЕРВАЯ ТРАНЗАКЦИЯ",
    who: "olga",
    text: "У тебя прошла первая операция в магазине — покупка, продажа или подарок. Экономика заработала! Только не забывай: то, что отдаёшь — кому-то достаётся, и наоборот",
    image: "olga.png"
  },
  {
    code: "first_contract",
    title: "ЗАПИСЬ #008 // ПЕРВОЕ ПОРУЧЕНИЕ",
    who: "architect",
    text: "Оператор оформил первое поручение на доске контрактов! Бюрократия — древнейшая технология контроля, и она прекрасно работает даже в киберпанке. Спасибо, что заполнили форму. Действительно, это редкость",
    image: "architect_happy.png"
  },
  {
    code: "architect_intro",
    title: "ЗАПИСЬ #009 // ПЕРЕД АКТИВАЦИЕЙ ПРОТОКОЛА АРХИТЕКТОРА",
    who: "architect",
    text: "Решили бросить вызов системе? Ну что ж, посмотрим, сколько вы сможете продержаться. Здесь нет места ошибкам, останутся сильнейшие",
    image: "architect_event_before.png"
  },
  {
    code: "architect_victory",
    title: "ЗАПИСЬ #010 // ПОСЛЕ ПОБЕДЫ",
    who: "architect",
    text: "Не может быть, цифры не могут обманывать... Можете наслаждаться вашей победой, но впереди вас ждёт более серьёзная угроза, чем вы могли себе представить",
    image: "architect_ivent_losse.png"
  },
  {
    code: "architect_defeat",
    title: "ЗАПИСЬ #011 // ПОСЛЕ ПОРАЖЕНИЯ",
    who: "architect",
    text: "Протокол подавления завершён не в вашу пользу. Не страшно — система предусматривает повторные попытки, в отличие от некоторых людей. Перегруппируйтесь, отдохните и в следующий раз действуйте слаженнее. Я подожду, я всегда жду",
    image: "architect_ivent_winn.png"
  }
];

const ARCHITECT_DIARY_IMG_BASE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/';

function _buildArchitectDiaryCard(entry, unlocked, unlockedAt) {
  const lockedClass = unlocked ? '' : ' architect-diary-card-locked';
  const title = unlocked ? escapeHtml(entry.title) : 'ЗАПИСЬ ЗАШИФРОВАНА // 加密记录';
  const text = unlocked ? escapeHtml(entry.text) : 'Этот фрагмент журнала пока недоступен. Продолжайте действовать. Доступ откроется по мере прогресса';
  const meta = unlocked && unlockedAt ? `<div class="architect-diary-card-meta">// разблокировано: ${escapeHtml(unlockedAt)}</div>` : '';
  const image = (unlocked && entry.image)
    ? `<div class="architect-diary-card-img"><img src="${ARCHITECT_DIARY_IMG_BASE}${escapeHtml(entry.image)}" alt="" loading="lazy" oncontextmenu="return false"></div>`
    : '';
  const author = unlocked ? (ARCHITECT_DIARY_AUTHORS[entry.who] || ARCHITECT_DIARY_AUTHORS.architect) : null;
  const authorBadge = author
    ? `<div class="architect-diary-card-author" style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
         <img src="${ARCHITECT_DIARY_IMG_BASE}${escapeHtml(author.image)}" alt="" loading="lazy" oncontextmenu="return false" style="width:22px;height:22px;border-radius:50%;object-fit:cover;border:1px solid ${author.color}66;">
         <span style="font-size:11px;color:${author.color};letter-spacing:0.5px;">${escapeHtml(author.name)}</span>
       </div>`
    : '';

  return `
    <div class="card architect-diary-card${lockedClass}" style="margin-bottom:10px;">
      <div class="card-inner" style="padding:12px 14px;">
        <div class="architect-diary-card-title">${title}</div>
        ${authorBadge}
        ${image}
        <div class="architect-diary-card-text">${text}</div>
        ${meta}
      </div>
    </div>`;
}

async function renderArchitectDiary() {
  const el = document.getElementById('architectDiaryContainer');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка журнала...</div>';

  let unlockedMap = {};
  try {
    const { data } = await apiGetJson(`/api/diary/architect/${currentUserId}`);
    (data?.entries || []).forEach(e => { unlockedMap[e.entry_code] = e.unlocked_at; });
  } catch (e) {}

  unlockedMap['intro'] = unlockedMap['intro'] || true;

  const html = ARCHITECT_DIARY_ENTRIES.map(entry => {
    const unlocked = entry.code === 'intro' || Object.prototype.hasOwnProperty.call(unlockedMap, entry.code);
    const unlockedAt = typeof unlockedMap[entry.code] === 'string' ? unlockedMap[entry.code] : null;
    return _buildArchitectDiaryCard(entry, unlocked, unlockedAt);
  }).join('');

  el.innerHTML = html;
}

async function unlockArchitectDiaryEntry(entryCode) {
  if (!currentUserId) return;
  try {
    const { data } = await apiPostJson('/api/diary/architect/unlock', {
      telegram_id: currentUserId,
      entry_code: entryCode
    });
    if (data && data.unlocked) {
      const entry = ARCHITECT_DIARY_ENTRIES.find(e => e.code === entryCode);
      if (entry) showArchitectPopup(entry);
    }
  } catch (e) {}
}

const ARCHITECT_DIARY_SEEN_KEY = 'architectDiarySeenEntries';
const ARCHITECT_DIARY_BASELINE_KEY = 'architectDiaryBaselineDone';

function _getArchitectDiarySeen() {
  try {
    const raw = localStorage.getItem(ARCHITECT_DIARY_SEEN_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function _markArchitectDiarySeen(codes) {
  try {
    const seen = new Set(_getArchitectDiarySeen());
    codes.forEach(c => seen.add(c));
    localStorage.setItem(ARCHITECT_DIARY_SEEN_KEY, JSON.stringify([...seen]));
  } catch (e) {}
}

async function checkArchitectDiaryUnlocks() {
  if (!currentUserId) return;
  try {
    const { data } = await apiGetJson(`/api/diary/architect/${currentUserId}`);
    const unlockedCodes = (data?.entries || []).map(e => e.entry_code);
    const baselineDone = localStorage.getItem(ARCHITECT_DIARY_BASELINE_KEY);
    if (!baselineDone) {
      // First run on this device: baseline existing unlocks without popping them all.
      _markArchitectDiarySeen(unlockedCodes);
      localStorage.setItem(ARCHITECT_DIARY_BASELINE_KEY, '1');
      return;
    }
    const seen = new Set(_getArchitectDiarySeen());
    const newlyUnlocked = unlockedCodes.filter(code => !seen.has(code));
    if (!newlyUnlocked.length) return;
    _markArchitectDiarySeen(newlyUnlocked);
    handleDiaryUnlocks(newlyUnlocked);
  } catch (e) {}
}
window.checkArchitectDiaryUnlocks = checkArchitectDiaryUnlocks;

function handleDiaryUnlocks(diaryUnlocked) {
  if (!Array.isArray(diaryUnlocked) || !diaryUnlocked.length) return;
  _markArchitectDiarySeen(diaryUnlocked);
  const entries = diaryUnlocked
    .map(code => ARCHITECT_DIARY_ENTRIES.find(e => e.code === code))
    .filter(Boolean);
  entries.forEach((entry, idx) => {
    setTimeout(() => showArchitectPopup(entry), idx * 400);
  });
}
window.handleDiaryUnlocks = handleDiaryUnlocks;

let architectPopupTypeTimer = null;

function showArchitectPopup(entry) {
  const overlay = document.getElementById('architectPopupOverlay');
  const imageEl = document.getElementById('architectPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('architectPopupText');
  const titleEl = document.getElementById('architectPopupTitle');
  if (!overlay || !textEl) return;

  const author = ARCHITECT_DIARY_AUTHORS[entry.who] || ARCHITECT_DIARY_AUTHORS.architect;
  if (titleEl) { titleEl.textContent = author.name; titleEl.style.color = author.color; }

  if (imageEl) {
    imageEl.style.backgroundImage = entry.image ? `url('${ARCHITECT_DIARY_IMG_BASE}${entry.image}')` : '';
    imageEl.style.animation = 'none';
    void imageEl.offsetWidth;
    imageEl.style.animation = '';
  }
  if (box) {
    box.style.animation = 'none';
    void box.offsetWidth;
    box.style.animation = '';
  }

  document.body.classList.add('architect-popup-open');
  overlay.style.display = 'flex';
  typeArchitectPopupText(entry.text);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}

function typeArchitectPopupText(text) {
  const textEl = document.getElementById('architectPopupText');
  if (!textEl) return;
  if (architectPopupTypeTimer) {
    clearInterval(architectPopupTypeTimer);
    architectPopupTypeTimer = null;
  }

  textEl.innerHTML = '<span class="architect-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.architect-popup-typed');
  let i = 0;
  architectPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(architectPopupTypeTimer);
      architectPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeArchitectPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('architectPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  document.body.classList.remove('architect-popup-open');
  if (architectPopupTypeTimer) {
    clearInterval(architectPopupTypeTimer);
    architectPopupTypeTimer = null;
  }
}
