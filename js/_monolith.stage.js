
const tg = window.Telegram?.WebApp || {
  ready:()=>{}, expand:()=>{}, close:()=>{},
  setHeaderColor:()=>{}, setBackgroundColor:()=>{},
  showAlert:(msg)=>alert(msg),
  showPopup:(opts,cb)=>{ const msg=(opts.title||'')+'\n'+(opts.message||''); setTimeout(()=>{ if(confirm(msg)) cb(opts.buttons&&opts.buttons[0]?opts.buttons[0].id:'confirm'); else cb('cancel'); },0); },
  HapticFeedback:{ notificationOccurred:()=>{}, impactOccurred:()=>{}, selectionChanged:()=>{} },
  initDataUnsafe:{user:null}, BackButton:{show:()=>{},hide:()=>{},onClick:()=>{}},
  MainButton:{show:()=>{},hide:()=>{}}, themeParams:{}
};
try { tg.expand(); } catch(e) {}
try { tg.setHeaderColor('#050510'); } catch(e) {}
try { tg.setBackgroundColor('#050510'); } catch(e) {}

const API_URL = 'https://hk.marucho.icu:8443';
const THEMES = ['', 'nw-light', 'genshin-light', 'genshin-dark'];
const WEATHER_KEY = '03232b342b9270f8b24ed68e2c55d8f4';
const EXCHANGE_KEY = 'a8c5f8c5d5e5b5a5';
const ADMIN_IDS = [389741116, 244487659, 1190015933, 491711713];

let currentUserId = null;
let currentThemePath = null; // "cyberpunk" | "genshin" | null
let currentPoints = 0;
let userConfig = null;
let isAdmin = false;
let isSpinning = false;
let selectedLaundryDate = null;
let laundryData = [];
let shopMode = 'store';
let currentMoreSection = null;
let currentArchitectEvent = null;
let currentArchitectEventId = null;
let globalAlertPollingHandle = null;
let casinoPlayOriginalMarkup = '';
let shopStoreOriginalMarkup = '';


