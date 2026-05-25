function getLastSeenGlobalAlertId() {
  return Number(localStorage.getItem('last_global_alert_id') || '0');
}

function setLastSeenGlobalAlertId(alertId) {
  localStorage.setItem('last_global_alert_id', String(alertId || 0));
}

let adminSelectedUser = null;
let adminSearchTimer = null;
let adminUsersCache = [];

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
  ['schedule','announce','laundry','users','presence','blackwall','contracts'].forEach(s => {
    const el = document.getElementById('admin-'+s); if(el) el.style.display='none';
  });
  document.querySelectorAll('.admin-sec-btn').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const statusEl = document.getElementById('adminPanelStatus');
  if (statusEl) {
    const now = new Date();
    const dateStr = now.toLocaleDateString('ru-RU', { weekday:'short', day:'numeric', month:'short' });
    const timeStr = now.toLocaleTimeString('ru-RU', { hour:'2-digit', minute:'2-digit' });
    statusEl.textContent = `${dateStr} · ${timeStr} · SYS:${name.toUpperCase()}`;
  }
  const el = document.getElementById('admin-'+name);
  if(el) el.style.display = 'block';
  if (name==='laundry') adminLoadLaundrySlots();
  if (name==='users') {
    adminSearchUsers();
    adminLoadActionLog();
  }
  if (name==='presence') adminLoadPresenceAll();
  if (name==='blackwall' && typeof loadArchitectEventAvailability === 'function') loadArchitectEventAvailability();
  if (name==='contracts') adminLoadContracts();
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
      const data = await r.json().catch(() => ({}));
      const notifyText = data.notified ? 'Игрок получил уведомление от NetWatch.' : 'Уведомление не отправлено, проверь BOT_TOKEN на API.';
      showToast(`${freeze ? '⛔ Аккаунт заморожен!' : '✅ Аккаунт разморожен!'}\n${notifyText}`);
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
      const taken = !!slot.taken_by;
      return `<div class="admin-slot-item ${taken ? 'taken' : 'free'}">
    <div class="admin-slot-icon">${taken ? '✓' : '○'}</div>
    <div class="admin-slot-info">
      <div class="admin-slot-time">${slot.day} · ${slot.time}</div>
      ${slot.note ? `<div class="admin-slot-note">${slot.note}</div>` : ''}
      <div class="admin-slot-status">${taken ? slot.taken_by.name : 'Свободно'}</div>
    </div>
    <button class="admin-slot-del" onclick="adminDeleteLaundrySlot(${slot.id})"><i class="ti ti-trash"></i></button>
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
  <div class="admin-slot-item free">
    <div class="admin-slot-icon">💧</div>
    <div class="admin-slot-info">
      <div class="admin-slot-time">${slot.day} · ${slot.time}</div>
      ${slot.note ? `<div class="admin-slot-note">${slot.note}</div>` : ''}
      <div class="admin-slot-status">Свободно</div>
    </div>
    <button class="admin-slot-del" onclick="adminDeleteWaterSlot(${slot.id})"><i class="ti ti-trash"></i></button>
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

async function adminAwardRep() {
  await adminAdjustRepFromForm(1);
}

async function adminPenalizeRep() {
  await adminAdjustRepFromForm(-1);
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

function adminUserAvatarHtml(user, large = false) {
  const avatar = String(user?.avatar_url || '').trim();
  const name = user?.full_name || user?.name || '?';
  const cls = large ? 'admin-user-avatar large' : 'admin-user-avatar';
  if (avatar) {
    return `<div class="${cls} has-image"><img src="${escapeHtml(avatar)}" alt=""></div>`;
  }
  return `<div class="${cls}">${escapeHtml(adminUserInitial(name))}</div>`;
}

function adminRenderUserCard(user) {
  const active = adminSelectedUser && adminSelectedUser.telegram_id === user.telegram_id;
  const room = String(user.room_number || '').trim();
  return `<div class="admin-user-card ${active ? 'active' : ''}" onclick="adminSelectUserById(${Number(user.telegram_id) || 0})">
    ${adminUserAvatarHtml(user)}
    <div class="admin-user-main">
      <div class="admin-user-name">${escapeHtml(user.full_name)} ${user.is_admin ? '<span class="inventory-pill">ADMIN</span>' : ''}</div>
      <div class="admin-user-meta">ID ${user.telegram_id}${user.username ? ` · ${escapeHtml(user.username)}` : ''}${room ? ` · комната ${escapeHtml(room)}` : ''}</div>
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
    adminUsersCache = users;
    container.innerHTML = users.length
      ? users.map(adminRenderUserCard).join('')
      : '<div class="empty-state">Никого не найдено</div>';
  } catch (e) {
    container.innerHTML = '<div class="empty-state">Ошибка поиска</div>';
  }
}

function adminSelectUserById(telegramId) {
  const user = adminUsersCache.find(item => Number(item.telegram_id) === Number(telegramId));
  if (!user) {
    showToast('Не удалось открыть карточку игрока');
    return;
  }
  adminSelectUser(user.telegram_id, user.full_name, user.points, user);
  adminLoadUserDossier(user.telegram_id);
}

function adminRenderRoommates(roommates) {
  if (!Array.isArray(roommates) || !roommates.length) {
    return '<div class="admin-roommate-empty">Соседи пока не указаны</div>';
  }
  return roommates.map(roommate => `
    <div class="admin-roommate-chip">
      ${adminUserAvatarHtml(roommate)}
      <span>${escapeHtml(roommate.full_name || roommate.telegram_id)}</span>
    </div>
  `).join('');
}

