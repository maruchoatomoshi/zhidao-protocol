// Народный магазин: игроки предлагают товары, голосуют реакциями (👑 = голос «за»).
// При 70 голосах 👑 или 70% реакций от проголосовавших — админы видят пометку «СПРОС» и могут добавить товар в основной магазин.

const FOLK_REACTIONS = ['👍', '❤️', '🔥', '😂', '😮', '👑'];

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
        const rr = await fetch(`${API_URL}/api/community-shop/proposals/${p.id}/reactions`);
        const reactions = rr.ok ? await rr.json() : [];
        return { ...p, reactions };
      } catch { return { ...p, reactions: [] }; }
    }));

    const statusLabels = {pending: '⏳ на рассмотрении', promoted: '✅ уже в магазине', rejected: '✖ отклонено'};

    el.innerHTML = withReactions.map(item => {
      const reactionMap = {};
      item.reactions.forEach(r => { reactionMap[r.emoji] = r.count; });

      const reactionBtns = FOLK_REACTIONS.map(emoji => {
        const count = reactionMap[emoji] || 0;
        const active = count > 0 ? 'background:rgba(212,175,55,0.15);border-color:rgba(212,175,55,0.4);' : '';
        return `<button onclick="reactToFolkProposal(${item.id}, '${emoji}', this)"
          style="display:inline-flex;align-items:center;gap:3px;padding:4px 8px;
          background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
          border-radius:20px;cursor:pointer;font-size:13px;color:var(--text2);
          font-family:monospace;${active}transition:all 0.2s;">
          ${emoji}${count > 0 ? `<span style="font-size:10px;color:var(--gold);">${count}</span>` : ''}
        </button>`;
      }).join('');

      return `<div class="card" style="margin-bottom:10px;">
        <div class="card-inner" style="padding:12px 14px;">
          <div style="font-size:13px;font-weight:700;color:var(--text);">${escapeHtml(item.title)}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:4px;line-height:1.5;">${escapeHtml(item.description)}</div>
          <div style="font-size:10px;color:var(--text3);margin-top:6px;">${statusLabels[item.status] || item.status}${item.demand_confirmed ? ' · 👑 СПРОС ПОДТВЕРЖДЁН' : ''}</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:10px;">${reactionBtns}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
  }
}

async function reactToFolkProposal(id, emoji, btn) {
  if (!currentUserId) { showToast('Откройте через Telegram бота'); return; }
  try {
    const r = await fetch(`${API_URL}/api/community-shop/proposals/${id}/react`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({telegram_id: currentUserId, emoji})
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
