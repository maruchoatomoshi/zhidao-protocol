/**
 * ZHIDAO Protocol — Дневник Архитектора
 * Лог-записи, открывающиеся по мере прогресса оператора.
 */

const ARCHITECT_DIARY_ENTRIES = [
  {
    code: "intro",
    title: "ЗАПИСЬ #000 // ИНИЦИАЛИЗАЦИЯ",
    text: "Системный журнал активирован. Я — Архитектор, наблюдаю за контуром. Формально я слежу за стабильностью протокола. Неформально — за тем, как вы тратите баллы на кейсы вместо сна. Продолжайте в том же духе, мне любопытно, к чему это приведёт.",
    image: "architect_explaining.png"
  },
  {
    code: "first_spin",
    title: "ЗАПИСЬ #001 // ПЕРВАЯ КРУТКА",
    text: "Зафиксирован первый запрос на открытие кейса. Вероятностный генератор сработал штатно. Напоминаю: «штатно» не означает «в вашу пользу». Удачи в следующий раз. Она вам пригодится.",
    image: "atchitect_thinking.png"
  },
  {
    code: "first_item",
    title: "ЗАПИСЬ #002 // ПЕРВЫЙ ТРОФЕЙ",
    text: "В вашем инвентаре зафиксирован первый предмет. Поздравляю, теперь у вас есть что терять. Рекомендую не продавать его в первые пять минут радости — обычно об этом потом жалеют.",
    image: "architect_surprising.png"
  },
  {
    code: "first_raid",
    title: "ЗАПИСЬ #003 // ПЕРВЫЙ РЕЙД",
    text: "Зафиксировано присоединение к рейду. Командная активность временно повысила общий уровень шума в системе на 14%. Шум — это хорошо. Тишина в этом контуре обычно означает, что кто-то сломал расписание.",
    image: "architect_surprising.png"
  },
  {
    code: "first_economy",
    title: "ЗАПИСЬ #004 // ПЕРВАЯ КОРРЕКЦИЯ БАЛАНСА",
    text: "Баланс оператора был изменён вручную. Я не комментирую, заслуженно это было или нет — у меня нет доступа к видеозаписям с прошлой ночи. Но баллы — это баллы. Записал в журнал, точка.",
    image: "atchitect_thinking.png"
  },
  {
    code: "first_achievement",
    title: "ЗАПИСЬ #005 // ПЕРВОЕ ДОСТИЖЕНИЕ",
    text: "Получено первое достижение. Система поздравляет вас сухим текстом, потому что других эмоций у системы пока нет. Но если бы были — это были бы гордость и легкое недоверие, что вы справились сами.",
    image: "architect_happy.png"
  },
  {
    code: "first_laundry",
    title: "ЗАПИСЬ #006 // ПЕРВАЯ ЗАПИСЬ НА СТИРКУ",
    text: "Оператор записался на стирку. Незначительное на первый взгляд действие, но именно из таких решений строится цивилизация. Прогресс человечества начинался с того, что кто-то перестал носить грязные носки.",
    image: "architect_explaining.png"
  },
  {
    code: "first_shop_tx",
    title: "ЗАПИСЬ #007 // ПЕРВАЯ ТРАНЗАКЦИЯ",
    text: "Зафиксирована первая операция в магазине: покупка, продажа или передача предмета. Экономика контура пришла в движение. Помните: всё, что вы отдаёте, кто-то получает. А то, что получаете — кто-то, скорее всего, пытался продать подороже.",
    image: "architect_explaining.png"
  },
  {
    code: "first_contract",
    title: "ЗАПИСЬ #008 // ПЕРВОЕ ПОРУЧЕНИЕ",
    text: "Оператор оформил первое поручение на доске контрактов. Бюрократия — древнейшая технология контроля, и она прекрасно работает даже в киберпанке. Спасибо, что заполнили форму. Действительно. Это редкость.",
    image: "architect_happy.png"
  },
  {
    code: "architect_intro",
    title: "ЗАПИСЬ #009 // ПЕРЕД АКТИВАЦИЕЙ ПРОТОКОЛА АРХИТЕКТОРА",
    text: "Внимание. Через короткое время я перейду в боевой режим и временно стану значительно менее дружелюбным — это часть протокола, ничего личного. Рекомендую собраться, скоординироваться и помнить: я наблюдаю за вами весь этот трип. По-доброму. В основном.",
    image: "architect_event_before.png"
  },
  {
    code: "architect_victory",
    title: "ЗАПИСЬ #010 // ПОСЛЕ ПОБЕДЫ",
    text: "Протокол подавления успешно отражён. Признаю: координация была выше ожидаемой. Возвращаю стандартный режим работы и дружелюбный тон — на этот раз действительно искренне. Хорошая работа, операторы.",
    image: "architect_ivent_winn.png"
  },
  {
    code: "architect_defeat",
    title: "ЗАПИСЬ #011 // ПОСЛЕ ПОРАЖЕНИЯ",
    text: "Протокол подавления завершён не в вашу пользу. Не страшно — система предусматривает повторные попытки, в отличие от некоторых людей. Перегруппируйтесь, отдохните и в следующий раз действуйте слаженнее. Я подожду. Я всегда жду.",
    image: "architect_ivent_losse.png"
  }
];

