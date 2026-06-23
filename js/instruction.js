// ===== Инструкция (Юлия Витальевна) =====

const INSTRUCTION_IMG_BASE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/';

function instructionEnsureMoreSection(section) {
  try { showPage('more', document.getElementById('nav-more-btn')); } catch (e) {}
  if (currentMoreSection !== section) {
    try { openMore(section); } catch (e) {}
  }
}

function _instructionResolve(value) {
  return typeof value === 'function' ? value() : value;
}

const INSTRUCTION_TOUR_STEPS = [
  {
    page: 'home',
    image: 'julia_based.png',
    title: 'ГЛАВНЫЙ ЭКРАН // 主页',
    highlight: '#profileCard',
    text: 'Привет! Я Юлия Витальевна — на связи как ассистент протокола ZHIDAO. Это главный экран: твои баллы ★ и профиль оператора — аватар, ранг, путь развития, рамки и витрина. Жми «Далее», и я покажу всё остальное'
  },
  {
    page: 'schedule',
    image: 'julia_explaining.png',
    title: 'РАСПИСАНИЕ // 日程',
    highlight: '#page-schedule',
    text: 'Вкладка «日程» — расписание поездки и объявления. Здесь всегда видно, что происходит сегодня и что запланировано дальше'
  },
  {
    page: 'rating',
    image: 'julia_explaining2.png',
    title: 'РЕЙТИНГ // 排名',
    highlight: '#page-rating',
    text: '«排名» — общий рейтинг операторов по REP (репутации), а ниже отдельный рейтинг по дневнику. Следи за своим местом в таблице'
  },
  {
    page: 'shop',
    image: 'julia_based2.png',
    title: 'МАГАЗИН // 商店',
    highlight: '#shopStoreContent',
    text: '«商店» — магазин. Здесь каталог товаров и призов за ★, а также твой собственный инвентарь — посмотреть, что уже куплено, использовать или подарить предмет'
  },
  {
    page: 'shop',
    action: () => { try { showPage('contracts', document.getElementById('nav-shop-btn')); } catch (e) {} },
    image: 'julia_thinking.png',
    title: 'ДОСКА ПОРУЧЕНИЙ // 任务板',
    highlight: '#page-contracts',
    text: 'Кнопка «📋 ДОСКА» открывает доску поручений — список заданий от операторов и команды. Выполняй их, чтобы получать дополнительные ★'
  },
  {
    page: 'casino',
    action: () => { try { switchCasinoTab(currentThemePath === 'genshin' ? 'genshin' : 'play', document.getElementById('casinoPlayBtn')); } catch (e) {} },
    image: 'julia_thinking.png',
    title: () => currentThemePath === 'genshin' ? 'МОЛИТВЫ // 祈愿' : 'КЕЙСЫ // 箱子',
    highlight: () => currentThemePath === 'genshin' ? '#casinoGenshinContent' : '#page-casino',
    text: () => currentThemePath === 'genshin'
      ? '«祈愿» — молитвы. Открывай их за попытки и получай импланты и карточки со случайной редкостью — это твой шанс поймать что-то ценное. В теме NetWatch та же система называется «箱子» — кейсы'
      : '«箱子» — кейсы. Открывай их за попытки открытия и получай импланты и карточки со случайной редкостью — это твой шанс поймать что-то ценное. В теме Genshin та же система называется «✦ Молитвы»'
  },
  {
    page: 'implants',
    action: () => { try { switchImplantsTab('implants'); } catch (e) {} },
    image: 'julia_explaining.png',
    title: 'ИМПЛАНТЫ // 植入物',
    highlight: '#implants-tab',
    text: '«植入物» — твои импланты с пассивными бонусами. Ниже — каталог всех имплантов, чтобы заранее знать, что можно получить и для чего оно нужно'
  },
  {
    page: 'implants',
    action: () => { try { switchImplantsTab('cards'); } catch (e) {} },
    image: 'julia_based2.png',
    title: 'КАРТОЧКИ // 卡片',
    highlight: '#cards-tab',
    text: 'Вкладка «✦ КАРТОЧКИ» — твои карточки (в теме Genshin особенно красивые). Так же есть каталог карточек ниже — у каждой свой пассивный бонус, в том числе в ивентах'
  },
  {
    page: 'diary-stars',
    action: () => { try { showPage('diary-stars', document.getElementById('nav-more-btn')); } catch (e) {} },
    image: 'julia_explaining2.png',
    title: 'ДНЕВНИК 💎 // 日记评分',
    highlight: '#page-diary-stars',
    text: '«ДНЕВНИК 💎» — здесь видно оценки твоего дневника по дням и общий рейтинг по дневникам. Чем выше оценка 💎 — тем больше ★ и REP ты получаешь'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('map'),
    image: 'julia_based.png',
    title: 'КАРТА КАМПУСА // 校园地图',
    highlight: '#more-map',
    text: '«КАРТА» — интерактивная карта кампуса. Помогает быстро найти нужное здание или место на территории'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('laundry'),
    image: 'julia_explaining.png',
    title: 'СТИРКА И ВОДА // 洗衣饮水',
    highlight: '#more-laundry',
    text: '«СТИРКА» — расписание и запись на стиральные машины, а также информация про питьевую воду. Удобно, чтобы не занимать машинку зря'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('weather'),
    image: 'julia_thinking.png',
    title: 'ПОГОДА И КУРС // 天气 / 汇率',
    highlight: '#more-weather',
    text: '«ПОГОДА» — прогноз в Пекине: температура, ощущения, влажность и ветер. А ниже — актуальный курс юаня, чтобы было проще считать покупки'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('themes'),
    image: 'julia_explaining2.png',
    title: 'ТЕМЫ // 主题',
    highlight: '#more-themes',
    text: '«ТЕМЫ» — оформление интерфейса. NetWatch (киберпанк) или Genshin, светлая или тёмная версия — выбирай, что ближе тебе'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('achievements'),
    image: 'julia_based2.png',
    title: 'АЧИВКИ // 成就',
    highlight: '#more-achievements',
    text: '«АЧИВКИ» — достижения за активность в приложении и в поездке. Часть из них можно получить только за особые действия — постарайся собрать их все'
  },
  {
    page: 'more',
    action: () => instructionEnsureMoreSection('team'),
    image: 'julia_explaining.png',
    title: 'КОМАНДА // 团队',
    highlight: '#more-team',
    text: '«КОМАНДА» — операторы контура: сопровождающие и админы поездки. Если что-то понадобится — ты теперь знаешь, к кому обратиться'
  },
  {
    page: 'home',
    image: 'julia_goodbyeing.png',
    title: 'УДАЧИ, ОПЕРАТОР',
    highlight: null,
    text: 'Это всё основное! В этой поездке я не рядом, но мой протокол остаётся на связи — открой эту инструкцию снова через профиль, если понадоблюсь. Удачной поездки! 🏮'
  },
];

