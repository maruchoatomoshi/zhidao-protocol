// ===== ДОСКА ПОРУЧЕНИЙ =====

const CONTRACT_CATEGORY_LABELS = {
  living:   '🏠 Быт',
  chinese:  '🀄 Китайский',
  app:      '📱 Приложение',
  reminder: '🔔 Напоминание',
  trade:    '🔄 Обмен',
  other:    '📦 Другое',
};

const CONTRACT_MIN_REWARD = 5;
const CONTRACT_MAX_REWARD = 50;
const CONTRACT_ADMIN_MAX_REWARD = 100;

const CONTRACT_STATUS_LABELS = {
  open:      'Ждёт исполнителя',
  accepted:  'В работе',
  completed: 'Завершено',
  cancelled: 'Отменён',
  disputed:  'Спор',
};

const CONTRACT_STATUS_HINTS = {
  open:      'Можно принять поручение',
  accepted:  'Исполнитель взял задачу',
  completed: 'Награда выплачена',
  cancelled: 'Поручение закрыто',
  disputed:  'Нужна помощь администратора',
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
let contractsCategoryFilter = 'all';
let contractsOpenCache = [];
let contractsMyCache = [];

async function contractFetch(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

function getCurrentContractUserName() {
  return (document.getElementById('username')?.textContent || tg?.initDataUnsafe?.user?.first_name || 'Игрок').trim();
}

function updateContractInCaches(id, patch = {}) {
  let updatedContract = null;
  const updateOne = (contract) => {
    if (!contract || Number(contract.id) !== Number(id)) return contract;
    updatedContract = { ...contract, ...patch };
    return updatedContract;
  };
  contractsOpenCache = contractsOpenCache.map(updateOne).filter(c => c.status === 'open');
  contractsMyCache = contractsMyCache.map(updateOne);
  if (updatedContract && !contractsMyCache.some(c => Number(c.id) === Number(id))) {
    contractsMyCache.unshift(updatedContract);
  }
  renderContractsFromCache();
  return updatedContract;
}

function removeContractFromCaches(id) {
  contractsOpenCache = contractsOpenCache.filter(c => Number(c.id) !== Number(id));
  contractsMyCache = contractsMyCache.filter(c => Number(c.id) !== Number(id));
  renderContractsFromCache();
}

function switchContractsTabLocal(tab) {
  contractsActiveTab = ['my', 'disputed'].includes(tab) ? tab : 'open';
  const openEl = document.getElementById('contracts-tab-open');
  const myEl = document.getElementById('contracts-tab-my');
  const disputedEl = document.getElementById('contracts-tab-disputed');
  const btnOpen = document.getElementById('ctab-open');
  const btnMy = document.getElementById('ctab-my');
  const btnDisputed = document.getElementById('ctab-disputed');
  if (openEl) openEl.style.display = contractsActiveTab === 'open' ? 'block' : 'none';
  if (myEl) myEl.style.display = contractsActiveTab === 'my' ? 'block' : 'none';
  if (disputedEl) disputedEl.style.display = contractsActiveTab === 'disputed' ? 'block' : 'none';
  if (btnOpen) btnOpen.classList.toggle('active', contractsActiveTab === 'open');
  if (btnMy) btnMy.classList.toggle('active', contractsActiveTab === 'my');
  if (btnDisputed) btnDisputed.classList.toggle('active', contractsActiveTab === 'disputed');
  renderContractsFromCache();
}

function getContractMaxReward() {
  return isAdmin ? CONTRACT_ADMIN_MAX_REWARD : CONTRACT_MAX_REWARD;
}

function isAdminContractCreator(contract) {
  const creatorId = Number(contract?.creator_telegram_id || 0);
  return Boolean(contract?.creator_is_admin) || ADMIN_IDS.includes(creatorId);
}

function syncContractRewardLimits() {
  const maxReward = getContractMaxReward();
  const label = document.getElementById('contractRewardLabel');
  const input = document.getElementById('contractReward');
  const badge = document.getElementById('contractsRewardLimitBadge');
  if (label) label.textContent = `НАГРАДА (${CONTRACT_MIN_REWARD}–${maxReward} ★)`;
  if (badge) badge.textContent = `${CONTRACT_MIN_REWARD}–${maxReward}★`;
  if (input) input.max = String(maxReward);
}

// Called by showPage() when navigating to contracts
function openContractsPage() {
  syncContractRewardLimits();
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
  if (contractsActiveTab === 'my' || contractsActiveTab === 'disputed') {
    return loadMyContracts(options);
  }
  return loadOpenContracts(options);
}

function refreshContractsAfterAction() {
  loadOpenContracts({ silent: true });
  if (currentUserId) loadMyContracts({ silent: true });
}

function setContractsCategoryFilter(category) {
  contractsCategoryFilter = CONTRACT_CATEGORY_LABELS[category] ? category : 'all';
  syncContractsCategoryFilterUI();
  renderContractsFromCache();
}

function syncContractsCategoryFilterUI() {
  document.querySelectorAll('.contracts-filter-chip').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.category === contractsCategoryFilter);
  });
}

