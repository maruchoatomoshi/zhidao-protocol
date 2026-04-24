
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
let currentPoints = 0;
let userConfig = null;
let isAdmin = false;
let isSpinning = false;
let selectedLaundryDate = null;
let laundryData = [];
let shopMode = 'store';
let currentMoreSection = null;

const PRIZES = [
  { code:'empty',   icon:'рџЌљ', name:'РџСѓСЃС‚Р°СЏ РјРёСЃРєР° СЂРёСЃР°', desc:'РќРёС‡РµРіРѕ РЅРµ РІС‹РїР°Р»Рѕ...', points:0,   rarity:'common' },
  { code:'small',   icon:'в­ђ', name:'+30 Р±Р°Р»Р»РѕРІ',        desc:'РќРµР±РѕР»СЊС€РѕР№ Р±РѕРЅСѓСЃ',     points:30,  rarity:'common' },
  { code:'medium',  icon:'рџ’«', name:'+60 Р±Р°Р»Р»РѕРІ',        desc:'РќРµРїР»РѕС…Рѕ!',            points:60,  rarity:'uncommon' },
  { code:'walk',    icon:'рџ•ђ', name:'+30 РјРёРЅ СЃРІРѕР±РѕРґС‹',   desc:'РџРѕРєР°Р¶Рё СЃРєСЂРёРЅ РІРѕР¶Р°С‚РѕРјСѓ', points:0, rarity:'uncommon' },
  { code:'laundry', icon:'рџ§є', name:'Р’РЅРµ РѕС‡РµСЂРµРґРё!',      desc:'РџРµСЂРІС‹Рј РЅР° СЃС‚РёСЂРєСѓ',    points:0,   rarity:'rare' },
  { code:'skip',    icon:'рџ›Ў', name:'РРјРјСѓРЅРёС‚РµС‚!',        desc:'РћРґРёРЅ РїСЂРѕРїСѓСЃРє Р±РµР· С€С‚СЂР°С„Р°', points:0, rarity:'rare' },
  { code:'jackpot', icon:'рџ‘‘', name:'Р”Р–Р•РљРџРћРў!',          desc:'+250 Р±Р°Р»Р»РѕРІ! РќРµРІРµСЂРѕСЏС‚РЅРѕ!', points:250, rarity:'jackpot' },
];
const PURPLE_PRIZES = [
  { code:'implant_guanxi',    icon:'рџ¤ќ', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true', name:'Р“СѓР°РЅСЊСЃРё е…ізі»',    desc:'РРјРїР»Р°РЅС‚: -10% Рє С†РµРЅР°Рј РІ РјР°РіР°Р·РёРЅРµ', points:0, rarity:'rare' },
  { code:'implant_terracota', icon:'рџ—ї', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/armor.png?raw=true',          name:'РўРµСЂСЂР°РєРѕС‚Р° е…µй©¬дї‘', desc:'РРјРїР»Р°РЅС‚: Р±Р»РѕРє 1 С€С‚СЂР°С„Р° РІ РґРµРЅСЊ',    points:0, rarity:'rare' },
];
const BLACK_PRIZES = [
  { code:'implant_red_dragon', icon:'рџђ‰', img:'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true', name:'РљСЂР°СЃРЅС‹Р№ Р”СЂР°РєРѕРЅ зєўйѕ™', desc:'вљЎ Р›Р•Р“Р•РќР”РђР РќР«Р™ РџР РћРўРћРљРћР›!', points:0, rarity:'jackpot' },
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
  polyglot:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g5" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g5)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M10 18 Q26 12 42 18 L42 32 Q26 38 10 32 Z" fill="url(#g5)" opacity="0.3" stroke="url(#g5)" stroke-width="1.5"/><text x="26" y="29" text-anchor="middle" font-size="14" font-weight="bold" fill="url(#g5)">дЅ еҐЅ</text></svg>`,
  explorer:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g6" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g6)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M14 38 L20 14 L26 32 L32 18 L38 38" stroke="url(#g6)" stroke-width="2.5" fill="none" stroke-linejoin="round"/><circle cx="26" cy="18" r="4" fill="url(#g6)"/></svg>`,
  brave:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g7" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g7)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M18 36 L18 22 Q18 16 24 16 L28 16 Q30 16 30 20 L30 24 L34 24 Q38 24 38 28 L38 36" stroke="url(#g7)" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="22" cy="36" r="2" fill="url(#g7)"/><circle cx="34" cy="36" r="2" fill="url(#g7)"/></svg>`,
  exemplary:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g8" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g8)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="26" cy="26" r="12" stroke="url(#g8)" stroke-width="2" fill="none"/><path d="M19 26 L23 30 L33 20" stroke="url(#g8)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>`,
  helper:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g9" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g9)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M16 26 Q16 20 22 20 L24 20 Q26 20 26 22 Q26 20 28 20 L30 20 Q36 20 36 26 Q36 32 26 38 Q16 32 16 26 Z" fill="url(#g9)"/></svg>`,
  dragon:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g10" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g10)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M10 36 Q14 28 18 24 Q20 18 26 16 Q32 14 36 18 Q40 22 38 28 Q36 34 30 36 Q26 38 22 36 Q18 40 10 36 Z" fill="url(#g10)" opacity="0.6" stroke="url(#g10)" stroke-width="1.5"/><circle cx="32" cy="22" r="2" fill="#050510"/></svg>`,
  night_watch:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g11" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g11)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><circle cx="22" cy="22" r="4" fill="url(#g11)"/><circle cx="30" cy="22" r="4" fill="url(#g11)"/><circle cx="22" cy="22" r="2" fill="#050510"/><circle cx="30" cy="22" r="2" fill="#050510"/><path d="M18 30 Q26 36 34 30" stroke="url(#g11)" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`,
  master:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g12" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g12)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><rect x="18" y="14" width="16" height="8" rx="2" fill="url(#g12)" opacity="0.6"/><rect x="14" y="26" width="8" height="12" rx="2" fill="url(#g12)" opacity="0.4"/><rect x="26" y="26" width="12" height="12" rx="2" fill="url(#g12)" opacity="0.8"/></svg>`,
  gambler:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g13" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g13)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><rect x="12" y="16" width="28" height="22" rx="4" stroke="url(#g13)" stroke-width="2" fill="rgba(212,175,55,0.1)"/><text x="19" y="31" font-size="8" fill="#f5d05a" font-weight="bold">7</text><text x="26" y="31" font-size="8" fill="#f5d05a" font-weight="bold">в™¦</text><text x="33" y="31" font-size="8" fill="#f5d05a" font-weight="bold">7</text></svg>`,
  lucky:`<svg viewBox="0 0 52 52" fill="none"><defs><linearGradient id="g14" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#f5d05a"/><stop offset="100%" stop-color="#b8860b"/></linearGradient></defs><circle cx="26" cy="26" r="24" stroke="url(#g14)" stroke-width="1.5" fill="rgba(212,175,55,0.08)"/><path d="M26 14 Q26 20 20 20 Q26 20 26 26 Q26 20 32 20 Q26 20 26 14 Z" fill="url(#g14)"/><path d="M26 26 Q26 32 20 32 Q26 32 26 38 Q26 32 32 32 Q26 32 26 26 Z" fill="url(#g14)"/><circle cx="26" cy="26" r="2" fill="url(#g14)"/></svg>`
};

// РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
const user = tg.initDataUnsafe?.user;
if (user) {
  currentUserId = user.id;
  isAdmin = ADMIN_IDS.includes(user.id);
  loadUserData(user.id);
  loadPoints(user.id);
  loadImplants(user.id);
  if (isAdmin) {
    document.getElementById('adminMoreBtn').style.display = 'block';
    document.getElementById('shopResetBtn').style.display = 'block';
  }
}

loadSavedTheme();
const genshinTabBtn = document.getElementById('genshinTabBtn');
if (genshinTabBtn) genshinTabBtn.style.display = 'block';
loadWeather();
loadYuanRate();
loadSchedule();
loadAnnouncements();
loadLeaderboard();
loadAchievements();
initLaundry();

// ===== РќРђР’РР“РђР¦РРЇ =====
function showPage(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  if (btn) btn.classList.add('active');

  if (name === 'schedule') { loadAnnouncements(); loadSchedule(); }
  if (name === 'implants') loadImplants(currentUserId);
  if (name === 'shop') loadShop();
  if (name === 'rating') { loadLeaderboard(); updateRatingPoints(); }
  if (name === 'casino') {
    fetch(`${API_URL}/api/settings`).then(r => r.json()).then(settings => {
      if (settings.blackwall && !isAdmin) {
        document.getElementById('casinoPlayContent').innerHTML =
          '<div class="blackwall-screen"><div class="blackwall-title">BlackWall е·ІжїЂжґ»</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">зі»з»џи®їй—®е·ІеЏ—й™ђ<br>вЂ” NetWatch зЅ‘з»њдїќе®‰ вЂ”</div></div>';
      } else {
        document.getElementById('casinoPlayContent').style.display = 'flex';
        setTimeout(initRoulette, 50);
        setTimeout(() => loadPoints(currentUserId), 300);
      }
    }).catch(() => { setTimeout(initRoulette, 50); });
  }
}

function openMore(section) {
  // РЎРєСЂС‹РІР°РµРј РІСЃРµ СЃСѓР±СЃС‚СЂР°РЅРёС†С‹
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

// ===== Р”РђРќРќР«Р• =====
async function loadUserData(telegramId) {
  try {
    const r = await fetch(`${API_URL}/api/user/${telegramId}`);
    if (r.ok) {
      const data = await r.json();
      userConfig = data.link;
      document.getElementById('status').textContent = 'в—Џ РђРљРўРР’Р•Рќ';
      document.getElementById('status').style.color = '#cc4444';
      document.getElementById('username').textContent = data.username;
      document.getElementById('serverTag').textContent = 'HK NODE // ' + ((data.used_traffic || 0) / 1024/1024/1024).toFixed(2) + ' GB';
      const used = data.used_traffic || 0;
      const usedGB = (used / 1024/1024/1024).toFixed(2);
      document.getElementById('trafficValue').textContent = usedGB + ' GB';
      const percent = Math.min((used / (10*1024*1024*1024)) * 100, 100);
      setTimeout(() => { document.getElementById('progressFill').style.width = percent + '%'; }, 300);
    } else {
      document.getElementById('status').textContent = 'в—Џ РќР• РќРђР™Р”Р•Рќ';
      document.getElementById('username').textContent = 'РќРµС‚ РїРѕРґРїРёСЃРєРё';
    }
  } catch(e) {
    document.getElementById('status').textContent = 'в—Џ РћР¤Р›РђР™Рќ';
    document.getElementById('username').textContent = 'РћС€РёР±РєР° СЃРІСЏР·Рё';
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
      if (data.double_win) {
        const b = document.getElementById('casinoBonusBanner');
        b.style.display = 'block'; b.textContent = 'рџѓЏ РЈР”Р’РћР•РќРР• РђРљРўРР’РќРћ!';
      }
    }
  } catch(e) {}
}

async function loadImplants(telegramId) {
  if (!telegramId) return;
  const IMPLANT_IMGS = {
    'implant_guanxi':     'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/guanxi_implant.png?raw=true',
    'implant_terracota':  'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/armor.png?raw=true',
    'implant_red_dragon': 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/honglong_implant.png?raw=true',
  };
  try {
    const r = await fetch(`${API_URL}/api/casino/implants/${telegramId}`);
    if (!r.ok) return;
    const data = await r.json();

    const homeContainer = document.getElementById('homeImplants');
    const pageContainer = document.getElementById('myImplantsPage');

    if (!data.length) {
      const empty = '<div class="empty-state" style="padding:12px;">РРјРїР»Р°РЅС‚С‹ РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅС‹<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">РћС‚РєСЂС‹РІР°Р№ С„РёРѕР»РµС‚РѕРІС‹Рµ Рё С‡С‘СЂРЅС‹Рµ РєРµР№СЃС‹!</span></div>';
      if (homeContainer) homeContainer.innerHTML = empty;
      if (pageContainer) pageContainer.innerHTML = empty;
      return;
    }

    // РЎС‡РёС‚Р°РµРј РґСѓР±Р»Рё
    const implantCounts = {};
    data.forEach(imp => { implantCounts[imp.implant_id] = (implantCounts[imp.implant_id] || 0) + 1; });
    const seenTypes = {};

    // Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р° вЂ” РєРѕРјРїР°РєС‚РЅРѕ
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

    // РЎС‚СЂР°РЅРёС†Р° РёРјРїР»Р°РЅС‚РѕРІ вЂ” СЃ РєРЅРѕРїРєРѕР№ СЂР°Р·Р±РѕСЂРєРё РґР»СЏ РґСѓР±Р»РµР№
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
        ? `<span style="background:rgba(212,175,55,0.15);border:1px solid rgba(212,175,55,0.3);color:var(--gold);font-size:8px;padding:1px 6px;border-radius:3px;font-family:monospace;margin-left:6px;">Р”РЈР‘Р›Р¬</span>`
        : '';

      const disassembleBtn = isSecond
        ? `<button onclick="disassembleImplant(${imp.id})" style="margin-top:8px;width:100%;padding:7px;background:rgba(212,175,55,0.08);border:1px solid rgba(212,175,55,0.25);color:var(--gold);border-radius:6px;font-size:9px;font-family:monospace;cursor:pointer;letter-spacing:1px;">вљ™пёЏ [ Р РђР—РћР‘Р РђРўР¬ +100 в… ]</button>`
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
            <div style="font-size:9px;color:var(--text3);font-family:monospace;margin-top:2px;">РџРѕР»СѓС‡РµРЅ: ${new Date(imp.obtained_at).toLocaleDateString('ru-RU')}</div>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
            <div style="font-size:8px;color:var(--text3);font-family:monospace;">Р—РђР РЇР”Р«</div>
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
  document.getElementById('myPoints').textContent = currentPoints + ' в…';
  document.getElementById('myPointsBig').textContent = currentPoints;
  document.getElementById('casinoPoints').textContent = currentPoints + ' в…';
  document.getElementById('shopPoints').textContent = currentPoints + ' в…';
  document.getElementById('myPointsRating').textContent = currentPoints;
}

function updateRatingPoints() {
  document.getElementById('myPointsRating').textContent = currentPoints;
}

// ===== РљРћРќР¤РР“ =====
function getConfig() {
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
  if (userConfig) {
    document.getElementById('configBox').textContent = userConfig;
    document.getElementById('configBox').style.display = 'block';
    document.getElementById('copyBtn').style.display = 'block';
  } else { tg.showAlert('РљРѕРЅС„РёРі РЅРµ РЅР°Р№РґРµРЅ. РђРєС‚РёРІРёСЂСѓР№С‚Рµ РєРѕРґ С‡РµСЂРµР· /start РљРћР” РІ Р±РѕС‚Рµ.'); }
}

function copyConfig() {
  if (userConfig) {
    navigator.clipboard.writeText(userConfig);
    const btn = document.getElementById('copyBtn');
    btn.textContent = 'вњ… РЎРљРћРџРР РћР’РђРќРћ!';
    setTimeout(() => { btn.textContent = 'рџ“‹ РЎРљРћРџРР РћР’РђРўР¬'; }, 2000);
  }
}

function showHelp() {
  tg.showPopup({ title: 'рџ“– РРЅСЃС‚СЂСѓРєС†РёСЏ', message: '1. РќР°Р¶РјРё "РљРћРќР¤РР“"\n2. РќР°Р¶РјРё "РЎРљРћРџРР РћР’РђРўР¬"\n3. РћС‚РєСЂРѕР№ Happ в†’ + в†’ РІСЃС‚Р°РІСЊ СЃСЃС‹Р»РєСѓ\n4. РџРѕРґРєР»СЋС‡РёСЃСЊ!', buttons: [{type:'ok'}] });
}

function contactAdmin() { tg.openTelegramLink('https://t.me/christianpastor'); }

// ===== Р РђРЎРџРРЎРђРќРР• =====
async function loadSchedule() {
  try {
    const r = await fetch(`${API_URL}/api/schedule`);
    const data = await r.json();
    const container = document.getElementById('scheduleContent');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Р Р°СЃРїРёСЃР°РЅРёРµ РїРѕРєР° РЅРµ РґРѕР±Р°РІР»РµРЅРѕ</div>'; return; }
    const byDay = {};
    data.forEach(item => { if (!byDay[item.day]) byDay[item.day] = []; byDay[item.day].push(item); });
    let html = '';
    for (const day in byDay) {
      html += `<div class="schedule-day">рџЏ® ${day}</div>`;
      byDay[day].forEach(item => {
        html += `<div class="schedule-item">
          <div class="schedule-time">${item.time}</div>
          <div class="schedule-info">
            <div class="schedule-subject">${item.subject}</div>
            <div class="schedule-location">рџ“Ќ ${item.location}</div>
          </div>
          ${isAdmin ? `<button onclick="deleteSchedule(${item.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-size:16px;padding:4px;">вњ•</button>` : ''}
        </div>`;
      });
    }
    container.innerHTML = html;
    if (isAdmin) document.getElementById('adminScheduleForm').style.display = 'block';
  } catch(e) { document.getElementById('scheduleContent').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
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
  if (!day || !time || !subject || !location) { tg.showAlert('Р—Р°РїРѕР»РЅРёС‚Рµ РІСЃРµ РїРѕР»СЏ'); return; }
  try {
    const r = await fetch(`${API_URL}/api/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day,time,subject,location})
    });
    if (r.ok) {
      tg.showAlert('вњ… Р”РѕР±Р°РІР»РµРЅРѕ!');
      ['schDay','schTime','schSubject','schLocation','adminSchDay','adminSchTime','adminSchSubject','adminSchLocation']
        .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
      loadSchedule();
    }
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

async function deleteSchedule(id) {
  try { await fetch(`${API_URL}/api/schedule/${id}`, {method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadSchedule(); } catch(e) {}
}

// ===== Р Р•Р™РўРРќР“ =====
// ===== РўР•РњР« =====

function setTheme(theme) {
  // РЈР±РёСЂР°РµРј РІСЃРµ РєР»Р°СЃСЃС‹ С‚РµРј
  THEMES.forEach(t => {
    if (t) document.body.classList.remove('theme-' + t);
  });
  // РџСЂРёРјРµРЅСЏРµРј РЅРѕРІСѓСЋ
  if (theme) document.body.classList.add('theme-' + theme);

  // РЎРѕС…СЂР°РЅСЏРµРј
  try {
    localStorage.setItem('zhidao_theme', theme);
    if(window.Telegram?.WebApp?.CloudStorage) tg.CloudStorage.setItem('zhidao_theme', theme, ()=>{});
  } catch(e) {}

  // РћР±РЅРѕРІР»СЏРµРј РіР°Р»РѕС‡РєРё
  THEMES.forEach(t => {
    const key = t || 'default';
    const el = document.getElementById('check-' + key);
    if (el) el.style.display = (t === theme) ? 'block' : 'none';
  });

  // РћР±РЅРѕРІР»СЏРµРј Р»РѕРіРѕС‚РёРї РїРѕРґ С‚РµРјСѓ
  const logoImg = document.querySelector('.main-logo img');
  const isG = theme === 'genshin-light' || theme === 'genshin-dark';
  document.body.classList.toggle('theme-genshin', isG);
  if (logoImg) {
    logoImg.src = isG
      ? 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/logo_genshintheme_nobackground.png'
      : 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/logo.png?raw=true';
  }
  // РџРµСЂРµРёРјРµРЅРѕРІС‹РІР°РµРј СЂР°Р·РґРµР»С‹ РїРѕРґ С‚РµРјСѓ
  const el = (id) => document.getElementById(id);
  if (el('nav-casino-label'))    el('nav-casino-label').textContent = isG ? 'зҐ€ж„ї' : 'з®±е­ђ';
  if (el('nav-casino-icon'))     el('nav-casino-icon').className    = isG ? 'ti ti-sparkles' : 'ti ti-package';
  if (el('nav-implants-label'))  el('nav-implants-label').textContent = isG ? 'еЌЎз‰‡' : 'ж¤Ќе…Ґз‰©';
  if (el('nav-implants-icon'))   el('nav-implants-icon').className  = isG ? 'ti ti-cards' : 'ti ti-cpu';
  if (el('casino-page-cn'))      el('casino-page-cn').textContent   = isG ? 'зҐ€ж„ї' : 'з®±е­ђ';
  if (el('casino-page-title'))   el('casino-page-title').firstChild.textContent = isG ? 'РњРћР›РРўР’Р« ' : 'РљР•Р™РЎР« ';
  if (el('implants-page-cn'))    el('implants-page-cn').textContent = isG ? 'еЌЎз‰‡' : 'ж¤Ќе…Ґз‰©';
  if (el('implants-page-title')) el('implants-page-title').firstChild.textContent = isG ? 'РљРђР РўРћР§РљР ' : 'РРњРџР›РђРќРўР« ';
  if (el('home-neuro-divider'))  el('home-neuro-divider').textContent = isG ? 'вњ¦ еЌЎз‰‡ Р°СЂС‚РµС„Р°РєС‚С‹ вњ¦' : 'рџЏ® зЅ‘з»њй“ѕжЋҐ РЅРµР№СЂРѕР»РёРЅРє рџЏ®';
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

async function loadLeaderboard() {
  try {
    const r = await fetch(`${API_URL}/api/leaderboard`);
    const data = await r.json();
    const container = document.getElementById('leaderboardContent');
    if (!data.length) { container.innerHTML = '<div class="empty-state">Р РµР№С‚РёРЅРі РїРѕРєР° РїСѓСЃС‚</div>'; return; }
    const medals = ['рџҐ‡','рџҐ€','рџҐ‰'];
    let myRank = 'вЂ”', html = '';
    data.forEach((item, i) => {
      const medal = medals[i] || (i+1)+'.';
      const isMe = currentUserId && item.telegram_id === currentUserId;
      if (isMe) myRank = i+1;
      const titleBadge = item.has_title ? ' рџ‘‘' : '';

      // Р¦РІРµС‚ РЅРёРєР° РїРѕ РёРјРїР»Р°РЅС‚Сѓ
      let nameStyle = '';
      let implantBadge = '';
      if (item.implant === 'implant_red_dragon') {
        nameStyle = 'color:#cc2200;text-shadow:0 0 8px rgba(200,0,0,0.4);font-weight:700;';
        implantBadge = ' <span style="font-size:10px;">рџђ‰</span>';
      } else if (item.implant === 'implant_guanxi' || item.implant === 'implant_terracota') {
        nameStyle = 'color:#9b59b6;text-shadow:0 0 8px rgba(155,89,182,0.3);font-weight:700;';
        implantBadge = ' <span style="font-size:10px;">рџ’њ</span>';
      }

      html += `<div class="lb-item ${isMe?'me':''}">
        <div class="lb-rank">${medal}</div>
        <div class="lb-name" style="${nameStyle}">${item.name}${titleBadge}${implantBadge}${isMe?' рџ‘€':''}</div>
        <div class="lb-points">${item.points} в…</div>
      </div>`;
    });
    container.innerHTML = html;
    document.getElementById('myRankSub').textContent = myRank !== 'вЂ”' ? `// РњРµСЃС‚Рѕ РІ СЂРµР№С‚РёРЅРіРµ: #${myRank}` : '// РЈС‡Р°СЃС‚РІСѓР№ С‡С‚РѕР±С‹ РїРѕРїР°СЃС‚СЊ РІ СЂРµР№С‚РёРЅРі!';
  } catch(e) { document.getElementById('leaderboardContent').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

// ===== РњРђР“РђР—РРќ =====
function switchShopTab(mode, btn) {
  shopMode = mode;
  document.querySelectorAll('#page-shop .subtab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (mode === 'store') {
    document.getElementById('shopStoreContent').style.display = 'block';
    document.getElementById('shopInventoryContent').style.display = 'none';
    loadShop();
  } else {
    document.getElementById('shopStoreContent').style.display = 'none';
    document.getElementById('shopInventoryContent').style.display = 'block';
    loadInventory();
  }
}

// РњР°РїРїРёРЅРі РёРєРѕРЅРѕРє РјР°РіР°Р·РёРЅР° вЂ” Tabler РІРјРµСЃС‚Рѕ СЌРјРѕРґР·Рё
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
  card_zhongli:   {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',emoji:'рџЄЁ',stars:'в…в…в…в…в…',starsColor:'#c0a040',pool:'gold',backCn:'еІ©',petals:['вњ¦','в…','рџЊџ','в—†','вњ§'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_star:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',emoji:'в­ђ',stars:'в…в…в…в…в…',starsColor:'#c0a040',pool:'gold',backCn:'жџ',petals:['вњ¦','в…','рџЊџ','в—†'],petalColor:'rgba(255,215,0,0.75)',rayColor:'rgba(255,215,0,0.85)',rayCount:24,partCount:50,vortexColor:'rgba(255,200,0,',bgFrom:'#f0e0a0',bgTo:'#f8f0c0',flashColor:'rgba(255,240,180,0.9)',backGrad:['#f0dca0','#f8f0c0'],backBorder:'rgba(192,160,64,0.8)',frontGrad:['#f8f0d0','#fffae8'],frontBorder:'rgba(192,160,64,0.9)',frontBg:'rgba(192,160,64,0.1)',revealDelay:800},
  card_pyro:      {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',emoji:'рџ”Ґ',stars:'в…в…в…в…',starsColor:'#c39ef5',pool:'purple',backCn:'з„°',petals:['рџЊё','вњ¦','рџ’њ','вњї'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fox:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',emoji:'рџ¦Љ',stars:'в…в…в…в…',starsColor:'#c39ef5',pool:'purple',backCn:'з‹ђ',petals:['вњ¦','рџ’њ','вњї','в—€'],petalColor:'rgba(195,158,245,0.7)',rayColor:'rgba(195,158,245,0.8)',rayCount:16,partCount:30,vortexColor:'rgba(155,89,182,',bgFrom:'#d8c0f0',bgTo:'#e8d0f8',flashColor:'rgba(220,200,255,0.7)',backGrad:['#c8b0e8','#dcc8f5'],backBorder:'rgba(155,89,182,0.7)',frontGrad:['#ecdcf8','#f5eeff'],frontBorder:'rgba(155,89,182,0.8)',frontBg:'rgba(155,89,182,0.08)',revealDelay:1000},
  card_fairy:     {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',emoji:'рџЊё',stars:'в…в…в…в…',starsColor:'#4a9af5',pool:'blue',backCn:'жЎѓ',petals:['рџЊё','вњ¦','рџ’§','вќЂ'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_literature:{img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',emoji:'рџ“њ',stars:'в…в…в…в…',starsColor:'#4a9af5',pool:'blue',backCn:'ж–‡',petals:['рџ“њ','вњ¦','вќЂ','вњї'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_forest:    {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',emoji:'рџЊї',stars:'в…в…в…в…',starsColor:'#4a9af5',pool:'blue',backCn:'жњЁ',petals:['рџЊї','вњ¦','рџЌѓ','вќЂ'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_sea:       {img:'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',emoji:'рџЊЉ',stars:'в…в…в…в…',starsColor:'#4a9af5',pool:'blue',backCn:'жµ·',petals:['рџЊЉ','вњ¦','рџ’§','в—€'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
  card_moon:      {emoji:'рџЊ™',stars:'в…в…в…в…',starsColor:'#4a9af5',pool:'blue',backCn:'жњ€',petals:['рџЊ™','вњ¦','в­ђ','вњї'],petalColor:'rgba(74,122,204,0.65)',rayColor:'rgba(74,122,204,0.75)',rayCount:12,partCount:20,vortexColor:'rgba(74,122,204,',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.6)',backGrad:['#c0d5f0','#dce8f8'],backBorder:'rgba(74,122,204,0.6)',frontGrad:['#dceef8','#eef5fc'],frontBorder:'rgba(74,122,204,0.7)',frontBg:'rgba(74,122,204,0.08)',revealDelay:1200},
};
// РџСЂРёР·С‹ РЅРµ-РєР°СЂС‚РѕС‡РєРё
const GS_PRIZE_CONFIGS = {
  points: {emoji:'вњ¦',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:15,petalColor:'rgba(219,177,101,0.7)',petals:['вњ¦','в…'],revealDelay:1200},
  immunity:{emoji:'рџ›Ў',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(74,122,204,0.6)',petals:['рџ›Ў','вњ¦'],revealDelay:1200},
  walk:    {emoji:'рџЏ®',pool:'blue',bgFrom:'#c8dff5',bgTo:'#d8e8f5',flashColor:'rgba(200,220,255,0.5)',rayColor:null,partCount:12,petalColor:'rgba(219,177,101,0.6)',petals:['рџЏ®','вњ¦'],revealDelay:1200},
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
    <text x="75" y="120" font-size="34" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" opacity="0.75">${c.backCn||'зџҐ'}</text>
    <text x="75" y="168" font-size="9" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" text-anchor="middle" letter-spacing="3" opacity="0.6">вњ¦ зҐ€ж„ї вњ¦</text>
    <text x="24" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">йѕ™</text>
    <text x="118" y="44" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">жњ€</text>
    <text x="24" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">иЉ±</text>
    <text x="118" y="184" font-size="16" fill="${c.petalColor||'rgba(74,122,204,0.5)'}" font-family="serif" opacity="0.45">жџ</text>
  </svg>`;
  const front = document.getElementById('gsCardFront');
  front.style.background = `linear-gradient(180deg,${c.frontGrad?c.frontGrad[0]:'#dceef8'},${c.frontGrad?c.frontGrad[1]:'#eef5fc'})`;
  front.style.border = `2px solid ${c.frontBorder||'rgba(74,122,204,0.7)'}`;
  front.innerHTML = `
    <div style="flex:1;width:100%;display:flex;align-items:center;justify-content:center;position:relative;">
      <div style="position:absolute;inset:4px;border-radius:10px;background:${c.frontBg||'rgba(74,122,204,0.08)'};border:1px solid ${(c.frontBorder||'rgba(74,122,204,0.7)').replace(/[\d.]+\)$/,'0.2)')}"></div>
      ${(c.img) ? `<img src="${c.img}" style="width:110px;height:130px;object-fit:contain;position:relative;z-index:2;border-radius:8px;">` : `<div style="font-size:58px;position:relative;z-index:2;filter:drop-shadow(0 4px 10px ${c.petalColor||'rgba(74,122,204,0.5)'})">${c.emoji||'вњ¦'}</div>`}
    </div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:3px;padding-bottom:2px;">
      <div style="font-size:10px;font-weight:700;color:#2a2040;font-family:serif;letter-spacing:1px;text-align:center;">${cardInfo?cardInfo.name:''}</div>
      <div style="font-size:12px;color:${c.starsColor||'#4a9af5'};letter-spacing:3px;">${c.stars||'в…в…в…в…'}</div>
      <div style="font-size:7px;color:rgba(42,32,64,0.6);text-align:center;line-height:1.4;padding:0 4px;font-family:serif;">${cardInfo?cardInfo.passive:''}</div>
    </div>`;
}

async function openGenshinCase() {
  if (gsAnimating) return;
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
  // РџСЂРѕРІРµСЂСЏРµРј Р·Р°РјРѕСЂРѕР·РєСѓ
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('в›” РђРєРєР°СѓРЅС‚ Р·Р°РјРѕСЂРѕР¶РµРЅ. РњРѕР»РёС‚РІС‹ РЅРµРґРѕСЃС‚СѓРїРЅС‹.'); return; }
  } catch(e) {}
  const btn = document.getElementById('genshinOpenBtn');
  btn.disabled = true; btn.textContent = 'вњ¦ РњРѕР»РёС‚РІР° СЃРѕРІРµСЂС€Р°РµС‚СЃСЏ... вњ¦';
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
      if (data.detail==='Only for girls') tg.showAlert('РњРѕР»РёС‚РІС‹ РґРѕСЃС‚СѓРїРЅС‹ С‚РѕР»СЊРєРѕ РґРµРІРѕС‡РєР°Рј рџЊё');
      else if (data.detail==='Not enough points') tg.showAlert('РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ вњ¦! РќСѓР¶РЅРѕ РјРёРЅРёРјСѓРј 80');
      else if (data.detail==='Daily limit reached') tg.showAlert('Р›РёРјРёС‚ РјРѕР»РёС‚РІ РЅР° СЃРµРіРѕРґРЅСЏ РёСЃС‡РµСЂРїР°РЅ');
      else tg.showAlert('РћС€РёР±РєР°: ' + (data.detail||''));
      gsAnimating = false; btn.disabled=false; btn.textContent='вњ¦ РЎРѕРІРµСЂС€РёС‚СЊ РјРѕР»РёС‚РІСѓ вЂ” 50 вњ¦ вњ¦';
      currentPoints = data.new_points || currentPoints;
      updatePoints();
      return;
    }

    currentPoints = data.new_points; updatePoints();
    curGsCardId = data.card_id || null;
    const cfg = GS_CARD_CONFIGS[data.card_id] || GS_PRIZE_CONFIGS[data.type] || GS_PRIZE_CONFIGS.points;

    // Р¤РѕРЅ
    document.getElementById('gsBgLayer').style.background = gsGetThemeBg(cfg);

    // РЎС‚СЂРѕРёРј РєР°СЂС‚РѕС‡РєСѓ (РїРµСЂРµРІС‘СЂРЅСѓС‚Р°СЏ СЂСѓР±Р°С€РєРѕР№)
    gsBuildCard(data.card_id, {name: data.name||'', passive: data.passive||''});

    // РЁРђР“ 1: Р’РёС…СЂСЊ
    gsRunVortex(cfg);
    gsRunParticles(cfg);

    // РЁРђР“ 2: Р’СЃРїС‹С€РєР° + Р»СѓС‡Рё + РєР°СЂС‚РѕС‡РєР°
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
        btn.disabled=false; btn.textContent='вњ¦ РЎРѕРІРµСЂС€РёС‚СЊ РјРѕР»РёС‚РІСѓ вЂ” 50 вњ¦ вњ¦';
      }, 700);
    }, cfg.revealDelay);

    // РџРѕРґРіРѕС‚Р°РІР»РёРІР°РµРј РёРЅС„Рѕ
    document.getElementById('gsResStars').textContent = cfg.stars || 'в…в…в…в…';
    document.getElementById('gsResStars').style.color = cfg.starsColor || '#4a9af5';
    document.getElementById('gsResName').textContent = data.name || '';
    document.getElementById('gsResPassive').textContent = data.passive || (data.amount ? `+${data.amount}в… РЅР°С‡РёСЃР»РµРЅРѕ` : '');

    if (data.rarity === 5) { setTimeout(() => launchConfetti(80), cfg.revealDelay + 400); }

  } catch(e) {
    tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ');
    gsAnimating=false; btn.disabled=false; btn.textContent='вњ¦ РЎРѕРІРµСЂС€РёС‚СЊ РјРѕР»РёС‚РІСѓ вЂ” 50 вњ¦ вњ¦';
  }
}

// РљР»РёРє РїРѕ СЌРєСЂР°РЅСѓ РјРѕР»РёС‚РІС‹ вЂ” РїРµСЂРµРІРѕСЂР°С‡РёРІР°РµС‚ РєР°СЂС‚РѕС‡РєСѓ
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

// РџРµСЂРµРєР»СЋС‡Р°С‚РµР»СЊ С‚Р°Р±РѕРІ РёРјРїР»Р°РЅС‚С‹/РєР°СЂС‚РѕС‡РєРё
function switchImplantsTab(tab) {
  document.getElementById('implants-tab').style.display = tab === 'implants' ? 'block' : 'none';
  document.getElementById('cards-tab').style.display = tab === 'cards' ? 'block' : 'none';
  document.getElementById('tab-implants-btn').classList.toggle('active', tab === 'implants');
  document.getElementById('tab-cards-btn').classList.toggle('active', tab === 'cards');
  if (tab === 'cards') loadCards(currentUserId);
}

const GENSHIN_EMOJIS = {
  'card_zhongli':'рџЄЁ','card_pyro':'рџ”Ґ','card_fox':'рџ¦Љ',
  'card_fairy':'рџЊё','card_literature':'рџ“њ','card_forest':'рџЊї',
  'card_sea':'рџЊЉ','card_star':'в­ђ','card_moon':'рџЊ™'
};

const GENSHIN_IMGS = {
  'card_zhongli':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_zhongli.png',
  'card_pyro':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_pyro.png',
  'card_fox':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fox.png',
  'card_fairy':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_fairy.png',
  'card_literature':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_literature.png',
  'card_forest':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_forest.png',
  'card_sea':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_sea.png',
  'card_star':'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/card_star.png',
};

async function loadCards(telegramId) {
  if (!telegramId) {
    const container = document.getElementById('myCardsContent');
    if (container) container.innerHTML = '<div class="empty-state">РљР°СЂС‚РѕС‡РµРє РїРѕРєР° РЅРµС‚<br><span style="font-size:10px;font-family:serif;color:var(--text3);">РЎРѕРІРµСЂС€Рё РјРѕР»РёС‚РІСѓ РІРѕ РІРєР»Р°РґРєРµ РљРµР№СЃС‹!</span></div>';
    return;
  }
  const container = document.getElementById('myCardsContent');
  if (!container) return;
  try {
    const r = await fetch(`${API_URL}/api/cards/${telegramId}`);
    if (!r.ok) { container.innerHTML = '<div class="empty-state">РљР°СЂС‚РѕС‡РµРє РїРѕРєР° РЅРµС‚</div>'; return; }
    const data = await r.json();
    if (!data.length) {
      container.innerHTML = '<div class="empty-state">РљР°СЂС‚РѕС‡РµРє РїРѕРєР° РЅРµС‚<br><span style="font-size:10px;font-family:serif;color:var(--text3);">РЎРѕРІРµСЂС€Рё РјРѕР»РёС‚РІСѓ РІРѕ РІРєР»Р°РґРєРµ РљРµР№СЃС‹!</span></div>';
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
      const stars = 'в…'.repeat(rarity);
      const emoji = GENSHIN_EMOJIS[card.card_id] || 'вњЁ';
      const imgSrc = GENSHIN_IMGS[card.card_id];
      const cardPassive = card.passive || '';
      const cardVisual = imgSrc
        ? `<img src="${imgSrc}" style="width:50px;height:60px;object-fit:contain;border-radius:8px;border:1px solid ${rarityColor}44;">`
        : `<div style="font-size:28px;">${emoji}</div>`;
      const dots = Array(3).fill(0).map((_,i) =>
        `<div style="width:8px;height:8px;border-radius:50%;background:${i < card.durability ? rarityColor : 'rgba(255,255,255,0.1)'};"></div>`
      ).join('');
      const disassembleBtn = isSecond
        ? `<button onclick="disassembleCard(${card.id})" style="margin-top:8px;width:100%;padding:6px;background:rgba(219,177,101,0.08);border:1px solid rgba(219,177,101,0.25);color:var(--gold);border-radius:16px;font-size:9px;font-family:serif;cursor:pointer;">вњ¦ [ Р РђР—РћР‘Р РђРўР¬ +50 вњ¦ ]</button>`
        : '';
      return `<div style="background:var(--bg2);border:1px solid ${isDup ? 'rgba(219,177,101,0.3)' : 'var(--border)'};border-radius:12px;padding:12px;margin-bottom:8px;position:relative;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:50px;height:60px;background:var(--bg3);border:1px solid ${rarityColor}33;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">${cardVisual}</div>
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <div style="font-size:12px;font-weight:700;color:var(--text);font-family:serif;">${card.name}</div>
              ${isDup ? `<span style="font-size:7px;background:rgba(219,177,101,0.15);border:1px solid rgba(219,177,101,0.3);color:var(--gold);padding:1px 6px;border-radius:10px;font-family:monospace;">Р”РЈР‘Р›Р¬</span>` : ''}
            </div>
            <div style="font-size:10px;color:${rarityColor};margin-top:2px;">${stars}</div>
            <div style="font-size:9px;color:var(--text2);font-family:serif;margin-top:3px;">${cardPassive}</div>
          </div>
          <div style="display:flex;gap:3px;">${dots}</div>
        </div>
        ${disassembleBtn}
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

async function disassembleCard(id) {
  tg.showPopup({
    title: 'вњ¦ Р Р°Р·РѕР±СЂР°С‚СЊ РєР°СЂС‚РѕС‡РєСѓ?',
    message: 'РўС‹ РїРѕР»СѓС‡РёС€СЊ +50 вњ¦ Р·Р° РґСѓР±Р»СЊ. РљР°СЂС‚РѕС‡РєР° Р±СѓРґРµС‚ СѓРЅРёС‡С‚РѕР¶РµРЅР°.',
    buttons: [{id:'confirm', type:'default', text:'вњ¦ Р Р°Р·РѕР±СЂР°С‚СЊ +50 вњ¦'}, {type:'cancel'}]
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
        tg.showAlert(`вњ¦ Р Р°Р·РѕР±СЂР°РЅРѕ! +50 вњ¦\nР‘Р°Р»Р°РЅСЃ: ${data.new_points} вњ¦`);
        loadCards(currentUserId);
      } else tg.showAlert('РћС€РёР±РєР° СЂР°Р·Р±РѕСЂРєРё');
    } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
  });
}

async function loadShop() {
  try {
    const settingsR = await fetch(`${API_URL}/api/settings`);
    if (!settingsR.ok) throw new Error('settings');
    const settings = await settingsR.json();
    if (settings.blackwall && !isAdmin) {
      document.getElementById('shopStoreContent').innerHTML =
        '<div class="blackwall-screen"><div class="blackwall-title">BlackWall е·ІжїЂжґ»</div><div style="font-size:11px;color:#555;font-family:monospace;line-height:1.8;">зі»з»џи®їй—®е·ІеЏ—й™ђ<br>вЂ” NetWatch зЅ‘з»њдїќе®‰ вЂ”</div></div>';
      return;
    }
    const r = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId||0}`);
    if (!r.ok) throw new Error('shop');
    const data = await r.json();
    document.getElementById('shopPoints').textContent = currentPoints + ' в…';
    if (data.frozen) document.getElementById('shopFrozenBanner').style.display = 'block';
    const catInfo = {
      'privilege': { name:'з‰№жќѓ РџР РР’РР›Р•Р“РР', cn:'рџЏ®' },
      'points':    { name:'з§Їе€† Р‘РђР›Р›Р«', cn:'в­ђ' },
      'social':    { name:'з¤ѕдє¤ РЎРћР¦РРђР›Р¬РќРћР•', cn:'рџ¤ќ' },
      'food':      { name:'йЈџз‰© Р•Р”Рђ', cn:'рџЌњ' },
      'vip':       { name:'VIP иґµе®ѕ', cn:'рџ‘‘' },
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
        const limitText = item.daily_limit > 0 ? `РћСЃС‚Р°Р»РѕСЃСЊ: ${item.daily_limit - item.sold_today} РёР· ${item.daily_limit}` : 'Р‘РµР· РѕРіСЂР°РЅРёС‡РµРЅРёР№';
        html += `<div class="shop-item ${!item.available?'unavailable':''}">
          <div class="shop-item-icon">${SHOP_ICONS[item.code] || item.icon}</div>
          <div style="flex:1;">
            <div class="shop-item-name">${item.name}</div>
            <div class="shop-item-cn">${item.description}</div>
            <div class="shop-item-limit">${limitText}</div>
          </div>
          <button class="shop-item-buy" onclick="buyItem('${item.code}','${item.name}',${item.price})" ${!canBuy?'disabled':''}>${item.price} в…</button>
        </div>`;
      });
    }
    document.getElementById('shopStoreContent').innerHTML = html || '<div class="empty-state">РњР°РіР°Р·РёРЅ РїСѓСЃС‚</div>';
  } catch(e) { document.getElementById('shopStoreContent').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

async function buyItem(code, name, price) {
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
  tg.showPopup({
    title: `РљСѓРїРёС‚СЊ ${name}?`,
    message: `РЎС‚РѕРёРјРѕСЃС‚СЊ: ${price} в…\nРўРІРѕР№ Р±Р°Р»Р°РЅСЃ: ${currentPoints} в…`,
    buttons: [{id:'confirm',type:'default',text:'вњ… РљСѓРїРёС‚СЊ'},{type:'cancel'}]
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
        tg.showAlert(`вњ… РљСѓРїР»РµРЅРѕ: ${data.item}!\nРћСЃС‚Р°С‚РѕРє: ${data.new_points} в…`);
        loadShop();
      } else {
        const err = await r.json();
        if (err.detail === 'Daily limit reached') tg.showAlert('Р­С‚РѕС‚ С‚РѕРІР°СЂ СѓР¶Рµ СЂР°Р·РѕР±СЂР°Р»Рё!');
        else if (err.detail === 'Not enough points') tg.showAlert('РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ!');
        else if (err.detail === 'Account frozen') tg.showAlert('в›” РђРєРєР°СѓРЅС‚ РїРѕРґ РЅР°РґР·РѕСЂРѕРј NetWatch');
        else tg.showAlert('РћС€РёР±РєР° РїРѕРєСѓРїРєРё');
      }
    } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
  });
}

async function loadInventory() {
  try {
    const r = await fetch(`${API_URL}/api/shop/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('shopInventoryContent');
    const digital = ['extra_case','extra_raid_attempt','double_win','title_player','immunity','raid_insurance','raid_beacon','raid_overclock'];
    const physical = data.filter(item => !digital.includes(item.code));
    if (!physical.length) { container.innerHTML = '<div class="empty-state">РРЅРІРµРЅС‚Р°СЂСЊ РїСѓСЃС‚<br>РљСѓРїРё С‡С‚Рѕ-РЅРёР±СѓРґСЊ РІ РјР°РіР°Р·РёРЅРµ!</div>'; return; }
    container.innerHTML = physical.map(item =>
      `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div><div class="inventory-name">${item.name}</div><div class="inventory-date">${new Date(item.purchased_at).toLocaleDateString('ru-RU')} В· ID: ${item.id}</div></div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useItem(${item.id},'${item.name}')">вњ… РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ</button>
          <button class="inv-btn inv-btn-gift" onclick="giftItem(${item.id},'${item.name}')">рџЋЃ РџРѕРґР°СЂРёС‚СЊ</button>
          <button class="inv-btn inv-btn-sell" onclick="sellItem(${item.id},'${item.name}',${item.price})">рџ’° РџСЂРѕРґР°С‚СЊ</button>
        </div>
      </div>`
    ).join('');
  } catch(e) { document.getElementById('shopInventoryContent').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

function useItem(id, name) {
  tg.showPopup({
    title: `РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ ${name}?`,
    message: 'РџРѕРєР°Р¶Рё СЌС‚РѕС‚ СЌРєСЂР°РЅ РІРѕР¶Р°С‚РѕРјСѓ. РџРѕСЃР»Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ С‚РѕРІР°СЂ СЃРїРёС€РµС‚СЃСЏ.',
    buttons: [{id:'confirm', type:'default', text:'вњ… РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ'}, {type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/use/${id}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({telegram_id: currentUserId})
      });
      if (r.ok) {
        try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
        tg.showAlert(`вњ… ${name} РёСЃРїРѕР»СЊР·РѕРІР°РЅ!\nРџРѕРєР°Р¶Рё СЌС‚Рѕ СЃРѕРѕР±С‰РµРЅРёРµ РІРѕР¶Р°С‚РѕРјСѓ.`);
        loadInventory();
      } else {
        tg.showAlert('РћС€РёР±РєР° РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ');
      }
    } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
  });
}
function giftItem(id, name) { tg.showPopup({title:`РџРѕРґР°СЂРёС‚СЊ ${name}?`,message:'Р’РІРµРґРё РёРјСЏ РїРѕР»СѓС‡Р°С‚РµР»СЏ РІ С‡Р°С‚Рµ Р±РѕС‚Р° РєРѕРјР°РЅРґРѕР№ /РїРѕРґР°СЂРёС‚СЊ РРњРЇ\n\nРќР°Р»РѕРі РЅР° РґР°СЂРµРЅРёРµ: 20 Р±Р°Р»Р»РѕРІ',buttons:[{type:'ok'}]}); }

async function sellItem(id, name, price) {
  const refund = Math.floor(price / 2);
  tg.showPopup({
    title:`РџСЂРѕРґР°С‚СЊ ${name}?`,
    message:`РўС‹ РїРѕР»СѓС‡РёС€СЊ ${refund} в… (50% РѕС‚ СЃС‚РѕРёРјРѕСЃС‚Рё ${price} в…)`,
    buttons:[{id:'confirm',type:'destructive',text:`рџ’° РџСЂРѕРґР°С‚СЊ Р·Р° ${refund} в…`},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/shop/sell`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purchase_id:id,telegram_id:currentUserId})});
      if (r.ok) { const data=await r.json(); currentPoints=data.new_points; updatePoints(); tg.showAlert(`вњ… РџСЂРѕРґР°РЅРѕ! +${data.refund} в…`); loadInventory(); }
    } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
  });
}

async function resetShop() {
  try {
    const r = await fetch(`${API_URL}/api/admin/reset_shop`,{method:'POST',headers:{'x-admin-id':currentUserId}});
    if (r.ok) tg.showAlert('вњ… РњР°РіР°Р·РёРЅ СЃР±СЂРѕС€РµРЅ!');
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

// ===== РљРђР—РРќРћ =====
function switchCasinoTab(mode, btn) {
  loadPoints(currentUserId);
  document.querySelectorAll('#page-casino .subtab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const ids = ['casinoPlayContent','casinoInventoryContent','casinoHistoryContent','casinoRulesContent','casinoGenshinContent'];
  ids.forEach(id => { const el=document.getElementById(id); if(el) el.style.display='none'; });
  if (mode==='play') { document.getElementById('casinoPlayContent').style.display='flex'; setTimeout(initRoulette,50); }
  else if (mode==='inventory') { document.getElementById('casinoInventoryContent').style.display='flex'; loadCasinoInventory(); }
  else if (mode==='history') { document.getElementById('casinoHistoryContent').style.display='flex'; loadCasinoHistory(); }
  else if (mode==='rules') { document.getElementById('casinoRulesContent').style.display='flex'; }
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
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
  if (currentPoints < 80) { tg.showAlert('РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ! РќСѓР¶РЅРѕ РјРёРЅРёРјСѓРј 80 в…'); return; }
  // РџСЂРѕРІРµСЂСЏРµРј Р·Р°РјРѕСЂРѕР·РєСѓ
  try {
    const fr = await fetch(`${API_URL}/api/shop?telegram_id=${currentUserId}`);
    const fd = await fr.json();
    if (fd.frozen && !isAdmin) { tg.showAlert('в›” РђРєРєР°СѓРЅС‚ Р·Р°РјРѕСЂРѕР¶РµРЅ. РљРµР№СЃС‹ РЅРµРґРѕСЃС‚СѓРїРЅС‹.'); return; }
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
      if (err.detail==='Daily limit reached') tg.showAlert('Р›РёРјРёС‚ 3 РєРµР№СЃР° РІ РґРµРЅСЊ! РљСѓРїРё РґРѕРї РєРµР№СЃ РІ РјР°РіР°Р·РёРЅРµ рџ„');
      else if (err.detail==='Not enough points') tg.showAlert('РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ!');
      else tg.showAlert('РћС€РёР±РєР°!');
      isSpinning = false;
      document.getElementById('openCaseBtn').disabled = false;
      return;
    }
    const data = await r.json();
    const caseType = data.prize.case_type || 'gold';
    initRoulette(caseType);
    isSpinning = true;
    document.getElementById('openCaseBtn').disabled = true;
    const prize = PRIZE_MAP[data.prize.code] || { code:data.prize.code, icon:data.prize.icon||'рџЋЃ', name:data.prize.name, desc:'Р РµРґРєРёР№ РїСЂРёР·!', points:data.prize.points||0 };
    await spinRoulette(prize, caseType);
    showPrizeResult(prize, caseType);
    currentPoints = data.new_points;
    updatePoints();
    // РћР±РЅРѕРІР»СЏРµРј РєРЅРѕРїРєСѓ РїРѕСЃР»Рµ РѕС‚РєСЂС‹С‚РёСЏ
    const casBtn = document.getElementById('openCaseBtn');
    if (data.remaining_today !== undefined && data.remaining_today <= 0) {
      casBtn.disabled = true;
      casBtn.style.background = 'rgba(255,255,255,0.05)';
      casBtn.style.borderColor = 'rgba(255,255,255,0.08)';
      casBtn.style.color = 'rgba(255,255,255,0.2)';
      casBtn.textContent = '[ РџРѕРїС‹С‚РєРё РёСЃС‡РµСЂРїР°РЅС‹ // РџСЂРёС…РѕРґРёС‚Рµ Р·Р°РІС‚СЂР° ]';
    } else {
      casBtn.disabled = false;
      casBtn.style.background = '';
      casBtn.style.borderColor = '';
      casBtn.style.color = '';
      casBtn.textContent = 'рџЏ® [ ејЂз®± // РћРўРљР Р«РўР¬ РљР•Р™РЎ вЂ” 50 в… ] рџЏ®';
    }
    if (prize.code==='jackpot'||prize.code==='implant_red_dragon') { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(100); }
    else if (prize.code.startsWith('implant_')) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(50); }
    else if (prize.points > 50) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} launchConfetti(30); }
    else if (prize.code==='empty') try{tg.HapticFeedback.notificationOccurred('error');}catch(e){}
    else try{tg.HapticFeedback.impactOccurred('medium');}catch(e){}
    
    if (prize.code.startsWith('implant_')) loadImplants(currentUserId);
  } catch(e) {
    tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ');
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

  // РЎРѕР·РґР°С‘Рј РѕРІРµСЂР»РµР№
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
  const tagText = isLegendary ? 'в… Р›Р•Р“Р•РќР”РђР РќР«Р™ в…' : isPurple ? 'Р Р•Р”РљРР™ // Р¤РРћР›Р•РўРћР’Р«Р™' : 'РћР‘Р«Р§РќР«Р™';

  let imgHtml = prize.img
    ? `<img src="${prize.img}" style="width:110px;height:110px;object-fit:contain;filter:drop-shadow(0 0 20px ${glowColor});animation:cyberPulse 2s ease-in-out infinite;">`
    : `<div style="font-size:72px;filter:drop-shadow(0 0 16px ${glowColor});">${prize.icon}</div>`;

  let contentHtml = '';
  if (prize.points > 0) {
    contentHtml = `<div style="font-size:36px;font-weight:900;font-family:monospace;color:${particleColor};text-shadow:0 0 20px ${particleColor};animation:fadeUpAnim 0.4s ease-out 0.5s both;">+${prize.points}в…</div>`;
  } else {
    contentHtml = `<div style="font-size:14px;font-weight:700;color:#fff;font-family:monospace;letter-spacing:1px;text-align:center;animation:fadeUpAnim 0.3s ease-out 0.7s both;">${prize.name}</div>`;
  }

  // Р›СѓС‡Рё
  let raysHtml = '';
  if (rayColor) {
    const count = isLegendary ? 24 : 16;
    for (let i = 0; i < count; i++) {
      raysHtml += `<div style="position:absolute;width:3px;height:${isLegendary?170:150}px;border-radius:2px;background:linear-gradient(0deg,${rayColor},transparent);transform:rotate(${i*(360/count)}deg) translateX(-50%);transform-origin:bottom;left:50%;top:calc(50% - ${isLegendary?170:150}px);margin-left:-1.5px;animation:cyberRayIn 0.4s ease-out ${i*0.015}s both;opacity:0;"></div>`;
    }
  }

  // Р§Р°СЃС‚РёС†С‹
  let partsHtml = '';
  const count = isLegendary ? 40 : isPurple ? 25 : 15;
  const symbols = isLegendary ? ['йѕ™','в…','з¦Џ','вњ¦'] : isPurple ? ['вњ¦','в…','в—€'] : ['в…','вњ¦'];
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
    <div style="position:absolute;bottom:24px;font-size:9px;color:rgba(255,255,255,0.25);font-family:monospace;letter-spacing:2px;animation:cyberBlink 2s ease-in-out 1.2s infinite;">РЅР°Р¶РјРё С‡С‚РѕР±С‹ РїСЂРѕРґРѕР»Р¶РёС‚СЊ в–ј</div>`;
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
    title: 'вљ™пёЏ Р Р°Р·РѕР±СЂР°С‚СЊ РёРјРїР»Р°РЅС‚?',
    message: 'РўС‹ РїРѕР»СѓС‡РёС€СЊ +100 в… Р·Р° СЂР°Р·Р±РѕСЂРєСѓ РґСѓР±Р»СЏ. РРјРїР»Р°РЅС‚ Р±СѓРґРµС‚ СѓРЅРёС‡С‚РѕР¶РµРЅ.',
    buttons: [{id:'confirm', type:'default', text:'вљ™пёЏ Р Р°Р·РѕР±СЂР°С‚СЊ +100 в…'}, {type:'cancel'}]
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
        tg.showAlert(`вњ… Р Р°Р·РѕР±СЂР°РЅРѕ! +100 в…\nР‘Р°Р»Р°РЅСЃ: ${data.new_points} в…`);
        loadImplants(currentUserId);
      } else {
        const err = await r.json();
        if (err.detail === 'Not a duplicate') tg.showAlert('Р­С‚Рѕ РЅРµ РґСѓР±Р»СЊ вЂ” РЅРµР»СЊР·СЏ СЂР°Р·РѕР±СЂР°С‚СЊ!');
        else tg.showAlert('РћС€РёР±РєР° СЂР°Р·Р±РѕСЂРєРё');
      }
    } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
  });
}

async function loadCasinoInventory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/inventory/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoInventoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">РџСЂРёР·РѕРІ РїРѕРєР° РЅРµС‚<br>РћС‚РєСЂС‹РІР°Р№ РєРµР№СЃС‹!</div>'; return; }
    container.innerHTML = data.map(item => {
      const expires = item.expires_at ? `<div style="color:#cc4444;font-size:10px;margin-top:3px;">вЏ° Р”Рѕ ${item.expires_at.slice(11,16)}</div>` : '';
      return `<div class="inventory-item">
        <div class="inventory-header">
          <div class="inventory-icon">${item.icon}</div>
          <div><div class="inventory-name">${item.name}</div><div class="inventory-date">${item.desc}</div>${expires}</div>
        </div>
        <div class="inventory-actions">
          <button class="inv-btn inv-btn-use" onclick="useCasinoPrize(${item.id},'${item.name}')">вњ… РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ</button>
        </div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoInventoryList').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

async function useCasinoPrize(id, name) {
  tg.showPopup({
    title:`РСЃРїРѕР»СЊР·РѕРІР°С‚СЊ ${name}?`, message:'РџРѕРєР°Р¶Рё СЌС‚РѕС‚ СЌРєСЂР°РЅ РІРѕР¶Р°С‚РѕРјСѓ РґР»СЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ.',
    buttons:[{id:'confirm',type:'default',text:'вњ… РџРѕРєР°Р·Р°С‚СЊ РІРѕР¶Р°С‚РѕРјСѓ'},{type:'cancel'}]
  }, async (btnId) => {
    if (btnId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/casino/use/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
      if (r.ok) { tg.showAlert('вњ… РџСЂРёР· РёСЃРїРѕР»СЊР·РѕРІР°РЅ!'); loadCasinoInventory(); }
      else { const err=await r.json(); tg.showAlert(err.detail==='Prize expired'?'вЏ° РџСЂРёР· РёСЃС‚С‘Рє!':'РћС€РёР±РєР°'); }
    } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
  });
}

async function loadCasinoHistory() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/casino/history/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('casinoHistoryList');
    if (!data.length) { container.innerHTML = '<div class="empty-state">РСЃС‚РѕСЂРёСЏ РїСѓСЃС‚Р°<br>РћС‚РєСЂРѕР№ РїРµСЂРІС‹Р№ РєРµР№СЃ!</div>'; return; }
    container.innerHTML = data.map(item => {
      const date = new Date(item.created_at).toLocaleDateString('ru-RU');
      const time = item.created_at.slice(11,16);
      return `<div class="schedule-item">
        <div style="font-size:24px;min-width:35px;text-align:center;">${item.icon}</div>
        <div class="schedule-info"><div class="schedule-subject">${item.name}</div><div class="schedule-location">${date} РІ ${time}</div></div>
      </div>`;
    }).join('');
  } catch(e) { document.getElementById('casinoHistoryList').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

// ===== РџРћР“РћР”Рђ =====
async function loadWeather() {
  try {
    const r = await fetch(`https://api.openweathermap.org/data/2.5/weather?id=1816670&appid=${WEATHER_KEY}&units=metric&lang=ru`);
    const data = await r.json();
    document.getElementById('weatherTemp').innerHTML = `${Math.round(data.main.temp)}<span>В°C</span>`;
    document.getElementById('weatherDesc').textContent = data.weather[0].description.charAt(0).toUpperCase() + data.weather[0].description.slice(1);
    document.getElementById('weatherHumidity').textContent = data.main.humidity;
    document.getElementById('weatherWind').textContent = data.wind.speed;
    document.getElementById('weatherFeels').textContent = Math.round(data.main.feels_like);
    document.getElementById('weatherIcon').textContent = getWeatherIcon(data.weather[0].id);
  } catch(e) { document.getElementById('weatherDesc').textContent = 'РќРµРґРѕСЃС‚СѓРїРЅРѕ'; }
}

async function loadYuanRate() {
  try {
    const r = await fetch('https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@2024-03-28/v1/currencies/cny.json');
    const data = await r.json();
    const rub = data.cny.rub;
    if (rub) {
      document.getElementById('yuanRate').innerHTML = `${rub.toFixed(2)}<span> в‚Ѕ</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    }
  } catch(e) {
    try {
      const r2 = await fetch('https://open.er-api.com/v6/latest/CNY');
      const data2 = await r2.json();
      document.getElementById('yuanRate').innerHTML = `${data2.rates.RUB.toFixed(2)}<span> в‚Ѕ</span>`;
      document.getElementById('rateUpdated').textContent = new Date().toLocaleDateString('ru-RU');
    } catch(e2) { document.getElementById('yuanRate').innerHTML = `вЂ”<span> в‚Ѕ</span>`; }
  }
}

function getWeatherIcon(id) {
  if (id >= 200 && id < 300) return 'в›€'; if (id >= 300 && id < 400) return 'рџЊ¦';
  if (id >= 500 && id < 600) return 'рџЊ§'; if (id >= 600 && id < 700) return 'вќ„пёЏ';
  if (id >= 700 && id < 800) return 'рџЊ«'; if (id === 800) return 'вЂпёЏ';
  if (id === 801) return 'рџЊ¤'; if (id === 802) return 'в›…'; return 'вЃпёЏ';
}

// ===== РЎРўРР РљРђ =====
function initLaundry() {
  // Р—Р°РіСЂСѓР·РєР° РїСЂРѕРёСЃС…РѕРґРёС‚ РїСЂРё РѕС‚РєСЂС‹С‚РёРё СЂР°Р·РґРµР»Р°, РЅРµ РїСЂРё СЃС‚Р°СЂС‚Рµ
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

async function loadLaundrySchedule() {
  const container = document.getElementById('laundryScheduleContent');
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) {
      container.innerHTML = `<div class="empty-state" style="padding:16px;">Р Р°СЃРїРёСЃР°РЅРёРµ СЃС‚РёСЂРєРё РµС‰С‘ РЅРµ СЃРѕСЃС‚Р°РІР»РµРЅРѕ<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Р’РѕР¶Р°С‚С‹Рµ СЃРєРѕСЂРѕ РґРѕР±Р°РІСЏС‚ СЃР»РѕС‚С‹</span></div>`;
      return;
    }
    container.innerHTML = data.map(slot => {
      const taken = slot.taken_by;
      const isMe = taken && taken.telegram_id === currentUserId;
      const isFree = !taken;
      let icon, statusText, clickable;
      if (isMe) {
        icon = `<i class="ti ti-circle-check" style="color:#2ecc71;font-size:18px;"></i>`;
        statusText = `<span style="color:#2ecc71;">Р’Р°С€Р° Р·Р°РїРёСЃСЊ</span>`;
        clickable = `onclick="cancelLaundrySlot(${slot.id})"`;
      } else if (isFree) {
        icon = `<i class="ti ti-circle-plus" style="color:var(--red);font-size:18px;"></i>`;
        statusText = `<span style="color:var(--red);">РЎРІРѕР±РѕРґРЅРѕ</span>`;
        clickable = `onclick="bookLaundrySlot(${slot.id})"`;
      } else {
        icon = `<i class="ti ti-circle-x" style="color:var(--text3);font-size:18px;"></i>`;
        statusText = `<span style="color:var(--text3);">Р—Р°РЅСЏС‚Рѕ</span>`;
        clickable = '';
      }
      return `<div ${clickable} style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);${clickable?'cursor:pointer;':''}">
        ${icon}
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.day} В· ${slot.time}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.note||'РњР°С€РёРЅРєР° СЃРІРѕР±РѕРґРЅР°'}</div>
        </div>
        <div style="font-size:10px;">${statusText}</div>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

async function loadWaterSchedule() {
  const container = document.getElementById('waterScheduleContent');
  try {
    const r = await fetch(`${API_URL}/api/water/schedule`);
    const data = r.ok ? await r.json() : [];
    if (!data.length) {
      container.innerHTML = `<div class="empty-state" style="padding:16px;">Р Р°СЃРїРёСЃР°РЅРёРµ РІРѕРґС‹ РµС‰С‘ РЅРµ СЃРѕСЃС‚Р°РІР»РµРЅРѕ<br><span style="font-size:10px;font-family:monospace;color:var(--text3);">Р’РѕР¶Р°С‚С‹Рµ СЃРєРѕСЂРѕ РґРѕР±Р°РІСЏС‚ СЃР»РѕС‚С‹</span></div>`;
      return;
    }
    container.innerHTML = data.map(slot => {
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);">
        <i class="ti ti-droplet" style="color:#60b4d4;font-size:18px;"></i>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.day} В· ${slot.time}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.note||'РќР°Р±РѕСЂ РІРѕРґС‹'}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

async function bookLaundrySlot(slotId) {
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule/${slotId}/book`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    if (r.ok) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} tg.showAlert('вњ… Р—Р°РїРёСЃР°РЅС‹ РЅР° СЃС‚РёСЂРєСѓ!'); loadLaundrySchedule(); }
    else { const e=await r.json(); tg.showAlert(e.detail==='Already booked'?'РЈ РІР°СЃ СѓР¶Рµ РµСЃС‚СЊ Р·Р°РїРёСЃСЊ':'РЎР»РѕС‚ Р·Р°РЅСЏС‚'); }
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

async function cancelLaundrySlot(slotId) {
  tg.showPopup({title:'РћС‚РјРµРЅРёС‚СЊ Р·Р°РїРёСЃСЊ?',message:'РЎР»РѕС‚ СЃРЅРѕРІР° СЃС‚Р°РЅРµС‚ СЃРІРѕР±РѕРґРЅС‹Рј.',buttons:[{id:'ok',type:'default',text:'РћС‚РјРµРЅРёС‚СЊ Р·Р°РїРёСЃСЊ'},{type:'cancel'}]},(b)=>{
    if(b!=='ok')return;
    fetch(`${API_URL}/api/laundry/schedule/${slotId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})})
      .then(()=>loadLaundrySchedule()).catch(()=>{});
  });
}

// РЎС‚Р°СЂС‹Рµ С„СѓРЅРєС†РёРё вЂ” РѕСЃС‚Р°РІР»СЏРµРј РґР»СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
async function loadLaundry() { loadLaundrySchedule(); }
function renderLaundrySlots() {}
async function bookLaundry(time) {}

async function cancelLaundry(id) {
  try {
    const r = await fetch(`${API_URL}/api/laundry/${id}`,{method:'DELETE',headers:{'x-telegram-id':currentUserId}});
    if (r.ok) { tg.showAlert('Р—Р°РїРёСЃСЊ РѕС‚РјРµРЅРµРЅР°'); loadLaundry(); }
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

// ===== РћР‘РЄРЇР’Р›Р•РќРРЇ =====
async function loadAnnouncements() {
  const containers = Array.from(document.querySelectorAll('.announcements-content'));
  const renderToAll = (html) => containers.forEach(container => { container.innerHTML = html; });
  try {
    const r = await fetch(`${API_URL}/api/announcements`);
    const data = await r.json();
    if (!data.length) {
      renderToAll('<div class="empty-state">РћР±СЉСЏРІР»РµРЅРёР№ РїРѕРєР° РЅРµС‚</div>');
      return;
    }

    const REACTIONS = ['рџ‘Ќ', 'вќ¤пёЏ', 'рџ”Ґ', 'рџ‚', 'рџ®', 'рџ‘‘'];

    // Р—Р°РіСЂСѓР¶Р°РµРј СЂРµР°РєС†РёРё РґР»СЏ РєР°Р¶РґРѕРіРѕ РѕР±СЉСЏРІР»РµРЅРёСЏ
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

      return `<div class="announcement-item">
        <div class="announcement-text">${item.text}</div>
        <div class="announcement-date">${new Date(item.created_at).toLocaleDateString('ru-RU')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:10px;">${reactionBtns}</div>
        ${isAdmin ? `<button onclick="deleteAnnouncement(${item.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-size:11px;margin-top:6px;font-family:monospace;">[ РЈР”РђР›РРўР¬ ]</button>` : ''}
      </div>`;
    }).join('');

    renderToAll(html);
    document.querySelectorAll('.admin-announce-form').forEach(form => {
      form.style.display = isAdmin ? 'block' : 'none';
    });
  } catch(e) {
    renderToAll('<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>');
  }
}

async function reactToAnnouncement(id, emoji, btn) {
  if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
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
  if (!text) { tg.showAlert('Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) {
      tg.showAlert('вњ… РћРїСѓР±Р»РёРєРѕРІР°РЅРѕ!');
      ['announceText', 'announceTextMore'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      loadAnnouncements();
    }
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

async function addAnnouncementAdmin() {
  const text = document.getElementById('announceTextAdmin').value;
  if (!text) { tg.showAlert('Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) { tg.showAlert('вњ… РћРїСѓР±Р»РёРєРѕРІР°РЅРѕ!'); document.getElementById('announceTextAdmin').value=''; loadAnnouncements(); }
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

async function deleteAnnouncement(id) {
  try { await fetch(`${API_URL}/api/announcements/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadAnnouncements(); } catch(e) {}
}

// ===== РђР§РР’РљР =====
async function loadAchievements() {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/achievements/${currentUserId}`);
    const data = await r.json();
    const container = document.getElementById('achievementsContent');
    const earned = data.filter(a => a.earned).length;
    let html = `<div class="achievement-count">// РџРѕР»СѓС‡РµРЅРѕ: <b style="color:var(--gold)">${earned}</b> РёР· ${data.length}</div><div class="achievements-grid">`;
    data.forEach(a => {
      const svgIcon = ACHIEVEMENT_ICONS[a.code] || `<svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="20" fill="rgba(212,175,55,0.3)"/></svg>`;
      html += `<div class="achievement-card ${a.earned?'':'locked'}" onclick="showAchievementInfo('${a.name}','${a.description}',${a.earned})">
        ${a.earned ? '<div class="achievement-earned-badge">вњЁ</div>' : ''}
        <div class="achievement-svg">${svgIcon}</div>
        <div class="achievement-name">${a.name}</div>
      </div>`;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch(e) { document.getElementById('achievementsContent').innerHTML = '<div class="empty-state">РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё</div>'; }
}

function showAchievementInfo(name, description, earned) {
  tg.showPopup({title:earned?'вњ… '+name:'рџ”’ '+name,message:description+(earned?'\n\nвњЁ РџРѕР»СѓС‡РµРЅРѕ!':'\n\nвќЊ Р•С‰С‘ РЅРµ РїРѕР»СѓС‡РµРЅРѕ'),buttons:[{type:'ok'}]});
}

// ===== РђРќРћРќРРњРќР«Р™ Р’РћРџР РћРЎ =====
function askAnonymous() { document.getElementById('questionModal').classList.add('show'); document.getElementById('questionText').value=''; }
function closeQuestion() { document.getElementById('questionModal').classList.remove('show'); }

async function submitQuestion() {
  const text = document.getElementById('questionText').value.trim();
  if (!text) { tg.showAlert('РќР°РїРёС€Рё РІРѕРїСЂРѕСЃ!'); return; }
  try {
    const r = await fetch(`${API_URL}/api/question`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,telegram_id:currentUserId})});
    if (r.ok) { closeQuestion(); tg.showAlert('вњ… Р’РѕРїСЂРѕСЃ РѕС‚РїСЂР°РІР»РµРЅ Р°РЅРѕРЅРёРјРЅРѕ!'); try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} }
    else tg.showAlert('РћС€РёР±РєР° РѕС‚РїСЂР°РІРєРё');
  } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
}

// ===== РђР”РњРРќ =====
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
    if (!data.length) { container.innerHTML = '<div class="empty-state">Р—Р°РїРёСЃРµР№ РЅРµС‚</div>'; return; }
    container.innerHTML = data.map(b => `
      <div class="schedule-item">
        <div class="schedule-info"><div class="schedule-subject">${b.username}</div><div class="schedule-location">${b.date} РІ ${b.time}</div></div>
        <button onclick="adminCancelLaundry(${b.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-family:monospace;font-size:10px;">вњ•</button>
      </div>`).join('');
  } catch(e) {}
}

async function adminCancelLaundry(id) {
  try { await fetch(`${API_URL}/api/laundry/${id}`,{method:'DELETE',headers:{'x-telegram-id':currentUserId}}); loadAdminLaundry(); loadLaundry(); } catch(e) {}
}

async function adminFreeze(freeze) {
  const telegramId = parseInt(document.getElementById('freezeId').value);
  if (!telegramId) { tg.showAlert('Р’РІРµРґРё Telegram ID РёРіСЂРѕРєР°'); return; }

  try {
    const r = await fetch(`${API_URL}/api/admin/freeze`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
      body: JSON.stringify({telegram_id: telegramId, frozen: freeze})
    });
    if (r.ok) {
      if (freeze) {
        // РћС‚РїСЂР°РІР»СЏРµРј СѓРІРµРґРѕРјР»РµРЅРёРµ С‡РµСЂРµР· Р±РѕС‚Р°
        await fetch(`https://api.telegram.org/bot8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc/sendMessage`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chat_id: telegramId,
            text: 'в›” NETWATCH зЅ‘з»њдїќе®‰\n\nзі»з»џжЈЂжµ‹е€°еј‚еёёжґ»еЉЁ\nРЎРёСЃС‚РµРјР° РѕР±РЅР°СЂСѓР¶РёР»Р° РїРѕРґРѕР·СЂРёС‚РµР»СЊРЅСѓСЋ Р°РєС‚РёРІРЅРѕСЃС‚СЊ СЃ РІР°С€РµР№ СЃС‚РѕСЂРѕРЅС‹.\n\nР’Р°С€ Р°РєРєР°СѓРЅС‚ РІСЂРµРјРµРЅРЅРѕ Р·Р°РјРѕСЂРѕР¶РµРЅ.\nРњР°РіР°Р·РёРЅ Рё РєРµР№СЃС‹ РЅРµРґРѕСЃС‚СѓРїРЅС‹.\n\nвЂ” NetWatch Protocol v1.4 вЂ”'
          })
        });
        tg.showAlert('в›” РђРєРєР°СѓРЅС‚ Р·Р°РјРѕСЂРѕР¶РµРЅ!\nРРіСЂРѕРє РїРѕР»СѓС‡РёР» СѓРІРµРґРѕРјР»РµРЅРёРµ РѕС‚ NetWatch.');
      } else {
        await fetch(`https://api.telegram.org/bot8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc/sendMessage`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chat_id: telegramId,
            text: 'вњ… NETWATCH зЅ‘з»њдїќе®‰\n\nи®їй—®е·ІжЃўе¤Ќ\nР”РѕСЃС‚СѓРї РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅ.\n\nР’Р°С€ Р°РєРєР°СѓРЅС‚ СЂР°Р·РјРѕСЂРѕР¶РµРЅ.\nРњР°РіР°Р·РёРЅ Рё РєРµР№СЃС‹ СЃРЅРѕРІР° РґРѕСЃС‚СѓРїРЅС‹.\n\nвЂ” NetWatch Protocol v1.4 вЂ”'
          })
        });
        tg.showAlert('вњ… РђРєРєР°СѓРЅС‚ СЂР°Р·РјРѕСЂРѕР¶РµРЅ!\nРРіСЂРѕРє РїРѕР»СѓС‡РёР» СѓРІРµРґРѕРјР»РµРЅРёРµ.');
      }
      document.getElementById('freezeId').value = '';
    } else {
      tg.showAlert('РћС€РёР±РєР°! РџСЂРѕРІРµСЂСЊ ID');
    }
  } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
}

// ===== РђР”РњРРќ: РЎРўРР РљРђ Р Р’РћР”Рђ =====
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
    if (!data.length) { container.innerHTML = '<div class="empty-state">РЎР»РѕС‚РѕРІ РЅРµС‚</div>'; return; }
    container.innerHTML = data.map(slot => {
      const taken = slot.taken_by ? `<span style="color:#2ecc71;font-size:9px;">вњ“ ${slot.taken_by.name}</span>` : `<span style="color:var(--text3);font-size:9px;">РЎРІРѕР±РѕРґРЅРѕ</span>`;
      return `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="flex:1;">
          <div style="font-size:11px;color:var(--text);font-weight:600;">${slot.day} В· ${slot.time}</div>
          <div style="font-size:9px;color:var(--text3);">${slot.note||''}</div>
          ${taken}
        </div>
        <button onclick="adminDeleteLaundrySlot(${slot.id})" style="background:none;border:1px solid rgba(200,50,50,0.3);color:rgba(200,80,80,0.7);padding:4px 10px;border-radius:4px;font-size:9px;font-family:monospace;cursor:pointer;"><i class="ti ti-trash"></i></button>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">РћС€РёР±РєР°</div>'; }
}

async function adminAddLaundrySlot() {
  const day = document.getElementById('lDay').value.trim();
  const time = document.getElementById('lTime').value.trim();
  const note = document.getElementById('lNote').value.trim();
  if (!day || !time) { tg.showAlert('Р—Р°РїРѕР»РЅРё РґРµРЅСЊ Рё РІСЂРµРјСЏ'); return; }
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day, time, note})
    });
    if (r.ok) {
      document.getElementById('lDay').value='';
      document.getElementById('lTime').value='';
      document.getElementById('lNote').value='';
      try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
      adminLoadLaundrySlots();
    } else tg.showAlert('РћС€РёР±РєР°!');
  } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
}

async function adminDeleteLaundrySlot(id) {
  tg.showPopup({title:'РЈРґР°Р»РёС‚СЊ СЃР»РѕС‚?',message:'Р—Р°РїРёСЃСЊ Р±СѓРґРµС‚ СѓРґР°Р»РµРЅР°.',buttons:[{id:'ok',type:'destructive',text:'РЈРґР°Р»РёС‚СЊ'},{type:'cancel'}]}, async(b)=>{
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
    if (!data.length) { container.innerHTML = '<div class="empty-state">РЎР»РѕС‚РѕРІ РЅРµС‚</div>'; return; }
    container.innerHTML = data.map(slot => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--border);">
        <div style="flex:1;">
          <div style="font-size:11px;color:var(--text);font-weight:600;">${slot.day} В· ${slot.time}</div>
          <div style="font-size:9px;color:var(--text3);">${slot.note||''}</div>
        </div>
        <button onclick="adminDeleteWaterSlot(${slot.id})" style="background:none;border:1px solid rgba(200,50,50,0.3);color:rgba(200,80,80,0.7);padding:4px 10px;border-radius:4px;font-size:9px;font-family:monospace;cursor:pointer;"><i class="ti ti-trash"></i></button>
      </div>`).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">РћС€РёР±РєР°</div>'; }
}

async function adminAddWaterSlot() {
  const day = document.getElementById('wDay').value.trim();
  const time = document.getElementById('wTime').value.trim();
  const note = document.getElementById('wNote').value.trim();
  if (!day || !time) { tg.showAlert('Р—Р°РїРѕР»РЅРё РґРµРЅСЊ Рё РІСЂРµРјСЏ'); return; }
  try {
    const r = await fetch(`${API_URL}/api/water/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day, time, note})
    });
    if (r.ok) {
      document.getElementById('wDay').value='';
      document.getElementById('wTime').value='';
      document.getElementById('wNote').value='';
      try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
      adminLoadWaterSlots();
    } else tg.showAlert('РћС€РёР±РєР°!');
  } catch(e) { tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ'); }
}

async function adminDeleteWaterSlot(id) {
  tg.showPopup({title:'РЈРґР°Р»РёС‚СЊ СЃР»РѕС‚?',message:'РЎР»РѕС‚ Р±СѓРґРµС‚ СѓРґР°Р»С‘РЅ.',buttons:[{id:'ok',type:'destructive',text:'РЈРґР°Р»РёС‚СЊ'},{type:'cancel'}]}, async(b)=>{
    if(b!=='ok')return;
    await fetch(`${API_URL}/api/water/schedule/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}});
    adminLoadWaterSlots();
  });
}