let instructionTourIndex = 0;
let instructionTypeTimer = null;
let instructionTourPrevPage = null;

function instructionResetCasinoTabIfNeeded() {
  if (instructionTourPrevPage === 'casino' && typeof switchCasinoTab === 'function') {
    try { switchCasinoTab('play'); } catch (e) {}
  }
}

function openInstructionModal() {
  const modal = document.getElementById('instructionModal');
  if (!modal) return;
  showInstructionChooser();
  modal.style.display = 'flex';
}

function closeInstructionModal(e) {
  if (e && e.target !== e.currentTarget) return;
  const modal = document.getElementById('instructionModal');
  if (modal) modal.style.display = 'none';
}

function showInstructionChooser() {
  const body = document.getElementById('instructionModalBody');
  if (!body) return;
  body.innerHTML = `
    <div class="instruction-modal-title">📖 ИНСТРУКЦИЯ // 说明书</div>
    <button class="instruction-option-btn" onclick="showInstructionTextGuide()">
      <strong>Текстовый гайд</strong>
      Краткое описание всех разделов приложения
    </button>
    <button class="instruction-option-btn" onclick="startInstructionTour()">
      <strong>Интерактивный гайд</strong>
      Юлия Витальевна проведёт по разделам и всё объяснит
    </button>
  `;
}