const PRIZES = [
  { code:'empty',   icon:'🍚', name:'Пустая миска риса', desc:'Ничего не выпало...', points:0,   rarity:'common' },
  { code:'small',   icon:'⭐', name:'+30 баллов',        desc:'Небольшой бонус',     points:30,  rarity:'common' },
  { code:'medium',  icon:'💫', name:'+60 баллов',        desc:'Неплохо!',            points:60,  rarity:'uncommon' },
  { code:'walk',    icon:'🕐', name:'+30 мин свободы',   desc:'Покажи скрин вожатому', points:0, rarity:'uncommon' },
  { code:'laundry', icon:'🧺', name:'Вне очереди!',      desc:'Первым на стирку',    points:0,   rarity:'rare' },
  { code:'skip',    icon:'🛡', name:'Иммунитет!',        desc:'Один пропуск без штрафа', points:0, rarity:'rare' },
  { code:'jackpot', icon:'👑', name:'ДЖЕКПОТ!',          desc:'+250 баллов! Невероятно!', points:250, rarity:'jackpot' },
];
const PURPLE_PRIZES = [
  { code:'implant_guanxi',    icon:'🤝', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true',           name:'Гуаньси 关系',       desc:'Имплант: -10% к ценам в магазине', points:0, rarity:'rare' },
  { code:'implant_terracota', icon:'🗿', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/armor.png?raw=true',                    name:'Терракота 兵马俑',   desc:'Имплант: блок 1 штрафа в день',    points:0, rarity:'rare' },
  { code:'implant_panda',     icon:'🐼', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/panda_implant.png?raw=true',      name:'Панда 🐼',           desc:'Кэшбек +10★ с покупки',            points:0, rarity:'rare' },
  { code:'implant_shaolin',   icon:'🥋', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/shaolin_implant.png?raw=true',    name:'Шаолинь 少林',       desc:'+20★ за перекличку вовремя',       points:0, rarity:'rare' },
  { code:'implant_linguasoft',icon:'🎙', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/linguasoft_implant.png?raw=true', name:'Linguasoft 口才',    desc:'+30★ за оценку 5/5 в дневнике',   points:0, rarity:'rare' },
  { code:'implant_caishen',   icon:'💰', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/caishen.png?raw=true',            name:'Цайшэнь 财神',       desc:'+15★ каждые 24 часа',              points:0, rarity:'rare' },
  { code:'implant_qilin',     icon:'🐉', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/qilin_implant.png?raw=true',      name:'Цилинь 麒麟',        desc:'+10★ за каждого владельца Цилиня', points:0, rarity:'rare' },
];
const BLACK_PRIZES = [
  { code:'implant_red_dragon', icon:'🐉', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true',           name:'Красный Дракон 红龙',    desc:'⚡ ЛЕГЕНДАРНЫЙ ПРОТОКОЛ!', points:0, rarity:'jackpot' },
  { code:'implant_netwatch',   icon:'🔴', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/wangluoshouwei_implant.png?raw=true', name:'Сетевой Дозор 网络守卫', desc:'⚡ ЛЕГЕНДАРНЫЙ ПРОТОКОЛ!', points:0, rarity:'jackpot' },
];
const PRIZE_MAP = {};
[...PRIZES, ...PURPLE_PRIZES, ...BLACK_PRIZES].forEach(p => PRIZE_MAP[p.code] = p);
const CASE_IMAGES = {
  gold:   'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/1774509730760.png',
  purple: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/purple_case.png',
  black:  'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/legendary_case.png',
};

const ACHIEVEMENT_ICONS = {
  early_bird:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g1)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="26" cy="22" r="7" fill="url(#g1)"/><path d="M14 32 Q26 18 38 32" stroke="url(#g1)" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M20 36 L26 28 L32 36" fill="url(#g1)"/><circle cx="26" cy="10" r="3" fill="url(#g1)"/></svg>`,
  iron_mode:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g2)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="26" cy="26" r="14" stroke="url(#g2)" stroke-width="2" fill="none"/><path d="M26 12 L26 16 M26 36 L26 40 M12 26 L16 26 M36 26 L40 26" stroke="url(#g2)" stroke-width="2.5" stroke-linecap="round"/><circle cx="26" cy="26" r="5" fill="url(#g2)"/></svg>`,
  legend:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g3" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g3)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M26 8 L30 20 L43 20 L33 28 L37 41 L26 33 L15 41 L19 28 L9 20 L22 20 Z" fill="url(#g3)"/></svg>`,
  curious:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g4" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g4)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="23" cy="23" r="10" stroke="url(#g4)" stroke-width="2.5" fill="none"/><line x1="30" y1="30" x2="40" y2="40" stroke="url(#g4)" stroke-width="3" stroke-linecap="round"/></svg>`,
  polyglot:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g5" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g5)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M10 18 Q26 12 42 18 L42 32 Q26 38 10 32 Z" fill="url(#g5)" opacity="0.3" stroke="url(#g5)" stroke-width="1.5"/><text x="26" y="29" text-anchor="middle" font-size="14" font-weight="bold" fill="url(#g5)">你好</text></svg>`,
  explorer:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g6" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g6)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M14 38 L20 14 L26 32 L32 18 L38 38" stroke="url(#g6)" stroke-width="2.5" fill="none" stroke-linejoin="round"/><circle cx="26" cy="18" r="4" fill="url(#g6)"/></svg>`,
  brave:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g7" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g7)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M18 36 L18 22 Q18 16 24 16 L28 16 Q30 16 30 20 L30 24 L34 24 Q38 24 38 28 L38 36" stroke="url(#g7)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="22" cy="36" r="2" fill="url(#g7)"/><circle cx="34" cy="36" r="2" fill="url(#g7)"/></svg>`,
  exemplary:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g8" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g8)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="26" cy="26" r="12" stroke="url(#g8)" stroke-width="2" fill="none"/><path d="M19 26 L23 30 L33 20" stroke="url(#g8)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
  helper:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g9" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g9)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M16 26 Q16 20 22 20 L24 20 Q26 20 26 22 Q26 20 28 20 L30 20 Q36 20 36 26 Q36 32 26 38 Q16 32 16 26 Z" fill="url(#g9)"/></svg>`,
  dragon:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g10" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g10)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M10 36 Q14 28 18 24 Q20 18 26 16 Q32 14 36 18 Q40 22 38 28 Q36 34 30 36 Q26 38 22 36 Q18 40 10 36 Z" fill="url(#g10)" opacity="0.6" stroke="url(#g10)" stroke-width="1.5"/><circle cx="32" cy="22" r="2" fill="#050510"/></svg>`,
  night_watch:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g11" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g11)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="22" cy="22" r="4" fill="url(#g11)"/><circle cx="30" cy="22" r="4" fill="url(#g11)"/><circle cx="22" cy="22" r="2" fill="#050510"/><circle cx="30" cy="22" r="2" fill="#050510"/><path d="M18 30 Q26 36 34 30" stroke="url(#g11)" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,
  master:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g12" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g12)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><rect x="18" y="14" width="16" height="8" rx="2" fill="url(#g12)" opacity="0.6"/><rect x="14" y="26" width="8" height="12" rx="2" fill="url(#g12)" opacity="0.4"/><rect x="26" y="26" width="12" height="12" rx="2" fill="url(#g12)" opacity="0.8"/></svg>`,
  gambler:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g13" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g13)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><rect x="12" y="16" width="28" height="22" rx="4" stroke="url(#g13)" stroke-width="2" fill="rgba(212,175,55,0.1)"/><text x="19" y="31" font-size="8" fill="#f5d05a" font-weight="bold">7</text><text x="26" y="31" font-size="8" fill="#f5d05a" font-weight="bold">♦</text><text x="33" y="31" font-size="8" fill="#f5d05a" font-weight="bold">7</text></svg>`,
  lucky:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g14" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g14)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M26 14 Q26 20 20 20 Q26 20 26 26 Q26 20 32 20 Q26 20 26 14 Z" fill="url(#g14)"/><path d="M26 26 Q26 32 20 32 Q26 32 26 38 Q26 32 32 32 Q26 32 26 26 Z" fill="url(#g14)"/><circle cx="26" cy="26" r="2" fill="url(#g14)"/></svg>`
};

// Инициализация пользователя
const user = tg.initDataUnsafe?.user;
if (user) {
  currentUserId = user.id;
  isAdmin = ADMIN_IDS.includes(user.id);
  loadUserData(user.id);
  loadPoints(user.id);
  loadImplants(user.id);
  startGlobalAlertPolling();
  if (isAdmin) {
    document.getElementById('adminMoreBtn').style.display = 'block';
    document.getElementById('shopResetBtn').style.display = 'block';
  }
}

loadSavedTheme();
// genshinTabBtn управляется через applyThemePath
loadWeather();
loadYuanRate();
loadSchedule();
loadAnnouncements();
loadLeaderboard();
loadAchievements();
initLaundry();

// ===== НАВИГАЦИЯ =====
function showPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');

  if (name === 'schedule') { loadAnnouncements(); loadSchedule(); }
  if (name === 'implants') loadImplants(currentUserId);
  if (name === 'shop') loadShop();
  if (name === 'rating') { loadLeaderboard(); updateRatingPoints(); }
  if (name === 'diary') loadDiaryPage();
  if (name === 'diary-stars') initDiaryStarsPage();
  if (name === 'casino') {
    fetch(`${API_URL}/api/settings`).then(r => r.json()).then(settings => {
      if (settings.blackwall && !isAdmin) {
        setCasinoBlackwallState(true);
      } else {
        setCasinoBlackwallState(false);
        if (currentThemePath === 'genshin') {
          document.getElementById('casinoPlayContent').style.display = 'none';
          const gcEl = document.getElementById('casinoGenshinContent');
          if (gcEl) gcEl.style.display = 'flex';
        } else {
          document.getElementById('casinoPlayContent').style.display = 'flex';
          setTimeout(initRoulette, 50);
        }
        setTimeout(() => loadPoints(currentUserId), 300);
      }
    }).catch(() => { setTimeout(initRoulette, 50); });
  }
}

function setCasinoBlackwallState(enabled) {
  const content = document.getElementById('casinoPlayContent');
  if (!content) return;

  if (enabled) {
    if (!casinoPlayOriginalMarkup) {
      casinoPlayOriginalMarkup = content.innerHTML;
    }
    if (content.dataset.blackwallActive === '1') return;
    content.innerHTML =
      '<div class="blackwall-screen"><div class="blackwall-title">BlackWall 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
    content.dataset.blackwallActive = '1';
    return;
  }

  if (content.dataset.blackwallActive === '1' && casinoPlayOriginalMarkup) {
    content.innerHTML = casinoPlayOriginalMarkup;
  }
  delete content.dataset.blackwallActive;
}

function setShopBlackwallState(enabled) {
  const content = document.getElementById('shopStoreContent');
  if (!content) return;

  if (enabled) {
    if (!shopStoreOriginalMarkup) {
      shopStoreOriginalMarkup = content.innerHTML;
    }
    if (content.dataset.blackwallActive === '1') return;
    content.innerHTML =
      '<div class="blackwall-screen"><div class="blackwall-title">BlackWall 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
    content.dataset.blackwallActive = '1';
    return;
  }

  if (content.dataset.blackwallActive === '1') {
    content.innerHTML = shopStoreOriginalMarkup;
  }
  delete content.dataset.blackwallActive;
}

function openDiaryPage() {
  showPage('diary');
  const moreBtn = document.getElementById('nav-more-btn');
  if (moreBtn) moreBtn.classList.add('active');
}

function openMore(section) {
  // Скрываем все субстраницы
  ['themes','weather','laundry','news','achievements','team','admin'].forEach(s => {
    const el = document.getElementById('more-' + s);
    if (el) el.style.display = 'none';
  });
  const el = document.getElementById('more-' + section);
  if (!el) return;
  if (currentMoreSection === section) {
    el.style.display = 'none';
    currentMoreSection = null;
  } else {
    el.style.display = 'block';
    currentMoreSection = section;
    if (section === 'achievements') loadAchievements();
    if (section === 'news') loadAnnouncements();
    if (section === 'laundry') { initLaundry(); }
  }
}

// ===== ДАННЫЕ =====
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
    if (!r.ok) { list.innerHTML = '<div class="diary-day-chip-empty" style="padding:20px;text-align:center;">Ошибка загрузки</div>'; return; }
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

  list.innerHTML = entries.map(entry => {
    const stars = entry.stars || 0;
    const bonus = entry.bonus || false;
    const starsHtml = stars ? '⭐'.repeat(stars) : '—';
    const bonusHtml = bonus ? ' <span style="color:#2ecc71;font-size:10px;">+✨</span>' : '';
    const pointsEarned = stars ? STAR_POINTS[stars] + (bonus ? 20 : 0) : 0;
    const canRate = isAdmin;
    const isMe = entry.telegram_id === currentUserId;
    // Студент видит только свою строку
    if (!isAdmin && !isMe) return '';

    return `<div class="diary-card" style="margin-bottom:8px;cursor:${canRate?'pointer':'default'};"
      ${canRate ? `onclick="openDiaryStarsPopup(${entry.telegram_id}, '${entry.full_name}', '${date}')"` : ''}>
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="flex:1;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">${entry.full_name}${isMe && !isAdmin ? ' 👈' : ''}</div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace;margin-top:2px;">
            ${stars ? starsHtml + bonusHtml + ' · +' + pointsEarned + '★' : 'ещё не оценено'}
          </div>
        </div>
        ${canRate ? `<div style="font-size:20px;color:var(--text3);">›</div>` : ''}
      </div>
    </div>`;
  }).join('');
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
  const { telegramId, date } = diaryStarsCurrentStudent;

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
      tg.showAlert(`✅ ${diaryStarsCurrentStudent.name}: +${data.points_awarded}★ начислено!`);
      loadDiaryStarsList();
    } else {
      tg.showAlert('Ошибка при начислении.');
    }
  } catch(e) {
    tg.showAlert('Нет соединения.');
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
      tg.showAlert(saved
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
  if (!currentUserId) { tg.showAlert('Открой через бота.'); return; }
  const entry     = collectDiaryFormData();
  const wordCount = countDiaryWords(entry);
  const hasStory  = entry.story.trim().length > 0;

  if (wordCount < 1 && !hasStory) {
    tg.showAlert('Заполни хотя бы несколько слов или напиши текст дня перед сдачей.');
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
        tg.showAlert('✅ День сдан на проверку!');
      } else {
        tg.showAlert('Ошибка при сдаче. Попробуй ещё раз.');
      }
    } catch(e) {
      tg.showAlert('Нет соединения с сервером.');
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
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      tg.showAlert('⭐ Оценки выставлены.');
    } else {
      tg.showAlert('Ошибка при сохранении оценки.');
    }
  } catch(e) {
    tg.showAlert('Нет соединения.');
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
      tg.showAlert(locked ? '🔒 Запись заблокирована.' : '🔓 Запись разблокирована.');
    }
  } catch(e) {
    tg.showAlert('Нет соединения.');
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


async function loadUserData(telegramId) {
  try {
    const r = await fetch(`${API_URL}/api/user/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      isAdmin = !!data.is_admin;
      userConfig = data.link;
      document.getElementById('status').textContent = '● АКТИВЕН';
      document.getElementById('status').style.color = '#cc4444';
      document.getElementById('username').textContent = data.username;
      document.getElementById('serverTag').textContent = 'HK NODE // ' + ((data.used_traffic || 0) / 1024/1024/1024).toFixed(2) + ' GB';
      const used = data.used_traffic || 0;
      const usedGB = (used / 1024/1024/1024).toFixed(2);
      document.getElementById('trafficValue').textContent = usedGB + ' GB';
      const percent = Math.min((used / (10*1024*1024*1024)) * 100, 100);
      setTimeout(() => { document.getElementById('progressFill').style.width = percent + '%'; }, 300);
    } else {
      document.getElementById('status').textContent = '● НЕ НАЙДЕН';
      document.getElementById('username').textContent = 'Нет подписки';
    }
  } catch(e) {
    document.getElementById('status').textContent = '● ОФЛАЙН';
    document.getElementById('username').textContent = 'Ошибка связи';
  }
}

// ── THEME PATH LOGIC ──────────────────────────────────────────

function applyThemePath(path) {
  currentThemePath = path;

  const nwCards    = ['theme-btn-default', 'theme-btn-nw-light'];
  const gsCards    = ['theme-btn-genshin-light', 'theme-btn-genshin-dark'];

  if (path === 'cyberpunk') {
    nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    const t = localStorage.getItem('zhidao_theme') || '';
    if (t.startsWith('genshin')) setTheme('');
    // Показываем импланты, скрываем карточки
    const implTab = document.getElementById('implants-tab'); if (implTab) implTab.style.display = 'block';
    const cardTab = document.getElementById('cards-tab'); if (cardTab) cardTab.style.display = 'none';
    const implCat = document.getElementById('implants-catalog'); if (implCat) implCat.style.display = 'block';
    // Кейсы — показываем рулетку
    const cp = document.getElementById('casinoPlayContent'); if (cp) cp.style.display = 'flex';
    const gc = document.getElementById('casinoGenshinContent'); if (gc) gc.style.display = 'none';
    const genshinTabBtn = document.getElementById('genshinTabBtn'); if (genshinTabBtn) genshinTabBtn.style.display = 'none';
    const playBtn = document.getElementById('casinoPlayBtn'); if (playBtn) playBtn.textContent = '🎰 ИГРАТЬ';
  } else if (path === 'genshin') {
    nwCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    gsCards.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = ''; });
    const t = localStorage.getItem('zhidao_theme') || '';
    if (!t.startsWith('genshin')) setTheme('genshin-light');
    // Показываем карточки, скрываем импланты
    const implTab = document.getElementById('implants-tab'); if (implTab) implTab.style.display = 'none';
    const cardTab = document.getElementById('cards-tab'); if (cardTab) cardTab.style.display = 'block';
    const implCat = document.getElementById('implants-catalog'); if (implCat) implCat.style.display = 'none';
    // Молитвы — показываем Геншин
    const cp = document.getElementById('casinoPlayContent'); if (cp) cp.style.display = 'none';
    const gc = document.getElementById('casinoGenshinContent'); if (gc) gc.style.display = 'flex';
    const playBtn = document.getElementById('casinoPlayBtn'); if (playBtn) playBtn.textContent = '✦ МОЛИТВЫ';
  } else {
    // path = null — первый вход, показываем экран выбора
    showPathChoiceScreen();
  }
}

function showPathChoiceScreen() {
  const overlay = document.getElementById('overlay-path-choice');
  if (overlay) overlay.style.display = 'flex';
}

async function chooseThemePath(path) {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/user/set_path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ telegram_id: currentUserId, path })
    });
    if (r.ok) {
      const overlay = document.getElementById('overlay-path-choice');
      if (overlay) overlay.style.display = 'none';
      try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
      applyThemePath(path);
    } else {
      tg.showAlert('Ошибка. Попробуй ещё раз.');
    }
  } catch(e) {
    tg.showAlert('Нет соединения.');
  }
}

async function loadPoints(telegramId) {
  if (!telegramId) return;
  try {
    const r = await fetch(`${API_URL}/api/points/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      currentPoints = data.points || 0;
      updatePoints();
      const b = document.getElementById('casinoBonusBanner');
      if (data.double_win) {
        if (b) {
        b.style.display = 'block'; b.textContent = '🃏 УДВОЕНИЕ АКТИВНО!';
      }
      // Применяем путь (Киберпанк / Геншин)
      } else if (b) {
        b.style.display = 'none';
        b.textContent = '';
      }
      if (!isAdmin) applyThemePath(data.theme_path || null);
    }
  } catch(e) {}
}

async function loadPoints(telegramId) {
  if (!telegramId) return;
  try {
    const r = await fetch(`${API_URL}/api/points/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      currentPoints = data.points || 0;
      updatePoints();

      const b = document.getElementById('casinoBonusBanner');
      if (b) {
        if (data.double_win) {
          b.style.display = 'block';
          b.textContent = '🃏 УДВОЕНИЕ АКТИВНО!';
        } else {
          b.style.display = 'none';
          b.textContent = '';
        }
      }

      // Применяем путь (Киберпанк / Геншин)
      if (!isAdmin) applyThemePath(data.theme_path || null);
    }
  } catch(e) {}
}

async function loadImplants(telegramId) {
  if (!telegramId) return;
  const IMPLANT_IMGS = {
    'implant_guanxi':     'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true',
    'implant_terracota':  'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/armor.png?raw=true',
    'implant_red_dragon': 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true',
    'implant_panda':      'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/panda_implant.png?raw=true',
    'implant_shaolin':    'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/shaolin_implant.png?raw=true',
    'implant_linguasoft': 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/linguasoft_implant.png?raw=true',
    'implant_caishen':    'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/caishen.png?raw=true',
    'implant_qilin':      'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/qilin_implant.png?raw=true',
    'implant_netwatch':   'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/wangluoshouwei_implant.png?raw=true',
  };
  try {
    const r = await fetch(`${API_URL}/api/casino/implants/${telegramId}`);
    if (!r.ok) return;
    const data = await r.json();

    const homeContainer = document.getElementById('homeImplants');
    const pageContainer = document.getElementById('myImplantsPage');

    if (!data.length) {
      const empty = '<div class="empty-state" style="padding:12px;">Импланты не установлены<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Открывай фиолетовые и чёрные кейсы!</span></div>';
      if (homeContainer) homeContainer.innerHTML = empty;
      if (pageContainer) pageContainer.innerHTML = empty;
      return;
    }

    // Считаем дубли
    const implantCounts = {};
    data.forEach(imp => { implantCounts[imp.implant_id] = (implantCounts[imp.implant_id] || 0) + 1; });
    const seenTypes = {};

    // Главная страница — компактно
    const homeHtml = data.map(imp => {
      const img = IMPLANT_IMGS[imp.implant_id];
      const dots = Array(3).fill(0).map((_,i) => {
        const cls = i < imp.durability ? (imp.implant_id==='implant_red_dragon'?'dur-dot on-r':'dur-dot on') : 'dur-dot off';
        return `<div class="${cls}"></div>`;
      }).join('');
      return `<div class="implant-row">
        <div class="implant-icon ${imp.implant_id==='implant_red_dragon'?'legendary':''}">
          ${img ? `<img src="${img}" style="width:24px;height:24px;object-fit:contain;border-radius:4px;">` : imp.icon}
        </div>
        <div>
          <div class="implant-cn">${imp.name}</div>
          <div class="implant-py">${imp.desc}</div>
        </div>
        <div class="implant-dur">${dots}</div>
      </div>`;
    }).join('');
    if (homeContainer) homeContainer.innerHTML = homeHtml;

    // Страница имплантов — с кнопкой разборки для дублей
    const pageHtml = data.map(imp => {
      const img = IMPLANT_IMGS[imp.implant_id];
      const isLeg = imp.implant_id === 'implant_red_dragon';
      const isDuplicate = implantCounts[imp.implant_id] > 1;
      seenTypes[imp.implant_id] = (seenTypes[imp.implant_id] || 0) + 1;
      const isSecond = seenTypes[imp.implant_id] > 1;

      const dots = Array(3).fill(0).map((_,i) => {
        const cls = i < imp.durability ? (isLeg?'dur-dot on-r':'dur-dot on') : 'dur-dot off';
        return `<div class="${cls}"></div>`;
      }).join('');

      const duplicateBadge = isDuplicate
        ? `<span style="background:rgba(212,175,55,0.15);border:1px solid rgba(212,175,55,0.3);color:var(--gold);font-size:8px;padding:1px 6px;border-radius:3px;font-family:monospace;margin-left:6px;">ДУБЛЬ</span>`
        : '';

      const disassembleBtn = isSecond
        ? `<button onclick="disassembleImplant(${imp.id})" style="margin-top:8px;width:100%;padding:7px;background:rgba(212,175,55,0.08);border:1px solid rgba(212,175,55,0.25);color:var(--gold);border-radius:6px;font-size:9px;font-family:monospace;cursor:pointer;letter-spacing:1px;">⚙️ [ РАЗОБРАТЬ +100 ★ ]</button>`
        : '';

      return `<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
        <div style="display:flex;align-items:center;gap:10px;">
          ${img ? `<img src="${img}" style="width:52px;height:52px;object-fit:contain;border-radius:8px;border:1px solid ${isLeg?'rgba(180,20,20,0.4)':'rgba(155,89,182,0.3)'};flex-shrink:0;">` : `<div style="font-size:28px;">${imp.icon}</div>`}
          <div style="flex:1;">
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;">
              <div style="font-size:13px;font-weight:700;color:#fff;">${imp.name}</div>
              ${duplicateBadge}
            </div>
            <div style="font-size:10px;color:rgba(212,175,55,0.6);font-family:serif;font-style:italic;margin-top:1px;">${imp.desc}</div>
            <div style="font-size:9px;color:var(--text3);font-family:monospace;margin-top:2px;">Получен: ${new Date(imp.obtained_at).toLocaleDateString('ru-RU')}</div>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
            <div style="font-size:8px;color:var(--text3);font-family:monospace;">ЗАРЯДЫ</div>
            <div class="implant-dur">${dots}</div>
          </div>
        </div>
        ${disassembleBtn}
      </div>`;
    }).join('');
    if (pageContainer) pageContainer.innerHTML = pageHtml;

  } catch(e) {}
}

function updatePoints() {
  document.getElementById('myPoints').textContent = currentPoints + ' ★';
  document.getElementById('myPointsBig').textContent = currentPoints;
  document.getElementById('casinoPoints').textContent = currentPoints + ' ★';
  document.getElementById('shopPoints').textContent = currentPoints + ' ★';
  document.getElementById('myPointsRating').textContent = currentPoints;
}

function updateRatingPoints() {
  document.getElementById('myPointsRating').textContent = currentPoints;
}

// ===== КОНФИГ =====
function getConfig() {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  if (userConfig) {
    document.getElementById('configBox').textContent = userConfig;
    document.getElementById('configBox').style.display = 'block';
    document.getElementById('copyBtn').style.display = 'block';
  } else { tg.showAlert('Конфиг не найден. Активируйте код через /start КОД в боте.'); }
}

function copyConfig() {
  if (userConfig) {
    navigator.clipboard.writeText(userConfig);
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✅ СКОПИРОВАНО!';
    setTimeout(() => { btn.textContent = '📋 СКОПИРОВАТЬ'; }, 2000);
  }
}

function showHelp() {
  tg.showPopup({ title: '📖 Инструкция', message: '1. Нажми "КОНФИГ"\n2. Нажми "СКОПИРОВАТЬ"\n3. Открой Happ → + → вставь ссылку\n4. Подключись!', buttons: [{type:'ok'}] });
}

function contactAdmin() { tg.openTelegramLink('https://t.me/christianpastor'); }

function getLastSeenGlobalAlertId() {
  return Number(localStorage.getItem('last_global_alert_id') || '0');
}

function setLastSeenGlobalAlertId(alertId) {
  localStorage.setItem('last_global_alert_id', String(alertId || 0));
}

async function triggerGlobalArchitectAlert() {
  if (!currentUserId) {
    openArchitectArrivalBanner();
    return;
  }

  try {
    const r = await fetch(`${API_URL}/api/global-alert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        telegram_id: currentUserId,
        alert_type: 'architect',
        title: 'ARCHITECT ONLINE',
        message: 'Critical override detected.',
      }),
    });
    const data = await r.json();

    if (!r.ok) {
      tg.showAlert(data.detail || 'Signal error');
      return;
    }

    if (data.alert_id) {
      setLastSeenGlobalAlertId(data.alert_id);
    }

    openArchitectArrivalBanner();
  } catch (e) {
    tg.showAlert('Connection error');
  }
}

async function checkGlobalAlert() {
  if (!currentUserId) return;

  try {
    const r = await fetch(`${API_URL}/api/global-alert/current`);
    if (!r.ok) return;

    const data = await r.json();
    const alert = data.alert;
    if (!alert || !alert.is_active) return;

    const alertId = Number(alert.id || 0);
    if (!alertId) return;

    if (getLastSeenGlobalAlertId() === alertId) {
      return;
    }

    setLastSeenGlobalAlertId(alertId);

    if (String(alert.alert_type || '').toLowerCase() === 'architect') {
      openArchitectArrivalBanner();
    }
  } catch (e) {}
}

function startGlobalAlertPolling() {
  if (globalAlertPollingHandle) return;
  checkGlobalAlert();
  globalAlertPollingHandle = setInterval(checkGlobalAlert, 4000);
}

function openArchitectArrivalBanner() {
  const overlay = document.getElementById('architectArrivalBanner');
  const audio = document.getElementById('architectArrivalAudio');
  if (!overlay) return;

  overlay.classList.add('show');

  if (audio) {
    try {
      audio.pause();
      audio.currentTime = 0;
      const maybePromise = audio.play();
      if (maybePromise && typeof maybePromise.catch === 'function') {
        maybePromise.catch(() => {});
      }
    } catch (e) {}
  }

  try { tg.HapticFeedback.notificationOccurred('warning'); } catch (e) {}
}

function closeArchitectArrivalBanner() {
  const overlay = document.getElementById('architectArrivalBanner');
  const audio = document.getElementById('architectArrivalAudio');
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

// ===== РАСПИСАНИЕ =====
async function loadSchedule() {
  try {
    const r = await fetch(`${API_URL}/api/schedule`);
    const data = await r.json();
    const container = document.getElementById('scheduleContent');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Расписание пока не добавлено</div>'; return; }
    const byDay = {};
    data.forEach(item => { if (!byDay[item.day]) byDay[item.day] = []; byDay[item.day].push(item); });
    let html = '';
    for (const day in byDay) {
      html += `<div class="schedule-day">🏮 ${day}</div>`;
      byDay[day].forEach(item => {
        html += `<div class="schedule-item">
          <div class="schedule-time">${item.time}</div>
          <div class="schedule-info">
            <div class="schedule-subject">${item.subject}</div>
            <div class="schedule-location">📍 ${item.location}</div>
          </div>
          ${isAdmin ? `<button onclick="deleteSchedule(${item.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-size:16px;padding:4px;">✕</button>` : ''}
        </div>`;
      });
    }
    container.innerHTML = html;
    if (isAdmin) document.getElementById('adminScheduleForm').style.display = 'block';
  } catch(e) { document.getElementById('scheduleContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function addScheduleItem() {
  const getValue = (ids) => ids.map(id => document.getElementById(id)).find(el => el && el.value.trim());
  const dayEl = getValue(['schDay', 'adminSchDay']) || document.getElementById('schDay') || document.getElementById('adminSchDay');
  const timeEl = getValue(['schTime', 'adminSchTime']) || document.getElementById('schTime') || document.getElementById('adminSchTime');
  const subjectEl = getValue(['schSubject', 'adminSchSubject']) || document.getElementById('schSubject') || document.getElementById('adminSchSubject');
  const locationEl = getValue(['schLocation', 'adminSchLocation']) || document.getElementById('schLocation') || document.getElementById('adminSchLocation');
  const day = dayEl ? dayEl.value.trim() : '';
  const time = timeEl ? timeEl.value.trim() : '';
  const subject = subjectEl ? subjectEl.value.trim() : '';
  const location = locationEl ? locationEl.value.trim() : '';
  if (!day || !time || !subject || !location) { tg.showAlert('Заполните все поля'); return; }
  try {
    const r = await fetch(`${API_URL}/api/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day,time,subject,location})
    });
    if (r.ok) {
      tg.showAlert('✅ Добавлено!');
      ['schDay','schTime','schSubject','schLocation','adminSchDay','adminSchTime','adminSchSubject','adminSchLocation']
        .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
      loadSchedule();
    }
  } catch(e) { tg.showAlert('Ошибка'); }
}

async function deleteSchedule(id) {
  try { await fetch(`${API_URL}/api/schedule/${id}`, {method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadSchedule(); } catch(e) {}
}

// ===== РЕЙТИНГ =====
// ===== ТЕМЫ =====

function setTheme(theme) {
  // Убираем все классы тем
  THEMES.forEach(t => {
    if (t) document.body.classList.remove('theme-' + t);
  });
  // Применяем новую
  if (theme) document.body.classList.add('theme-' + theme);

  // Сохраняем
  try {
    localStorage.setItem('zhidao_theme', theme);
    if(window.Telegram?.WebApp?.CloudStorage) tg.CloudStorage.setItem('zhidao_theme', theme, ()=>{});
  } catch(e) {}

  // Обновляем галочки
  THEMES.forEach(t => {
    const key = t || 'default';
    const el = document.getElementById('check-' + key);
    if (el) el.style.display = (t === theme) ? 'block' : 'none';
  });

  // Обновляем логотип под тему
  const logoImg = document.querySelector('.main-logo img');
  const isG = theme === 'genshin-light' || theme === 'genshin-dark';
  document.body.classList.toggle('theme-genshin', isG);
  if (logoImg) {
    logoImg.src = isG
      ? 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo_genshintheme_nobackground.png'
      : 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/logo.png?raw=true';
  }
  // Переименовываем разделы под тему
  const el = (id) => document.getElementById(id);
  if (el('nav-casino-label'))    el('nav-casino-label').textContent = isG ? '祈愿' : '箱子';
  if (el('nav-casino-icon'))     el('nav-casino-icon').className    = isG ? 'ti ti-sparkles' : 'ti ti-package';
  if (el('nav-implants-label'))  el('nav-implants-label').textContent = isG ? '卡片' : '植入物';
  if (el('nav-implants-icon'))   el('nav-implants-icon').className  = isG ? 'ti ti-cards' : 'ti ti-cpu';
  if (el('casino-page-cn'))      el('casino-page-cn').textContent   = isG ? '祈愿' : '箱子';
  if (el('casino-page-title'))   el('casino-page-title').firstChild.textContent = isG ? 'МОЛИТВЫ ' : 'КЕЙСЫ ';
  if (el('implants-page-cn'))    el('implants-page-cn').textContent = isG ? '卡片' : '植入物';
  if (el('implants-page-title')) el('implants-page-title').firstChild.textContent = isG ? 'КАРТОЧКИ ' : 'ИМПЛАНТЫ ';
  if (el('home-neuro-divider'))  el('home-neuro-divider').textContent = isG ? '✦ 卡片 артефакты ✦' : '🏮 网络链接 нейролинк 🏮';
  try { try{tg.HapticFeedback.impactOccurred('light');}catch(e){} } catch(e) {}
}

function loadSavedTheme() {
  try {
    if(window.Telegram?.WebApp?.CloudStorage) {
      tg.CloudStorage.getItem('zhidao_theme', (err, val) => {
        setTheme(val || localStorage.getItem('zhidao_theme') || '');
      });
    } else {
      setTheme(localStorage.getItem('zhidao_theme') || '');
    }
  } catch(e) { setTheme(''); }
}


function switchRatingTab(tab, btn) {
  document.querySelectorAll('#page-rating .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('rating-main-tab').style.display = tab === 'main' ? 'block' : 'none';
  document.getElementById('rating-diary-tab').style.display = tab === 'diary' ? 'block' : 'none';
  if (tab === 'diary') loadDiaryStarsLeaderboardRating();
}

async function loadDiaryStarsLeaderboardRating() {
  const container = document.getElementById('diaryStarsLeaderboardRating');
  container.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const headers = {'Content-Type': 'application/json'};
    if (currentUserId) headers['X-Telegram-Id'] = String(currentUserId);
    if (isAdmin) headers['X-Admin-Id'] = String(currentUserId);
    const r = await fetch(`${API_URL}/api/diary/stars/leaderboard`, {headers});
    const data = await r.json();
    if (!data.length) { container.innerHTML = '<div class="empty-state">Пока нет данных</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    container.innerHTML = data.map((row, i) => {
      const medal = medals[i] || `${i+1}.`;
      const isMe = row.telegram_id === currentUserId;
      return `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
        <div style="font-size:16px;min-width:28px;text-align:center;">${medal}</div>
        <div style="flex:1;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">${row.name}${isMe?' 👈':''}</div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace;">Дней оценено: ${row.days_rated}</div>
        </div>
        <div style="font-size:13px;font-weight:700;color:var(--gold);">${row.total_stars} ⭐</div>
      </div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function loadLeaderboard() {
  const IMPLANT_GLYPHS = {
    'implant_red_dragon':   ['龍', '#cc2200'],
    'implant_netwatch':     ['衛', '#cc2200'],
    'implant_guanxi':       ['義', '#9b59b6'],
    'implant_terracota':    ['兵', '#9b59b6'],
    'implant_panda':        ['熊', '#9b59b6'],
    'implant_shaolin':      ['武', '#9b59b6'],
    'implant_linguasoft':   ['言', '#9b59b6'],
    'implant_caishen':      ['財', '#9b59b6'],
    'implant_qilin':        ['麟', '#9b59b6'],
  };
  const TOP_COLORS = [
    'linear-gradient(90deg,#d4af37,#f5e070)',
    'linear-gradient(90deg,#b0b0b0,#e8e8e8)',
    'linear-gradient(90deg,#b87333,#e8a050)',
    '#e8c84a','#e8c84a','#c8a830','#c8a830','#a88820','#a88820','#887010'
  ];
  try {
    const r = await fetch(`${API_URL}/api/leaderboard`);
    const data = await r.json();
    const container = document.getElementById('leaderboardContent');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Рейтинг пока пуст</div>'; return; }
    const medals = ['🥇','🥈','🥉'];
    let myRank = '—', html = '';

    data.forEach((item, i) => {
      const medal = medals[i] || (i+1)+'.';
      const isMe = currentUserId && item.telegram_id === currentUserId;
      if (isMe) myRank = i+1;
      const topClass = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
      const animDelay = `animation-delay:${i*0.06}s`;

      // Цвет ника — топ-10 градиент
      const nameColor = i < 10 ? TOP_COLORS[i] : '';
      const isGradient = nameColor && nameColor.startsWith('linear');
      let nameStyle = isGradient
        ? `background:${nameColor};-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-weight:700;`
        : nameColor ? `color:${nameColor};font-weight:700;` : '';

      // Свечение топ-3
      if (i === 0) nameStyle += 'filter:drop-shadow(0 0 8px rgba(212,175,55,0.6));';
      else if (i === 1) nameStyle += 'filter:drop-shadow(0 0 6px rgba(200,200,200,0.4));';
      else if (i === 2) nameStyle += 'filter:drop-shadow(0 0 6px rgba(184,115,51,0.4));';

      // Легендарные импланты — красный ник поверх всего
      const isLegendary = item.implant === 'implant_red_dragon' || item.implant === 'implant_netwatch';
      if (isLegendary) {
        nameStyle = 'color:#cc2200;text-shadow:0 0 10px rgba(200,0,0,0.5);font-weight:700;';
      }

      // Иероглиф импланта
      let glyphHtml = '';
      if (item.implant && IMPLANT_GLYPHS[item.implant]) {
        const [glyph, color] = IMPLANT_GLYPHS[item.implant];
        glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
      } else if (item.card) {
        const CARD_GLYPHS = {
          'card_zhongli':    ['岩', '#d4af37'],
          'card_star':       ['紫', '#9b59b6'],
          'card_pyro':       ['焰', '#e74c3c'],
          'card_fox':        ['狐', '#e67e22'],
          'card_fairy':      ['桃', '#e91e8c'],
          'card_literature': ['文', '#3498db'],
          'card_forest':     ['木', '#2ecc71'],
          'card_sea':        ['海', '#1abc9c'],
          'card_moon':       ['月', '#b0c4de'],
        };
        if (CARD_GLYPHS[item.card]) {
          const [glyph, color] = CARD_GLYPHS[item.card];
          glyphHtml = `<span class="lb-implant-glyph" style="color:${color};">${glyph}</span>`;
        }
      }

      // Титул
      const titleHtml = item.has_title ? '<span style="font-size:12px;margin-left:3px;">👑</span>' : '';

      // Прогресс до следующего места
      let progressHtml = '';
      if (i > 0 && data[i-1]) {
        const prev = data[i-1].points;
        const curr = item.points;
        const pct = prev > 0 ? Math.round((curr / prev) * 100) : 100;
        const barColor = isLegendary ? 'rgba(200,34,0,0.5)' : i < 3 ? 'rgba(212,175,55,0.4)' : 'rgba(150,150,150,0.2)';
        progressHtml = `<div class="lb-progress" style="width:${pct}%;background:${barColor};max-width:100%;"></div>`;
      }

      // Разделитель после топ-3
      const divider = i === 3 ? '<div class="lb-divider">— — — ТОП 3 — — —</div>' : '';

      html += `${divider}<div class="lb-item ${topClass} ${isMe?'me':''}" style="${animDelay}">
        <div class="lb-rank">${medal}</div>
        <div class="lb-name-wrap">
          <div class="lb-name" style="${nameStyle}">${item.name}${titleHtml}${glyphHtml}${isMe?' 👈':''}</div>
          ${progressHtml}
        </div>
        <div class="lb-points">${item.points} ★</div>
      </div>`;
    });
    container.innerHTML = html;
    document.getElementById('myRankSub').textContent = myRank !== '—' ? `// Место в рейтинге: #${myRank}` : '// Участвуй чтобы попасть в рейтинг!';
  } catch(e) { document.getElementById('leaderboardContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

// ===== МАГАЗИН =====
function switchShopTab(mode, btn) {
  shopMode = mode;
  document.querySelectorAll('#page-shop .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  ['shopStoreContent','shopInventoryContent','shopFolkContent'].forEach(id => {
    const el = document.getElementById(id); if (el) el.style.display = 'none';
  });
  if (mode === 'store') {
    document.getElementById('shopStoreContent').style.display = 'block';
    loadShop();
  } else if (mode === 'inventory') {
    document.getElementById('shopInventoryContent').style.display = 'block';
    loadInventory();
  } else if (mode === 'folk') {
    document.getElementById('shopFolkContent').style.display = 'block';
  }
}

// Маппинг иконок магазина — Tabler вместо эмодзи
const SHOP_ICONS = {
  'immunity':     '<i class="ti ti-shield-half" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'laundry_vip':  '<i class="ti ti-wash" style="color:#60b4d4;font-size:22px;"></i>',
  'dj':           '<i class="ti ti-music" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'solo_seat':    '<i class="ti ti-brain" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'amnesty':      '<i class="ti ti-heart-handshake" style="color:#60b4d4;font-size:22px;"></i>',
  'kfc':          '<i class="ti ti-meat" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'bubbletea':    '<i class="ti ti-cup" style="color:#60b4d4;font-size:22px;"></i>',
  'snack':        '<i class="ti ti-ice-cream" style="color:var(--gold);font-size:22px;"></i>',
  'no_report':    '<i class="ti ti-file-off" style="color:rgba(200,80,80,0.9);font-size:22px;"></i>',
  'poizon':       '<i class="ti ti-shirt" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'extra_case':   '<i class="ti ti-package-plus" style="color:var(--gold);font-size:22px;"></i>',
  'extra_raid_attempt': '<i class="ti ti-sword" style="color:#cc4444;font-size:22px;"></i>',
  'raid_insurance': '<i class="ti ti-shield-dollar" style="color:var(--gold);font-size:22px;"></i>',
  'raid_beacon': '<i class="ti ti-link" style="color:#60b4d4;font-size:22px;"></i>',
  'raid_overclock': '<i class="ti ti-bolt" style="color:rgba(155,89,182,0.9);font-size:22px;"></i>',
  'double_win':   '<i class="ti ti-arrows-double-sw-ne" style="color:var(--gold);font-size:22px;"></i>',
  'title_player': '<i class="ti ti-crown" style="color:var(--gold);font-size:22px;"></i>',
};

const GS_CARD_CONFIGS = {
  card_zhongli:   {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',emoji:'🪨',stars:'★★★★★',starsColor:'#c0a040',pool:'gold',backCn:'岩',petals:['✦','★','🌟','◆','✧'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_star:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',emoji:'⭐',stars:'★★★★★',starsColor:'#c0a040',pool:'gold',backCn:'星',petals:['✦','★','🌟','◆'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_pyro:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',emoji:'🔥',stars:'★★★★',starsColor:'#c39ef5',pool:'purple',backCn:'焰',petals:['🌸','✦','💜','✿'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fox:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',emoji:'🦊',stars:'★★★★',starsColor:'#c39ef5',pool:'purple',backCn:'狐',petals:['✦','💜','✿','◈'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fairy:     {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',emoji:'🌸',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'桃',petals:['🌸','✦','💧','❀'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_literature:{img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',emoji:'📜',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'文',petals:['📜','✦','❀','✿'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_forest:    {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',emoji:'🌿',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'木',petals:['🌿','✦','🍃','❀'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_sea:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',emoji:'🌊',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'海',petals:['🌊','✦','💧','◈'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_moon:      {img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/moon_card.png?raw=true',emoji:'🌙',stars:'★★★★',starsColor:'#4a9af5',pool:'blue',backCn:'月',petals:['🌙','✦','⭐','✿'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
};
// Призы не-карточки
const GS_PRIZE_CONFIGS = {
  points: {emoji:'✦',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:15,petalColor:'rgba(219,177,101,0.7)',petals:['✦','★'],revealDelay:1200},
  immunity:{emoji:'🛡',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(74,122,204,0.6)',petals:['🛡','✦'],revealDelay:1200},
  walk:    {emoji:'🏮',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(219,177,101,0.6)',petals:['🏮','✦'],revealDelay:1200},
};

let gsAnimating = false, gsCardFlipped = false, curGsCardId = null;

function gsGetThemeBg(c) {
  const isLight = document.body.classList.contains('theme-genshin-light') || document.body.classList.contains('theme-nw-light');
  return `radial-gradient(ellipse at 50% 40%,${c.bgFrom} 0%,${c.bgTo} 60%,${c.bgFrom} 100%)`;
}

function gsRunVortex(c) {
  const v = document.getElementById('gsVortex'); v.innerHTML = '';
  [0.3,0.5,0.7].forEach((a,i) => {
    const ring = document.createElement('div');
    ring.style.cssText = `width:${80+i*50}px;height:${80+i*50}px;border-radius:50%;border:${2-i*0.3}px solid ${c.vortexColor}${a});animation:gsVortexSpin ${0.8+i*0.2}s ease-out ${i*0.1}s forwards;position:absolute;`;
    v.appendChild(ring);
  });
}

function gsRunParticles(c) {
  const p = document.getElementById('gsParticles'); p.innerHTML = '';
  for(let i=0;i<c.partCount;i++){
    const el=document.createElement('div');
    const isText=Math.random()>0.55;
    const px=(Math.random()-0.5)*300,py=(Math.random()-0.5)*300;
    if(isText){
      el.textContent=c.petals[Math.floor(Math.random()*c.petals.length)];
      el.style.cssText=`position:absolute;font-size:${10+Math.random()*10}px;color:${c.petalColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:gsPartFloat ${1.5+Math.random()*1.5}s ease-out ${Math.random()*0.5}s forwards;opacity:0;`;
    } else {
      const sz=Math.random()*5+2;
      el.style.cssText=`position:absolute;width:${sz}px;height:${sz}px;border-radius:50%;background:${c.petalColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:gsPartFloat ${1.5+Math.random()}s ease-out ${Math.random()*0.4}s forwards;opacity:0;`;
    }
    p.appendChild(el);
  }
}

function gsRunRays(c) {
  const r = document.getElementById('gsRays'); r.innerHTML = '';
  if(!c.rayColor){r.style.opacity='0';return;}
  r.style.opacity='1';
  for(let i=0;i<c.rayCount;i++){
    const ray=document.createElement('div');
    ray.style.cssText=`position:absolute;width:3px;height:180px;border-radius:2px;background:linear-gradient(0deg,${c.rayColor},transparent);transform:rotate(${i*(360/c.rayCount)}deg) translateX(-50%);transform-origin:bottom;left:50%;top:calc(50% - 180px);margin-left:-1.5px;animation:gsRayIn 0.4s ease-out ${i*0.015}s both;opacity:0;`;
    r.appendChild(ray);
  }
}

function gsRunCardStars(c) {
  const w = document.getElementById('gsCardStars'); w.innerHTML = '';
  const positions=[[-50,-30,30,'30deg'],[50,-30,-30,'-30deg'],[-60,10,60,'15deg'],[60,10,-60,'-15deg'],[-40,-55,20,'45deg'],[40,-55,-20,'-45deg'],[-55,50,40,'20deg'],[55,50,-40,'-20deg'],[0,-65,0,'0deg'],[0,65,0,'0deg']];
  positions.slice(0,Math.min(c.rayCount/2,10)).forEach(([tx,ty,tr],i)=>{
    const el=document.createElement('div');
    el.style.cssText=`position:absolute;left:50%;top:50%;font-size:${12+Math.random()*8}px;color:${c.petalColor};--tx:${tx}px;--ty:${ty}px;--tr:${tr};animation:gsStarPop 0.8s ease-out ${0.2+i*0.05}s forwards;opacity:0;font-family:serif;`;
    el.textContent=c.petals[Math.floor(Math.random()*c.petals.length)];
    w.appendChild(el);
  });
}

function gsBuildCard(cardId, cardInfo) {
  const c = GS_CARD_CONFIGS[cardId] || GS_PRIZE_CONFIGS.points;
  const back = document.getElementById('gsCardBack');
  back.style.background = `linear-gradient(135deg,${c.backGrad?c.backGrad[0]:'#c0d5f0'},${c.backGrad?c.backGrad[1]:'#dce8f8'})`;
  back.style.border = `2px solid ${c.backBorder||'rgba(74,122,204,0.6)'}`;
  back.innerHTML = `<svg width="150" height="210" viewBox="0 0 150 210" xmlns="http://www.w3.org/2000/svg">
    <rect width="150" height="210" rx="12" fill="none"/>
    <rect x="8" y="8" width="134" height="194" rx="8" fill="none" stroke="${c.backBorder||'rgba(74,122,204,0.6)'}" stroke-width="1.2" stroke-dasharray="6 3" opacity="0.7"/>
    <circle cx="75" cy="105" r="40" fill="none" stroke="${c.backBorder||'rgba(74,122,204,0.6)'}" stroke-width="1" opacity="0.4"/>
    <circle cx="75" cy="105" r="30" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" opacity="0.08"/>
    <text x="75" y="120" font-size="34" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" opacity="0.75">${c.backCn||'知'}</text>
    <text x="75" y="168" font-size="9" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" letter-spacing="3" opacity="0.6">✦ 祈愿 ✦</text>
    <text x="24" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">龙</text>
    <text x="118" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">月</text>
    <text x="24" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">花</text>
    <text x="118" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">星</text>
  </svg>`;
  const front = document.getElementById('gsCardFront');
  front.style.background = `linear-gradient(180deg,${c.frontGrad?c.frontGrad[0]:'#dceef8'},${c.frontGrad?c.frontGrad[1]:'#eef5fc'})`;
  front.style.border = `2px solid ${c.frontBorder||'rgba(74,122,204,0.7)'}`;
  front.innerHTML = `
    <div style="flex:1;width:100%;display:flex;align-items:center;justify-content:center;position:relative;">
      <div style="position:absolute;inset:4px;border-radius:10px;background:${c.frontBg||'rgba(74,122,204,0.08)'};border:1px solid ${(c.frontBorder||'rgba(74,122,204,0.7)').replace(/[\d.]+\)$/,'0.2)')}"></div>
      ${(c.img) ? `<img src="${c.img}" style="width:110px;height:130px;object-fit:contain;position:relative;z-index:2;border-radius:8px;">` : `<div style="font-size:58px;position:relative;z-index:2;filter:drop-shadow(0 4px 10px ${c.petalColor||'rgba(74,122,204,0.5)'})">${c.emoji||'✦'}</div>`}
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:3px;padding-bottom:2px;">
      <div style="font-size:10px;font-weight:700;color:#2a2040;font-family:serif;letter-spacing:1px;text-align:center;">${cardInfo?cardInfo.name:''}</div>
      <div style="font-size:12px;color:${c.starsColor||'#4a9af5'};letter-spacing:3px;">${c.stars||'★★★★'}</div>
      <div style="font-size:7px;color:rgba(42,32,64,0.6);text-align:center;line-height:1.4;padding:0 4px;font-family:serif;">${cardInfo?cardInfo.passive:''}</div>
    </div>`;
}

async function openGenshinCase() {
  if (gsAnimating) return;
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  // Проверяем заморозку
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('⛔ Аккаунт заморожен. Молитвы недоступны.'); return; }
  } catch(e) {}
  const btn = document.getElementById('genshinOpenBtn');
  btn.disabled = true; btn.textContent = '✦ Молитва совершается... ✦';
  gsAnimating = true; gsCardFlipped = false;
  document.getElementById('gsCard3dNew').style.transform = '';
  document.getElementById('gsCard3dNew').classList.remove('flipped');
  document.getElementById('gsTapHint').style.display = 'none';
  document.getElementById('gsResultInfo').style.opacity = '0';
  document.getElementById('gsCardWrap').style.opacity = '0';
  document.getElementById('gsRays').style.opacity = '0';
  document.getElementById('gsParticles').innerHTML = '';
  document.getElementById('gsVortex').innerHTML = '';
  document.getElementById('gsCardStars').innerHTML = '';

  try {
    const r = await fetch(`${API_URL}/api/genshin/open`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telegram_id: currentUserId})
    });
    const data = await r.json();
    if (!r.ok) {
      if (data.detail==='Only for girls') tg.showAlert('Молитвы доступны только девочкам 🌸');
      else if (data.detail==='Not enough points') tg.showAlert('Недостаточно ✦! Нужно минимум 80');
      else if (data.detail==='Daily limit reached') tg.showAlert('Лимит молитв на сегодня исчерпан');
      else tg.showAlert('Ошибка: ' + (data.detail||''));
      gsAnimating = false; btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
      currentPoints = data.new_points || currentPoints;
      updatePoints();
      return;
    }

    currentPoints = data.new_points; updatePoints();
    curGsCardId = data.card_id || null;
    const cfg = GS_CARD_CONFIGS[data.card_id] || GS_PRIZE_CONFIGS[data.type] || GS_PRIZE_CONFIGS.points;

    // Фон
    document.getElementById('gsBgLayer').style.background = gsGetThemeBg(cfg);

    // Строим карточку (перевёрнутая рубашкой)
    gsBuildCard(data.card_id, {name: data.name||'', passive: data.passive||''});

    // ШАГ 1: Вихрь
    gsRunVortex(cfg);
    gsRunParticles(cfg);

    // ШАГ 2: Вспышка + лучи + карточка
    setTimeout(() => {
      const fl = document.getElementById('gsFlash');
      fl.style.background = cfg.flashColor;
      fl.style.animation = 'gsFlashIn 0.5s ease-out forwards';
      setTimeout(() => { fl.style.animation='none'; fl.style.opacity='0'; }, 500);
      gsRunRays(cfg);
      const cw = document.getElementById('gsCardWrap');
      cw.style.animation = 'none'; cw.offsetHeight;
      cw.style.cssText += 'animation:gsCardIn 0.6s cubic-bezier(0.34,1.4,0.64,1) forwards;opacity:1;';
      setTimeout(() => gsRunCardStars(cfg), 350);
      setTimeout(() => {
        document.getElementById('gsTapHint').style.display = 'block';
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        gsAnimating = false;
        btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
      }, 700);
    }, cfg.revealDelay);

    // Подготавливаем инфо
    document.getElementById('gsResStars').textContent = cfg.stars || '★★★★';
    document.getElementById('gsResStars').style.color = cfg.starsColor || '#4a9af5';
    document.getElementById('gsResName').textContent = data.name || '';
    document.getElementById('gsResPassive').textContent = data.passive || (data.amount ? `+${data.amount}★ начислено` : '');

    if (data.rarity === 5) { setTimeout(() => launchConfetti(80), cfg.revealDelay + 400); }

  } catch(e) {
    tg.showAlert('Ошибка соединения');
    gsAnimating=false; btn.disabled=false; btn.textContent='✦ Совершить молитву — 50 ✦ ✦';
  }
}

// Клик по экрану молитвы — переворачивает карточку
document.addEventListener('DOMContentLoaded', () => {
  const screen = document.getElementById('gsPrayScreen');
  if (screen) screen.addEventListener('click', () => {
    if (gsAnimating || gsCardFlipped) return;
    gsCardFlipped = true;
    document.getElementById('gsCard3dNew').style.transform = 'rotateY(180deg)';
    document.getElementById('gsTapHint').style.display = 'none';
    setTimeout(() => {
      const info = document.getElementById('gsResultInfo');
      info.style.opacity = '1';
      info.style.animation = 'fadeUpAnim 0.4s ease-out forwards';
    }, 600);
  });
});

// Переключатель табов импланты/карточки
function switchImplantsTab(tab) {
  document.getElementById('implants-tab').style.display = tab === 'implants' ? 'block' : 'none';
  document.getElementById('cards-tab').style.display = tab === 'cards' ? 'block' : 'none';
  document.getElementById('tab-implants-btn').classList.toggle('active', tab === 'implants');
  document.getElementById('tab-cards-btn').classList.toggle('active', tab === 'cards');
  if (tab === 'cards') loadCards(currentUserId);
}

const GENSHIN_EMOJIS = {
  'card_zhongli':'🪨','card_pyro':'🔥','card_fox':'🦊',
  'card_fairy':'🌸','card_literature':'📜','card_forest':'🌿',
  'card_sea':'🌊','card_star':'⭐','card_moon':'🌙'
};

const GENSHIN_IMGS = {
  'card_zhongli':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',
  'card_pyro':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',
  'card_fox':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',
  'card_fairy':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',
  'card_literature':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',
  'card_forest':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',
  'card_sea':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',
  'card_moon':'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/moon_card.png?raw=true',
  'card_star':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',
};

async function loadCards(telegramId) {
  if (!telegramId) {
    const container = document.getElementById('myCardsContent');
    if (container) container.innerHTML = '<div class="empty-state">Карточек пока нет<br><span style="font-size:10px;font-family:serif;color:var(--text3);">Соверши молитву во вкладке Кейсы!</span></div>';
    return;
  }
  const container = document.getElementById('myCardsContent');
  if (!container) return;
  try {
    const r = await fetch(`${API_URL}/api/cards/${telegramId}`);
    if (!r.ok) { container.innerHTML = '<div class="empty-state">Карточек пока нет</div>'; return; }
    const data = await r.json();
    if (!data.length) {
      container.innerHTML = '<div class="empty-state">Карточек пока нет<br><span style="font-size:10px;font-family:serif;color:var(--text3);">Соверши молитву во вкладке Кейсы!</span></div>';
      return;
    }
    const cardCounts = {};
    data.forEach(c => { cardCounts[c.card_id] = (cardCounts[c.card_id] || 0) + 1; });
    const seen = {};
    container.innerHTML = data.map(card => {
      seen[card.card_id] = (seen[card.card_id] || 0) + 1;
      const isDup = cardCounts[card.card_id] > 1;
      const isSecond = seen[card.card_id] > 1;
      const rarity = card.rarity || 4;
      const rarityColor = rarity === 5 ? '#ffd700' : rarity === 4 ? '#9b59b6' : '#4b8fcf';
      const stars = '★'.repeat(rarity);
      const emoji = GENSHIN_EMOJIS[card.card_id] || '✨';
      const imgSrc = GENSHIN_IMGS[card.card_id];
      const cardPassive = card.passive || '';
      const cardVisual = imgSrc
        ? `<img src="${imgSrc}" style="width:50px;height:60px;object-fit:contain;border-radius:8px;border:1px solid ${rarityColor}44;">`
        : `<div style="font-size:28px;">${emoji}</div>`;
      const dots = Array(3).fill(0).map((_,i) =>
        `<div style="width:8px;height:8px;border-radius:50%;background:${i < card.durability ? rarityColor : 'rgba(255,255,255,0.1)'};"></div>`
      ).join('');
      const disassembleBtn = isSecond
        ? `<button onclick="disassembleCard(${card.id})" style="margin-top:8px;width:100%;padding:6px;background:rgba(219,177,101,0.08);border:1px solid rgba(219,177,101,0.25);color:var(--gold);border-radius:16px;font-size:9px;font-family:serif;cursor:pointer;">✦ [ РАЗОБРАТЬ +50 ✦ ]</button>`
        : '';
      return `<div style="background:var(--bg2);border:1px solid ${isDup ? 'rgba(219,177,101,0.3)' : 'var(--border)'};border-radius:12px;padding:12px;margin-bottom:8px;position:relative;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:50px;height:60px;background:var(--bg3);border:1px solid ${rarityColor}33;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">${cardVisual}</div>
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <div style="font-size:12px;font-weight:700;color:var(--text);font-family:serif;">${card.name}</div>
              ${isDup ? `<span style="font-size:7px;background:rgba(219,177,101,0.15);border:1px solid rgba(219,177,101,0.3);color:var(--gold);padding:1px 6px;border-radius:10px;font-family:monospace;">ДУБЛЬ</span>` : ''}
            </div>
            <div style="font-size:10px;color:${rarityColor};margin-top:2px;">${stars}</div>
            <div style="font-size:9px;color:var(--text2);font-family:serif;margin-top:3px;">${cardPassive}</div>
          </div>
          <div style="display:flex;gap:3px;">${dots}</div>
        </div>
        ${disassembleBtn}
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function disassembleCard(id) {
  tg.showPopup({
    title: '✦ Разобрать карточку?',
    message: 'Ты получишь +50 ✦ за дубль. Карточка будет уничтожена.',
    buttons: [{id:'confirm', type:'default', text:'✦ Разобрать +50 ✦'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/cards/disassemble/${id}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✦ Разобрано! +50 ✦\nБаланс: ${data.new_points} ✦`);
        loadCards(currentUserId);
      } else tg.showAlert('Ошибка разборки');
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadShop() {
  try {
    const settingsR = await fetch(`${API_URL}/api/settings`);
    if (!settingsR.ok) throw new Error('settings');
    const settings = await settingsR.json();
    if (settings.blackwall && !isAdmin) {
      document.getElementById('shopStoreContent').innerHTML =
        '<div class="blackwall-screen"><div class="blackwall-title">BlackWall 已激活</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">系统访问已受限<br>— NetWatch 网络保安 —</div></div>';
      return;
    }
    const r = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId||0}`);
    if (!r.ok) throw new Error('shop');
    const data = await r.json();
    document.getElementById('shopPoints').textContent = currentPoints + ' ★';
    document.getElementById('shopFrozenBanner').style.display = data.frozen ? 'block' : 'none';
    const catInfo = {
      'privilege': { name:'特权 ПРИВИЛЕГИИ', cn:'🏮' },
      'points':    { name:'积分 БАЛЛЫ', cn:'⭐' },
      'social':    { name:'社交 СОЦИАЛЬНОЕ', cn:'🤝' },
      'food':      { name:'食物 ЕДА', cn:'🍜' },
      'vip':       { name:'VIP 贵宾', cn:'👑' },
    };
    const categories = {};
    Object.keys(catInfo).forEach(k => { categories[k] = { ...catInfo[k], items:[] }; });
    data.items.forEach(item => { if (categories[item.category]) categories[item.category].items.push(item); });
    let html = '';
    for (const cat of Object.values(categories)) {
      if (!cat.items.length) continue;
      html += `<div class="shop-cat"><span class="cn">${cat.cn}</span> ${cat.name}</div>`;
      cat.items.forEach(item => {
        const canBuy = item.available && currentPoints >= item.price;
        const limitText = item.daily_limit > 0 ? `Осталось: ${item.daily_limit - item.sold_today} из ${item.daily_limit}` : 'Без ограничений';
        html += `<div class="shop-item ${!item.available?'unavailable':''}">
          <div class="shop-item-icon">${SHOP_ICONS[item.code] || item.icon}</div>
          <div style="flex:1;">
            <div class="shop-item-name">${item.name}</div>
            <div class="shop-item-cn">${item.description}</div>
            <div class="shop-item-limit">${limitText}</div>
          </div>
          <button class="shop-item-buy" onclick="buyItem('${item.code}','${item.name}',${item.price})" ${!canBuy?'disabled':''}>${item.price} ★</button>
        </div>`;
      });
    }
    document.getElementById('shopStoreContent').innerHTML = html || '<div class="empty-state">Магазин пуст</div>';
  } catch(e) { document.getElementById('shopStoreContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function loadShop() {
  try {
    const settingsR = await fetch(`${API_URL}/api/settings`);
    if (!settingsR.ok) throw new Error('settings');
    const settings = await settingsR.json();
    if (settings.blackwall && !isAdmin) {
      setShopBlackwallState(true);
      return;
    }

    setShopBlackwallState(false);

    const r = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId||0}`);
    if (!r.ok) throw new Error('shop');
    const data = await r.json();
    document.getElementById('shopPoints').textContent = currentPoints + ' ★';
    document.getElementById('shopFrozenBanner').style.display = data.frozen ? 'block' : 'none';

    const catInfo = {
      'privilege': { name:'特权 ПРИВИЛЕГИИ', cn:'🎮' },
      'points':    { name:'积分 БАЛЛЫ', cn:'⭐' },
      'social':    { name:'社交 СОЦИАЛЬНОЕ', cn:'🤝' },
      'food':      { name:'食物 ЕДА', cn:'🍜' },
      'vip':       { name:'VIP 特设', cn:'👑' },
    };

    const categories = {};
    Object.keys(catInfo).forEach(k => { categories[k] = { ...catInfo[k], items:[] }; });
    data.items.forEach(item => { if (categories[item.category]) categories[item.category].items.push(item); });

    let html = '';
    for (const cat of Object.values(categories)) {
      if (!cat.items.length) continue;
      html += `<div class="shop-cat"><span class="cn">${cat.cn}</span> ${cat.name}</div>`;
      cat.items.forEach(item => {
        const canBuy = item.available && currentPoints >= item.price;
        const limitText = item.daily_limit > 0 ? `Осталось: ${item.daily_limit - item.sold_today} из ${item.daily_limit}` : 'Без ограничений';
        html += `<div class="shop-item ${!item.available?'unavailable':''}">
          <div class="shop-item-icon">${SHOP_ICONS[item.code] || item.icon}</div>
          <div style="flex:1;">
            <div class="shop-item-name">${item.name}</div>
            <div class="shop-item-cn">${item.description}</div>
            <div class="shop-item-limit">${limitText}</div>
          </div>
          <button class="shop-item-buy" onclick="buyItem('${item.code}','${item.name}',${item.price})" ${!canBuy?'disabled':''}>${item.price} ★</button>
        </div>`;
      });
    }

    document.getElementById('shopStoreContent').innerHTML = html || '<div class="empty-state">Магазин пуст</div>';
  } catch(e) {
    document.getElementById('shopStoreContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function buyItem(code, name, price) {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  tg.showPopup({
    title: `Купить ${name}?`,
    message: `Стоимость: ${price} ★\nТвой баланс: ${currentPoints} ★`,
    buttons: [{id:'confirm',type:'default',text:'✅ Купить'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/buy`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({telegram_id:currentUserId, item_code:code})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✅ Куплено: ${data.item}!\nОстаток: ${data.new_points} ★`);
        loadShop();
      } else {
        const err = await r.json();
        if (err.detail === 'Daily limit reached') tg.showAlert('Этот товар уже разобрали!');
        else if (err.detail === 'Not enough points') tg.showAlert('Недостаточно баллов!');
        else if (err.detail === 'Account frozen') tg.showAlert('⛔ Аккаунт под надзором NetWatch');
        else tg.showAlert('Ошибка покупки');
      }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadInventory() {
  try {
    const r = await fetch(`${API_URL}/api/shop/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('shopInventoryContent');
    const digital = ['extra_case','extra_raid_attempt','double_win','title_player','immunity','raid_insurance','raid_beacon','raid_overclock'];
    const physical = data.filter(item => !digital.includes(item.code));
    if (!physical.length) { container.innerHTML = '<div class="empty-state">Инвентарь пуст<br>Купи что-нибудь в магазине!</div>'; return; }
    container.innerHTML = physical.map(item =>
      `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div><div class="inventory-name">${item.name}</div><div class="inventory-date">${new Date(item.purchased_at).toLocaleDateString('ru-RU')} · ID: ${item.id}</div></div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useItem(${item.id},'${item.name}')">✅ Использовать</button>
          <button class="inv-btn inv-btn-gift" onclick="giftItem(${item.id},'${item.name}')">🎁 Подарить</button>
          <button class="inv-btn inv-btn-sell" onclick="sellItem(${item.id},'${item.name}',${item.price})">💰 Продать</button>
        </div>
      </div>`
    ).join('');
  } catch(e) { document.getElementById('shopInventoryContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function useItem(id, name) {
  tg.showPopup({
    title: `Использовать ${name}?`,
    message: 'Покажи этот экран вожатому. После подтверждения товар спишется.',
    buttons: [{id:'confirm', type:'default', text:'✅ Использовать'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/use/${id}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✅ ${name} использован!\nПокажи это сообщение вожатому.`);
        loadInventory();
      } else {
        tg.showAlert('Ошибка использования');
      }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}
function giftItem(id, name) { tg.showPopup({title:`Подарить ${name}?`,message:'Введи имя получателя в чате бота командой /подарить ИМЯ\n\nНалог на дарение: 20 баллов',buttons:[{type:'ok'}]}); }

async function sellItem(id, name, price) {
  const refund = Math.floor(price / 2);
  tg.showPopup({
    title:`Продать ${name}?`,
    message:`Ты получишь ${refund} ★ (50% от стоимости ${price} ★)`,
    buttons:[{id:'confirm',type:'destructive',text:`💰 Продать за ${refund} ★`},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/sell`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purchase_id:id,telegram_id:currentUserId})});
      if (r.ok) { const data=await r.json(); currentPoints=data.new_points; updatePoints(); tg.showAlert(`✅ Продано! +${data.refund} ★`); loadInventory(); }
    } catch(e) { tg.showAlert('Ошибка'); }
  });
}

async function resetShop() {
  try {
    const r = await fetch(`${API_URL}/api/admin/reset_shop`,{method:'POST',headers:{'x-admin-id':currentUserId}});
    if (r.ok) tg.showAlert('✅ Магазин сброшен!');
  } catch(e) { tg.showAlert('Ошибка'); }
}

// ===== КАЗИНО =====
function switchCasinoTab(mode, btn) {
  loadPoints(currentUserId);
  document.querySelectorAll('#page-casino .subtab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const ids = ['casinoPlayContent','casinoInventoryContent','casinoHistoryContent','casinoRulesContent','casinoGenshinContent','genshinRulesContent'];
  ids.forEach(id => { const el=document.getElementById(id); if(el) el.style.display='none'; });
  const isGenshin = currentThemePath === 'genshin';
  if (mode==='play') {
    if (isGenshin) { document.getElementById('casinoGenshinContent').style.display='flex'; }
    else { document.getElementById('casinoPlayContent').style.display='flex'; setTimeout(initRoulette,50); }
  }
  else if (mode==='inventory') { document.getElementById('casinoInventoryContent').style.display='flex'; loadCasinoInventory(); }
  else if (mode==='history') { document.getElementById('casinoHistoryContent').style.display='flex'; loadCasinoHistory(); }
  else if (mode==='rules') {
    if (isGenshin) { const el = document.getElementById('genshinRulesContent'); if(el) el.style.display='flex'; }
    else { document.getElementById('casinoRulesContent').style.display='flex'; }
  }
  else if (mode==='genshin') { document.getElementById('casinoGenshinContent').style.display='flex'; }
}

function initRoulette(caseType = 'gold') {
  const strip = document.getElementById('rouletteStrip');
  if (!strip) return;
  strip.innerHTML = '';
  const imgUrl = CASE_IMAGES[caseType] || CASE_IMAGES.gold;
  const borderColor = caseType==='black' ? 'rgba(180,20,20,0.4)' : caseType==='purple' ? 'rgba(155,89,182,0.4)' : 'rgba(212,175,55,0.2)';
  for (let i = 0; i < 50; i++) {
    const el = document.createElement('div');
    el.className = 'roulette-item';
    el.style.borderColor = borderColor;
    el.innerHTML = `<img src="${imgUrl}" style="width:110px;height:110px;object-fit:contain;">`;
    strip.appendChild(el);
  }
  strip.style.transform = 'translateX(135px)';
  isSpinning = false;
  document.getElementById('openCaseBtn').disabled = false;
  
  document.getElementById('prizeResult').classList.remove('show');
  document.getElementById('prizeResult').style.borderColor = '';
  const track = document.querySelector('.roulette-track');
  if (track) {
    if (caseType==='black') track.style.borderColor='rgba(180,20,20,0.6)';
    else if (caseType==='purple') track.style.borderColor='rgba(155,89,182,0.6)';
    else track.style.borderColor='rgba(180,20,20,0.35)';
  }
}

async function openCase() {
  if (isSpinning) return;
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  if (currentPoints < 80) { tg.showAlert('Недостаточно баллов! Нужно минимум 80 ★'); return; }
  // Проверяем заморозку
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('⛔ Аккаунт заморожен. Кейсы недоступны.'); return; }
  } catch(e) {}
  isSpinning = true;
  document.getElementById('openCaseBtn').disabled = true;
  document.getElementById('prizeResult').classList.remove('show');
  try {
    const r = await fetch(`${API_URL}/api/casino/open`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({telegram_id:currentUserId})
    });
    if (!r.ok) {
      const err = await r.json();
      if (err.detail==='Daily limit reached') tg.showAlert('Лимит 3 кейса в день! Купи доп кейс в магазине 😄');
      else if (err.detail==='Not enough points') tg.showAlert('Недостаточно баллов!');
      else tg.showAlert('Ошибка!');
      isSpinning = false;
      document.getElementById('openCaseBtn').disabled = false;
      return;
    }
    const data = await r.json();
    const caseType = data.prize.case_type || 'gold';
    initRoulette(caseType);
    isSpinning = true;
    document.getElementById('openCaseBtn').disabled = true;
    const prize = PRIZE_MAP[data.prize.code] || { code:data.prize.code, icon:data.prize.icon||'🎁', name:data.prize.name, desc:'Редкий приз!', points:data.prize.points||0 };
    await spinRoulette(prize, caseType);
    showPrizeResult(prize, caseType);
    currentPoints = data.new_points;
    updatePoints();
    // Обновляем кнопку после открытия
    const casBtn = document.getElementById('openCaseBtn');
    if (data.remaining_today !== undefined && data.remaining_today <= 0) {
      casBtn.disabled = true;
      casBtn.style.background = 'rgba(255,255,255,0.05)';
      casBtn.style.borderColor = 'rgba(255,255,255,0.08)';
      casBtn.style.color = 'rgba(255,255,255,0.2)';
      casBtn.textContent = '[ Попытки исчерпаны // Приходите завтра ]';
    } else {
      casBtn.disabled = false;
      casBtn.style.background = '';
      casBtn.style.borderColor = '';
      casBtn.style.color = '';
      casBtn.textContent = '🏮 [ 开箱 // ОТКРЫТЬ КЕЙС — 50 ★ ] 🏮';
    }
    if (prize.code==='jackpot'||prize.code==='implant_red_dragon') { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(100); }
    else if (prize.code.startsWith('implant_')) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(50); }
    else if (prize.points > 50) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(30); }
    else if (prize.code==='empty') try{tg.HapticFeedback.notificationOccurred('error');}catch(e){}
    else try{tg.HapticFeedback.impactOccurred('medium');}catch(e){}
    
    if (prize.code.startsWith('implant_')) loadImplants(currentUserId);
  } catch(e) {
    tg.showAlert('Ошибка соединения');
    isSpinning = false;
    document.getElementById('openCaseBtn').disabled = false;
  }
}

async function spinRoulette(targetPrize, caseType = 'gold') {
  return new Promise(resolve => {
    const strip = document.getElementById('rouletteStrip');
    const items = strip.querySelectorAll('.roulette-item');
    const itemWidth = 130;
    const centerOffset = 135;
    const targetIdx = 38 + Math.floor(Math.random() * 4);
    const finalX = centerOffset - targetIdx * itemWidth;
    const startX = centerOffset;
    const duration = 4500;
    let startTime = null;
    function easeOut(t) { return 1 - Math.pow(1-t, 4); }
    function animate(timestamp) {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOut(progress);
      const currentX = startX + (finalX - startX) * eased;
      strip.style.transition = 'none';
      strip.style.transform = `translateX(${currentX}px)`;
      const speed = 1 - eased;
      if (speed > 0.1 && Math.random() < speed * 0.3) { try { try{tg.HapticFeedback.selectionChanged();}catch(e){} } catch(e) {} }
      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        const winner = items[targetIdx];
        winner.classList.add('winner', 'opening');
        setTimeout(() => {
          winner.classList.remove('opening');
          winner.classList.add('opened');
          const prizeContent = targetPrize.img
            ? `<img src="${targetPrize.img}" class="roulette-prize-reveal" style="width:80px;height:80px;object-fit:contain;border-radius:10px;"><div class="roulette-item-name">${targetPrize.name}</div>`
            : `<div class="roulette-item-icon roulette-prize-reveal">${targetPrize.icon}</div><div class="roulette-item-name">${targetPrize.name}</div>`;
          winner.innerHTML = prizeContent;
          if (targetPrize.code==='jackpot') winner.style.animation='shimmer 0.5s infinite';
          resolve();
        }, 600);
      }
    }
    requestAnimationFrame(animate);
  });
}

function showPrizeResult(prize, caseType = 'gold') {
  const isLegendary = caseType === 'black';
  const isPurple = caseType === 'purple';
  const isDark = !document.body.classList.contains('theme-nw-light') &&
                 !document.body.classList.contains('theme-genshin-light') &&
                 !document.body.classList.contains('theme-genshin-dark');

  // Создаём оверлей
  let ov = document.getElementById('cyberResultOverlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'cyberResultOverlay';
    document.getElementById('page-casino').appendChild(ov);
  }

  const bgColor = isLegendary
    ? 'radial-gradient(ellipse at 50% 35%,#2a1800 0%,#150c00 60%,#050300 100%)'
    : isPurple
    ? 'radial-gradient(ellipse at 50% 35%,#1e0a30 0%,#0d0518 60%,#050310 100%)'
    : 'radial-gradient(ellipse at 50% 35%,#0d0d20 0%,#050510 100%)';

  const glowColor = isLegendary ? 'rgba(255,200,0,0.8)' : isPurple ? 'rgba(155,89,182,0.7)' : 'rgba(212,175,55,0.4)';
  const particleColor = isLegendary ? '#ffd700' : isPurple ? '#9b59b6' : '#d4af37';
  const rayColor = isLegendary ? 'rgba(255,215,0,0.8)' : isPurple ? 'rgba(155,89,182,0.7)' : null;
  const tagBg = isLegendary ? 'rgba(212,175,55,0.2)' : isPurple ? 'rgba(155,89,182,0.15)' : 'rgba(100,150,200,0.15)';
  const tagBorder = isLegendary ? 'rgba(212,175,55,0.6)' : isPurple ? 'rgba(155,89,182,0.5)' : 'rgba(100,150,200,0.3)';
  const tagColor = isLegendary ? '#d4af37' : isPurple ? '#9b59b6' : '#6aa0d4';
  const tagText = isLegendary ? '★ ЛЕГЕНДАРНЫЙ ★' : isPurple ? 'РЕДКИЙ // ФИОЛЕТОВЫЙ' : 'ОБЫЧНЫЙ';

  let imgHtml = prize.img
    ? `<img src="${prize.img}" style="width:110px;height:110px;object-fit:contain;filter:drop-shadow(0 0 20px ${glowColor});animation:cyberPulse 2s ease-in-out infinite;">`
    : `<div style="font-size:72px;filter:drop-shadow(0 0 16px ${glowColor});">${prize.icon}</div>`;

  let contentHtml = '';
  if (prize.points > 0) {
    contentHtml = `<div style="font-size:36px;font-weight:900;font-family:monospace;color:${particleColor};text-shadow:0 0 20px ${particleColor};animation:fadeUpAnim 0.4s ease-out 0.5s both;">+${prize.points}★</div>`;
  } else {
    contentHtml = `<div style="font-size:14px;font-weight:700;color:#fff;font-family:monospace;letter-spacing:1px;text-align:center;animation:fadeUpAnim 0.3s ease-out 0.7s both;">${prize.name}</div>`;
  }

  // Лучи
  let raysHtml = '';
  if (rayColor) {
    const count = isLegendary ? 24 : 16;
    for (let i = 0; i < count; i++) {
      raysHtml += `<div style="position:absolute;width:3px;height:${isLegendary?170:150}px;border-radius:2px;background:linear-gradient(0deg,${rayColor},transparent);transform:rotate(${i*(360/count)}deg) translateX(-50%);transform-origin:bottom;left:50%;top:calc(50% - ${isLegendary?170:150}px);margin-left:-1.5px;animation:cyberRayIn 0.4s ease-out ${i*0.015}s both;opacity:0;"></div>`;
    }
  }

  // Частицы
  let partsHtml = '';
  const count = isLegendary ? 40 : isPurple ? 25 : 15;
  const symbols = isLegendary ? ['龙','★','福','✦'] : isPurple ? ['✦','★','◈'] : ['★','✦'];
  for (let i = 0; i < count; i++) {
    const px = (Math.random()-0.5)*300, py = (Math.random()-0.5)*300;
    const isText = Math.random() > 0.6;
    if (isText) {
      const sym = symbols[Math.floor(Math.random()*symbols.length)];
      partsHtml += `<div style="position:absolute;font-size:${12+Math.random()*10}px;color:${particleColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:cyberPartFloat ${1.5+Math.random()*1.5}s ease-out ${Math.random()*0.5}s forwards;opacity:0;">${sym}</div>`;
    } else {
      const sz = Math.random()*5+2;
      partsHtml += `<div style="position:absolute;width:${sz}px;height:${sz}px;border-radius:50%;background:${particleColor};left:${20+Math.random()*60}%;top:${20+Math.random()*60}%;--px:${px}px;--py:${py}px;animation:cyberPartFloat ${1.5+Math.random()}s ease-out ${Math.random()*0.4}s forwards;opacity:0;"></div>`;
    }
  }

  ov.style.cssText = `position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;background:${bgColor};animation:cyberOverlayIn 0.3s ease-out forwards;`;
  ov.onclick = () => {
    ov.style.animation = 'cyberOverlayOut 0.3s ease-out forwards';
    setTimeout(() => { ov.style.display='none'; resetCasino(); }, 300);
  };
  ov.innerHTML = `
    <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;pointer-events:none;">${raysHtml}</div>
    <div style="position:absolute;inset:0;overflow:hidden;pointer-events:none;">${partsHtml}</div>
    <div style="position:relative;z-index:5;display:flex;flex-direction:column;align-items:center;gap:10px;">
      <div style="animation:cyberItemIn 0.6s cubic-bezier(0.34,1.56,0.64,1) forwards;">${imgHtml}</div>
      <div style="font-size:8px;font-family:monospace;letter-spacing:2px;padding:3px 14px;background:${tagBg};border:1px solid ${tagBorder};color:${tagColor};border-radius:2px;animation:fadeUpAnim 0.3s ease-out 0.5s both;opacity:0;">${tagText}</div>
      ${contentHtml}
      <div style="font-size:9px;color:rgba(255,255,255,0.4);font-family:monospace;text-align:center;max-width:200px;line-height:1.6;animation:fadeUpAnim 0.3s ease-out 0.9s both;opacity:0;">${prize.desc||''}</div>
    </div>
    <div style="position:absolute;bottom:24px;font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;letter-spacing:2px;animation:cyberBlink 2s ease-in-out 1.2s infinite;">нажми чтобы продолжить ▼</div>`;
}

function resetCasino() {
  isSpinning = false;
  document.getElementById('prizeResult').classList.remove('show');
  
  document.getElementById('openCaseBtn').disabled = false;
  initRoulette();
}

function launchConfetti(count) {
  const container = document.getElementById('confettiContainer');
  const colors = ['#f5d05a','#d4af37','#fff','#cc2200','#9b59b6','#ff4444'];
  for (let i = 0; i < count; i++) {
    const piece = document.createElement('div');
    piece.className = 'confetti-piece';
    piece.style.left = Math.random() * 100 + '%';
    piece.style.background = colors[Math.floor(Math.random() * colors.length)];
    piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '0';
    piece.style.width = (Math.random() * 8 + 6) + 'px';
    piece.style.height = (Math.random() * 8 + 6) + 'px';
    piece.style.animationDuration = (Math.random() * 2 + 2) + 's';
    piece.style.animationDelay = (Math.random() * 1) + 's';
    container.appendChild(piece);
    setTimeout(() => piece.remove(), 4000);
  }
}

async function disassembleImplant(id) {
  tg.showPopup({
    title: '⚙️ Разобрать имплант?',
    message: 'Ты получишь +100 ★ за разборку дубля. Имплант будет уничтожен.',
    buttons: [{id:'confirm', type:'default', text:'⚙️ Разобрать +100 ★'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/casino/implants/disassemble/${id}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        const data = await r.json();
        currentPoints = data.new_points;
        updatePoints();
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`✅ Разобрано! +100 ★\nБаланс: ${data.new_points} ★`);
        loadImplants(currentUserId);
      } else {
        const err = await r.json();
        if (err.detail === 'Not a duplicate') tg.showAlert('Это не дубль — нельзя разобрать!');
        else tg.showAlert('Ошибка разборки');
      }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadCasinoInventory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoInventoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Призов пока нет<br>Открывай кейсы!</div>'; return; }
    container.innerHTML = data.map(item => {
      const expires = item.expires_at ? `<div style="color:#cc4444;font-size:10px;margin-top:3px;">⏰ До ${item.expires_at.slice(11,16)}</div>` : '';
      return `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div><div class="inventory-name">${item.name}</div><div class="inventory-date">${item.desc}</div>${expires}</div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useCasinoPrize(${item.id},'${item.name}')">✅ Использовать</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoInventoryList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function useCasinoPrize(id, name) {
  tg.showPopup({
    title:`Использовать ${name}?`, message:'Покажи этот экран вожатому для подтверждения.',
    buttons:[{id:'confirm',type:'default',text:'✅ Показать вожатому'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/casino/use/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
      if (r.ok) { tg.showAlert('✅ Приз использован!'); loadCasinoInventory(); }
      else { const err=await r.json(); tg.showAlert(err.detail==='Prize expired'?'⏰ Приз истёк!':'Ошибка'); }
    } catch(e) { tg.showAlert('Ошибка соединения'); }
  });
}

async function loadCasinoHistory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/history/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoHistoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">История пуста<br>Открой первый кейс!</div>'; return; }
    container.innerHTML = data.map(item => {
      const date = new Date(item.created_at).toLocaleDateString('ru-RU');
      const time = item.created_at.slice(11,16);
      return `<div class="schedule-item">
        <div style="font-size:24px;min-width:35px;text-align:center;">${item.icon}</div>
        <div class="schedule-info"><div class="schedule-subject">${item.name}</div><div class="schedule-location">${date} в ${time}</div></div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoHistoryList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

// ===== ПОГОДА =====
async function loadWeather() {
  try {
    const r = await fetch(`https://api.openweathermap.org/data/2.5/weather?id=1816670&appid=${WEATHER_KEY}&units=metric&lang=ru`);
    const data = await r.json();
    document.getElementById('weatherTemp').innerHTML = `${Math.round(data.main.temp)}<span>°C</span>`;
    document.getElementById('weatherDesc').textContent = data.weather[0].description.charAt(0).toUpperCase() + data.weather[0].description.slice(1);
    document.getElementById('weatherHumidity').textContent = data.main.humidity;
    document.getElementById('weatherWind').textContent = data.wind.speed;
    document.getElementById('weatherFeels').textContent = Math.round(data.main.feels_like);
    document.getElementById('weatherIcon').textContent = getWeatherIcon(data.weather[0].id);
  } catch(e) { document.getElementById('weatherDesc').textContent = 'Недоступно'; }
}

async function loadYuanRate() {
  try {
    const r = await fetch('https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@2024-03-28/v1/currencies/cny.json');
    const data = await r.json();
    const rub = data.cny.rub;
    if (rub) {
      document.getElementById('yuanRate').innerHTML = `${rub.toFixed(2)}<span> ₽</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    }
  } catch(e) {
    try {
      const r2 = await fetch('https://open.er-api.com/v6/latest/CNY');
      const data2 = await r2.json();
      document.getElementById('yuanRate').innerHTML = `${data2.rates.RUB.toFixed(2)}<span> ₽</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    } catch(e2) { document.getElementById('yuanRate').innerHTML = `—<span> ₽</span>`; }
  }
}

function getWeatherIcon(id) {
  if (id >= 200 && id < 300) return '⛈'; if (id >= 300 && id < 400) return '🌦';
  if (id >= 500 && id < 600) return '🌧'; if (id >= 600 && id < 700) return '❄️';
  if (id >= 700 && id < 800) return '🌫'; if (id === 800) return '☀️';
  if (id === 801) return '🌤'; if (id === 802) return '⛅'; return '☁️';
}

// ===== СТИРКА =====
function initLaundry() {
  // Загрузка происходит при открытии раздела, не при старте
}

function switchLaundryTab(tab) {
  const lt = document.getElementById('laundry-tab');
  const wt = document.getElementById('water-tab');
  if (lt) lt.style.display = tab==='laundry' ? 'block' : 'none';
  if (wt) wt.style.display = tab==='water' ? 'block' : 'none';
  const lb = document.getElementById('ltab-laundry');
  const wb = document.getElementById('ltab-water');
  if (lb) lb.classList.toggle('active', tab==='laundry');
  if (wb) wb.classList.toggle('active', tab==='water');
  if (tab==='laundry') loadLaundrySchedule();
  else loadWaterSchedule();
}

async function bookWaterSlot(slotId) {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/water/schedule/${slotId}/book`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    if (r.ok) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} tg.showAlert('✅ Записаны на набор воды!'); loadWaterSchedule(); }
    else { const e=await r.json(); tg.showAlert(e.detail==='Slot full'?'Мест нет':'Вы уже записаны'); }
  } catch(e) { tg.showAlert('Ошибка'); }
}

async function cancelWaterSlot(slotId) {
  tg.showPopup({title:'Отменить запись?',message:'Слот снова станет свободным.',buttons:[{id:'ok',type:'default',text:'Отменить запись'},{type:'cancel'}]},(b)=>{
    if(b!=='ok')return;
    fetch(`${API_URL}/api/water/schedule/${slotId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})})
      .then(()=>loadWaterSchedule()).catch(()=>{});
  });
}

async function loadLaundrySchedule() {
  const container = document.getElementById('laundryScheduleContent');
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) {
      container.innerHTML = `<div class="empty-state" style="padding:16px;">Расписание стирки ещё не составлено<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Вожатые скоро добавят слоты</span></div>`;
      return;
    }
    container.innerHTML = data.map(slot => {
      const capacity = slot.capacity || 1;
      const booked = slot.booked || 0;
      const bookings = slot.bookings || [];
      const isMe = bookings.some(b => b.telegram_id === currentUserId);
      const isFull = booked >= capacity;
      let icon, statusText, clickable;
      if (isMe) {
        icon = `<i class="ti ti-circle-check" style="color:#2ecc71;font-size:18px;"></i>`;
        statusText = `<span style="color:#2ecc71;">Ваша запись</span>`;
        clickable = `onclick="cancelWaterSlot(${slot.id})"`;
      } else if (!isFull) {
        icon = `<i class="ti ti-droplet" style="color:#60b4d4;font-size:18px;"></i>`;
        statusText = `<span style="color:#60b4d4;">Свободно</span>`;
        clickable = `onclick="bookWaterSlot(${slot.id})"`;
      } else {
        icon = `<i class="ti ti-circle-x" style="color:var(--text3);font-size:18px;"></i>`;
        statusText = `<span style="color:var(--text3);">Занято</span>`;
        clickable = '';
      }
      return `<div ${clickable} style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);${clickable?'cursor:pointer;':''}">
        ${icon}
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.day} · ${slot.time}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.note||'Набор воды'}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:10px;">${statusText}</div>
          <div style="font-size:9px;color:var(--text3);font-family:monospace;margin-top:2px;">${booked}/${capacity} мест</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function loadWaterSchedule() {
  const container = document.getElementById('waterScheduleContent');
  try {
    const r = await fetch(`${API_URL}/api/water/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) {
      container.innerHTML = `<div class="empty-state" style="padding:16px;">Расписание воды ещё не составлено<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Вожатые скоро добавят слоты</span></div>`;
      return;
    }
    container.innerHTML = data.map(slot => {
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);">
        <i class="ti ti-droplet" style="color:#60b4d4;font-size:18px;"></i>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.day} · ${slot.time}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.note||'Набор воды'}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function bookLaundrySlot(slotId) {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule/${slotId}/book`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    if (r.ok) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} tg.showAlert('✅ Записаны на стирку!'); loadLaundrySchedule(); }
    else { const e=await r.json(); tg.showAlert(e.detail==='Already booked'?'У вас уже есть запись':'Слот занят'); }
  } catch(e) { tg.showAlert('Ошибка'); }
}

async function cancelLaundrySlot(slotId) {
  tg.showPopup({title:'Отменить запись?',message:'Слот снова станет свободным.',buttons:[{id:'ok',type:'default',text:'Отменить запись'},{type:'cancel'}]},(b)=>{
    if(b!=='ok')return;
    fetch(`${API_URL}/api/laundry/schedule/${slotId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})})
      .then(()=>loadLaundrySchedule()).catch(()=>{});
  });
}

// Старые функции — оставляем для совместимости
async function loadLaundry() { loadLaundrySchedule(); }
function renderLaundrySlots() {}
async function bookLaundry(time) {}

async function cancelLaundry(id) {
  try {
    const r = await fetch(`${API_URL}/api/laundry/${id}`,{method:'DELETE',headers:{'x-telegram-id':currentUserId}});
    if (r.ok) { tg.showAlert('Запись отменена'); loadLaundry(); }
  } catch(e) { tg.showAlert('Ошибка'); }
}

// ===== ОБЪЯВЛЕНИЯ =====
async function loadAnnouncements() {
  const containers = Array.from(document.querySelectorAll('.announcements-content'));
  const renderToAll = (html) => containers.forEach(container => { container.innerHTML = html; });
  try {
    const r = await fetch(`${API_URL}/api/announcements`);
    const data = await r.json();
    if (!data.length) {
      renderToAll('<div class="empty-state">Объявлений пока нет</div>');
      return;
    }

    const REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '👑'];

    // Загружаем реакции для каждого объявления
    const withReactions = await Promise.all(data.map(async item => {
      try {
        const rr = await fetch(`${API_URL}/api/announcements/${item.id}/reactions`);
        const reactions = rr.ok ? await rr.json() : [];
        return { ...item, reactions };
      } catch { return { ...item, reactions: [] }; }
    }));

    const html = withReactions.map(item => {
      const reactionMap = {};
      item.reactions.forEach(r => { reactionMap[r.emoji] = r.count; });

      const reactionBtns = REACTIONS.map(emoji => {
        const count = reactionMap[emoji] || 0;
        const active = count > 0 ? 'background:rgba(212,175,55,0.15);border-color:rgba(212,175,55,0.4);' : '';
        return `<button onclick="reactToAnnouncement(${item.id}, '${emoji}', this)" 
          style="display:inline-flex;align-items:center;gap:3px;padding:4px 8px;
          background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
          border-radius:20px;cursor:pointer;font-size:13px;color:var(--text2);
          font-family:monospace;${active}transition:all 0.2s;">
          ${emoji}${count > 0 ? `<span style="font-size:10px;color:var(--gold);">${count}</span>` : ''}
        </button>`;
      }).join('');

     function formatAnnouncementText(text = '') {
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\r\n/g, '\n')
        .replace(/\n/g, '<br>');
    }
      
      return `<div class="announcement-item">
        <div class="announcement-text">${formatAnnouncementText(item.text || '')}</div>
        <div class="announcement-date">${new Date(item.created_at).toLocaleDateString('ru-RU')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:10px;">${reactionBtns}</div>
        ${isAdmin ? `<button onclick="deleteAnnouncement(${item.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-size:11px;margin-top:6px;font-family:monospace;">[ УДАЛИТЬ ]</button>` : ''}
      </div>`;
    }).join('');

    renderToAll(html);
    document.querySelectorAll('.admin-announce-form').forEach(form => {
      form.style.display = isAdmin ? 'block' : 'none';
    });
  } catch(e) {
    renderToAll('<div class="empty-state">Ошибка загрузки</div>');
  }
}