function adminDossierStatusLabel(status) {
  const labels = {
    pending: 'Ожидает',
    confirmed: 'Отмечен',
    free_time: 'Свободное время',
    leave_requested: 'Запрос отгула',
    admin_approved: 'Разрешено',
    leave_rejected: 'Отгул отклонён',
    needs_attention: 'Проверить',
    penalized: 'Штраф',
    skipped: 'Отменено',
  };
  return labels[status] || status || '—';
}

function adminDossierCheckTypeLabel(type) {
  if (type === 'morning') return 'Подъём';
  if (type === 'evening') return 'Вечер';
  if (type === 'excursion') return 'Экскурсия';
  return type || 'Отметка';
}

function adminDossierActionLabel(action) {
  const labels = {
    points_adjust: 'Баллы',
    rep_adjust: 'Репутация',
    room_update: 'Комната',
    presence_approve: 'Отметка разрешена',
    presence_reject: 'Отгул отклонён',
    presence_penalty: 'Штраф отметки',
    presence_cancel: 'Отметка отменена',
    reset_shop: 'Сброс магазина',
    blackwall: 'BlackWall',
    architect_event: 'Architect Event',
  };
  return labels[action] || String(action || 'Операция').replace(/_/g, ' ');
}

function adminRenderDossierStat(label, value, note = '') {
  return `<div class="admin-dossier-stat">
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(value)}</strong>
    ${note ? `<em>${escapeHtml(note)}</em>` : ''}
  </div>`;
}

function adminRenderDossierPresence(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return '<div class="admin-dossier-empty">Отметок пока нет</div>';
  }
  return rows.map(row => `
    <div class="admin-dossier-row ${escapeHtml(row.status || '')}">
      <div>
        <strong>${escapeHtml(adminDossierCheckTypeLabel(row.check_type))} · ${escapeHtml(row.check_date || '')}</strong>
        <span>${escapeHtml(adminDossierStatusLabel(row.status))}${row.attempts_sent ? ` · попыток ${row.attempts_sent}` : ''}</span>
      </div>
      ${row.penalty_points ? `<b class="minus">-${Number(row.penalty_points)}★</b>` : ''}
    </div>
  `).join('');
}

function adminRenderDossierDiary(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return '<div class="admin-dossier-empty">Оценок дневника пока нет</div>';
  }
  return rows.map(row => `
    <div class="admin-dossier-row">
      <div>
        <strong>${escapeHtml(row.entry_date || '')}</strong>
        <span>дневник</span>
      </div>
      <b>${Number(row.stars || 0)}★${row.bonus ? ` +${Number(row.bonus)} бонус` : ''}</b>
    </div>
  `).join('');
}

function adminRenderDossierActions(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return '<div class="admin-dossier-empty">Истории операций пока нет</div>';
  }
  return rows.map(row => {
    const delta = Number(row.points_delta || 0);
    const unit = row.action_type === 'rep_adjust' ? ' REP' : '★';
    const date = row.created_at ? new Date(row.created_at).toLocaleDateString('ru-RU') : '';
    return `<div class="admin-dossier-row">
      <div>
        <strong>${escapeHtml(adminDossierActionLabel(row.action_type))}</strong>
        <span>${escapeHtml(row.reason || '')}${date ? ` · ${escapeHtml(date)}` : ''}</span>
      </div>
      ${delta ? `<b class="${delta > 0 ? 'plus' : 'minus'}">${delta > 0 ? '+' : ''}${delta}${unit}</b>` : ''}
    </div>`;
  }).join('');
}

function adminRenderDossierEconomy(rows) {
  const ECON_META = {
    shop_purchase:         {label:'Покупка в магазине', icon:'🛒', tone:'spend'},
    shop_refund:           {label:'Продажа / возврат', icon:'↩', tone:'gain'},
    gift_tax:              {label:'Налог на подарок', icon:'🎁', tone:'spend'},
    gift_receive:          {label:'Получен подарок', icon:'🎁', tone:'gain'},
    case_open:             {label:'Открытие кейса', icon:'📦', tone:'case'},
    prayer_open:           {label:'Молитва', icon:'✦', tone:'case'},
    card_disassemble:      {label:'Разбор карточки', icon:'🃏', tone:'gain'},
    implant_disassemble:   {label:'Разбор импланта', icon:'植', tone:'gain'},
    diary_reward:          {label:'Дневник', icon:'日', tone:'gain'},
    admin_points:          {label:'Админ: звёзды', icon:'★', tone:'admin'},
    admin_rep:             {label:'Админ: REP', icon:'REP', tone:'rep'},
    presence_penalty:      {label:'Штраф отметки', icon:'!', tone:'danger'},
    contract_freeze:       {label:'Поручение: резерв', icon:'契', tone:'contract'},
    contract_refund:       {label:'Поручение: возврат', icon:'↩', tone:'gain'},
    contract_accept:       {label:'Поручение принято', icon:'✓', tone:'contract'},
    contract_payout:       {label:'Поручение: выплата', icon:'★', tone:'gain'},
    contract_fee_burn:     {label:'Комиссия Дозора', icon:'税', tone:'spend'},
    contract_dispute:      {label:'Спор по поручению', icon:'⚠', tone:'danger'},
    contract_admin_refund: {label:'Админ: возврат', icon:'↩', tone:'admin'},
    contract_admin_pay:    {label:'Админ: выплата', icon:'★', tone:'admin'},
    contract_admin_split:  {label:'Админ: раздел', icon:'⇄', tone:'admin'},
    contract_admin_burn:   {label:'Админ: сжигание', icon:'火', tone:'danger'},
  };
  if (!Array.isArray(rows) || !rows.length) {
    return '<div class="admin-dossier-empty">Экономических операций пока нет</div>';
  }
  return `<div class="economy-journal">${rows.map(row => {
    const amount = Number(row.amount || 0);
    const meta = ECON_META[row.operation] || {label: row.operation || 'Операция', icon:'◇', tone:'neutral'};
    const isRep = row.reference_type === 'rep' || String(row.operation || '').includes('rep');
    const unit = isRep ? ' REP' : '★';
    const date = row.created_at ? new Date(row.created_at).toLocaleString('ru-RU', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '';
    const amountClass = amount > 0 ? 'plus' : amount < 0 ? 'minus' : 'zero';
    const amountText = amount ? `${amount > 0 ? '+' : ''}${amount}${unit}` : '0';
    return `<div class="economy-log-card ${escapeHtml(meta.tone)}">
      <div class="economy-log-icon">${escapeHtml(meta.icon)}</div>
      <div class="economy-log-main">
        <div class="economy-log-topline">
          <strong>${escapeHtml(meta.label)}</strong>
          <span>${escapeHtml(date)}</span>
        </div>
        <div class="economy-log-note">${escapeHtml(row.note || 'Без комментария')}</div>
      </div>
      <b class="economy-log-amount ${amountClass}">${escapeHtml(amountText)}</b>
    </div>`;
  }).join('')}</div>`;
}

