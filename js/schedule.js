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
  if (!day || !time || !subject || !location) { showToast('Заполните все поля'); return; }
  try {
    const r = await fetch(`${API_URL}/api/schedule`, {
      method:'POST', headers:{'Content-Type':'application/json','x-admin-id':currentUserId},
      body: JSON.stringify({day,time,subject,location})
    });
    if (r.ok) {
      showToast('✅ Добавлено!');
      ['schDay','schTime','schSubject','schLocation','adminSchDay','adminSchTime','adminSchSubject','adminSchLocation']
        .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
      loadSchedule();
    }
  } catch(e) { showToast('Ошибка'); }
}

async function deleteSchedule(id) {
  try { await fetch(`${API_URL}/api/schedule/${id}`, {method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadSchedule(); } catch(e) {}
}

// ===== РЕЙТИНГ =====
// ===== ТЕМЫ =====
