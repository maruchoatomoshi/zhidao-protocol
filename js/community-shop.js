// Народный магазин: игроки предлагают товары, голосуют 👑.
// При 70 голосах 👑 ИЛИ когда проголосовало 70% игроков — админы видят пометку «СПРОС» и могут добавить товар в основной магазин.

const FOLK_VOTE_EMOJI = '👑';
const FOLK_DEMAND_THRESHOLD = 70;

async function loadFolkShop() {
  const el = document.getElementById('folkShopFeed');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка...</div>';
  try {
    const r = await fetch(`${API_URL}/api/community-shop/proposals`);
    const proposals = await r.json();
    if (!proposals.length) {
      el.innerHTML = '<div class="empty-state">Предложений пока нет. Стань первым!</div>';
      return;
    }

    const withReactions = await Promise.all(proposals.map(async p => {
      try {
        const qs = currentUserId ? `?telegram_id=${currentUserId}` : '';
        const rr = await fetch(`${API_URL}/api/community-shop/proposals/${p.id}/reactions${qs}`);
        const reactions = rr.ok ? await rr.json() : [];
        return { ...p, reactions };
      } catch { return { ...p, reactions: [] }; }
    }));

    const statusLabels = {pending: '⏳ на рассмотрении', promoted: '✅ уже в магазине', rejected: '✖ отклонено'};

    el.innerHTML = withReactions.map(item => {
      const crown = item.reactions.find(r => r.emoji === FOLK_VOTE_EMOJI);
      const count = crown ? crown.count : 0;
      const voted = !!(crown && crown.you);
      const participationPct = Number(item.participation_pct || 0);
      const pct = Math.min(100, Math.max(Math.round((count / FOLK_DEMAND_THRESHOLD) * 100), Math.round(participationPct)));
      const isHot = item.demand_confirmed || count >= FOLK_DEMAND_THRESHOLD || participationPct >= 70;

      let statusClass = '';
      let statusText = statusLabels[item.status] || item.status;
      if (item.status === 'promoted') statusClass = 'status-promoted';
      else if (item.status === 'rejected') statusClass = 'status-rejected';
      else if (item.demand_confirmed) { statusClass = 'status-hot'; statusText += ' · 👑 СПРОС ПОДТВЕРЖДЁН'; }

      return `<div class="folk-item-card${isHot ? ' is-hot' : ''}">
        <div class="card-inner">
          <div class="folk-item-head">
            <div>
              <div class="folk-item-title">${escapeHtml(item.title)}</div>
              <div class="folk-item-desc">${escapeHtml(item.description)}</div>
            </div>
            <button class="folk-crown-btn${voted ? ' is-voted' : ''}" onclick="reactToFolkProposal(${item.id}, this)">
              <span class="folk-crown-emoji">👑</span>
              <span class="folk-crown-count">${count}</span>
            </button>
          </div>
          <div class="folk-item-status ${statusClass}">${statusText}</div>
          ${item.status === 'pending' ? `
            <div class="folk-item-progress-track"><div class="folk-item-progress-fill" style="width:${pct}%;"></div></div>
            <div class="folk-item-progress-label"><span>${count} / ${FOLK_DEMAND_THRESHOLD} 👑 · ${participationPct}% участников</span><span>${pct}%</span></div>
          ` : ''}
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function reactToFolkProposal(id, btn) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/community-shop/proposals/${id}/react`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, emoji: FOLK_VOTE_EMOJI})
    });
    if (r.ok) {
      try { tg.HapticFeedback.impactOccurred('light'); } catch (e) {}
      loadFolkShop();
    }
  } catch (e) {}
}

async function submitFolkProposal() {
  const title = (document.getElementById('folkProposalTitle').value || '').trim();
  const description = (document.getElementById('folkProposalDescription').value || '').trim();
  if (!title || !description) { showToast('Заполни название и описание'); return; }
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }

  try {
    const r = await fetch(`${API_URL}/api/community-shop/propose`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, title, description})
    });
    if (r.ok) {
      showToast('📨 Предложение отправлено');
      document.getElementById('folkProposalTitle').value = '';
      document.getElementById('folkProposalDescription').value = '';
      loadFolkShop();
    } else {
      showToast('Ошибка отправки');
    }
  } catch (e) { showToast('Ошибка соединения'); }
}
