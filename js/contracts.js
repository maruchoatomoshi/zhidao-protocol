// ===== ДОСКА ПОРУЧЕНИЙ =====

const CONTRACT_CATEGORY_LABELS = {
  living:   '🏠 Быт',
  chinese:  '🀄 Китайский',
  app:      '📱 Приложение',
  reminder: '🔔 Напоминание',
  trade:    '🔄 Обмен',
  other:    '📦 Другое',
};

const CONTRACT_STATUS_LABELS = {
  open:      'Открыт',
  accepted:  'Принят',
  completed: 'Выполнен',
  cancelled: 'Отменён',
  disputed:  'Спор',
};

const CONTRACT_STATUS_COLORS = {
  open:      '#e67e22',
  accepted:  '#3498db',
  completed: '#2ecc71',
  cancelled: 'var(--text3)',
  disputed:  '#e74c3c',
};

// Called by showPage() when navigating to contracts
function openContractsPage() {
  loadOpenContracts();
  showContractsTab('open');
}

function showContractsTab(tab) {
  const openEl = document.getElementById('contracts-tab-open');
  const myEl   = document.getElementById('contracts-tab-my');
  const btnOpen = document.getElementById('ctab-open');
  const btnMy   = document.getElementById('ctab-my');
  if (!openEl || !myEl) return;

  if (tab === 'open') {
    openEl.style.display = 'block';
    myEl.style.display = 'none';
    if (btnOpen) {
      btnOpen.style.background = 'rgba(230,126,34,0.15)';
      btnOpen.style.color = '#e67e22';
      btnOpen.style.border = '1px solid rgba(230,126,34,0.5)';
    }
    if (btnMy) {
      btnMy.style.background = 'transparent';
      btnMy.style.color = 'var(--text3)';
      btnMy.style.border = '1px solid var(--border)';
    }
    loadOpenContracts();
  } else {
    openEl.style.display = 'none';
    myEl.style.display = 'block';
    if (btnMy) {
      btnMy.style.background = 'rgba(230,126,34,0.15)';
      btnMy.style.color = '#e67e22';
      btnMy.style.border = '1px solid rgba(230,126,34,0.5)';
    }
    if (btnOpen) {
      btnOpen.style.background = 'transparent';
      btnOpen.style.color = 'var(--text3)';
      btnOpen.style.border = '1px solid var(--border)';
    }
    loadMyContracts();
  }
}

async function loadOpenContracts() {
  const el = document.getElementById('contractsOpenList');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const r = await fetch(`${API_URL}/api/contracts`, {
      headers: currentUserId ? { 'X-Telegram-Id': String(currentUserId) } : {},
    });
    if (r.status === 403) {
      const d = await r.json().catch(() => ({}));
      showContractsBlackwall(d.detail || 'BlackWall активен');
      return;
    }
    const data = await r.json();
    if (!r.ok) { el.innerHTML = `<div class="empty-state">${escapeHtml(data.detail || 'Ошибка')}</div>`; return; }
    if (!data.length) { el.innerHTML = '<div class="empty-state">Открытых поручений нет</div>'; return; }
    el.innerHTML = data.map(c => renderContractCard(c)).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Нет соединения</div>';
  }
}