async function reactToAnnouncement(id, emoji, btn) {
  if (!currentUserId) { tg.showAlert('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements/${id}/react`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, emoji})
    });
    if (r.ok) {
      try{tg.HapticFeedback.impactOccurred('light');}catch(e){}
      loadAnnouncements();
    }
  } catch(e) {}
}

async function addAnnouncement() {
  const source = ['announceText', 'announceTextMore']
    .map(id => document.getElementById(id))
    .find(el => el && el.value.trim());
  const text = source ? source.value.trim() : '';
  if (!text) { tg.showAlert('Введите текст'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) {
      tg.showAlert('✅ Опубликовано!');
      ['announceText', 'announceTextMore'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      loadAnnouncements();
    }
  } catch(e) { tg.showAlert('Ошибка'); }
}

async function addAnnouncementAdmin() {
  const text = document.getElementById('announceTextAdmin').value;
  if (!text) { tg.showAlert('Введите текст'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) { tg.showAlert('✅ Опубликовано!'); document.getElementById('announceTextAdmin').value=''; loadAnnouncements(); }
  } catch(e) { tg.showAlert('Ошибка'); }
}

async function deleteAnnouncement(id) {
  try { await fetch(`${API_URL}/api/announcements/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadAnnouncements(); } catch(e) {}
}

// ===== АЧИВКИ =====
async function loadAchievements() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/achievements/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('achievementsContent');
    const earned = data.filter(a => a.earned).length;
    let html = `<div class="achievement-count">// Получено: <b style="color:var(--gold)">${earned}</b> из ${data.length}</div><div class="achievements-grid">`;
    data.forEach(a => {
      const svgIcon = ACHIEVEMENT_ICONS[a.code] || `<svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="20" fill="rgba(212,175,55,0.3)"/></svg>`;
      html += `<div class="achievement-card ${a.earned?'':'locked'}" onclick="showAchievementInfo('${a.name}','${a.description}',${a.earned})">
        ${a.earned ? '<div class="achievement-earned-badge">✨</div>' : ''}
        <div class="achievement-svg">${svgIcon}</div>
        <div class="achievement-name">${a.name}</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch(e) { document.getElementById('achievementsContent').innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

function showAchievementInfo(name, description, earned) {
  tg.showPopup({title:earned?'✅ '+name:'🔒 '+name,message:description+(earned?'\n\n✨ Получено!':'\n\n❌ Ещё не получено'),buttons:[{type:'ok'}]});
}

// ===== АНОНИМНЫЙ ВОПРОС =====
function askAnonymous() { document.getElementById('questionModal').classList.add('show'); document.getElementById('questionText').value=''; }
function closeQuestion() { document.getElementById('questionModal').classList.remove('show'); }

async function submitQuestion() {
  const text = document.getElementById('questionText').value.trim();
  if (!text) { tg.showAlert('Напиши вопрос!'); return; }
  try {
    const r = await fetch(`${API_URL}/api/question`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,telegram_id:currentUserId})});
    if (r.ok) { closeQuestion(); tg.showAlert('✅ Вопрос отправлен анонимно!'); try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} }
    else tg.showAlert('Ошибка отправки');
  } catch(e) { tg.showAlert('Ошибка соединения'); }
}

// ===== АДМИН =====
function showAdminSection(name, btn) {
  ['schedule','announce','laundry','users','blackwall'].forEach(s => {
    const el = document.getElementById('admin-'+s); if(el) el.style.display='none';
  });
  document.querySelectorAll('.admin-sec-btn').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const el = document.getElementById('admin-'+name);
  if(el) el.style.display = 'block';
  if (name==='laundry') adminLoadLaundrySlots();
}

async function loadAdminLaundry() {
  try {
    const r = await fetch(`${API_URL}/api/laundry`);
    const data = await r.json();
    const container = document.getElementById('adminLaundryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Записей нет</div>'; return; }
    container.innerHTML = data.map(b => `
      <div class="schedule-item">
        <div class="schedule-info"><div class="schedule-subject">${b.username}</div><div class="schedule-location">${b.date} в ${b.time}</div></div>
        <button onclick="adminCancelLaundry(${b.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-family:monospace;font-size:10px;">✕</button>
      </div>`).join('');
  } catch(e) {}
}

async function adminCancelLaundry(id) {
  try { await fetch(`${API_URL}/api/laundry/${id}`,{method:'DELETE',headers:{'x-telegram-id':currentUserId}}); loadAdminLaundry(); loadLaundry(); } catch(e) {}
}

async function adminFreeze(freeze) {
  const telegramId = parseInt(document.getElementById('freezeId').value);
  if (!telegramId) { tg.showAlert('Введи Telegram ID игрока'); return; }

  try {
    const r = await fetch(`${API_URL}/api/admin/freeze`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
      body: JSON.stringify({telegram_id: telegramId, frozen: freeze})
    });
    if (r.ok) {
      if (freeze) {
        // Отправляем уведомление через бота
        await fetch(`https://api.telegram.org/bot8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc/sendMessage`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chat_id: telegramId,
            text: '⛔ NETWATCH 网络保安\n\n系统检测到异常活动\nСистема обнаружила подозрительную активность с вашей стороны.\n\nВаш аккаунт временно заморожен.\nМагазин и кейсы недоступны.\n\n— NetWatch Protocol v1.4 —'
          })
        });
        tg.showAlert('⛔ Аккаунт заморожен!\nИгрок получил уведомление от NetWatch.');
      } else {
        await fetch(`https://api.telegram.org/bot8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc/sendMessage`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chat_id: telegramId,
            text: '✅ NETWATCH 网络保安\n\n访问已恢复\nДоступ восстановлен.\n\nВаш аккаунт разморожен.\nМагазин и кейсы снова доступны.\n\n— NetWatch Protocol v1.4 —'
          })
        });
        tg.showAlert('✅ Аккаунт разморожен!\nИгрок получил уведомление.');
      }
      document.getElementById('freezeId').value = '';
    } else {
      tg.showAlert('Ошибка! Проверь ID');
    }
  } catch(e) { tg.showAlert('Ошибка соединения'); }
}

