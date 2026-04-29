function getLastSeenGlobalAlertId() {
  return Number(localStorage.getItem('last_global_alert_id') || '0');
}

function setLastSeenGlobalAlertId(alertId) {
  localStorage.setItem('last_global_alert_id', String(alertId || 0));
}

let adminSelectedUser = null;
let adminSearchTimer = null;

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
      showToast(data.detail || 'Signal error');
      return;
    }

    if (data.alert_id) {
      setLastSeenGlobalAlertId(data.alert_id);
    }

    openArchitectArrivalBanner();
  } catch (e) {
    showToast('Connection error');
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
  if (name==='users') {
    adminSearchUsers();
    adminLoadActionLog();
  }
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
  if (!telegramId) { showToast('Введи Telegram ID игрока'); return; }

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
        showToast('⛔ Аккаунт заморожен!\nИгрок получил уведомление от NetWatch.');
      } else {
        await fetch(`https://api.telegram.org/bot8383270927:AAGC4sgTk6O6nzU1P2vA88s59kZmduJRIbc/sendMessage`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            chat_id: telegramId,
            text: '✅ NETWATCH 网络保安\n\n访问已恢复\nДоступ восстановлен.\n\nВаш аккаунт разморожен.\nМагазин и кейсы снова доступны.\n\n— NetWatch Protocol v1.4 —'
          })
        });
        showToast('✅ Аккаунт разморожен!\nИгрок получил уведомление.');
      }
      document.getElementById('freezeId').value = '';
    } else {
      showToast('Ошибка! Проверь ID');
    }
  } catch(e) { showToast('Ошибка соединения'); }
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
  if (!day || !time) { showToast('Заполни день и время'); return; }
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
    } else showToast('Ошибка!');
  } catch(e) { showToast('Ошибка соединения'); }
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
  if (!day || !time) { showToast('Заполни день и время'); return; }
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
    } else showToast('Ошибка!');
  } catch(e) { showToast('Ошибка соединения'); }
}