function filterContractsByCategory(list) {
  if (contractsCategoryFilter === 'all') return list || [];
  return (list || []).filter(c => c.category === contractsCategoryFilter);
}

function renderContractsEmpty(message, hint) {
  return `<div class="contracts-empty">
    <div class="contracts-empty-icon">契</div>
    <div class="contracts-empty-title">${escapeHtml(message)}</div>
    ${hint ? `<div class="contracts-empty-hint">${escapeHtml(hint)}</div>` : ''}
  </div>`;
}

function renderContractsList(list, options = {}) {
  const filtered = filterContractsByCategory(list);
  if (!filtered.length) {
    const hasFilter = contractsCategoryFilter !== 'all';
    return renderContractsEmpty(
      hasFilter ? 'В этой категории пока пусто' : (options.emptyTitle || 'Поручений пока нет'),
      hasFilter ? 'Смени фильтр или создай новое поручение.' : (options.emptyHint || 'Можно создать первое поручение и предложить награду в ★.')
    );
  }
  return filtered.map(c => renderContractCard(c, !!options.showActions)).join('');
}

function renderMyContractsList(list) {
  const filtered = filterContractsByCategory(list);
  if (!filtered.length) {
    const hasFilter = contractsCategoryFilter !== 'all';
    return renderContractsEmpty(
      hasFilter ? 'Нет твоих поручений в этой категории' : 'У тебя пока нет контрактов',
      hasFilter ? 'Выбери другую категорию или открой общий список.' : 'Создай поручение или прими задачу другого участника.'
    );
  }
  const asCreator = filtered.filter(c => c.creator_telegram_id === currentUserId);
  const asAssignee = filtered.filter(c => c.assignee_telegram_id === currentUserId);
  let html = '';
  if (asCreator.length) {
    html += `<div class="contracts-section-label">Я заказчик</div>` + asCreator.map(c => renderContractCard(c, true)).join('');
  }
  if (asAssignee.length) {
    html += `<div class="contracts-section-label">Я исполнитель</div>` + asAssignee.map(c => renderContractCard(c, true)).join('');
  }
  return html || renderContractsEmpty('Контрактов не найдено', 'Смени фильтр или обнови список.');
}

function renderDisputedContractsList(list) {
  const disputed = filterContractsByCategory(list).filter(c => c.status === 'disputed');
  if (!disputed.length) {
    return renderContractsEmpty(
      contractsCategoryFilter !== 'all' ? 'Споров в этой категории нет' : 'Спорных поручений нет',
      'Если по поручению открыли спор, он появится здесь вместе со статусом.'
    );
  }
  return `<div class="contracts-section-label dispute">Требуется решение администратора</div>`
    + disputed.map(c => renderContractCard(c, true)).join('');
}

function renderContractsFromCache() {
  syncContractsCategoryFilterUI();
  const openEl = document.getElementById('contractsOpenList');
  const myEl = document.getElementById('contractsMyList');
  const disputedEl = document.getElementById('contractsDisputedList');
  if (openEl && contractsActiveTab === 'open') {
    openEl.classList.remove('empty-state');
    openEl.innerHTML = renderContractsList(contractsOpenCache, {
      emptyTitle: 'Открытых поручений нет',
      emptyHint: 'Пока никто не оставил задачу на Доске.',
    });
  }
  if (myEl && contractsActiveTab === 'my') {
    myEl.classList.remove('empty-state');
    myEl.innerHTML = renderMyContractsList(contractsMyCache);
  }
  if (disputedEl && contractsActiveTab === 'disputed') {
    disputedEl.classList.remove('empty-state');
    disputedEl.innerHTML = renderDisputedContractsList(contractsMyCache);
  }
}