function showInstructionTextGuide() {
  const body = document.getElementById('instructionModalBody');
  if (!body) return;
  const sections = INSTRUCTION_TOUR_STEPS.map(s => `
    <div class="instruction-text-section">
      <h4>${escapeHtml(_instructionResolve(s.title))}</h4>
      <p>${escapeHtml(_instructionResolve(s.text))}</p>
    </div>
  `).join('');
  body.innerHTML = `
    <div class="instruction-modal-title">📖 ИНСТРУКЦИЯ // 说明书</div>
    ${sections}
    <button class="instruction-option-btn instruction-back-btn" onclick="showInstructionChooser()">← Назад</button>
  `;
}

function startInstructionTour() {
  closeInstructionModal();
  instructionTourIndex = 0;
  instructionTourPrevPage = null;
  const overlay = document.getElementById('instructionTourOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  renderInstructionTourStep();
}

function closeInstructionTour() {
  const overlay = document.getElementById('instructionTourOverlay');
  if (overlay) overlay.style.display = 'none';
  if (instructionTypeTimer) {
    clearInterval(instructionTypeTimer);
    instructionTypeTimer = null;
  }
  instructionSetHighlight(null);
  instructionResetCasinoTabIfNeeded();
  instructionTourPrevPage = null;
}

function instructionSetHighlight(selector) {
  document.querySelectorAll('.instruction-highlight').forEach(el => el.classList.remove('instruction-highlight'));
  if (!selector) return;
  const el = document.querySelector(selector);
  if (el) {
    el.classList.add('instruction-highlight');
    try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
  }
}

function renderInstructionTourStep() {
  const step = INSTRUCTION_TOUR_STEPS[instructionTourIndex];
  if (!step) {
    closeInstructionTour();
    return;
  }

  if (step.page !== 'casino') instructionResetCasinoTabIfNeeded();

  const navBtn = document.querySelector(`.bottom-nav button[onclick*="showPage('${step.page}'"]`);
  try { showPage(step.page, navBtn || undefined); } catch (e) {}
  if (typeof step.action === 'function') {
    try { step.action(); } catch (e) {}
  }

  instructionTourPrevPage = step.page;

  setTimeout(() => instructionSetHighlight(_instructionResolve(step.highlight)), 80);

  const avatar = document.getElementById('instructionTourAvatar');
  if (avatar) avatar.style.backgroundImage = `url('${INSTRUCTION_IMG_BASE}${step.image}')`;

  const title = document.getElementById('instructionTourTitle');
  if (title) title.textContent = _instructionResolve(step.title);

  const progress = document.getElementById('instructionTourProgress');
  if (progress) progress.textContent = `${instructionTourIndex + 1} / ${INSTRUCTION_TOUR_STEPS.length}`;

  const nextBtn = document.getElementById('instructionTourNextBtn');
  if (nextBtn) nextBtn.textContent = instructionTourIndex === INSTRUCTION_TOUR_STEPS.length - 1 ? 'ЗАВЕРШИТЬ' : 'ДАЛЕЕ →';

  typeInstructionTourText(_instructionResolve(step.text));
}

function typeInstructionTourText(text) {
  const bubble = document.getElementById('instructionTourBubble');
  if (!bubble) return;
  if (instructionTypeTimer) {
    clearInterval(instructionTypeTimer);
    instructionTypeTimer = null;
  }

  bubble.innerHTML = '<span class="instruction-tour-typed"></span><span class="instruction-tour-cursor">▌</span>';
  const typedEl = bubble.querySelector('.instruction-tour-typed');
  let i = 0;
  instructionTypeTimer = setInterval(() => {
    i++;
    typedEl.textContent = text.slice(0, i);
    if (i >= text.length) {
      clearInterval(instructionTypeTimer);
      instructionTypeTimer = null;
      const cursor = bubble.querySelector('.instruction-tour-cursor');
      if (cursor) cursor.remove();
    }
  }, 22);
}

function instructionTourNext() {
  if (instructionTourIndex >= INSTRUCTION_TOUR_STEPS.length - 1) {
    closeInstructionTour();
    return;
  }
  instructionTourIndex++;
  renderInstructionTourStep();
}

function instructionTourSkip() {
  if (instructionTypeTimer) {
    clearInterval(instructionTypeTimer);
    instructionTypeTimer = null;
    const step = INSTRUCTION_TOUR_STEPS[instructionTourIndex];
    const bubble = document.getElementById('instructionTourBubble');
    if (bubble && step) bubble.textContent = step.text;
    return;
  }
  instructionTourNext();
}