function adminPreparePointAction(delta, reason) {
  if (!adminSelectedUser) {
    showToast('Сначала выбери игрока');
    return;
  }
  const awardName = document.getElementById('awardName');
  const awardPoints = document.getElementById('awardPoints');
  const awardReason = document.getElementById('awardReason');
  if (awardName) awardName.value = adminSelectedUser.telegram_id;
  if (awardPoints) awardPoints.value = Math.abs(Number(delta || 0));
  if (awardReason) awardReason.value = reason || '';
  adminAdjustPointsFromForm(delta > 0 ? 1 : -1);
}

function adminPrepareRepAction(delta, reason) {
  if (!adminSelectedUser) {
    showToast('Сначала выбери игрока');
    return;
  }
  const awardName = document.getElementById('awardName');
  const awardPoints = document.getElementById('awardPoints');
  const awardReason = document.getElementById('awardReason');
  if (awardName) awardName.value = adminSelectedUser.telegram_id;
  if (awardPoints) awardPoints.value = Math.abs(Number(delta || 0));
  if (awardReason) awardReason.value = reason || '';
  adminAdjustRepFromForm(delta > 0 ? 1 : -1);
}

async function adminLoadUserDossier(telegramId) {
  if (!isAdmin || !currentUserId || !telegramId) return;
  try {
    const r = await fetch(`${API_URL}/api/admin/user/${encodeURIComponent(telegramId)}/dossier`, {
      headers: {'x-admin-id': currentUserId},
    });
    const data = await r.json();
    if (!r.ok || !data.user) {
      showToast(data.detail || 'Не удалось загрузить досье');
      return;
    }
    const user = {
      ...data.user,
      rep_score: data.user.rep_score || 0,
      dossier: {
        stats: data.stats || {},
        presence: Array.isArray(data.presence) ? data.presence : [],
        diary: Array.isArray(data.diary) ? data.diary : [],
        actions: Array.isArray(data.actions) ? data.actions : [],
        economy: Array.isArray(data.economy) ? data.economy : [],
      },
    };
    adminSelectUser(user.telegram_id, user.full_name, user.points, user, {skipSearch: true});
  } catch (e) {
    showToast('Ошибка загрузки досье');
  }
}

function adminEnsureDossierModal() {
  let modal = document.getElementById('adminDossierModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'adminDossierModal';
    modal.className = 'admin-dossier-modal';
    modal.innerHTML = `
      <div class="admin-dossier-backdrop" onclick="adminCloseDossier()"></div>
      <div class="admin-dossier-sheet">
        <div class="admin-dossier-sheet-head">
          <div>
            <div class="admin-console-kicker">OPERATOR DOSSIER</div>
            <div class="admin-console-title">Карточка игрока</div>
          </div>
          <button class="event-close-btn" onclick="adminCloseDossier()">×</button>
        </div>
        <div id="adminDossierBody"></div>
      </div>
    `;
    document.body.appendChild(modal);
  }
  return modal;
}

function adminCloseDossier() {
  const modal = document.getElementById('adminDossierModal');
  if (modal) modal.classList.remove('show');
}