async function adminAward() {
  const name=document.getElementById('awardName').value, points=parseInt(document.getElementById('awardPoints').value), reason=document.getElementById('awardReason').value;
  if (!name||!points||!reason) { tg.showAlert('Р—Р°РїРѕР»РЅРё РІСЃРµ РїРѕР»СЏ'); return; }
  tg.showAlert('Р”Р»СЏ РЅР°С‡РёСЃР»РµРЅРёСЏ Р±Р°Р»Р»РѕРІ РёСЃРїРѕР»СЊР·СѓР№ /award РІ Р±РѕС‚Рµ');
}

async function adminPenalize() {
  tg.showAlert('Р”Р»СЏ СЃРЅСЏС‚РёСЏ Р±Р°Р»Р»РѕРІ РёСЃРїРѕР»СЊР·СѓР№ /penalize РІ Р±РѕС‚Рµ');
}

async function setBlackwall(enabled) {
  try {
    const r = await fetch(`${API_URL}/api/admin/blackwall`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({enabled})});
    if (r.ok) tg.showAlert(enabled ? 'в›” BlackWall РІРєР»СЋС‡С‘РЅ!' : 'вњ… BlackWall РІС‹РєР»СЋС‡РµРЅ!');
  } catch(e) { tg.showAlert('РћС€РёР±РєР°'); }
}