async function loadMyContracts() {
  const el = document.getElementById('contractsMyList');
  if (!el || !currentUserId) {
    if (el) el.innerHTML = '<div class="empty-state">Войди в систему</div>';
    return;
  }
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const r = await fetch(`${API_URL}/api/contracts/my`, {
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    if (r.status === 403) {
      const d = await r.json().catch(() => ({}));
      showContractsBlackwall(d.detail || 'BlackWall активен');
      return;
    }
    const data = await r.json();
    if (!r.ok) { el.innerHTML = `<div class="empty-state">${escapeHtml(data.detail || 'Ошибка')}</div>`; return; }
    if (!data.length) { el.innerHTML = '<div class="empty-state">У тебя пока нет контрактов</div>'; return; }
    el.innerHTML = data.map(c => renderContractCard(c, true)).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Нет соединения</div>';
  }
}

function showContractsBlackwall(msg) {
  const bw = document.getElementById('contractsBlackwallMsg');
  const main = document.getElementById('contractsMain');
  if (bw) { bw.style.display = 'block'; if (msg) bw.querySelector('div:last-child').textContent = msg; }
  if (main) main.style.display = 'none';
}

function renderContractCard(c, showActions) {
  const isMe = currentUserId && c.creator_telegram_id === currentUserId;
  const isAssignee = currentUserId && c.assignee_telegram_id === currentUserId;
  const statusLabel = CONTRACT_STATUS_LABELS[c.status] || c.status;
  const statusColor = CONTRACT_STATUS_COLORS[c.status] || 'var(--text3)';
  const catLabel = CONTRACT_CATEGORY_LABELS[c.category] || c.category;
  const suspHtml = c.is_suspicious
    ? `<div style="font-size:9px;color:#e74c3c;font-family:monospace;margin-top:4px;">⚠ Подозрительный: ${escapeHtml(c.suspicious_reason || '')}</div>`
    : '';

  let actionsHtml = '';
  if (showActions || true) {
    if (c.status === 'open' && !isMe && currentUserId) {
      actionsHtml = `<button onclick="acceptContract(${c.id})"
        style="width:100%;margin-top:10px;padding:10px;background:rgba(52,152,219,0.15);
               border:1px solid rgba(52,152,219,0.4);border-radius:10px;
               color:#3498db;font-family:monospace;font-size:11px;font-weight:700;cursor:pointer;">
        Принять поручение
      </button>`;
    }
    if (c.status === 'open' && isMe) {
      actionsHtml = `<button onclick="cancelContract(${c.id})"
        style="width:100%;margin-top:10px;padding:9px;background:transparent;
               border:1px solid var(--border);border-radius:10px;
               color:var(--text3);font-family:monospace;font-size:10px;cursor:pointer;">
        Отменить (вернуть ★)
      </button>`;
    }
    if (c.status === 'accepted' && isMe) {
      actionsHtml = `
        <button onclick="completeContract(${c.id})"
          style="width:100%;margin-top:10px;padding:10px;background:rgba(46,204,113,0.15);
                 border:1px solid rgba(46,204,113,0.4);border-radius:10px;
                 color:#2ecc71;font-family:monospace;font-size:11px;font-weight:700;cursor:pointer;">
          ✓ Подтвердить выполнение
        </button>
        <button onclick="disputeContract(${c.id})"
          style="width:100%;margin-top:6px;padding:9px;background:transparent;
                 border:1px solid rgba(231,76,60,0.3);border-radius:10px;
                 color:#e74c3c;font-family:monospace;font-size:10px;cursor:pointer;">
          Открыть спор
        </button>`;
    }
    if (c.status === 'accepted' && isAssignee && !isMe) {
      actionsHtml = `<button onclick="disputeContract(${c.id})"
        style="width:100%;margin-top:10px;padding:9px;background:transparent;
               border:1px solid rgba(231,76,60,0.3);border-radius:10px;
               color:#e74c3c;font-family:monospace;font-size:10px;cursor:pointer;">
        Открыть спор
      </button>`;
    }
  }

  const assigneeHtml = c.assignee_name
    ? `<span style="color:var(--text2);">Исполнитель: ${escapeHtml(c.assignee_name)}</span>`
    : '';

  return `<div class="diary-card" style="margin-bottom:10px;">
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:700;color:var(--text);word-break:break-word;">${escapeHtml(c.title)}</div>
        <div style="font-size:10px;color:var(--text3);font-family:monospace;margin-top:2px;">${catLabel}</div>
      </div>
      <div style="text-align:right;flex-shrink:0;">
        <div style="font-size:15px;font-weight:700;color:var(--gold);">${c.reward_stars}★</div>
        <div style="font-size:9px;color:var(--text3);font-family:monospace;">→ ${c.payout_stars}★ исп.</div>
      </div>
    </div>
    <div style="font-size:11px;color:var(--text2);margin-bottom:8px;line-height:1.5;">${escapeHtml(c.description)}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:10px;font-family:monospace;color:var(--text3);">
      <span style="color:${statusColor};font-weight:700;">${statusLabel}</span>
      <span>Заказчик: ${escapeHtml(c.creator_name)}${isMe ? ' (ты)' : ''}</span>
      ${assigneeHtml}
    </div>
    ${suspHtml}
    ${actionsHtml}
  </div>`;
}

// ===== CREATE MODAL =====

function openCreateContractModal() {
  const modal = document.getElementById('createContractModal');
  if (!modal) return;
  modal.style.display = 'flex';
  const errEl = document.getElementById('contractCreateError');
  if (errEl) errEl.style.display = 'none';
  updateContractFeePreview();
}

function closeCreateContractModal() {
  const modal = document.getElementById('createContractModal');
  if (modal) modal.style.display = 'none';
}

function updateContractFeePreview() {
  const rewardEl = document.getElementById('contractReward');
  const previewEl = document.getElementById('contractFeePreview');
  if (!rewardEl || !previewEl) return;
  const reward = parseInt(rewardEl.value) || 0;
  const fee = Math.max(2, Math.round(reward * 0.1));
  const payout = reward - fee;
  if (reward >= 5 && reward <= 50) {
    previewEl.textContent = `Исполнитель получит: ${payout}★ · Комиссия Сетевого Дозора: ${fee}★`;
    previewEl.style.color = 'var(--text3)';
  } else {
    previewEl.textContent = 'Награда должна быть от 5 до 50 ★';
    previewEl.style.color = '#e74c3c';
  }
}

async function submitCreateContract() {
  const title    = (document.getElementById('contractTitle')?.value || '').trim();
  const desc     = (document.getElementById('contractDesc')?.value || '').trim();
  const category = document.getElementById('contractCategory')?.value || 'other';
  const reward   = parseInt(document.getElementById('contractReward')?.value) || 0;
  const errEl    = document.getElementById('contractCreateError');

  const showErr = (msg) => {
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
  };

  if (!currentUserId) { showErr('Войди в систему'); return; }
  if (title.length < 3) { showErr('Название слишком короткое'); return; }
  if (desc.length < 5)  { showErr('Описание слишком короткое'); return; }
  if (reward < 5 || reward > 50) { showErr('Награда: от 5 до 50 ★'); return; }

  try {
    const r = await fetch(`${API_URL}/api/contracts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Telegram-Id': String(currentUserId) },
      body: JSON.stringify({ title, description: desc, category, reward_stars: reward }),
    });
    const data = await r.json();
    if (!r.ok) { showErr(data.detail || 'Ошибка создания'); return; }
    closeCreateContractModal();
    // Update local balance display
    currentPoints = Math.max(0, currentPoints - reward);
    updatePoints();
    showContractsTab('my');
  } catch (e) {
    showErr('Нет соединения');
  }
}

// ===== CONTRACT ACTIONS =====

async function acceptContract(id) {
  if (!currentUserId) return;
  try {
    const r = await fetch(`${API_URL}/api/contracts/${id}/accept`, {
      method: 'POST',
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    const data = await r.json();
    if (!r.ok) { alert(data.detail || 'Ошибка'); return; }
    loadOpenContracts();
  } catch (e) { alert('Нет соединения'); }
}

async function completeContract(id) {
  if (!currentUserId) return;
  if (!confirm('Подтвердить выполнение поручения? Исполнитель получит ★.')) return;
  try {
    const r = await fetch(`${API_URL}/api/contracts/${id}/complete`, {
      method: 'POST',
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    const data = await r.json();
    if (!r.ok) { alert(data.detail || 'Ошибка'); return; }
    loadMyContracts();
  } catch (e) { alert('Нет соединения'); }
}

async function cancelContract(id) {
  if (!currentUserId) return;
  if (!confirm('Отменить поручение? Звёзды вернутся на твой баланс.')) return;
  try {
    const r = await fetch(`${API_URL}/api/contracts/${id}/cancel`, {
      method: 'POST',
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    const data = await r.json();
    if (!r.ok) { alert(data.detail || 'Ошибка'); return; }
    if (data.refunded) {
      currentPoints += data.refunded;
      updatePoints();
    }
    loadOpenContracts();
    loadMyContracts();
  } catch (e) { alert('Нет соединения'); }
}

async function disputeContract(id) {
  if (!currentUserId) return;
  if (!confirm('Открыть спор? Администратор примет решение.')) return;
  try {
    const r = await fetch(`${API_URL}/api/contracts/${id}/dispute`, {
      method: 'POST',
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    const data = await r.json();
    if (!r.ok) { alert(data.detail || 'Ошибка'); return; }
    loadMyContracts();
  } catch (e) { alert('Нет соединения'); }
}