function adminSelectUser(telegramId, fullName, points, extra = {}, options = {}) {
  adminSelectedUser = {
    ...(adminSelectedUser || {}),
    ...extra,
    telegram_id: telegramId,
    full_name: fullName,
    points,
  };
  const awardName = document.getElementById('awardName');
  const freezeId = document.getElementById('freezeId');
  if (awardName) awardName.value = telegramId;
  if (freezeId) freezeId.value = telegramId;
  const inlineSelected = document.getElementById('adminSelectedUser');
  if (inlineSelected) {
    inlineSelected.style.display = 'none';
    inlineSelected.innerHTML = '';
  }

  const modal = adminEnsureDossierModal();
  const selected = document.getElementById('adminDossierBody');
  if (selected) {
    const room = String(adminSelectedUser.room_number || '').trim();
    const roommates = adminSelectedUser.roommates || [];
    const dossier = adminSelectedUser.dossier || {};
    const stats = dossier.stats || {};
    selected.innerHTML = `
      <div class="admin-dossier-head">
        ${adminUserAvatarHtml(adminSelectedUser, true)}
        <div class="admin-dossier-main">
          <div class="admin-user-name">${escapeHtml(fullName)} ${adminSelectedUser.is_admin ? '<span class="inventory-pill">ADMIN</span>' : ''}</div>
          <div class="admin-user-meta">Telegram ID ${telegramId}${adminSelectedUser.username ? ` · ${escapeHtml(adminSelectedUser.username)}` : ''}</div>
        </div>
        <div style="text-align:right;">
          <div class="admin-user-points">${points || 0}★</div>
          <div style="font-size:10px;color:var(--text3);font-family:monospace;">${adminSelectedUser.rep_score || 0} REP</div>
        </div>
      </div>
      <div class="admin-dossier-grid">
        ${adminRenderDossierStat('★ Баланс', `${points || 0}★`, 'расходный кошелёк')}
        ${adminRenderDossierStat('REP', adminSelectedUser.rep_score || 0, 'рейтинг протокола')}
        ${adminRenderDossierStat('Комната', room || '—', roommates.length ? `соседей: ${roommates.length}` : 'не задана')}
        ${adminRenderDossierStat('Отметки', stats.presence_confirmed || 0, `${stats.presence_attention || 0} требуют внимания`)}
        ${adminRenderDossierStat('Дневник', `${stats.diary_stars || 0}★`, `${stats.diary_days || 0} дней`)}
        ${adminRenderDossierStat('Контракты', `${stats.contracts_created || 0} / ${stats.contracts_done || 0}`, `создал / выполнил · споры: ${stats.contracts_disputed || 0}`)}
      </div>
      <div class="admin-dossier-quick">
        <button onclick="adminPreparePointAction(10, 'быстрый бонус')">+10★</button>
        <button onclick="adminPreparePointAction(50, 'особый бонус')">+50★</button>
        <button onclick="adminPreparePointAction(-10, 'небольшой штраф')">-10★</button>
        <button onclick="adminPreparePointAction(-20, 'нарушение режима')">-20★</button>
        <button onclick="adminPrepareRepAction(5, 'полезная помощь')">+5 REP</button>
        <button onclick="adminPrepareRepAction(10, 'вклад в группу')">+10 REP</button>
        <button onclick="adminPrepareRepAction(-5, 'нарушение')">-5 REP</button>
        <button onclick="adminPrepareRepAction(-20, 'серьёзное нарушение')">-20 REP</button>
      </div>
      <div class="admin-dossier-room">
        <div class="admin-room-row">
          <input class="admin-input admin-room-input" id="adminRoomInput" placeholder="Комната" value="${escapeHtml(room)}">
          <button class="admin-console-refresh" onclick="adminSaveSelectedRoom()">СОХРАНИТЬ</button>
        </div>
        <div class="admin-roommate-title">Соседи</div>
        <div id="adminRoommates" class="admin-roommate-list">${adminRenderRoommates(roommates)}</div>
      </div>
      <div class="admin-dossier-panels">
        <div class="admin-dossier-panel">
          <div class="admin-dossier-panel-title">Последние отметки</div>
          ${adminRenderDossierPresence(dossier.presence)}
        </div>
        <div class="admin-dossier-panel">
          <div class="admin-dossier-panel-title">Дневник</div>
          ${adminRenderDossierDiary(dossier.diary)}
        </div>
        <div class="admin-dossier-panel wide">
          <div class="admin-dossier-panel-title">История действий</div>
          ${adminRenderDossierActions(dossier.actions)}
        </div>
        <div class="admin-dossier-panel wide">
          <div class="admin-dossier-panel-title">Экономический журнал</div>
          ${adminRenderDossierEconomy(dossier.economy)}
        </div>
      </div>`;
    modal.classList.add('show');
  }
  if (!options.skipSearch) adminSearchUsers();
}

async function adminSaveSelectedRoom() {
  if (!adminSelectedUser || !currentUserId) {
    showToast('Сначала выбери игрока');
    return;
  }
  const input = document.getElementById('adminRoomInput');
  const roomNumber = String(input?.value || '').trim();
  try {
    const r = await fetch(`${API_URL}/api/admin/user/room`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
      body: JSON.stringify({telegram_id: adminSelectedUser.telegram_id, room_number: roomNumber}),
    });
    const data = await r.json();
    if (!r.ok) {
      showToast(data.detail || 'Не удалось сохранить комнату');
      return;
    }
    adminSelectedUser.room_number = data.room_number || '';
    adminSelectedUser.roommates = data.roommates || [];
    const list = document.getElementById('adminRoommates');
    if (list) list.innerHTML = adminRenderRoommates(adminSelectedUser.roommates);
    showToast(data.room_number ? `Комната сохранена: ${data.room_number}` : 'Комната очищена');
    adminSearchUsers();
    adminLoadActionLog();
    adminLoadUserDossier(adminSelectedUser.telegram_id);
  } catch (e) {
    showToast('Ошибка соединения');
  }
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
      adminSelectUser(targetId, data.full_name, data.new_points, adminSelectedUser);
      adminLoadUserDossier(targetId);
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