/* --- Р›РћР“РРљРђ Р Р•Р™Р”РћР’РћР™ РЎРРЎРўР•РњР« v2.0 (Р‘С‹СЃС‚СЂС‹Р№ СЃС‚Р°СЂС‚) --- */

// РќРђРЎРўР РћР™РљР
const RAID_CONFIG = {
    minPlayers: 3,
    maxPlayers: 15,
    adminIds: [389741116, 244487659, 1190015933, 491711713],
    cyberpunk: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_netwatchtheme.png?raw=true',
        title: '// MICHAEL SMASHER PROTOCOL // TARGET: РњР®',
        placeholderColor: '#ff003c'
    },
    genshin: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_genshintheme.png?raw=true',
        title: 'рџ’Ћ РњРРљР•Р›РђРќР”Р–Р•Р›Рћ // РџР•Р Р’Р«Р™ РџР Р•Р”Р’Р•РЎРўРќРРљ РћРўР‘РћРЇ',
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
        ready ? 'РћС‚СЂСЏРґ СЃРѕР±СЂР°РЅ. РљР°РЅР°Р» РіРѕС‚РѕРІ Рє Р·Р°РїСѓСЃРєСѓ.' : `РРґС‘С‚ СЃРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ РѕС‚СЂСЏРґР°: ${safeCount}/${safeTarget}`,
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
        { percent: 8, state: 'LINK', hint: 'РќРµР№СЂРѕР»РёРЅРє РёРЅРёС†РёРёСЂРѕРІР°РЅ', status: 'РџРѕРґРіРѕС‚РѕРІРєР° Р±РѕРµРІРѕРіРѕ РєР°РЅР°Р»Р°...' },
        { percent: 24, state: 'SCAN', hint: 'РЎРєР°РЅРёСЂРѕРІР°РЅРёРµ СЃРёРіРЅР°С‚СѓСЂС‹ Р±РѕСЃСЃР°', status: 'РЎС‡РёС‚С‹РІР°РµРј РїРѕРІРµРґРµРЅС‡РµСЃРєРёР№ РїСЂРѕС„РёР»СЊ РђР»СЊС„Р°Р±РѕСЃСЃР°...' },
        { percent: 41, state: 'WALL', hint: 'РћР±С…РѕРґ BlackWall', status: 'РџСЂРѕР±РёРІР°РµРј РІРЅРµС€РЅРёР№ Р·Р°С‰РёС‚РЅС‹Р№ СЃР»РѕР№...' },
        { percent: 63, state: 'ROUTE', hint: 'РњР°СЂС€СЂСѓС‚РёР·Р°С†РёСЏ РѕС‚СЂСЏРґР°', status: 'РЎРѕР±РёСЂР°РµРј С‚РѕС‡РєРё РІС…РѕРґР° РґР»СЏ СѓРґР°СЂРЅРѕР№ РіСЂСѓРїРїС‹...' },
        { percent: 82, state: 'LOCK', hint: 'Р¤РёРєСЃР°С†РёСЏ Р±РѕРµРІРѕРіРѕ РєР°РЅР°Р»Р°', status: 'РљР°РЅР°Р» РїРѕС‡С‚Рё СЃС‚Р°Р±РёР»РµРЅ. Р”РµСЂР¶РёРј СЃРёРіРЅР°Р»...' },
        { percent: 100, state: 'READY', hint: 'РЎРёСЃС‚РµРјР° РіРѕС‚РѕРІР° Рє СЂРµР№РґСѓ', status: 'РљРѕРЅС‚СѓСЂ Р°РєС‚РёРІРµРЅ. РњРѕР¶РЅРѕ РїРѕРґРєР»СЋС‡Р°С‚СЊСЃСЏ Рє Р°С‚Р°РєРµ.' }
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
    setRaidStatusText('РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ СЂРµР№РґР°...');
    setRaidButtonState('Р—Р°РіСЂСѓР·РєР° СЃС‚Р°С‚СѓСЃР°...', true);

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
        const remainingToday = isAdmin ? 'Р±РµР· Р»РёРјРёС‚Р°' : `${numericRemaining}/${raidLimit}`;

        if (!data.raid) {
            updateRaidUI(0);
            setRaidProgressVisual(6, 'STANDBY', 'РќРё РѕРґРёРЅ РѕС‚СЂСЏРґ РµС‰С‘ РЅРµ СЃРѕР±СЂР°РЅ', 'pending');
            setRaidStatusText(
                isAdmin
                    ? 'Р РµР№Рґ РµС‰С‘ РЅРµ СЃРѕР·РґР°РЅ. РђРґРјРёРЅ РјРѕР¶РµС‚ СЃС‚Р°СЂС‚РѕРІР°С‚СЊ РІ Р»СЋР±РѕР№ РјРѕРјРµРЅС‚.'
                    : `Р РµР№Рґ РµС‰С‘ РЅРµ СЃРѕР±СЂР°РЅ. РћСЃС‚Р°Р»РѕСЃСЊ РїРѕРїС‹С‚РѕРє СЃРµРіРѕРґРЅСЏ: ${remainingToday}.`
            );
            setRaidButtonState(
                'РџРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ Рє РЅРµР№СЂРѕР»РёРЅРєСѓ',
                finishedToday >= raidLimit && !isAdmin
            );
            return;
        }

        const participants = data.participants || [];
        const count = data.count ?? participants.length ?? 0;
        const participantNames = participants.map(p => p.name).join(' вЂў ');
        const alreadyJoined = participants.some(p => p.telegram_id === currentUserId);

        if (data.raid.status === 'finished') {
            const success = data.raid.result === 'success';
            updateRaidUI(Math.max(count, RAID_CONFIG.minPlayers));
            setRaidProgressVisual(
                100,
                success ? 'VICTORY' : 'FAIL',
                success ? 'РђР»СЊС„Р°Р±РѕСЃСЃ РїСЂРѕР±РёС‚. РќР°РіСЂР°РґР° РЅР°С‡РёСЃР»РµРЅР°.' : 'РљРѕРЅС‚СѓСЂ СЃРѕСЂРІР°РЅ. РЎС‚Р°РІРєРё РїРѕС‚РµСЂСЏРЅС‹.',
                success ? 'success' : 'danger'
            );
            setRaidStatusText(
                success
                    ? `Р РµР№Рґ Р·Р°РІРµСЂС€С‘РЅ: +150в… РєР°Р¶РґРѕРјСѓ.${participantNames ? ' Р‘РѕР№С†С‹: ' + participantNames : ''}`
                    : `РђР»СЊС„Р°Р±РѕСЃСЃ РѕС‚Р±РёР»СЃСЏ.${participantNames ? ' Р’ РѕС‚СЂСЏРґРµ Р±С‹Р»Рё: ' + participantNames : ''}`,
                success ? '#2ecc71' : '#cc4444'
            );
            setRaidButtonState(
                isAdmin || numericRemaining > 0 ? 'РќР°С‡Р°С‚СЊ РЅРѕРІС‹Р№ СЂРµР№Рґ' : 'Р РµР№РґС‹ РЅР° СЃРµРіРѕРґРЅСЏ Р·Р°РєСЂС‹С‚С‹',
                !isAdmin && numericRemaining <= 0
            );
            return;
        }

        updateRaidUI(count);
        setRaidProgressVisual(
            Math.min((count / RAID_CONFIG.minPlayers) * 100, 100),
            alreadyJoined ? 'LINKED' : 'ASSEMBLING',
            alreadyJoined ? 'РўС‹ СѓР¶Рµ СЃРёРЅС…СЂРѕРЅРёР·РёСЂРѕРІР°РЅ СЃ РѕС‚СЂСЏРґРѕРј.' : 'РРґС‘С‚ РґРѕР±РѕСЂ Р±РѕР№С†РѕРІ РґР»СЏ Р·Р°РїСѓСЃРєР°.',
            count >= RAID_CONFIG.minPlayers ? 'success' : 'pending'
        );
        setRaidStatusText(
            alreadyJoined
                ? `РўС‹ СѓР¶Рµ РІ РѕС‚СЂСЏРґРµ. Р‘РѕР№С†РѕРІ: ${count}/${RAID_CONFIG.minPlayers}.${participantNames ? ' ' + participantNames : ''}`
                : `РЎР±РѕСЂ РѕС‚СЂСЏРґР°: ${count}/${RAID_CONFIG.minPlayers}.${participantNames ? ' ' + participantNames : ''} ${isAdmin ? '' : 'РћСЃС‚Р°Р»РѕСЃСЊ СЂРµР№РґРѕРІ: ' + remainingToday + '.'}`,
            alreadyJoined ? '#2ecc71' : 'var(--text2)'
        );
        setRaidButtonState(
            alreadyJoined ? 'РўС‹ СѓР¶Рµ РІ РѕС‚СЂСЏРґРµ' : 'РџРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ Рє РЅРµР№СЂРѕР»РёРЅРєСѓ',
            alreadyJoined || isJoiningRaid
        );
    } catch(e) {
        updateRaidUI(0);
        setRaidStatusText('РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃС‚Р°С‚СѓСЃ СЂРµР№РґР°.', '#cc4444');
        setRaidButtonState('РџРѕРІС‚РѕСЂРёС‚СЊ РїРѕРґРєР»СЋС‡РµРЅРёРµ', false);
    }
}