async function adminDeleteWaterSlot(id) {
  tg.showPopup({title:'Удалить слот?',message:'Слот будет удалён.',buttons:[{id:'ok',type:'destructive',text:'Удалить'},{type:'cancel'}]}, async(b)=>{
    if(b!=='ok')return;
    await fetch(`${API_URL}/api/water/schedule/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}});
    adminLoadWaterSlots();
  });
}

async function adminAward() {
  await adminAdjustPointsFromForm(1);
}

async function adminPenalize() {
  await adminAdjustPointsFromForm(-1);
}

function adminSearchUsersDebounced() {
  clearTimeout(adminSearchTimer);
  adminSearchTimer = setTimeout(adminSearchUsers, 280);
}

function adminResolveTargetId() {
  const raw = String(document.getElementById('awardName')?.value || '').trim();
  if (adminSelectedUser && (!raw || raw === String(adminSelectedUser.telegram_id) || raw === adminSelectedUser.full_name)) {
    return adminSelectedUser.telegram_id;
  }
  if (/^\d+$/.test(raw)) return Number(raw);
  return null;
}

function adminUserInitial(name) {
  const text = String(name || '?').trim();
  return (text[0] || '?').toUpperCase();
}

function adminRenderUserCard(user) {
  const active = adminSelectedUser && adminSelectedUser.telegram_id === user.telegram_id;
  const safeName = JSON.stringify(String(user.full_name || 'Аноним'));
  return `<div class="admin-user-card ${active ? 'active' : ''}" onclick='adminSelectUser(${user.telegram_id}, ${safeName}, ${user.points || 0})'>
    <div class="admin-user-avatar">${escapeHtml(adminUserInitial(user.full_name))}</div>
    <div class="admin-user-main">
      <div class="admin-user-name">${escapeHtml(user.full_name)} ${user.is_admin ? '<span class="inventory-pill">ADMIN</span>' : ''}</div>
      <div class="admin-user-meta">ID ${user.telegram_id}${user.username ? ` · ${escapeHtml(user.username)}` : ''}</div>
    </div>
    <div class="admin-user-points">${user.points || 0}★</div>
  </div>`;
}

async function adminSearchUsers() {
  if (!isAdmin || !currentUserId) return;
  const container = document.getElementById('adminUserResults');
  if (!container) return;
  const q = String(document.getElementById('adminUserSearch')?.value || '').trim();
  container.innerHTML = '<div class="empty-state">Поиск...</div>';
  try {
    const r = await fetch(`${API_URL}/api/admin/users?q=${encodeURIComponent(q)}`, {
      headers: {'x-admin-id': currentUserId},
    });
    const data = await r.json();
    if (!r.ok) {
      container.innerHTML = '<div class="empty-state">Нет доступа</div>';
      return;
    }
    const users = Array.isArray(data.users) ? data.users : [];
    container.innerHTML = users.length
      ? users.map(adminRenderUserCard).join('')
      : '<div class="empty-state">Никого не найдено</div>';
  } catch (e) {
    container.innerHTML = '<div class="empty-state">Ошибка поиска</div>';
  }
}

function adminSelectUser(telegramId, fullName, points) {
  adminSelectedUser = { telegram_id: telegramId, full_name: fullName, points };
  const awardName = document.getElementById('awardName');
  const freezeId = document.getElementById('freezeId');
  if (awardName) awardName.value = telegramId;
  if (freezeId) freezeId.value = telegramId;
  const selected = document.getElementById('adminSelectedUser');
  if (selected) {
    selected.style.display = 'block';
    selected.innerHTML = `
      <div class="admin-console-kicker">SELECTED TARGET</div>
      <div class="admin-log-top">
        <div>
          <div class="admin-user-name">${escapeHtml(fullName)}</div>
          <div class="admin-user-meta">Telegram ID ${telegramId}</div>
        </div>
        <div class="admin-user-points">${points || 0}★</div>
      </div>`;
  }
  adminSearchUsers();
}

async function adminAdjustPointsFromForm(direction) {
  const targetId = adminResolveTargetId();
  const points = Math.abs(parseInt(document.getElementById('awardPoints')?.value, 10));
  const reason = String(document.getElementById('awardReason')?.value || '').trim();
  if (!targetId || !points || !reason) {
    showToast('Выбери пользователя, укажи баллы и причину');
    return;
  }
  const delta = points * direction;
  const title = delta > 0 ? 'Начислить баллы?' : 'Снять баллы?';
  const dangerText = Math.abs(delta) >= 100 ? '\n\n⚠️ Крупная операция. Проверь сумму и цель.' : '';
  const targetName = adminSelectedUser?.telegram_id === targetId ? adminSelectedUser.full_name : String(targetId);
  tg.showPopup({
    title,
    message: `${targetName}\n${delta > 0 ? '+' : ''}${delta}★\nПричина: ${reason}${dangerText}`,
    buttons: [
      {id: 'confirm', type: delta < 0 ? 'destructive' : 'default', text: delta > 0 ? 'Начислить' : 'Снять'},
      {type: 'cancel'}
    ]
  }, async (buttonId) => {
    if (buttonId !== 'confirm') return;
    await adminSubmitPointAdjustment(targetId, delta, reason);
  });
}

async function adminSubmitPointAdjustment(targetId, delta, reason) {
  try {
    const r = await fetch(`${API_URL}/api/admin/points`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
      body: JSON.stringify({telegram_id: targetId, delta, reason}),
    });
    const data = await r.json();
    if (!r.ok) {
      showToast(data.detail || 'Ошибка операции');
      return;
    }
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
    const actualDelta = Number(data.delta || delta);
    showToast(`${data.full_name}: ${actualDelta > 0 ? '+' : ''}${actualDelta}★\nБаланс: ${data.new_points}★`);
    document.getElementById('awardPoints').value = '';
    document.getElementById('awardReason').value = '';
    if (adminSelectedUser && adminSelectedUser.telegram_id === targetId) {
      adminSelectedUser.points = data.new_points;
      adminSelectUser(targetId, data.full_name, data.new_points);
    }
    adminSearchUsers();
    adminLoadActionLog();
    if (targetId === currentUserId) {
      currentPoints = data.new_points;
      updatePoints();
    }
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

async function adminLoadActionLog() {
  if (!isAdmin || !currentUserId) return;
  const container = document.getElementById('adminActionLog');
  if (!container) return;
  container.innerHTML = '<div class="empty-state">Загрузка журнала...</div>';
  try {
    const r = await fetch(`${API_URL}/api/admin/actions?limit=30`, {
      headers: {'x-admin-id': currentUserId},
    });
    const data = await r.json();
    if (!r.ok) {
      container.innerHTML = '<div class="empty-state">Нет доступа к журналу</div>';
      return;
    }
    const logs = Array.isArray(data.logs) ? data.logs : [];
    if (!logs.length) {
      container.innerHTML = '<div class="empty-state">Операций пока нет</div>';
      return;
    }
    container.innerHTML = logs.map(log => {
      const delta = Number(log.points_delta || 0);
      const sign = delta > 0 ? '+' : '';
      const cls = delta >= 0 ? 'plus' : 'minus';
      const action = String(log.action_type || '').replace(/_/g, ' ').toUpperCase();
      const date = log.created_at ? new Date(log.created_at).toLocaleString('ru-RU') : '';
      const deltaHtml = delta
        ? `<div class="admin-log-delta ${cls}">${sign}${delta}★</div>`
        : `<div class="inventory-pill">${escapeHtml(action)}</div>`;
      return `<div class="admin-log-card">
        <div class="admin-log-top">
          <div class="admin-log-text">${escapeHtml(log.target_name || log.target_id)} · ${escapeHtml(log.reason || '')}</div>
          ${deltaHtml}
        </div>
        <div class="admin-log-meta">ADMIN ${escapeHtml(log.admin_name || log.admin_id)} · ${date}</div>
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = '<div class="empty-state">Ошибка загрузки журнала</div>';
  }
}

async function setBlackwall(enabled) {
  try {
    const r = await fetch(`${API_URL}/api/admin/blackwall`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({enabled})});
    if (r.ok) showToast(enabled ? '⛔ BlackWall включён!' : '✅ BlackWall выключен!');
  } catch(e) { showToast('Ошибка'); }
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
