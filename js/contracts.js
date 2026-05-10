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

let contractsActiveTab = 'open';
let contractsRefreshTimer = null;
let contractsOpenLoading = false;
let contractsMyLoading = false;

// Called by showPage() when navigating to contracts
function openContractsPage() {
  const bw = document.getElementById('contractsBlackwallMsg');
  const main = document.getElementById('contractsMain');
  if (bw) bw.style.display = 'none';
  if (main) main.style.display = 'block';
  startContractsAutoRefresh();
  showContractsTab(contractsActiveTab || 'open');
}

function isContractsPageActive() {
  const page = document.getElementById('page-contracts');
  return !!page && page.classList.contains('active') && document.visibilityState !== 'hidden';
}

function startContractsAutoRefresh() {
  if (contractsRefreshTimer) return;
  contractsRefreshTimer = window.setInterval(() => {
    if (!isContractsPageActive()) {
      stopContractsAutoRefresh();
      return;
    }
    refreshContractsActiveTab({ silent: true });
  }, 6000);
}

function stopContractsAutoRefresh() {
  if (!contractsRefreshTimer) return;
  window.clearInterval(contractsRefreshTimer);
  contractsRefreshTimer = null;
}

function refreshContractsActiveTab(options = {}) {
  if (contractsActiveTab === 'my') {
    return loadMyContracts(options);
  }
  return loadOpenContracts(options);
}

function refreshContractsAfterAction() {
  loadOpenContracts({ silent: true });
  if (currentUserId) loadMyContracts({ silent: true });
}

function showContractsTab(tab) {
  const openEl = document.getElementById('contracts-tab-open');
  const myEl   = document.getElementById('contracts-tab-my');
  const btnOpen = document.getElementById('ctab-open');
  const btnMy   = document.getElementById('ctab-my');
  if (!openEl || !myEl) return;
  contractsActiveTab = tab === 'my' ? 'my' : 'open';
  startContractsAutoRefresh();

  if (contractsActiveTab === 'open') {
    openEl.style.display = 'block';
    myEl.style.display = 'none';
    if (btnOpen) btnOpen.classList.add('active');
    if (btnMy) btnMy.classList.remove('active');
    loadOpenContracts();
  } else {
    openEl.style.display = 'none';
    myEl.style.display = 'block';
    if (btnMy) btnMy.classList.add('active');
    if (btnOpen) btnOpen.classList.remove('active');
    loadMyContracts();
  }
}

function syncContractsBlackwallVisible(isBlocked, msg) {
  const bw = document.getElementById('contractsBlackwallMsg');
  const main = document.getElementById('contractsMain');
  if (bw) {
    bw.style.display = isBlocked ? 'block' : 'none';
    if (isBlocked && msg) {
      const textEl = bw.querySelector('.contracts-blackwall-text') || bw.querySelector('div:last-child');
      if (textEl) textEl.textContent = msg;
    }
  }
  if (main) main.style.display = isBlocked ? 'none' : 'block';
}

async function loadOpenContracts(options = {}) {
  const el = document.getElementById('contractsOpenList');
  if (!el) return;
  if (contractsOpenLoading) return;
  contractsOpenLoading = true;
  const silent = !!options.silent;
  if (!silent || !el.innerHTML.trim()) {
    el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  }
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
    syncContractsBlackwallVisible(false);
    if (!data.length) { el.innerHTML = '<div class="empty-state">Открытых поручений нет</div>'; return; }
    el.innerHTML = data.map(c => renderContractCard(c)).join('');
  } catch (e) {
    if (!silent || !el.innerHTML.trim()) {
      el.innerHTML = '<div class="empty-state">Нет соединения</div>';
    }
  } finally {
    contractsOpenLoading = false;
  }
}