// ===== АДМИН: СТИРКА И ВОДА =====
function switchAdminLaundryTab(tab) {
  document.getElementById('al-laundry-tab').style.display = tab==='laundry' ? 'block' : 'none';
  document.getElementById('al-water-tab').style.display = tab==='water' ? 'block' : 'none';
  document.getElementById('altab-laundry').classList.toggle('active', tab==='laundry');
  document.getElementById('altab-water').classList.toggle('active', tab==='water');
  if (tab==='laundry') adminLoadLaundrySlots();
  else adminLoadWaterSlots();
}

async function adminLoadLaundrySlots() {
  const container = document.getElementById('adminLaundryList');
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) { container.innerHTML = '<div class="empty-state">Слотов нет</div>'; return; }
    container.innerHTML = data.map(slot => {
      const taken = slot.taken_by ? `<span style="color:#2ecc71;font-size:9px;">✓ ${slot.taken_by.name}</span>` : `<span style="color:var(--text3);font-size:9px;">Свободно</span>`;
      return `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="flex:1;">
          <div style="font-size:11px;color:var(--text);font-weight:600;">${slot.day} · ${slot.time}</div>
          <div style="font-size:9px;color:var(--text3);">${slot.note||''}</div>
          ${taken}
        </div>
        <button onclick="adminDeleteLaundrySlot(${slot.id})" style="background:none;border:1px solid rgba(200,50,50,0.3);color:rgba(200,80,80,0.7);padding:4px 10px;border-radius:4px;font-size:9px;font-family:monospace;cursor:pointer;"><i class="ti ti-trash"></i></button>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка</div>'; }
}

async function adminAddLaundrySlot() {
  const day = document.getElementById('lDay').value.trim();
  const time = document.getElementById('lTime').value.trim();
  const note = document.getElementById('lNote').value.trim();
  if (!day || !time) { tg.showAlert('Заполни день и время'); return; }
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day, time, note, capacity: parseInt(document.getElementById('lCapacity').value)||1})
    });
    if (r.ok) {
      document.getElementById('lDay').value='';
      document.getElementById('lTime').value='';
      document.getElementById('lNote').value='';
      try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
      adminLoadLaundrySlots();
    } else tg.showAlert('Ошибка!');
  } catch(e) { tg.showAlert('Ошибка соединения'); }
}

async function adminDeleteLaundrySlot(id) {
  tg.showPopup({title:'Удалить слот?',message:'Запись будет удалена.',buttons:[{id:'ok',type:'destructive',text:'Удалить'},{type:'cancel'}]}, async(b)=>{
    if(b!=='ok')return;
    await fetch(`${API_URL}/api/laundry/schedule/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}});
    adminLoadLaundrySlots();
  });
}

