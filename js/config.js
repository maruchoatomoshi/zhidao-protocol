const tg = window.Telegram?.WebApp || {
  ready:()=>{}, expand:()=>{}, close:()=>{},
  setHeaderColor:()=>{}, setBackgroundColor:()=>{},
  showAlert:(msg)=>{ if(typeof showToast==='function') showToast(msg); else alert(msg); },
  showPopup:(opts,cb)=>{ const msg=(opts.title||'')+'\n'+(opts.message||''); setTimeout(()=>{ const id = confirm(msg) ? (opts.buttons&&opts.buttons[0]?opts.buttons[0].id:'confirm') : 'cancel'; if (typeof cb === 'function') cb(id); },0); },
  HapticFeedback:{ notificationOccurred:()=>{}, impactOccurred:()=>{}, selectionChanged:()=>{} },
  initDataUnsafe:{user:null}, BackButton:{show:()=>{},hide:()=>{},onClick:()=>{}},
  MainButton:{show:()=>{},hide:()=>{}}, themeParams:{}
};
try { tg.expand(); } catch(e) {}
try { tg.setHeaderColor('#050510'); } catch(e) {}
try { tg.setBackgroundColor('#050510'); } catch(e) {}

const API_URL = 'https://hk.marucho.icu:8443';
const THEMES = ['', 'nw-light', 'genshin-light', 'genshin-dark', 'admin', 'admin-light', 'architect', 'aqua'];
const WEATHER_KEY = '';
const EXCHANGE_KEY = '';
const ADMIN_IDS = [];
window.ADMIN_CONTACT_URL = '';

window.APP_LAUNCH_LOCK_ENABLED = false;
window.APP_LAUNCH_TARGET_AT = '2026-07-04T09:00:00+08:00';
window.ARCHITECT_EVENT_ENABLED = false;
window.MJU_EVENT_ENABLED = false;

// 
// 
// 
window.APP_FEATURE_FREEZE_ENABLED = true;
window.APP_FROZEN_FEATURES = {
  casino:        true,
  shop:          true,
  implants:      true,
  laundry:       false,
  achievements:  true,
  'diary-stars': true,
  rating:        true,
  contracts:     true,
  presence:      false,
  // Элементы карточки игрока: рамки, ранг и выбор импланта (витрина).
  'profile-frame':    true,
  'profile-rank':     true,
  'profile-showcase': true,
};
// Таймер обратного отсчёта в окне заморозки: открытие утром 6 июля 7:00 (по Пекину).
window.APP_FREEZE_TARGET_AT = '2026-07-06T07:00:00+08:00';
