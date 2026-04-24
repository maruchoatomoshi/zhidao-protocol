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