async function adminLoadWaterSlots() {
  const container = document.getElementById('adminWaterList');
  try {
    const r = await fetch(`${API_URL}/api/water/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) { container.innerHTML = '<div class="empty-state">Слотов нет</div>'; return; }
    container.innerHTML = data.map(slot => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="flex:1;">
          <div style="font-size:11px;color:var(--text);font-weight:600;">${slot.day} · ${slot.time}</div>
          <div style="font-size:9px;color:var(--text3);">${slot.note||''}</div>
        </div>
        <button onclick="adminDeleteWaterSlot(${slot.id})" style="background:none;border:1px solid rgba(200,50,50,0.3);color:rgba(200,80,80,0.7);padding:4px 10px;border-radius:4px;font-size:9px;font-family:monospace;cursor:pointer;"><i class="ti ti-trash"></i></button>
      </div>`).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка</div>'; }
}

async function adminAddWaterSlot() {
  const day = document.getElementById('wDay').value.trim();
  const time = document.getElementById('wTime').value.trim();
  const note = document.getElementById('wNote').value.trim();
  if (!day || !time) { tg.showAlert('Заполни день и время'); return; }
  try {
    const r = await fetch(`${API_URL}/api/water/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day, time, note, capacity: parseInt(document.getElementById('wCapacity').value)||1})
    });
    if (r.ok) {
      document.getElementById('wDay').value='';
      document.getElementById('wTime').value='';
      document.getElementById('wNote').value='';
      try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
      adminLoadWaterSlots();
    } else tg.showAlert('Ошибка!');
  } catch(e) { tg.showAlert('Ошибка соединения'); }
}

async function adminDeleteWaterSlot(id) {
  tg.showPopup({title:'Удалить слот?',message:'Слот будет удалён.',buttons:[{id:'ok',type:'destructive',text:'Удалить'},{type:'cancel'}]}, async(b)=>{
    if(b!=='ok')return;
    await fetch(`${API_URL}/api/water/schedule/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}});
    adminLoadWaterSlots();
  });
}

