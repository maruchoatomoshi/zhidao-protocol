const tg = window.Telegram?.WebApp || {
  ready:()=>{}, expand:()=>{}, close:()=>{},
  setHeaderColor:()=>{}, setBackgroundColor:()=>{},
  showAlert:(msg)=>{ if(typeof showToast==='function') showToast(msg); else alert(msg); },
  showPopup:(opts,cb)=>{ const msg=(opts.title||'')+'\n'+(opts.message||''); setTimeout(()=>{ if(confirm(msg)) cb(opts.buttons&&opts.buttons[0]?opts.buttons[0].id:'confirm'); else cb('cancel'); },0); },
  HapticFeedback:{ notificationOccurred:()=>{}, impactOccurred:()=>{}, selectionChanged:()=>{} },
  initDataUnsafe:{user:null}, BackButton:{show:()=>{},hide:()=>{},onClick:()=>{}},
  MainButton:{show:()=>{},hide:()=>{}}, themeParams:{}
};
try { tg.expand(); } catch(e) {}
try { tg.setHeaderColor('#050510'); } catch(e) {}
try { tg.setBackgroundColor('#050510'); } catch(e) {}

const API_URL = 'https://hk.marucho.icu:8443';
const THEMES = ['', 'nw-light', 'genshin-light', 'genshin-dark', 'admin', 'architect'];
const WEATHER_KEY = '';
const EXCHANGE_KEY = '';
const ADMIN_IDS = [];
window.ADMIN_CONTACT_URL = '';

window.APP_LAUNCH_LOCK_ENABLED = false;
window.APP_LAUNCH_TARGET_AT = '2026-07-04T09:00:00+08:00';
window.ARCHITECT_EVENT_ENABLED = false;
