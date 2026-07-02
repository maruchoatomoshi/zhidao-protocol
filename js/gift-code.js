// ===== Подарочные коды (Михаил Юрьевич) — живое событие =====

const MJU_POPUP_IMG = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/mu_givingcode.png';
const MJU_SEEN_KEY = 'mjuSeenCodes';

let mjuPopupTypeTimer = null;
let _mjuPollInterval = null;
let _mjuActiveCode = null;

function _getMjuSeen() {
  try { return new Set(JSON.parse(localStorage.getItem(MJU_SEEN_KEY) || '[]')); } catch (e) { return new Set(); }
}
function _markMjuSeen(code) {
  try {
    const s = _getMjuSeen(); s.add(code);
    localStorage.setItem(MJU_SEEN_KEY, JSON.stringify([...s]));
  } catch (e) {}
}

function startGiftCodePoller() {
  if (_mjuPollInterval) return;
  checkActiveGiftCode();
  _mjuPollInterval = setInterval(checkActiveGiftCode, 10000);
}
window.startGiftCodePoller = startGiftCodePoller;

async function checkActiveGiftCode() {
  if (!currentUserId) return;
  if (document.hidden) return; // не бьём в API, пока мини-апп свёрнут
  try {
    const { data } = await apiGetJson('/api/gift-code/active');
    if (!data || !data.active) return;
    const seen = _getMjuSeen();
    if (seen.has(data.code)) return;
    if (_mjuActiveCode === data.code) return;
    _mjuActiveCode = data.code;
    showMjuPopup(
      `Стоп. Код активен — первые ${data.max_uses} оператора берут награду. Быстро`,
      data.code,
      data.reward_stars
    );
  } catch (e) {}
}

async function claimMjuCode() {
  if (!_mjuActiveCode || !currentUserId) return;
  const btn = document.getElementById('mjuClaimBtn');
  if (btn) btn.disabled = true;

  try {
    const { data } = await apiPostJson('/api/gift-code/redeem', {
      telegram_id: currentUserId,
      code: _mjuActiveCode,
    });

    if (data.success) {
      _markMjuSeen(_mjuActiveCode);
      currentPoints = data.new_points;
      updatePoints();
      if (btn) {
        btn.textContent = `✓ Получено! +${data.reward_stars} ★`;
        btn.style.color = '#2ecc71';
        btn.style.borderColor = '#2ecc71';
      }
      try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
    } else {
      const detail = data.detail || data.error || '';
      let msg = 'Не удалось активировать';
      if (detail === 'Already redeemed') msg = 'Ты уже забрал этот код';
      else if (detail === 'Code exhausted') msg = '⚠ Лимит исчерпан — опоздал';
      else if (detail === 'Code expired') msg = 'Код устарел';
      if (btn) { btn.textContent = msg; btn.style.color = 'var(--text2)'; }
      try { tg.HapticFeedback.notificationOccurred('error'); } catch (e) {}
    }
  } catch (e) {
    if (btn) { btn.textContent = 'Ошибка соединения'; btn.disabled = false; }
  }
}
window.claimMjuCode = claimMjuCode;

function showMjuPopup(text, code, rewardStars) {
  const overlay = document.getElementById('mjuPopupOverlay');
  const imageEl = document.getElementById('mjuPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('mjuPopupText');
  const codeBlock = document.getElementById('mjuCodeBlock');
  const codeDisplay = document.getElementById('mjuCodeDisplay');
  const claimBtn = document.getElementById('mjuClaimBtn');
  if (!overlay || !textEl) return;

  if (imageEl) {
    imageEl.style.backgroundImage = `url('${MJU_POPUP_IMG}')`;
    imageEl.style.animation = 'none';
    void imageEl.offsetWidth;
    imageEl.style.animation = '';
  }
  if (box) {
    box.style.animation = 'none';
    void box.offsetWidth;
    box.style.animation = '';
  }

  if (codeDisplay) codeDisplay.textContent = code || '';
  if (codeBlock) codeBlock.style.display = code ? 'block' : 'none';
  if (claimBtn) {
    claimBtn.style.display = code ? 'block' : 'none';
    claimBtn.disabled = false;
    claimBtn.textContent = rewardStars ? `ЗАБРАТЬ +${rewardStars} ★` : 'ЗАБРАТЬ ★';
    claimBtn.style.color = '#ff003c';
    claimBtn.style.borderColor = 'rgba(255,0,60,0.4)';
  }

  document.body.classList.add('architect-popup-open');
  overlay.style.display = 'flex';
  typeMjuPopupText(text);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}

function typeMjuPopupText(text) {
  const textEl = document.getElementById('mjuPopupText');
  if (!textEl) return;
  if (mjuPopupTypeTimer) { clearInterval(mjuPopupTypeTimer); mjuPopupTypeTimer = null; }
  textEl.innerHTML = '<span class="mju-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.mju-popup-typed');
  let i = 0;
  mjuPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(mjuPopupTypeTimer);
      mjuPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeMjuPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('mjuPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  if (mjuPopupTypeTimer) { clearInterval(mjuPopupTypeTimer); mjuPopupTypeTimer = null; }
  document.body.classList.remove('architect-popup-open');
  _mjuActiveCode = null;
}
