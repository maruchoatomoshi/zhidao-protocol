async function loadAnnouncements() {
  const containers = Array.from(document.querySelectorAll('.announcements-content'));
  const renderToAll = (html) => containers.forEach(container => { container.innerHTML = html; });
  try {
    const r = await fetch(`${API_URL}/api/announcements`);
    const data = await r.json();
    if (!data.length) {
      renderToAll('<div class="empty-state">Объявлений пока нет</div>');
      return;
    }

    const REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '👑'];

    // Загружаем реакции для каждого объявления
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

     function formatAnnouncementText(text = '') {
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\r\n/g, '\n')
        .replace(/\n/g, '<br>');
    }
      
      return `<div class="announcement-item">
        <div class="announcement-text">${formatAnnouncementText(item.text || '')}</div>
        <div class="announcement-date">${new Date(item.created_at).toLocaleDateString('ru-RU')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:10px;">${reactionBtns}</div>
        ${isAdmin ? `<button onclick="deleteAnnouncement(${item.id})" style="background:none;border:none;color:#cc4444;cursor:pointer;font-size:11px;margin-top:6px;font-family:monospace;">[ УДАЛИТЬ ]</button>` : ''}
      </div>`;
    }).join('');

    renderToAll(html);
    document.querySelectorAll('.admin-announce-form').forEach(form => {
      form.style.display = isAdmin ? 'block' : 'none';
    });
  } catch(e) {
    renderToAll('<div class="empty-state">Ошибка загрузки</div>');
  }
}

async function reactToAnnouncement(id, emoji, btn) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
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
  if (!text) { showToast('Введите текст'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) {
      const result = await r.json();
      const sent = result.telegram_delivery && Number.isFinite(Number(result.telegram_delivery.sent))
        ? Number(result.telegram_delivery.sent)
        : null;
      showToast(sent === null ? '✅ Опубликовано!' : `✅ Опубликовано! Бот отправил: ${sent}`);
      ['announceText', 'announceTextMore'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      loadAnnouncements();
    }
  } catch(e) { showToast('Ошибка'); }
}

async function addAnnouncementAdmin() {
  const text = document.getElementById('announceTextAdmin').value;
  if (!text) { showToast('Введите текст'); return; }
  try {
    const r = await fetch(`${API_URL}/api/announcements`,{method:'POST',headers:{'Content-Type':'application/json','x-admin-id':currentUserId},body:JSON.stringify({text})});
    if (r.ok) {
      const result = await r.json();
      const sent = result.telegram_delivery && Number.isFinite(Number(result.telegram_delivery.sent))
        ? Number(result.telegram_delivery.sent)
        : null;
      showToast(sent === null ? '✅ Опубликовано!' : `✅ Опубликовано! Бот отправил: ${sent}`);
      document.getElementById('announceTextAdmin').value='';
      loadAnnouncements();
    }
  } catch(e) { showToast('Ошибка'); }
}

async function deleteAnnouncement(id) {
  try { await fetch(`${API_URL}/api/announcements/${id}`,{method:'DELETE',headers:{'x-admin-id':currentUserId}}); loadAnnouncements(); } catch(e) {}
}

// ===== АЧИВКИ =====
