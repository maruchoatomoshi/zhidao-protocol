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

// === ЗАМОРОЗКА ФИЧ (до официального старта) ===
// Разделы ниже закрыты для обычных игроков. Админы и архитекторы видят всё.
// Чтобы разморозить раздел — поставь false. Чтобы выключить всю систему — APP_FEATURE_FREEZE_ENABLED = false.
window.APP_FEATURE_FREEZE_ENABLED = false;
window.APP_FROZEN_FEATURES = {
  casino:        true,  // кейсы / молитвы
  shop:          true,  // магазин
  implants:      true,  // импланты / карточки
  laundry:       false, // стирка / вода
  achievements:  true,  // ачивки
  'diary-stars': true,  // дневник ★
  rating:        true,  // рейтинг
};
// Таймер обратного отсчёта в окне заморозки: открытие утром 5 июля (по Пекину).
window.APP_FREEZE_TARGET_AT = '2026-07-05T00:00:00+08:00';