async function adminGrantFragments() {
  if (!isArchitect) return;
  const rawId = String(document.getElementById('fragmentTargetId')?.value || '').trim();
  const amount = parseInt(document.getElementById('fragmentAmount')?.value, 10);
  const targetId = parseInt(rawId, 10) || adminResolveTargetId();
  if (!targetId || !amount || amount < 1) {
    showToast('Укажи Telegram ID и количество'); return;
  }
  try {
    const r = await fetch(`${API_URL}/api/admin/fragments`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': String(currentUserId)},
      body: JSON.stringify({telegram_id: targetId, amount}),
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.detail || 'Ошибка'); return; }
    try { tg.HapticFeedback.notificationOccurred('success'); } catch(e) {}
    showToast(`✅ Выдано ${amount} фрагментов\nИтого у игрока: ${data.protocol_fragments}`);
    document.getElementById('fragmentAmount').value = '';
  } catch(e) { showToast('Ошибка соединения'); }
}

async function adminAdjustRepFromForm(direction) {
  const targetId = adminResolveTargetId();
  const amount = Math.abs(parseInt(document.getElementById('awardPoints')?.value, 10));
  const reason = String(document.getElementById('awardReason')?.value || '').trim();
  if (!targetId || !amount || !reason) {
    showToast('Выбери пользователя, укажи REP и причину');
    return;
  }
  const delta = amount * direction;
  const title = delta > 0 ? 'Начислить REP?' : 'Снять REP?';
  const dangerText = Math.abs(delta) >= 50 ? '\n\n⚠️ Крупное изменение репутации. Проверь цель.' : '';
  const targetName = adminSelectedUser?.telegram_id === targetId ? adminSelectedUser.full_name : String(targetId);
  tg.showPopup({
    title,
    message: `${targetName}\n${delta > 0 ? '+' : ''}${delta} REP\nПричина: ${reason}${dangerText}`,
    buttons: [
      {id: 'confirm', type: delta < 0 ? 'destructive' : 'default', text: delta > 0 ? 'Начислить' : 'Снять'},
      {type: 'cancel'}
    ]
  }, async (buttonId) => {
    if (buttonId !== 'confirm') return;
    await adminSubmitRepAdjustment(targetId, delta, reason);
  });
}