async function adminAward() {
  const name=document.getElementById('awardName').value, points=parseInt(document.getElementById('awardPoints').value), reason=document.getElementById('awardReason').value;
  if (!name||!points||!reason) { tg.showAlert('Заполни все поля'); return; }
  tg.showAlert('Для начисления баллов используй /award в боте');
}

async function adminPenalize() {
  tg.showAlert('Для снятия баллов используй /penalize в боте');
}

async function setBlackwall(enabled) {
  try {
    const r = await fetch(`${API_URL}/api/admin/blackwall`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({enabled})});
    if (r.ok) tg.showAlert(enabled ? '⛔ BlackWall включён!' : '✅ BlackWall выключен!');
  } catch(e) { tg.showAlert('Ошибка'); }
}

/* --- ЛОГИКА РЕЙДОВОЙ СИСТЕМЫ v2.0 (Быстрый старт) --- */

// НАСТРОЙКИ
const RAID_CONFIG = {
    minPlayers: 3,
    maxPlayers: 15,
    adminIds: [389741116, 244487659, 1190015933, 491711713],
    cyberpunk: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_netwatchtheme.png?raw=true',
        title: '// MICHAEL SMASHER PROTOCOL // TARGET: МЮ',
        placeholderColor: '#ff003c'
    },
    genshin: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_genshintheme.png?raw=true',
        title: '💎 МИКЕЛАНДЖЕЛО // ПЕРВЫЙ ПРЕДВЕСТНИК ОТБОЯ',
        placeholderColor: '#dbb165'
    }
};