async function loadMyContracts(options = {}) {
  const el = document.getElementById('contractsMyList');
  if (!el || !currentUserId) {
    if (el) el.innerHTML = '<div class="empty-state">Войди в систему</div>';
    return;
  }
  if (contractsMyLoading) return;
  contractsMyLoading = true;
  const silent = !!options.silent;
  if (!silent || !el.innerHTML.trim()) {
    el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  }
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
    syncContractsBlackwallVisible(false);
    if (!data.length) { el.innerHTML = '<div class="empty-state">У тебя пока нет контрактов</div>'; return; }
    el.innerHTML = data.map(c => renderContractCard(c, true)).join('');
  } catch (e) {
    if (!silent || !el.innerHTML.trim()) {
      el.innerHTML = '<div class="empty-state">Нет соединения</div>';
    }
  } finally {
    contractsMyLoading = false;
  }
}

function showContractsBlackwall(msg) {
  syncContractsBlackwallVisible(true, msg);
}

function renderContractCard(c, showActions) {
  const isMe = currentUserId && c.creator_telegram_id === currentUserId;
  const isAssignee = currentUserId && c.assignee_telegram_id === currentUserId;
  const statusLabel = CONTRACT_STATUS_LABELS[c.status] || c.status;
  const statusColor = CONTRACT_STATUS_COLORS[c.status] || 'var(--text3)';
  const catLabel = CONTRACT_CATEGORY_LABELS[c.category] || c.category;
  const suspHtml = c.is_suspicious
    ? `<div class="contract-warning">⚠ Подозрительный: ${escapeHtml(c.suspicious_reason || '')}</div>`
    : '';

  let actionsHtml = '';
  if (showActions || true) {
    if (c.status === 'open' && !isMe && currentUserId) {
      actionsHtml = `<button class="contract-action-btn accept" onclick="acceptContract(${c.id})">
        Принять поручение
      </button>`;
    }
    if (c.status === 'open' && isMe) {
      actionsHtml = `<button class="contract-action-btn ghost" onclick="cancelContract(${c.id})">
        Отменить (вернуть ★)
      </button>`;
    }
    if (c.status === 'accepted' && isMe) {
      actionsHtml = `
        <button class="contract-action-btn complete" onclick="completeContract(${c.id})">
          ✓ Подтвердить выполнение
        </button>
        <button class="contract-action-btn dispute" onclick="disputeContract(${c.id})">
          Открыть спор
        </button>`;
    }
    if (c.status === 'accepted' && isAssignee && !isMe) {
      actionsHtml = `<button class="contract-action-btn dispute" onclick="disputeContract(${c.id})">
        Открыть спор
      </button>`;
    }
  }

  const assigneeHtml = c.assignee_name
    ? `<span class="contract-person">Исполнитель: ${escapeHtml(c.assignee_name)}</span>`
    : '';

  return `<div class="contract-card status-${escapeHtml(c.status || 'unknown')}">
    <div class="contract-card-head">
      <div class="contract-card-titlebox">
        <div class="contract-card-title">${escapeHtml(c.title)}</div>
        <div class="contract-category">${catLabel}</div>
      </div>
      <div class="contract-reward">
        <div class="contract-reward-main">${c.reward_stars}★</div>
        <div class="contract-reward-sub">→ ${c.payout_stars}★ исп.</div>
      </div>
    </div>
    <div class="contract-description">${escapeHtml(c.description)}</div>
    <div class="contract-meta">
      <span class="contract-status" style="--contract-status-color:${statusColor};">${statusLabel}</span>
      <span class="contract-person">Заказчик: ${escapeHtml(c.creator_name)}${isMe ? ' (ты)' : ''}</span>
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
    showContractsTab('my');
    refreshContractsAfterAction();
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
    refreshContractsAfterAction();
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
    refreshContractsAfterAction();
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
    refreshContractsAfterAction();
  } catch (e) { alert('Нет соединения'); }
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    stopContractsAutoRefresh();
  } else if (isContractsPageActive()) {
    startContractsAutoRefresh();
    refreshContractsActiveTab({ silent: true });
  }
});