async function adminSubmitRepAdjustment(targetId, delta, reason) {
  try {
    const r = await fetch(`${API_URL}/api/admin/rep`, {
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
    showToast(`${data.full_name}: ${actualDelta > 0 ? '+' : ''}${actualDelta} REP\nРепутация: ${data.new_rep_score}`);
    document.getElementById('awardPoints').value = '';
    document.getElementById('awardReason').value = '';
    if (adminSelectedUser && adminSelectedUser.telegram_id === targetId) {
      adminSelectedUser.rep_score = data.new_rep_score;
      adminSelectUser(targetId, data.full_name, data.points, adminSelectedUser);
      adminLoadUserDossier(targetId);
    }
    adminSearchUsers();
    adminLoadActionLog();
    if (typeof loadLeaderboard === 'function') loadLeaderboard();
  } catch (e) {
    showToast('Ошибка соединения');
  }
}

const ADMIN_PRESENCE_LABELS = {
  pending: 'Ожидают',
  confirmed: 'Подтвердили',
  free_time: 'Свободное время',
  leave_requested: 'Запросили отгул',
  admin_approved: 'Разрешено',
  leave_rejected: 'Отгул отклонён',
  needs_attention: 'Проверить',
  penalized: 'Оштрафованы',
  skipped: 'Отменены',
};

const ADMIN_PRESENCE_ORDER = [
  'pending',
  'confirmed',
  'free_time',
  'leave_requested',
  'admin_approved',
  'leave_rejected',
  'needs_attention',
  'penalized',
  'skipped',
];

function adminPresenceTarget(checkType) {
  if (checkType === 'morning') return document.getElementById('adminPresenceMorning');
  if (checkType === 'manual') return document.getElementById('adminPresenceManual');
  return document.getElementById('adminPresenceEvening');
}

function adminPresenceLabel(checkType) {
  if (checkType === 'morning') return 'утренняя отметка';
  if (checkType === 'manual') return 'ручная перекличка';
  return 'вечерняя отметка';
}

function adminRenderPresenceOverview(checkType, data) {
  const container = adminPresenceTarget(checkType);
  if (!container) return;

  const counts = data.counts || {};
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const activeRows = checks.filter(row => ['pending', 'leave_requested', 'leave_rejected', 'needs_attention'].includes(row.status));
  const statusGrid = ADMIN_PRESENCE_ORDER.map(key => `
    <div class="admin-presence-chip ${key}">
      <span>${ADMIN_PRESENCE_LABELS[key] || key}</span>
      <strong>${counts[key] || 0}</strong>
    </div>
  `).join('');

  const attentionList = activeRows.length
    ? `<div class="admin-presence-list">
        ${activeRows.slice(0, 8).map(row => `
          <div class="admin-presence-row ${row.status}">
            <div>
              <div class="admin-presence-name">${escapeHtml(row.full_name || row.telegram_id || 'Без имени')}</div>
              <div class="admin-presence-meta">ID ${escapeHtml(row.telegram_id)} · ${ADMIN_PRESENCE_LABELS[row.status] || row.status} · попыток ${row.attempts_sent || 0}</div>
            </div>
            <div class="admin-presence-row-badge">${row.status === 'needs_attention' ? 'ALERT' : 'WAIT'}</div>
          </div>
        `).join('')}
      </div>`
    : '<div class="empty-state">Нет активных тревог или ожиданий</div>';

  const rawDate = String(data.check_date || 'сегодня');
  const displayDate = checkType === 'manual' && rawDate.includes('__')
    ? rawDate.replace('__', ' · ').replace(/(\d{2})(\d{2})(\d{2})\d*$/, '$1:$2:$3')
    : rawDate;
  container.innerHTML = `
    <div class="admin-presence-date">${checkType === 'manual' ? 'Сессия' : 'Дата'}: ${escapeHtml(displayDate)}</div>
    <div class="admin-presence-chips">${statusGrid}</div>
    ${attentionList}
  `;
}

async function adminLoadPresence(checkType) {
  if (!isAdmin || !currentUserId) return;
  const container = adminPresenceTarget(checkType);
  if (container) container.innerHTML = '<div class="empty-state">Загрузка статуса...</div>';
  try {
    const r = await fetch(`${API_URL}/api/presence/admin/overview?check_type=${encodeURIComponent(checkType)}`, {
      headers: {'x-admin-id': currentUserId},
    });
    const data = await r.json();
    if (!r.ok) {
      if (container) container.innerHTML = `<div class="empty-state">${escapeHtml(data.detail || 'Нет доступа')}</div>`;
      return;
    }
    adminRenderPresenceOverview(checkType, data);
  } catch (e) {
    if (container) container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

function adminLoadPresenceAll() {
  adminLoadPresence('morning');
  adminLoadPresence('evening');
  adminLoadPresence('manual');
}

async function adminDispatchPresence(checkType) {
  if (!isAdmin || !currentUserId) return;
  const label = adminPresenceLabel(checkType);
  tg.showPopup({
    title: 'Запустить отметку?',
    message: `${label} будет отправлена детям прямо сейчас через Telegram-бота.`,
    buttons: [
      {id: 'confirm', type: 'default', text: 'Запустить'},
      {type: 'cancel'}
    ]
  }, async (buttonId) => {
    if (buttonId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/presence/admin/dispatch`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
        body: JSON.stringify({check_type: checkType, attempt_no: 1, note: 'Mini App dispatch'}),
      });
      const data = await r.json();
      if (!r.ok) {
        showToast(data.detail || 'Не удалось запустить отметку');
        return;
      }
      showToast(`Отправлено: ${data.sent_count || 0}\nОшибок: ${data.failed_count || 0}`);
      adminLoadPresence(checkType);
    } catch (e) {
      showToast('Ошибка соединения');
    }
  });
}

async function adminCancelPresence(checkType) {
  if (!isAdmin || !currentUserId) return;
  const label = adminPresenceLabel(checkType);
  tg.showPopup({
    title: 'Отменить отметку?',
    message: `${label} будет помечена как отменённая для тех, кто ещё не подтвердил.`,
    buttons: [
      {id: 'confirm', type: 'destructive', text: 'Отменить'},
      {type: 'cancel'}
    ]
  }, async (buttonId) => {
    if (buttonId !== 'confirm') return;
    try {
      const r = await fetch(`${API_URL}/api/presence/admin/cancel`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
        body: JSON.stringify({check_type: checkType, admin_id: currentUserId, reason: 'Отменено из Mini App'}),
      });
      const data = await r.json();
      if (!r.ok) {
        showToast(data.detail || 'Не удалось отменить отметку');
        return;
      }
      showToast(`Отменено статусов: ${data.cancelled || 0}`);
      adminLoadPresence(checkType);
    } catch (e) {
      showToast('Ошибка соединения');
    }
  });
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
      const unit = log.action_type === 'rep_adjust' ? ' REP' : '★';
      const date = log.created_at ? new Date(log.created_at).toLocaleString('ru-RU') : '';
      const deltaHtml = delta
        ? `<div class="admin-log-delta ${cls}">${sign}${delta}${unit}</div>`
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

async function setArchitectEventEnabled(enabled) {
  try {
    const r = await fetch(`${API_URL}/api/admin/architect-event`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-admin-id': currentUserId},
      body: JSON.stringify({enabled})
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      showToast(data.detail || 'Ошибка переключения ивента');
      return;
    }

    if (typeof syncArchitectEventAvailability === 'function') {
      syncArchitectEventAvailability(!!data.architect_event);
    }
    showToast(enabled ? '⚡ Architect Event открыт!' : '⛔ Architect Event скрыт!');
  } catch(e) {
    showToast('Ошибка соединения');
  }
}

// ===== ADMIN CONTRACTS =====

let adminContractsActiveFilter = '';

async function adminLoadContracts(status, btn) {
  adminContractsActiveFilter = status || '';
  if (btn) {
    document.querySelectorAll('.admin-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
  const el = document.getElementById('adminContractsList');
  if (!el || !currentUserId) return;
  el.innerHTML = '<div style="color:var(--text3);">Загрузка...</div>';
  try {
    const url = status && status !== 'suspicious'
      ? `${API_URL}/api/admin/contracts?status=${encodeURIComponent(status)}`
      : `${API_URL}/api/admin/contracts`;
    const r = await fetch(url, { headers: {'x-admin-id': String(currentUserId)} });
    let data = await r.json();
    if (!r.ok) { el.innerHTML = `<div style="color:#e74c3c;">${escapeHtml(data.detail || 'Ошибка')}</div>`; return; }
    if (status === 'suspicious') data = data.filter(c => c.is_suspicious);
    if (!data.length) { el.innerHTML = '<div style="color:var(--text3);">Контрактов нет</div>'; return; }
    if (!status) {
      const disputed = data.filter(c => c.status === 'disputed');
      const rest = data.filter(c => c.status !== 'disputed');
      el.innerHTML = `
        ${disputed.length ? `<div class="admin-contracts-section-title danger">СПОРНЫЕ · требуют решения</div>${disputed.map(c => adminRenderContractCard(c)).join('')}` : ''}
        <div class="admin-contracts-section-title">ВСЕ КОНТРАКТЫ</div>
        ${rest.length ? rest.map(c => adminRenderContractCard(c)).join('') : '<div style="color:var(--text3);">Других контрактов нет</div>'}
      `;
      return;
    }
    el.innerHTML = data.map(c => adminRenderContractCard(c)).join('');
  } catch (e) { el.innerHTML = '<div style="color:#e74c3c;">Нет соединения</div>'; }
}

async function adminLoadContractMonitor() {
  const el = document.getElementById('adminContractMonitor');
  if (!el || !currentUserId) return;
  el.style.display = 'block';
  el.innerHTML = '<div class="empty-state">Сканирую экономические связи...</div>';
  try {
    const r = await fetch(`${API_URL}/api/admin/contracts/monitor`, {
      headers: {'x-admin-id': String(currentUserId)},
    });
    const data = await r.json();
    if (!r.ok) {
      el.innerHTML = `<div class="empty-state">${escapeHtml(data.detail || 'Ошибка мониторинга')}</div>`;
      return;
    }
    el.innerHTML = adminRenderContractMonitor(data);
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Нет соединения</div>';
  }
}

function adminRenderContractMonitor(data) {
  const summary = data.summary || {};
  const status = summary.status_counts || {};
  const contractPairs = Array.isArray(data.contract_pairs) ? data.contract_pairs : [];
  const giftPairs = Array.isArray(data.gift_pairs) ? data.gift_pairs : [];
  const gifts = Array.isArray(data.recent_gifts) ? data.recent_gifts : [];

  const riskCount = contractPairs.filter(p => (p.flags || []).length).length
    + giftPairs.filter(p => (p.flags || []).length).length
    + Number(summary.cross_pairs || 0);

  const cards = [
    ['Оборот', `${Number(summary.total_turnover || 0)}★`, `${Number(summary.total_contracts || 0)} контрактов`],
    ['Комиссии', `${Number(summary.fee_burned || 0)}★`, 'сгорело в системе'],
    ['Споры', `${Number(status.disputed || 0)}`, 'активные конфликты'],
    ['Риски', `${riskCount}`, 'пары/связки'],
  ].map(([label, value, hint]) => `
    <div class="contract-monitor-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <em>${escapeHtml(hint)}</em>
    </div>
  `).join('');

  const contractPairHtml = contractPairs.length
    ? contractPairs.slice(0, 8).map(p => adminRenderMonitorPair({
        title: `${p.creator_name} → ${p.assignee_name}`,
        meta: `${p.count} контрактов · оборот ${p.reward_total}★ · выплачено ${p.payout_total}★ · комиссия ${p.fee_total}★`,
        flags: p.flags,
      })).join('')
    : '<div class="empty-state">Контрактных связок пока нет</div>';

  const giftPairHtml = giftPairs.length
    ? giftPairs.slice(0, 8).map(p => adminRenderMonitorPair({
        title: `${p.from_name} → ${p.to_name}`,
        meta: `${p.count} подарков · стоимость предметов ${p.item_value}★`,
        flags: p.flags,
      })).join('')
    : '<div class="empty-state">Подарков пока нет</div>';

  const giftHtml = gifts.length
    ? gifts.slice(0, 8).map(g => `
        <div class="contract-monitor-row">
          <div>
            <strong>${escapeHtml(g.from_name)} → ${escapeHtml(g.to_name)}</strong>
            <span>${escapeHtml(g.item_name || g.item_code)} · ${Number(g.item_price || 0)}★</span>
          </div>
          <b>🎁</b>
        </div>
      `).join('')
    : '<div class="empty-state">Истории подарков пока нет</div>';

  return `
    <div class="contract-monitor-panel">
      <div class="contract-monitor-head">
        <div>
          <div class="admin-console-kicker">ECONOMY SURVEILLANCE</div>
          <div class="contract-monitor-title">Мониторинг контрактов и подарков</div>
        </div>
        <button class="admin-console-refresh" onclick="adminLoadContractMonitor()">Обновить</button>
      </div>
      <div class="contract-monitor-stats">${cards}</div>
      <div class="contract-monitor-note">
        Подарки не дают прямой перевод ★, но могут использоваться как обходной канал через предметы. Смотри повторяющиеся пары и пересечение “контракты + подарки”.
      </div>
      <div class="contract-monitor-grid">
        <div>
          <div class="admin-contracts-section-title danger">КОНТРАКТНЫЕ СВЯЗКИ</div>
          ${contractPairHtml}
        </div>
        <div>
          <div class="admin-contracts-section-title danger">ПОДАРКИ / ПРЕДМЕТЫ</div>
          ${giftPairHtml}
        </div>
      </div>
      <div class="admin-contracts-section-title">ПОСЛЕДНИЕ ПОДАРКИ</div>
      ${giftHtml}
    </div>
  `;
}

function adminRenderMonitorPair({title, meta, flags}) {
  const flagHtml = Array.isArray(flags) && flags.length
    ? `<div class="contract-monitor-flags">${flags.map(f => `<span>${escapeHtml(f)}</span>`).join('')}</div>`
    : '';
  return `<div class="contract-monitor-row ${flagHtml ? 'risk' : ''}">
    <div>
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(meta)}</span>
      ${flagHtml}
    </div>
    <b>${flagHtml ? '!' : 'OK'}</b>
  </div>`;
}

function adminRenderContractCard(c) {
  const STATUS_COLOR = {open:'#e67e22',accepted:'#3498db',completed:'#2ecc71',cancelled:'var(--text3)',disputed:'#e74c3c'};
  const STATUS_RU    = {open:'Открыт',accepted:'Принят',completed:'Завершён',cancelled:'Отменён',disputed:'Спор'};
  const CAT = {living:'🏠',chinese:'🀄',app:'📱',reminder:'🔔',trade:'🔄',other:'📦'};
  const sc = STATUS_COLOR[c.status] || 'var(--text3)';
  const sr = STATUS_RU[c.status] || c.status;
  const suspHtml = c.is_suspicious
    ? `<div style="font-size:9px;color:#e74c3c;font-family:monospace;margin:3px 0;">⚠ ${escapeHtml(c.suspicious_reason||'подозрительный')}</div>`
    : '';
  const resolveHtml = (c.status === 'disputed' || c.status === 'accepted')
    ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px;">
        <button onclick="adminResolveContract(${c.id},'refund_creator')" style="font-size:9px;padding:3px 7px;background:transparent;border:1px solid #e67e22;border-radius:6px;color:#e67e22;cursor:pointer;font-family:monospace;">↩ Заказчику</button>
        ${c.assignee_telegram_id ? `<button onclick="adminResolveContract(${c.id},'pay_assignee')" style="font-size:9px;padding:3px 7px;background:transparent;border:1px solid #2ecc71;border-radius:6px;color:#2ecc71;cursor:pointer;font-family:monospace;">💰 Исполнителю</button>` : ''}
        ${c.assignee_telegram_id ? `<button onclick="adminResolveContract(${c.id},'split')" style="font-size:9px;padding:3px 7px;background:transparent;border:1px solid #3498db;border-radius:6px;color:#3498db;cursor:pointer;font-family:monospace;">⇄ Раздел</button>` : ''}
        <button onclick="adminResolveContract(${c.id},'cancel_no_refund')" style="font-size:9px;padding:3px 7px;background:transparent;border:1px solid #e74c3c;border-radius:6px;color:#e74c3c;cursor:pointer;font-family:monospace;">🔥 Сжечь</button>
      </div>`
    : '';
  const removeHtml = `<button onclick="adminResolveContract(${c.id},'remove')" style="font-size:9px;padding:3px 7px;background:transparent;border:1px solid var(--border);border-radius:6px;color:var(--text3);cursor:pointer;font-family:monospace;margin-top:4px;">🗑 Удалить</button>`;

  return `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px;margin-bottom:8px;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:4px;">
      <div style="flex:1;min-width:0;">
        <span style="font-size:10px;">${CAT[c.category]||'📦'}</span>
        <strong style="font-size:12px;color:var(--text);">${escapeHtml(c.title)}</strong>
      </div>
      <div style="text-align:right;flex-shrink:0;">
        <span style="color:${sc};font-size:10px;font-family:monospace;font-weight:700;">${sr}</span>
        <div style="font-size:12px;font-weight:700;color:var(--gold);">${c.reward_stars}★</div>
      </div>
    </div>
    <div style="font-size:10px;color:var(--text3);font-family:monospace;line-height:1.5;">
      Заказчик: ${escapeHtml(c.creator_name||'—')} (${c.creator_telegram_id})
      ${c.assignee_name ? ` · Исполнитель: ${escapeHtml(c.assignee_name)} (${c.assignee_telegram_id})` : ''}
      · #{${c.id}} · ${c.created_at ? new Date(c.created_at).toLocaleDateString('ru-RU') : ''}
    </div>
    ${suspHtml}${resolveHtml}${removeHtml}
  </div>`;
}

async function adminResolveContract(id, action) {
  const labels = {
    refund_creator: 'вернуть ★ заказчику',
    pay_assignee:   'выплатить исполнителю',
    split:          'разделить поровну',
    cancel_no_refund: 'сжечь без возврата',
    remove:         'удалить контракт',
  };
  if (!confirm(`Действие: ${labels[action] || action}. Продолжить?`)) return;
  try {
    const r = await fetch(`${API_URL}/api/admin/contracts/${id}/resolve`, {
      method: 'POST',
      headers: {'Content-Type':'application/json','x-admin-id': String(currentUserId)},
      body: JSON.stringify({action}),
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.detail || 'Ошибка'); return; }
    showToast('Решение применено');
    adminLoadContracts(adminContractsActiveFilter);
  } catch (e) { showToast('Нет соединения'); }
}

/* --- ЛОГИКА РЕЙДОВОЙ СИСТЕМЫ v2.0 (Быстрый старт) --- */

// НАСТРОЙКИ
const RAID_CONFIG = {
    minPlayers: 3,
    maxPlayers: 15,
    cyberpunk: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_netwatchtheme.png?raw=true',
        title: '// NIGHT RAID // TARGET: ALPHA',
        kicker: 'MU RAID // 夜间行动',
        chips: ['Stealth', 'Team Sync', 'Risk 40%'],
        placeholderColor: '#ff003c'
    },
    genshin: {
        img: 'https://github.com/maruchoatomoshi/zhidao-protocol/blob/main/alpha_boss_genshintheme.png?raw=true',
        title: '璃月试炼 // ALPHA TRIAL',
        kicker: 'LIYUE TRIAL // 璃月试炼',
        chips: ['契约', '共鸣', '胜算 40%'],
        placeholderColor: '#dbb165'
    }
};

let raidRefreshTimer = null;
let isJoiningRaid = false;
let raidIntroToken = 0;
