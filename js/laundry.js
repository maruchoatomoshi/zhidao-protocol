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
