// ===== Инструкция (Юля) =====

const INSTRUCTION_IMG_BASE = 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/';

const INSTRUCTION_TOUR_STEPS = [
  {
    page: 'home',
    image: 'julia_based.png',
    title: 'ПРОФИЛЬ // 主页',
    text: 'Привет! Я Юля — на связи как ассистент протокола ZHIDAO. Здесь, на главной, твой профиль: баллы ★, ранг, путь развития и аватар. Жми «Далее», покажу остальное.'
  },
  {
    page: 'schedule',
    image: 'julia_explaining.png',
    title: 'РАСПИСАНИЕ // 日程',
    text: 'Вкладка «日程» — расписание поездки и объявления. Здесь всегда видно, что происходит сегодня и что запланировано дальше.'
  },
  {
    page: 'rating',
    image: 'julia_explaining2.png',
    title: 'РЕЙТИНГ // 排名',
    text: '«排名» — общий рейтинг операторов по баллам, а также рейтинг по дневнику. Следи за своим местом в таблице!'
  },
  {
    page: 'shop',
    image: 'julia_based2.png',
    title: 'МАГАЗИН // 商店',
    text: '«商店» — магазин. Трать заработанные ★ на предметы, кейсы и улучшения для профиля.'
  },
  {
    page: 'casino',
    image: 'julia_thinking.png',
    title: 'КЕЙСЫ // 箱子',
    text: '«箱子» — кейсы и испытания удачи. Открывай их за ★ и получай имплантанты и карточки с особыми бонусами.'
  },
  {
    page: 'implants',
    image: 'julia_explaining2.png',
    title: 'ИНВЕНТАРЬ // 植入物',
    text: '«植入物» — твой инвентарь: имплантанты и карточки. Многие из них дают бонусы в ивентах вроде Architect Protocol.'
  },
  {
    page: 'more',
    image: 'julia_explaining.png',
    title: 'ЕЩЁ // 更多',
    text: '«更多» — здесь всё остальное: дневник со звёздами, темы оформления, карта кампуса, стирка, ачивки и команда. Загляни сюда за деталями.'
  },
  {
    page: 'home',
    image: 'julia_goodbyeing.png',
    title: 'УДАЧИ, ОПЕРАТОР',
    text: 'Это основное! В этой поездке я не рядом, но мой протокол остаётся на связи — открой эту инструкцию снова через профиль, если понадоблюсь. Удачной поездки! 🏮'
  },
];

let instructionTourIndex = 0;
let instructionTypeTimer = null;

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
      Краткое описание всех разделов приложения.
    </button>
    <button class="instruction-option-btn" onclick="startInstructionTour()">
      <strong>Интерактивный гайд</strong>
      Юля проведёт по разделам и всё объяснит.
    </button>
  `;
}

function showInstructionTextGuide() {
  const body = document.getElementById('instructionModalBody');
  if (!body) return;
  const sections = INSTRUCTION_TOUR_STEPS.map(s => `
    <div class="instruction-text-section">
      <h4>${escapeHtml(s.title)}</h4>
      <p>${escapeHtml(s.text)}</p>
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
}

function renderInstructionTourStep() {
  const step = INSTRUCTION_TOUR_STEPS[instructionTourIndex];
  if (!step) {
    closeInstructionTour();
    return;
  }

  const navBtn = document.querySelector(`.bottom-nav button[onclick*="showPage('${step.page}'"]`);
  try { showPage(step.page, navBtn || undefined); } catch (e) {}

  const avatar = document.getElementById('instructionTourAvatar');
  if (avatar) avatar.style.backgroundImage = `url('${INSTRUCTION_IMG_BASE}${step.image}')`;

  const title = document.getElementById('instructionTourTitle');
  if (title) title.textContent = step.title;

  const progress = document.getElementById('instructionTourProgress');
  if (progress) progress.textContent = `${instructionTourIndex + 1} / ${INSTRUCTION_TOUR_STEPS.length}`;

  const nextBtn = document.getElementById('instructionTourNextBtn');
  if (nextBtn) nextBtn.textContent = instructionTourIndex === INSTRUCTION_TOUR_STEPS.length - 1 ? 'ЗАВЕРШИТЬ' : 'ДАЛЕЕ →';

  typeInstructionTourText(step.text);
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