let raidRefreshTimer = null;
let isJoiningRaid = false;
let raidIntroToken = 0;

function getRaidThemeKey() {
    return document.body.classList.contains('theme-genshin') ? 'genshin' : 'cyberpunk';
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function setRaidButtonState(text, disabled, background = '', color = '') {
    const btn = document.getElementById('raid-action-btn');
    if (!btn) return;
    btn.disabled = !!disabled;
    btn.innerHTML = `<i class="ti ti-broadcast"></i> ${text}`;
    btn.style.background = background;
    btn.style.color = color;
    btn.style.opacity = disabled ? '0.72' : '1';
}

function setRaidStatusText(text, color = 'var(--text2)') {
    const status = document.getElementById('raid-status-text');
    if (!status) return;
    status.textContent = text;
    status.style.color = color;
}

function setRaidProgressVisual(percent, state = 'INIT', hint = 'Neural handshake pending', tone = 'pending') {
    const progressBar = document.getElementById('raid-progress-bar');
    const percentLabel = document.getElementById('raid-progress-percent');
    const hintLabel = document.getElementById('raid-progress-hint');
    const stateLabel = document.getElementById('raid-sync-state');
    if (!progressBar || !percentLabel || !hintLabel || !stateLabel) return;

    const safePercent = Math.max(0, Math.min(Math.round(percent || 0), 100));
    const palette = {
        pending: {
            background: 'linear-gradient(90deg, var(--red), #ff7a18)',
            glow: '0 0 18px rgba(255, 80, 55, 0.42)',
            color: 'var(--text)'
        },
        success: {
            background: 'linear-gradient(90deg, #2ecc71, #6cffb8)',
            glow: '0 0 20px rgba(46, 204, 113, 0.42)',
            color: '#d6ffe9'
        },
        danger: {
            background: 'linear-gradient(90deg, #a30d15, #ff4d5a)',
            glow: '0 0 20px rgba(220, 65, 82, 0.45)',
            color: '#ffd6dc'
        }
    };
    const activeTone = palette[tone] || palette.pending;

    progressBar.style.width = safePercent + '%';
    progressBar.style.background = activeTone.background;
    progressBar.style.boxShadow = activeTone.glow;
    percentLabel.textContent = safePercent + '%';
    hintLabel.textContent = hint;
    stateLabel.textContent = state;
    stateLabel.style.color = activeTone.color;
}

function updateRaidUI(joinedCount, target = RAID_CONFIG.minPlayers) {
    const currentLabel = document.getElementById('raid-current-count');
    const maxLabel = document.getElementById('raid-max-count');
    if (!currentLabel || !maxLabel) return;

    const safeCount = Math.max(0, Math.min(joinedCount || 0, RAID_CONFIG.maxPlayers));
    const safeTarget = Math.max(1, target || RAID_CONFIG.minPlayers);
    const percentage = Math.min((safeCount / safeTarget) * 100, 100);
    const ready = safeCount >= safeTarget;

    currentLabel.innerText = safeCount;
    maxLabel.innerText = safeTarget;
    setRaidProgressVisual(
        percentage,
        ready ? 'READY' : 'ASSEMBLING',
        ready ? 'Отряд собран. Канал готов к запуску.' : `Идёт синхронизация отряда: ${safeCount}/${safeTarget}`,
        ready ? 'success' : 'pending'
    );
}

function prepareRaidVisual() {
    const currentTheme = getRaidThemeKey();
    const config = RAID_CONFIG[currentTheme];
    const bossImg = document.getElementById('boss-img');
    const bossTitle = document.getElementById('boss-title');
    const frame = document.querySelector('.boss-frame');
    const existingPlaceholder = frame ? frame.querySelector('.boss-placeholder') : null;

    if (bossTitle) bossTitle.innerText = config.title;
    if (existingPlaceholder) existingPlaceholder.remove();
    if (!bossImg) return;

    bossImg.style.display = 'block';
    bossImg.style.backgroundColor = 'transparent';
    bossImg.onload = function() {
        const placeholder = frame ? frame.querySelector('.boss-placeholder') : null;
        if (placeholder) placeholder.remove();
        this.style.display = 'block';
    };
    bossImg.onerror = function() {
        this.style.display = 'none';
        if (!frame || frame.querySelector('.boss-placeholder')) return;

        const placeholder = document.createElement('div');
        placeholder.className = 'boss-placeholder';
        placeholder.style.width = '228px';
        placeholder.style.height = '252px';
        placeholder.style.borderRadius = currentTheme === 'genshin' ? '24px' : '28px';
        placeholder.style.background = config.placeholderColor;
        placeholder.style.display = 'flex';
        placeholder.style.alignItems = 'center';
        placeholder.style.justifyContent = 'center';
        placeholder.style.color = '#fff';
        placeholder.style.fontSize = '40px';
        placeholder.style.fontWeight = 'bold';
        placeholder.style.boxShadow = '0 0 20px ' + config.placeholderColor;
        placeholder.innerText = 'M.Y.';
        Object.assign(placeholder.style, {
            transform: 'scale(0.92) translateY(12px)',
            opacity: '0',
            transition: 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) 0.3s',
            animation: 'bossFloat 4s ease-in-out infinite 0.9s'
        });
        frame.appendChild(placeholder);
        setTimeout(() => {
            placeholder.style.transform = 'scale(1) translateY(0)';
            placeholder.style.opacity = '1';
        }, 50);
    };
    bossImg.src = config.img;
}