function showContractsTab(tab) {
  const openEl = document.getElementById('contracts-tab-open');
  const myEl   = document.getElementById('contracts-tab-my');
  const disputedEl = document.getElementById('contracts-tab-disputed');
  const btnOpen = document.getElementById('ctab-open');
  const btnMy   = document.getElementById('ctab-my');
  const btnDisputed = document.getElementById('ctab-disputed');
  if (!openEl || !myEl || !disputedEl) return;
  contractsActiveTab = ['my', 'disputed'].includes(tab) ? tab : 'open';
  startContractsAutoRefresh();

  if (contractsActiveTab === 'open') {
    openEl.style.display = 'block';
    myEl.style.display = 'none';
    disputedEl.style.display = 'none';
    if (btnOpen) btnOpen.classList.add('active');
    if (btnMy) btnMy.classList.remove('active');
    if (btnDisputed) btnDisputed.classList.remove('active');
    syncContractsCategoryFilterUI();
    loadOpenContracts();
  } else if (contractsActiveTab === 'my') {
    openEl.style.display = 'none';
    myEl.style.display = 'block';
    disputedEl.style.display = 'none';
    if (btnMy) btnMy.classList.add('active');
    if (btnOpen) btnOpen.classList.remove('active');
    if (btnDisputed) btnDisputed.classList.remove('active');
    syncContractsCategoryFilterUI();
    loadMyContracts();
  } else {
    openEl.style.display = 'none';
    myEl.style.display = 'none';
    disputedEl.style.display = 'block';
    if (btnDisputed) btnDisputed.classList.add('active');
    if (btnOpen) btnOpen.classList.remove('active');
    if (btnMy) btnMy.classList.remove('active');
    syncContractsCategoryFilterUI();
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
    const r = await contractFetch(`${API_URL}/api/contracts`, {
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
    contractsOpenCache = Array.isArray(data) ? data : [];
    el.classList.remove('empty-state');
    el.innerHTML = renderContractsList(contractsOpenCache, {
      emptyTitle: 'Открытых поручений нет',
      emptyHint: 'Пока никто не оставил задачу на Доске.',
    });
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
  const disputedEl = document.getElementById('contractsDisputedList');
  const targetEl = contractsActiveTab === 'disputed' ? disputedEl : el;
  if (!targetEl || !currentUserId) {
    if (targetEl) targetEl.innerHTML = '<div class="empty-state">Войди в систему</div>';
    return;
  }
  if (contractsMyLoading) return;
  contractsMyLoading = true;
  const silent = !!options.silent;
  if (!silent || !targetEl.innerHTML.trim()) {
    targetEl.innerHTML = '<div class="empty-state">Загрузка...</div>';
  }
  try {
    const r = await contractFetch(`${API_URL}/api/contracts/my`, {
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    if (r.status === 403) {
      const d = await r.json().catch(() => ({}));
      showContractsBlackwall(d.detail || 'BlackWall активен');
      return;
    }
    const data = await r.json();
    if (!r.ok) { targetEl.innerHTML = `<div class="empty-state">${escapeHtml(data.detail || 'Ошибка')}</div>`; return; }
    syncContractsBlackwallVisible(false);
    contractsMyCache = Array.isArray(data) ? data : [];
    targetEl.classList.remove('empty-state');
    targetEl.innerHTML = contractsActiveTab === 'disputed'
      ? renderDisputedContractsList(contractsMyCache)
      : renderMyContractsList(contractsMyCache);
  } catch (e) {
    if (!silent || !targetEl.innerHTML.trim()) {
      targetEl.innerHTML = '<div class="empty-state">Нет соединения</div>';
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
  const statusLabel = getContractStatusLabel(c, isMe, isAssignee);
  const statusHint = getContractStatusHint(c, isMe, isAssignee);
  const statusColor = CONTRACT_STATUS_COLORS[c.status] || 'var(--text3)';
  const catLabel = CONTRACT_CATEGORY_LABELS[c.category] || c.category;
  const isAdminContract = isAdminContractCreator(c);
  const suspHtml = c.is_suspicious
    ? `<div class="contract-warning">⚠ Подозрительный: ${escapeHtml(c.suspicious_reason || '')}</div>`
    : '';

  let actionsHtml = '';
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

  const assigneeHtml = c.assignee_name
    ? `<span class="contract-person">исп.: ${escapeHtml(c.assignee_name)}</span>`
    : '';

  const creatorName = c.creator_name || '?';
  const avatarInitials = c.is_anonymous
    ? '隐'
    : creatorName.trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  const creatorAvatarHtml = c.creator_avatar_url
    ? `<img src="${escapeHtml(c.creator_avatar_url)}" alt="">`
    : `<span>${escapeHtml(avatarInitials || '?')}</span>`;

  const adminBadgeHtml = isAdminContract
    ? '<span class="contract-admin-badge">ADMIN ORDER</span>'
    : '';
  const flowSteps = ['open', 'accepted', 'completed'];
  const flowIndex = c.status === 'disputed'
    ? 1
    : (c.status === 'cancelled' ? -1 : flowSteps.indexOf(c.status));
  const flowHtml = `<div class="contract-flow-block">
    <div class="contract-flow contract-flow-${escapeHtml(c.status || 'unknown')}">
      ${flowSteps.map((step, idx) => `<span class="${idx <= flowIndex ? 'done' : ''}" data-step="${idx + 1}"></span>`).join('')}
    </div>
    <div class="contract-flow-labels">
      <span>Создано</span><span>Принято</span><span>Готово</span>
    </div>
  </div>`;

  return `<div class="contract-card status-${escapeHtml(c.status || 'unknown')}${isAdminContract ? ' admin-contract' : ''}">
    <div class="contract-card-head">
      <div class="contract-creator-avatar${c.creator_avatar_url ? ' has-image' : ''}">${creatorAvatarHtml}</div>
      <div class="contract-card-titlebox">
        <div class="contract-card-title">${escapeHtml(c.title)}</div>
        <div class="contract-card-badges">
          ${adminBadgeHtml}
          <span class="contract-category-badge">${catLabel}</span>
        </div>
      </div>
      <div class="contract-reward">
        <div class="contract-reward-main">${c.reward_stars}★</div>
        <div class="contract-reward-sub">${c.payout_stars}★ исп.</div>
      </div>
    </div>
    <div class="contract-description">${escapeHtml(c.description)}</div>
    <div class="contract-meta">
      <span class="contract-status" style="--contract-status-color:${statusColor};">${statusLabel}</span>
      <span class="contract-status-hint">${escapeHtml(statusHint)}</span>
      <span class="contract-person">${escapeHtml(creatorName)}${isMe ? ' · ты' : ''}</span>
      ${assigneeHtml}
    </div>
    ${flowHtml}
    ${suspHtml}
    ${actionsHtml}
  </div>`;
}

function getContractStatusLabel(contract, isCreator, isAssignee) {
  if (contract.status === 'accepted' && isCreator) return 'Ждёт подтверждения';
  if (contract.status === 'accepted' && isAssignee) return 'Ты выполняешь';
  return CONTRACT_STATUS_LABELS[contract.status] || contract.status || 'Статус неизвестен';
}

function getContractStatusHint(contract, isCreator, isAssignee) {
  if (contract.status === 'open' && isCreator) return 'Ты создал поручение, ждём исполнителя';
  if (contract.status === 'open') return 'Можно принять и выполнить';
  if (contract.status === 'accepted' && isCreator) return 'Проверь результат и подтверди';
  if (contract.status === 'accepted' && isAssignee) return 'Выполни задачу и жди подтверждения';
  return CONTRACT_STATUS_HINTS[contract.status] || '';
}

// ===== CREATE MODAL =====

function openCreateContractModal() {
  const modal = document.getElementById('createContractModal');
  if (!modal) return;
  syncContractRewardLimits();
  modal.style.display = 'flex';
  const errEl = document.getElementById('contractCreateError');
  if (errEl) errEl.style.display = 'none';
  updateContractFeePreview();
}

function closeCreateContractModal() {
  const modal = document.getElementById('createContractModal');
  if (!modal) return;
  modal.style.display = 'none';
  const titleEl = document.getElementById('contractTitle');
  const descEl  = document.getElementById('contractDesc');
  const catEl   = document.getElementById('contractCategory');
  const rewEl   = document.getElementById('contractReward');
  const anonEl  = document.getElementById('contractAnonymous');
  const errEl   = document.getElementById('contractCreateError');
  if (titleEl) titleEl.value = '';
  if (descEl)  descEl.value  = '';
  if (catEl)   catEl.value   = 'other';
  if (rewEl)   rewEl.value   = '20';
  if (anonEl)  anonEl.checked = false;
  if (errEl)   errEl.style.display = 'none';
  updateContractFeePreview();
}

function updateContractFeePreview() {
  const rewardEl = document.getElementById('contractReward');
  const previewEl = document.getElementById('contractFeePreview');
  if (!rewardEl || !previewEl) return;
  const reward = parseInt(rewardEl.value) || 0;
  const maxReward = getContractMaxReward();
  const fee = Math.max(2, Math.round(reward * 0.1));
  const payout = reward - fee;
  if (reward >= CONTRACT_MIN_REWARD && reward <= maxReward) {
    previewEl.textContent = `Исполнитель получит: ${payout}★ · Комиссия Сетевого Дозора: ${fee}★`;
    previewEl.style.color = 'var(--text3)';
  } else {
    previewEl.textContent = `Награда должна быть от ${CONTRACT_MIN_REWARD} до ${maxReward} ★`;
    previewEl.style.color = '#e74c3c';
  }
}

async function submitCreateContract() {
  const title    = (document.getElementById('contractTitle')?.value || '').trim();
  const desc     = (document.getElementById('contractDesc')?.value || '').trim();
  const category = document.getElementById('contractCategory')?.value || 'other';
  const reward   = parseInt(document.getElementById('contractReward')?.value) || 0;
  const isAnonymous = !!document.getElementById('contractAnonymous')?.checked;
  const errEl    = document.getElementById('contractCreateError');

  const showErr = (msg) => {
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
  };

  if (!currentUserId) { showErr('Войди в систему'); return; }
  if (title.length < 3) { showErr('Название слишком короткое'); return; }
  if (desc.length < 5)  { showErr('Описание слишком короткое'); return; }
  const maxReward = getContractMaxReward();
  if (reward < CONTRACT_MIN_REWARD || reward > maxReward) { showErr(`Награда: от ${CONTRACT_MIN_REWARD} до ${maxReward} ★`); return; }

  try {
    const r = await contractFetch(`${API_URL}/api/contracts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Telegram-Id': String(currentUserId) },
      body: JSON.stringify({ title, description: desc, category, reward_stars: reward, is_anonymous: isAnonymous }),
    });
    const data = await r.json();
    if (!r.ok) { showErr(data.detail || 'Ошибка создания'); return; }
    closeCreateContractModal();
    currentPoints = Math.max(0, currentPoints - reward);
    updatePoints();
    const localContract = {
      id: data.id,
      title,
      description: desc,
      category,
      reward_stars: reward,
      fee_stars: data.fee_stars,
      payout_stars: data.payout_stars,
      creator_telegram_id: currentUserId,
      assignee_telegram_id: null,
      creator_is_admin: !!isAdmin,
      creator_name: getCurrentContractUserName(),
      assignee_name: null,
      creator_avatar_url: null,
      assignee_avatar_url: null,
      is_anonymous: isAnonymous,
      status: 'open',
      is_suspicious: false,
      suspicious_reason: null,
      created_at: new Date().toISOString(),
      role: 'creator',
    };
    contractsMyCache.unshift(localContract);
    contractsOpenCache.unshift(localContract);
    switchContractsTabLocal('my');
  } catch (e) {
    showErr('Нет соединения');
  }
}

// ===== CONTRACT ACTIONS =====

async function acceptContract(id) {
  if (!currentUserId) return;
  try {
    const r = await contractFetch(`${API_URL}/api/contracts/${id}/accept`, {
      method: 'POST',
      headers: { 'X-Telegram-Id': String(currentUserId) },
    });
    const data = await r.json();
    if (!r.ok) {
      tg.showPopup({ title: 'Ошибка', message: data.detail || 'Не удалось принять', buttons: [{ type: 'ok' }] });
      return;
    }
    updateContractInCaches(id, {
      status: 'accepted',
      assignee_telegram_id: currentUserId,
      assignee_name: getCurrentContractUserName(),
      accepted_at: new Date().toISOString(),
      role: 'assignee',
    });
    switchContractsTabLocal('my');
  } catch (e) {
    tg.showPopup({ title: 'Ошибка', message: 'Нет соединения', buttons: [{ type: 'ok' }] });
  }
}

async function completeContract(id) {
  if (!currentUserId) return;
  tg.showPopup({
    title: 'Подтвердить выполнение?',
    message: 'Исполнитель получит ★ на баланс.',
    buttons: [{ id: 'ok', type: 'default', text: '✓ Подтвердить' }, { type: 'cancel' }],
  }, async (btn) => {
    if (btn !== 'ok') return;
    try {
      const r = await contractFetch(`${API_URL}/api/contracts/${id}/complete`, {
        method: 'POST',
        headers: { 'X-Telegram-Id': String(currentUserId) },
      });
      const data = await r.json();
      if (!r.ok) {
        tg.showPopup({ title: 'Ошибка', message: data.detail || 'Не удалось завершить', buttons: [{ type: 'ok' }] });
        return;
      }
      updateContractInCaches(id, { status: 'completed', completed_at: new Date().toISOString() });
    } catch (e) {
      tg.showPopup({ title: 'Ошибка', message: 'Нет соединения', buttons: [{ type: 'ok' }] });
    }
  });
}

async function cancelContract(id) {
  if (!currentUserId) return;
  tg.showPopup({
    title: 'Отменить поручение?',
    message: 'Замороженные ★ вернутся на твой баланс.',
    buttons: [{ id: 'ok', type: 'destructive', text: 'Отменить' }, { type: 'cancel' }],
  }, async (btn) => {
    if (btn !== 'ok') return;
    try {
      const r = await contractFetch(`${API_URL}/api/contracts/${id}/cancel`, {
        method: 'POST',
        headers: { 'X-Telegram-Id': String(currentUserId) },
      });
      const data = await r.json();
      if (!r.ok) {
        tg.showPopup({ title: 'Ошибка', message: data.detail || 'Не удалось отменить', buttons: [{ type: 'ok' }] });
        return;
      }
      if (data.refunded) {
        currentPoints += data.refunded;
        updatePoints();
      }
      removeContractFromCaches(id);
    } catch (e) {
      tg.showPopup({ title: 'Ошибка', message: 'Нет соединения', buttons: [{ type: 'ok' }] });
    }
  });
}

async function disputeContract(id) {
  if (!currentUserId) return;
  tg.showPopup({
    title: 'Открыть спор?',
    message: 'Администратор рассмотрит ситуацию и вынесет решение.',
    buttons: [{ id: 'ok', type: 'default', text: '⚠ Открыть спор' }, { type: 'cancel' }],
  }, async (btn) => {
    if (btn !== 'ok') return;
    try {
      const r = await contractFetch(`${API_URL}/api/contracts/${id}/dispute`, {
        method: 'POST',
        headers: { 'X-Telegram-Id': String(currentUserId) },
      });
      const data = await r.json();
      if (!r.ok) {
        tg.showPopup({ title: 'Ошибка', message: data.detail || 'Не удалось открыть спор', buttons: [{ type: 'ok' }] });
        return;
      }
      updateContractInCaches(id, { status: 'disputed', disputed_at: new Date().toISOString() });
      switchContractsTabLocal('disputed');
    } catch (e) {
      tg.showPopup({ title: 'Ошибка', message: 'Нет соединения', buttons: [{ type: 'ok' }] });
    }
  });
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    stopContractsAutoRefresh();
  } else if (isContractsPageActive()) {
    startContractsAutoRefresh();
    refreshContractsActiveTab({ silent: true });
  }
});
