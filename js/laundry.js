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
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/water/schedule/${slotId}/book`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    if (r.ok) { try{tg.HapticFeedback.notificationOccurred('success');}catch(e){} showToast('✅ Записаны на набор воды!'); loadWaterSchedule(); }
    else { const e=await r.json(); showToast(e.detail==='Slot full'?'Мест нет':'Вы уже записаны'); }
  } catch(e) { showToast('Ошибка'); }
}

async function cancelWaterSlot(slotId) {
  const ok = await showConfirmDialog({title:'Отменить запись?',message:'Слот снова станет свободным.',confirmText:'Отменить запись',danger:true});
  if (!ok) return;
  try {
    const r = await fetch(`${API_URL}/api/water/schedule/${slotId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    showToast(r.ok ? 'Запись отменена' : 'Не удалось отменить');
    loadWaterSchedule();
  } catch(e) { showToast('Нет соединения'); }
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
        clickable = `onclick="cancelLaundrySlot(${slot.id})"`;
      } else if (!isFull) {
        icon = `<i class="ti ti-wash" style="color:#60b4d4;font-size:18px;"></i>`;
        statusText = `<span style="color:#60b4d4;">Свободно</span>`;
        clickable = `onclick="bookLaundrySlot(${slot.id})"`;
      } else {
        icon = `<i class="ti ti-circle-x" style="color:var(--text3);font-size:18px;"></i>`;
        statusText = `<span style="color:var(--text3);">Занято</span>`;
        clickable = '';
      }
      return `<div ${clickable} style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);${clickable?'cursor:pointer;':''}">
        ${icon}
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.day} · ${slot.time}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.assignee ? `К кому подходить: ${slot.assignee}` : ''}</div>
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
      const booked = slot.booked || 0;
      const bookings = slot.bookings || [];
      const isMe = bookings.some(b => b.telegram_id === currentUserId);
      const scheduleText = [slot.day, slot.time].filter(Boolean).join(' · ');
      let icon, statusText, clickable;
      if (isMe) {
        icon = `<i class="ti ti-circle-check" style="color:#2ecc71;font-size:18px;"></i>`;
        statusText = `<span style="color:#2ecc71;">Ваша запись</span>`;
        clickable = `onclick="cancelWaterSlot(${slot.id})"`;
      } else {
        icon = `<i class="ti ti-droplet" style="color:#60b4d4;font-size:18px;"></i>`;
        statusText = `<span style="color:#60b4d4;">Свободно</span>`;
        clickable = `onclick="bookWaterSlot(${slot.id})"`;
      }
      return `<div ${clickable} style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);${clickable?'cursor:pointer;':''}">
        ${icon}
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;color:var(--text);">${slot.floor ? `Этаж ${slot.floor}` : 'Вода'}${scheduleText ? ` · ${scheduleText}` : ''}</div>
          <div style="font-size:10px;color:var(--text2);margin-top:1px;">${slot.assignee ? `К кому подходить: ${slot.assignee}` : ''}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:10px;">${statusText}</div>
          <div style="font-size:9px;color:var(--text3);font-family:monospace;margin-top:2px;">${booked} записано</div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { container.innerHTML = '<div class="empty-state">Ошибка загрузки</div>'; }
}

async function bookLaundrySlot(slotId) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule/${slotId}/book`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    if (r.ok) {
      try{tg.HapticFeedback.notificationOccurred('success');}catch(e){}
      const data = await r.json();
      if (typeof handleDiaryUnlocks === 'function') handleDiaryUnlocks(data.diary_unlocked);
      showToast('✅ Записаны на стирку!'); loadLaundrySchedule();
    }
    else { const e=await r.json(); showToast(e.detail==='Slot full'?'Мест нет':'Слот занят'); }
  } catch(e) { showToast('Ошибка'); }
}

async function cancelLaundrySlot(slotId) {
  const ok = await showConfirmDialog({title:'Отменить запись?',message:'Слот снова станет свободным.',confirmText:'Отменить запись',danger:true});
  if (!ok) return;
  try {
    const r = await fetch(`${API_URL}/api/laundry/schedule/${slotId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:currentUserId})});
    showToast(r.ok ? 'Запись отменена' : 'Не удалось отменить');
    loadLaundrySchedule();
  } catch(e) { showToast('Нет соединения'); }
}

// Алиас старого имени — всё ещё вызывается из admin.js и cancelLaundry().
async function loadLaundry() { loadLaundrySchedule(); }

async function cancelLaundry(id) {
  try {
    const r = await fetch(`${API_URL}/api/laundry/${id}`,{method:'DELETE',headers:{'x-telegram-id':currentUserId}});
    showToast(r.ok ? 'Запись отменена' : 'Не удалось отменить');
    loadLaundry();
  } catch(e) { showToast('Ошибка'); }
}

// ===== ОБЪЯВЛЕНИЯ =====
