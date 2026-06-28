// Перекличка для игроков: статус подъёма/отбоя за сегодня + запрос отгула на вечер.

const USER_PRESENCE_LABELS = {
  pending: 'Ожидание отметки',
  confirmed: 'Подтверждено',
  free_time: 'Свободное время',
  leave_requested: 'Заявка на отгул отправлена',
  admin_approved: 'Отгул разрешён',
  leave_rejected: 'Отгул отклонён',
  needs_attention: 'Требует внимания',
  penalized: 'Штраф: не подтверждено',
  skipped: 'Отметка отменена',
};

async function fetchUserPresenceStatus(checkType) {
  if (!currentUserId) return null;
  try {
    const r = await fetch(`${API_URL}/api/presence/status?check_type=${checkType}&telegram_id=${currentUserId}`);
    if (!r.ok) return null;
    const data = await r.json();
    return data.check || null;
  } catch (e) { return null; }
}

function userPresenceCard(kicker, hanzi, title, desc, check, extraHtml) {
  const status = check ? check.status : null;
  const label = status ? (USER_PRESENCE_LABELS[status] || status) : 'Перекличка не запускалась';
  const badgeColor = {
    confirmed: '#32d872', free_time: '#32d872', admin_approved: '#32d872',
    pending: 'var(--gold)', leave_requested: 'var(--gold)', needs_attention: 'var(--gold)',
    penalized: '#ff5a5a', leave_rejected: '#ff5a5a', skipped: 'var(--text3)',
  }[status] || 'var(--text3)';

  return `<div class="admin-presence-card">
    <div class="admin-presence-icon">${hanzi}</div>
    <div class="admin-presence-main">
      <div class="admin-presence-kicker">${kicker}</div>
      <div class="admin-presence-title">${title}</div>
      <div class="admin-presence-desc">${desc}</div>
    </div>
    <div class="admin-presence-row-badge" style="border-color:${badgeColor};background:transparent;color:${badgeColor};display:inline-flex;margin-bottom:10px;">${escapeHtml(label)}</div>
    ${check && check.note ? `<div class="admin-presence-meta" style="margin-bottom:8px;">«${escapeHtml(check.note)}»</div>` : ''}
    ${extraHtml || ''}
  </div>`;
}

async function loadUserPresence() {
  const root = document.getElementById('userPresenceRoot');
  if (!root) return;
  if (!currentUserId) { root.innerHTML = '<div class="empty-state">Откройте через Telegram бота</div>'; return; }
  root.innerHTML = '<div class="empty-state">Загрузка...</div>';

  const [morning, evening] = await Promise.all([
    fetchUserPresenceStatus('morning'),
    fetchUserPresenceStatus('evening'),
  ]);

  const canRequestLeave = evening && ['confirmed', 'free_time', 'leave_rejected'].includes(evening.status);
  const leaveForm = canRequestLeave ? `
    <div style="margin-top:4px;">
      <textarea id="presenceLeaveReason" placeholder="Куда и почему: погулять, сижу у друзей, спорт..." style="width:100%;min-height:54px;background:color-mix(in srgb, var(--bg3) 70%, transparent);border:1px solid var(--border);border-radius:10px;color:var(--text);font-family:monospace;font-size:11px;padding:8px;resize:vertical;"></textarea>
      <button class="admin-presence-btn primary" style="width:100%;margin-top:6px;" onclick="submitPresenceLeaveRequest()">🙋 Запросить отгул</button>
    </div>` : '';

  root.innerHTML = `
    <div class="admin-presence-grid">
      ${userPresenceCard('УТРО // 起床', '晨', 'Подъём', 'Подтверждение через Telegram-бота.', morning)}
      ${userPresenceCard('ВЕЧЕР // 晚点名', '夜', 'Комнаты / отбой', 'Если нужно задержаться — запроси отгул ниже.', evening, leaveForm)}
    </div>
  `;
}

async function submitPresenceLeaveRequest() {
  const textarea = document.getElementById('presenceLeaveReason');
  const reason = (textarea ? textarea.value : '').trim();
  if (!reason) { showToast('Укажи причину'); return; }
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }

  const ok = await showConfirmDialog({
    title: 'Запросить отгул?',
    message: `Причина: «${reason}». Заявку увидят админы и одобрят/отклонят её.`,
    confirmText: 'Отправить',
  });
  if (!ok) return;

  try {
    const r = await fetch(`${API_URL}/api/presence/confirm`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, check_type: 'evening', action: 'request_leave', note: reason}),
    });
    if (r.ok) {
      showToast('📨 Заявка на отгул отправлена');
      loadUserPresence();
    } else {
      showToast('Ошибка отправки заявки');
    }
  } catch (e) { showToast('Ошибка соединения'); }
}