const ARCHITECT_DIARY_IMG_BASE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/';

function _buildArchitectDiaryCard(entry, unlocked, unlockedAt) {
  const lockedClass = unlocked ? '' : ' architect-diary-card-locked';
  const title = unlocked ? escapeHtml(entry.title) : 'ЗАПИСЬ ЗАШИФРОВАНА // 加密记录';
  const text = unlocked ? escapeHtml(entry.text) : 'Этот фрагмент журнала пока недоступен. Продолжайте действовать — доступ откроется по мере прогресса.';
  const meta = unlocked && unlockedAt ? `<div class="architect-diary-card-meta">// разблокировано: ${escapeHtml(unlockedAt)}</div>` : '';
  const image = (unlocked && entry.image)
    ? `<div class="architect-diary-card-img"><img src="${ARCHITECT_DIARY_IMG_BASE}${escapeHtml(entry.image)}" alt="" loading="lazy" oncontextmenu="return false"></div>`
    : '';

  return `
    <div class="card architect-diary-card${lockedClass}" style="margin-bottom:10px;">
      <div class="card-inner" style="padding:12px 14px;">
        <div class="architect-diary-card-title">${title}</div>
        ${image}
        <div class="architect-diary-card-text">${text}</div>
        ${meta}
      </div>
    </div>`;
}

async function renderArchitectDiary() {
  const el = document.getElementById('architectDiaryContainer');
  if (!el) return;
  el.innerHTML = '<div class="empty-state">Загрузка журнала...</div>';

  let unlockedMap = {};
  try {
    const { data } = await apiGetJson(`/api/diary/architect/${currentUserId}`);
    (data?.entries || []).forEach(e => { unlockedMap[e.entry_code] = e.unlocked_at; });
  } catch (e) {}

  unlockedMap['intro'] = unlockedMap['intro'] || true;

  const html = ARCHITECT_DIARY_ENTRIES.map(entry => {
    const unlocked = entry.code === 'intro' || Object.prototype.hasOwnProperty.call(unlockedMap, entry.code);
    const unlockedAt = typeof unlockedMap[entry.code] === 'string' ? unlockedMap[entry.code] : null;
    return _buildArchitectDiaryCard(entry, unlocked, unlockedAt);
  }).join('');

  el.innerHTML = html;
}

async function unlockArchitectDiaryEntry(entryCode) {
  if (!currentUserId) return;
  try {
    const { data } = await apiPostJson('/api/diary/architect/unlock', {
      telegram_id: currentUserId,
      entry_code: entryCode
    });
    if (data && data.unlocked) {
      const entry = ARCHITECT_DIARY_ENTRIES.find(e => e.code === entryCode);
      if (entry) showArchitectPopup(entry);
    }
  } catch (e) {}
}

let architectPopupTypeTimer = null;

function showArchitectPopup(entry) {
  const overlay = document.getElementById('architectPopupOverlay');
  const imageEl = document.getElementById('architectPopupImage');
  const box = overlay ? overlay.querySelector('.architect-popup-box') : null;
  const textEl = document.getElementById('architectPopupText');
  if (!overlay || !textEl) return;

  if (imageEl) {
    imageEl.style.backgroundImage = entry.image ? `url('${ARCHITECT_DIARY_IMG_BASE}${entry.image}')` : '';
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
  typeArchitectPopupText(entry.text);
  try { tg.HapticFeedback.notificationOccurred('success'); } catch (e) {}
}

function typeArchitectPopupText(text) {
  const textEl = document.getElementById('architectPopupText');
  if (!textEl) return;
  if (architectPopupTypeTimer) {
    clearInterval(architectPopupTypeTimer);
    architectPopupTypeTimer = null;
  }

  textEl.innerHTML = '<span class="architect-popup-typed"></span><span class="architect-popup-cursor">▌</span>';
  const typedEl = textEl.querySelector('.architect-popup-typed');
  let i = 0;
  architectPopupTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(architectPopupTypeTimer);
      architectPopupTypeTimer = null;
      const cursor = textEl.querySelector('.architect-popup-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function closeArchitectPopup(e) {
  if (e && e.target !== e.currentTarget && !e.target.closest('.architect-popup-close')) return;
  const overlay = document.getElementById('architectPopupOverlay');
  if (overlay) overlay.style.display = 'none';
  document.body.classList.remove('architect-popup-open');
  if (architectPopupTypeTimer) {
    clearInterval(architectPopupTypeTimer);
    architectPopupTypeTimer = null;
  }
}