async function playRaidIntro(token) {
    const steps = [
        { percent: 8, state: 'LINK', hint: 'Нейролинк инициирован', status: 'Подготовка боевого канала...' },
        { percent: 24, state: 'SCAN', hint: 'Сканирование сигнатуры босса', status: 'Считываем поведенческий профиль Альфабосса...' },
        { percent: 41, state: 'WALL', hint: 'Обход BlackWall', status: 'Пробиваем внешний защитный слой...' },
        { percent: 63, state: 'ROUTE', hint: 'Маршрутизация отряда', status: 'Собираем точки входа для ударной группы...' },
        { percent: 82, state: 'LOCK', hint: 'Фиксация боевого канала', status: 'Канал почти стабилен. Держим сигнал...' },
        { percent: 100, state: 'READY', hint: 'Система готова к рейду', status: 'Контур активен. Можно подключаться к атаке.' }
    ];

    for (const step of steps) {
        if (token !== raidIntroToken) return false;
        setRaidProgressVisual(step.percent, step.state, step.hint, step.percent >= 100 ? 'success' : 'pending');
        setRaidStatusText(step.status, step.percent >= 100 ? '#2ecc71' : 'var(--text2)');
        await sleep(step.percent >= 100 ? 650 : 850);
    }

    return token === raidIntroToken;
}

function closeRaid() {
    const overlay = document.getElementById('raid-overlay');
    raidIntroToken += 1;
    if (overlay) overlay.classList.remove('active');
    if (raidRefreshTimer) {
        clearInterval(raidRefreshTimer);
        raidRefreshTimer = null;
    }
}

async function showRaid() {
    prepareRaidVisual();
    updateRaidUI(0);
    setRaidStatusText('Синхронизация рейда...');
    setRaidButtonState('Загрузка статуса...', true);

    const overlay = document.getElementById('raid-overlay');
    if (overlay) overlay.classList.add('active');

    if (raidRefreshTimer) {
        clearInterval(raidRefreshTimer);
        raidRefreshTimer = null;
    }

    const introToken = ++raidIntroToken;
    const introCompleted = await playRaidIntro(introToken);
    if (!introCompleted || !document.getElementById('raid-overlay')?.classList.contains('active')) return;

    await loadRaidStatus();

    if (raidRefreshTimer) clearInterval(raidRefreshTimer);
    raidRefreshTimer = setInterval(() => {
        const isOpen = document.getElementById('raid-overlay')?.classList.contains('active');
        if (isOpen && !isJoiningRaid) loadRaidStatus();
    }, 5000);
}

async function loadRaidStatus() {
    try {
        const r = await fetch(`${API_URL}/api/raid/status?telegram_id=${currentUserId || 0}`);
        if (!r.ok) throw new Error('status');

        const data = await r.json();
        const raidLimit = data.limit_today || 3;
        const finishedToday = data.finished_today || 0;
        const numericRemaining = typeof data.remaining_today === 'number'
            ? data.remaining_today
            : Math.max(0, raidLimit - finishedToday);
        const remainingToday = isAdmin ? 'без лимита' : `${numericRemaining}/${raidLimit}`;

        if (!data.raid) {
            updateRaidUI(0);
            setRaidProgressVisual(6, 'STANDBY', 'Ни один отряд ещё не собран', 'pending');
            setRaidStatusText(
                isAdmin
                    ? 'Рейд ещё не создан. Админ может стартовать в любой момент.'
                    : `Рейд ещё не собран. Осталось попыток сегодня: ${remainingToday}.`
            );
            setRaidButtonState(
                'Подключиться к нейролинку',
                finishedToday >= raidLimit && !isAdmin
            );
            return;
        }

        const participants = data.participants || [];
        const count = data.count ?? participants.length ?? 0;
        const participantNames = participants.map(p => p.name).join(' • ');
        const alreadyJoined = participants.some(p => p.telegram_id === currentUserId);

        if (data.raid.status === 'finished') {
            const success = data.raid.result === 'success';
            updateRaidUI(Math.max(count, RAID_CONFIG.minPlayers));
            setRaidProgressVisual(
                100,
                success ? 'VICTORY' : 'FAIL',
                success ? 'Альфабосс пробит. Награда начислена.' : 'Контур сорван. Ставки потеряны.',
                success ? 'success' : 'danger'
            );
            setRaidStatusText(
                success
                    ? `Рейд завершён: +150★ каждому.${participantNames ? ' Бойцы: ' + participantNames : ''}`
                    : `Альфабосс отбился.${participantNames ? ' В отряде были: ' + participantNames : ''}`,
                success ? '#2ecc71' : '#cc4444'
            );
            setRaidButtonState(
                isAdmin || numericRemaining > 0 ? 'Начать новый рейд' : 'Рейды на сегодня закрыты',
                !isAdmin && numericRemaining <= 0
            );
            return;
        }

        updateRaidUI(count);
        setRaidProgressVisual(
            Math.min((count / RAID_CONFIG.minPlayers) * 100, 100),
            alreadyJoined ? 'LINKED' : 'ASSEMBLING',
            alreadyJoined ? 'Ты уже синхронизирован с отрядом.' : 'Идёт добор бойцов для запуска.',
            count >= RAID_CONFIG.minPlayers ? 'success' : 'pending'
        );
        setRaidStatusText(
            alreadyJoined
                ? `Ты уже в отряде. Бойцов: ${count}/${RAID_CONFIG.minPlayers}.${participantNames ? ' ' + participantNames : ''}`
                : `Сбор отряда: ${count}/${RAID_CONFIG.minPlayers}.${participantNames ? ' ' + participantNames : ''} ${isAdmin ? '' : 'Осталось рейдов: ' + remainingToday + '.'}`,
            alreadyJoined ? '#2ecc71' : 'var(--text2)'
        );
        setRaidButtonState(
            alreadyJoined ? 'Ты уже в отряде' : 'Подключиться к нейролинку',
            alreadyJoined || isJoiningRaid
        );
    } catch(e) {
        updateRaidUI(0);
        setRaidStatusText('Не удалось загрузить статус рейда.', '#cc4444');
        setRaidButtonState('Повторить подключение', false);
    }
}

function getRaidErrorMessage(detail) {
    if (detail === 'Already joined') return 'Ты уже в этом рейде.';
    if (detail === 'Daily raid limit reached') return 'Сегодня лимит рейдов исчерпан. Попробуй завтра.';
    if (detail === 'Not enough points') return 'Недостаточно баллов для рейда.';
    return 'Не удалось присоединиться к рейду.';
}

async function joinRaid() {
    if (isJoiningRaid) return;
    if (!currentUserId) { tg.showAlert('Откройте приложение через Telegram бота'); return; }
    if (currentPoints < 50) { tg.showAlert('Недостаточно баллов. Нужно 50★'); return; }

    tg.showPopup({
        title: '⚔️ Вступить в рейд?',
        message: 'Ты ставишь 50★. Победа даст +150★ каждому участнику, поражение сожжёт ставку. Рейд стартует при 3 бойцах.',
        buttons: [{id:'confirm', type:'default', text:'⚔️ В БОЙ!'}, {type:'cancel'}]
    }, async (btnId) => {
        if (btnId !== 'confirm') return;

        isJoiningRaid = true;
        setRaidProgressVisual(92, 'BREACH', 'Подключаем тебя к боевому контуру...', 'pending');
        setRaidButtonState('Синхронизация...', true, '#e67e22', '#fff');

        try {
            const r = await fetch(`${API_URL}/api/raid/join`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({telegram_id: currentUserId})
            });
            const data = await r.json();

            if (!r.ok) {
                tg.showAlert(getRaidErrorMessage(data.detail));
                return;
            }

            if (typeof data.new_points === 'number') {
                currentPoints = data.new_points;
                updatePoints();
            }

            if (data.launched && data.result === 'success') {
                setRaidProgressVisual(100, 'VICTORY', 'Альфабосс пробит. Награда зачислена.', 'success');
                launchConfetti(80);
            } else if (data.launched && data.result === 'defended') {
                setRaidProgressVisual(100, 'FAIL', 'Контур сорван. Альфабосс удержал защиту.', 'danger');
            } else {
                setRaidProgressVisual(
                    Math.min(((data.count || 1) / RAID_CONFIG.minPlayers) * 100, 100),
                    'LINKED',
                    `Бойцов в контуре: ${data.count || 1}/${RAID_CONFIG.minPlayers}`,
                    'pending'
                );
            }

            try {
                tg.HapticFeedback.notificationOccurred(
                    data.launched && data.result === 'defended' ? 'error' : 'success'
                );
            } catch(e) {}

            tg.showAlert(data.message || 'Рейд обновлён.');
            loadLeaderboard();
            loadPoints(currentUserId);
        } catch(e) {
            tg.showAlert('Ошибка соединения с рейдом.');
        } finally {
            isJoiningRaid = false;
            loadRaidStatus();
        }
    });
}

// ===== RIPPLE ЭФФЕКТ =====
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.btn, .btn-primary, .shop-item-buy, .subtab, .nav-item');
  if (!btn) return;
  const ripple = document.createElement('div');
  ripple.className = 'ripple';
  const rect = btn.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height);
  ripple.style.width = ripple.style.height = size + 'px';
  ripple.style.left = (e.clientX - rect.left - size/2) + 'px';
  ripple.style.top = (e.clientY - rect.top - size/2) + 'px';
  btn.appendChild(ripple);
  setTimeout(() => ripple.remove(), 500);
});

function buildMatrixRain() {
  const root = document.getElementById('matrixRain');
  if (!root) return;

  root.innerHTML = '';

  const glyphs = ['智','道','龙','福','网','络','协','议','数','据','流','天','命','链','接','红','黑','墙','信','義','勇','中'];
  const columns = Math.max(10, Math.floor(window.innerWidth / 38));

  for (let i = 0; i < columns; i++) {
    const col = document.createElement('div');
    col.className = 'matrix-col';

    const length = 5 + Math.floor(Math.random() * 8);
    const chars = [];

    for (let j = 0; j < length; j++) {
      chars.push(glyphs[Math.floor(Math.random() * glyphs.length)]);
    }

    col.innerHTML = chars.join('<br>');
    col.style.left = `${Math.random() * 100}%`;
    col.style.setProperty('--dur', `${10 + Math.random() * 10}s`);
    col.style.setProperty('--delay', `${-Math.random() * 18}s`);
    col.style.setProperty('--drift', `${-12 + Math.random() * 24}px`);
    col.style.setProperty('--blur', `${Math.random() * 0.6}px`);
    col.style.fontSize = `${12 + Math.random() * 10}px`;
    col.style.opacity = `${0.35 + Math.random() * 0.35}`;

    root.appendChild(col);
  }
}

window.addEventListener('load', buildMatrixRain);
window.addEventListener('resize', buildMatrixRain);

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

function openEventOverlay() {
  const overlay = document.getElementById('eventOverlay');
  if (!overlay) return;

  overlay.style.display = 'block';

  const nav = document.querySelector('.bottom-nav');
  if (nav) nav.style.display = 'none';

  document.body.style.overflow = 'hidden';
  setArchitectAmbientVisibility(false);
  architectMusicUnlocked = true;

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

  const bossVideo = document.getElementById('eventBossVideo');
  if (bossVideo) {
    bossVideo.pause();
  }

  stopArchitectMusic();
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

