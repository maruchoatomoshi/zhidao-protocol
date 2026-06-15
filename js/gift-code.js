// ===== Подарочные коды (Михаил Юрьевич) =====

const MJU_POPUP_IMG = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/alpha_boss_netwatchtheme.png';

let mjuPopupTypeTimer = null;

async function redeemGiftCode() {
  const input = document.getElementById('giftCodeInput');
  const btn = document.getElementById('giftCodeRedeemBtn');
  const msgEl = document.getElementById('giftCodeMsg');
  if (!input || !currentUserId) return;

  const code = input.value.trim();
  if (!code) return;

  if (btn) btn.disabled = true;
  if (msgEl) { msgEl.textContent = ''; msgEl.className = 'gift-code-msg'; }

  try {
    const { response, data } = await apiPostJson('/api/gift-code/redeem', {
      telegram_id: currentUserId,
      code,
    });

    if (response.ok && data.success) {
      input.value = '';
      currentPoints = data.new_points;
      updatePoints();
      try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
      showMjuPopup(`Так, получил твой код. Награда — ${data.reward_stars} ★ на счёт. Не теряй чек, оператор`);
    } else {
      const detail = data.detail || '';
      let text = 'Код не подошёл. Проверь и попробуй ещё раз';
      if (detail === 'Code not found') text = 'Такого кода в системе нет. Проверь раскладку и попробуй снова';
      else if (detail === 'Already redeemed') text = 'Этот код ты уже использовал. Повторно не прокатит';
      else if (detail === 'Code expired') text = 'Срок действия кода истёк';
      else if (detail === 'Code exhausted') text = 'Лимит использований этого кода исчерпан';
      if (msgEl) { msgEl.textContent = text; msgEl.classList.add('gift-code-msg-error'); }
      try { tg.HapticFeedback.notificationOccurred('error'); } catch (e) {}
    }
  } catch (e) {
    if (msgEl) { msgEl.textContent = 'Ошибка соединения'; msgEl.classList.add('gift-code-msg-error'); }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function showMjuPopup(text) {
  const overlay = document.getElementById('mjuPopupOverlay');
  const imageEl = document.getElementById('mjuPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('mjuPopupText');
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

  document.body.classList.add('architect-popup-open');
  overlay.style.display = 'flex';
  typeMjuPopupText(text);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}

function typeMjuPopupText(text) {
  const textEl = document.getElementById('mjuPopupText');
  if (!textEl) return;
  if (mjuPopupTypeTimer) {
    clearInterval(mjuPopupTypeTimer);
    mjuPopupTypeTimer = null;
  }

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
  if (mjuPopupTypeTimer) {
    clearInterval(mjuPopupTypeTimer);
    mjuPopupTypeTimer = null;
  }
  document.body.classList.remove('architect-popup-open');
}