function getRaidErrorMessage(detail) {
    if (detail === 'Already joined') return 'РўС‹ СѓР¶Рµ РІ СЌС‚РѕРј СЂРµР№РґРµ.';
    if (detail === 'Daily raid limit reached') return 'РЎРµРіРѕРґРЅСЏ Р»РёРјРёС‚ СЂРµР№РґРѕРІ РёСЃС‡РµСЂРїР°РЅ. РџРѕРїСЂРѕР±СѓР№ Р·Р°РІС‚СЂР°.';
    if (detail === 'Not enough points') return 'РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ РґР»СЏ СЂРµР№РґР°.';
    return 'РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРёСЃРѕРµРґРёРЅРёС‚СЊСЃСЏ Рє СЂРµР№РґСѓ.';
}

async function joinRaid() {
    if (isJoiningRaid) return;
    if (!currentUserId) { tg.showAlert('РћС‚РєСЂРѕР№С‚Рµ РїСЂРёР»РѕР¶РµРЅРёРµ С‡РµСЂРµР· Telegram Р±РѕС‚Р°'); return; }
    if (currentPoints < 50) { tg.showAlert('РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ Р±Р°Р»Р»РѕРІ. РќСѓР¶РЅРѕ 50в…'); return; }

    tg.showPopup({
        title: 'вљ”пёЏ Р’СЃС‚СѓРїРёС‚СЊ РІ СЂРµР№Рґ?',
        message: 'РўС‹ СЃС‚Р°РІРёС€СЊ 50в…. РџРѕР±РµРґР° РґР°СЃС‚ +150в… РєР°Р¶РґРѕРјСѓ СѓС‡Р°СЃС‚РЅРёРєСѓ, РїРѕСЂР°Р¶РµРЅРёРµ СЃРѕР¶Р¶С‘С‚ СЃС‚Р°РІРєСѓ. Р РµР№Рґ СЃС‚Р°СЂС‚СѓРµС‚ РїСЂРё 3 Р±РѕР№С†Р°С….',
        buttons: [{id:'confirm', type:'default', text:'вљ”пёЏ Р’ Р‘РћР™!'}, {type:'cancel'}]
    }, async (btnId) => {
        if (btnId !== 'confirm') return;

        isJoiningRaid = true;
        setRaidProgressVisual(92, 'BREACH', 'РџРѕРґРєР»СЋС‡Р°РµРј С‚РµР±СЏ Рє Р±РѕРµРІРѕРјСѓ РєРѕРЅС‚СѓСЂСѓ...', 'pending');
        setRaidButtonState('РЎРёРЅС…СЂРѕРЅРёР·Р°С†РёСЏ...', true, '#e67e22', '#fff');

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
                setRaidProgressVisual(100, 'VICTORY', 'РђР»СЊС„Р°Р±РѕСЃСЃ РїСЂРѕР±РёС‚. РќР°РіСЂР°РґР° Р·Р°С‡РёСЃР»РµРЅР°.', 'success');
                launchConfetti(80);
            } else if (data.launched && data.result === 'defended') {
                setRaidProgressVisual(100, 'FAIL', 'РљРѕРЅС‚СѓСЂ СЃРѕСЂРІР°РЅ. РђР»СЊС„Р°Р±РѕСЃСЃ СѓРґРµСЂР¶Р°Р» Р·Р°С‰РёС‚Сѓ.', 'danger');
            } else {
                setRaidProgressVisual(
                    Math.min(((data.count || 1) / RAID_CONFIG.minPlayers) * 100, 100),
                    'LINKED',
                    `Р‘РѕР№С†РѕРІ РІ РєРѕРЅС‚СѓСЂРµ: ${data.count || 1}/${RAID_CONFIG.minPlayers}`,
                    'pending'
                );
            }

            try {
                tg.HapticFeedback.notificationOccurred(
                    data.launched && data.result === 'defended' ? 'error' : 'success'
                );
            } catch(e) {}

            tg.showAlert(data.message || 'Р РµР№Рґ РѕР±РЅРѕРІР»С‘РЅ.');
            loadLeaderboard();
            loadPoints(currentUserId);
        } catch(e) {
            tg.showAlert('РћС€РёР±РєР° СЃРѕРµРґРёРЅРµРЅРёСЏ СЃ СЂРµР№РґРѕРј.');
        } finally {
            isJoiningRaid = false;
            loadRaidStatus();
        }
    });
}

