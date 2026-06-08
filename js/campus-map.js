const CAMPUS_MAP_ASSETS = {
  cyberpunk: './cyberpunk_map.png',
  genshin: './genshin_map.png',
  original: './blcu_map.png',
};

const CAMPUS_MAP_CATEGORIES = [
  { id: 'all', label: 'Все' },
  { id: 'study', label: 'Учёба' },
  { id: 'food', label: 'Еда' },
  { id: 'dorm', label: 'Жильё' },
  { id: 'sport', label: 'Спорт' },
  { id: 'important', label: 'Важно' },
  { id: 'meeting', label: 'Сбор' },
];

const CAMPUS_POINTS = [
  {
    id: 'classroom-1',
    title: 'Учебный корпус No.1',
    cn: '教1楼',
    en: 'Classroom Building No.1',
    category: 'study',
    x: 75.7,
    y: 36.3,
    description: 'Один из основных учебных корпусов восточной части кампуса.',
  },
  {
    id: 'classroom-2',
    title: 'Учебный корпус No.2',
    cn: '教2楼',
    en: 'Classroom Building No.2',
    category: 'study',
    x: 81.5,
    y: 62.5,
    description: 'Учебный корпус рядом с восточной частью кампуса.',
  },
  {
    id: 'classroom-3',
    title: 'Учебный корпус No.3',
    cn: '教3楼',
    en: 'Classroom Building No.3',
    category: 'study',
    x: 57.8,
    y: 59.4,
    description: 'Учебный корпус в центрально-восточной части карты.',
  },
  {
    id: 'classroom-4',
    title: 'Учебный корпус No.4',
    cn: '教4楼',
    en: 'Classroom Building No.4',
    category: 'study',
    x: 65.7,
    y: 59.2,
    description: 'Учебный корпус рядом с No.3 и Run Run Shaw Teaching Building.',
  },
  {
    id: 'classroom-5',
    title: 'Учебный корпус No.5',
    cn: '教5楼',
    en: 'Administrative / Classroom Building',
    category: 'study',
    x: 60.8,
    y: 39.7,
    description: 'Корпус с административными и учебными помещениями.',
  },
  {
    id: 'library',
    title: 'Библиотека',
    cn: '图书馆',
    en: 'Library',
    category: 'study',
    x: 48.7,
    y: 43.2,
    description: 'Библиотека кампуса. Полезный ориентир в центральной части.',
  },
  {
    id: 'conference-center',
    title: 'Конференц-центр',
    cn: '会议中心',
    en: 'Conference Center',
    category: 'study',
    x: 48.8,
    y: 32.4,
    description: 'Конференц-центр рядом с библиотекой.',
  },
  {
    id: 'dining-1',
    title: 'Столовая No.1',
    cn: '第一食堂',
    en: 'Dining Hall No.1',
    category: 'food',
    x: 49.1,
    y: 72.2,
    description: 'Одна из основных столовых кампуса.',
  },
  {
    id: 'dining-2',
    title: 'Столовая No.2',
    cn: '第二食堂',
    en: 'Dining Hall No.2',
    category: 'food',
    x: 42.8,
    y: 72.6,
    description: 'Столовая рядом с южной частью центрального блока.',
  },
  {
    id: 'dining-3',
    title: 'Столовая No.3',
    cn: '第三食堂',
    en: 'Dining Hall No.3',
    category: 'food',
    x: 6.8,
    y: 48.6,
    description: 'Столовая в западной части кампуса.',
  },
  {
    id: 'student-dormitories',
    title: 'Студенческие общежития',
    cn: '学生宿舍',
    en: 'Student Dormitories',
    category: 'dorm',
    x: 64.1,
    y: 76.6,
    description: 'Зона студенческих общежитий в южной части восточного блока.',
  },
  {
    id: 'expert-building',
    title: 'Expert Building',
    cn: '专家宿舍',
    en: 'Expert Building',
    category: 'dorm',
    x: 77.5,
    y: 76.4,
    description: 'Жилой корпус / экспертное общежитие.',
  },
  {
    id: 'xijiao-hotel',
    title: 'Xijiao Hotel',
    cn: '西郊宾馆',
    en: 'Xijiao Hotel',
    category: 'dorm',
    x: 10.2,
    y: 22.7,
    description: 'Отель в северо-западной части схемы.',
  },
  {
    id: 'football-ground',
    title: 'Футбольное поле',
    cn: '足球场',
    en: 'Football Ground',
    category: 'sport',
    x: 39.9,
    y: 37.5,
    description: 'Крупная спортивная зона в центре кампуса.',
  },
  {
    id: 'basketball-court',
    title: 'Баскетбольная площадка',
    cn: '篮球场',
    en: 'Basketball Court',
    category: 'sport',
    x: 27.2,
    y: 58.6,
    description: 'Спортивная площадка западнее центральной дороги.',
  },
  {
    id: 'tennis-court',
    title: 'Теннисный корт',
    cn: '网球场',
    en: 'Tennis Court',
    category: 'sport',
    x: 36.2,
    y: 58.5,
    description: 'Теннисная зона рядом с баскетбольной площадкой.',
  },
  {
    id: 'sports-hall',
    title: 'Спортивный корпус',
    cn: '逸夫体育馆',
    en: 'Run Run Shaw Hall of Sports Activities',
    category: 'sport',
    x: 30.8,
    y: 36.4,
    description: 'Спортивный корпус рядом с центральными площадками.',
  },
  {
    id: 'hospital',
    title: 'Медпункт / больница',
    cn: '校医院',
    en: 'Hospital',
    category: 'important',
    x: 6.2,
    y: 70.3,
    description: 'Важная точка для медицинских вопросов.',
  },
  {
    id: 'international-office',
    title: 'Офис иностранных студентов',
    cn: '留学生办公室',
    en: 'International Student Office',
    category: 'important',
    x: 60.5,
    y: 45.0,
    description: 'Административная точка для иностранных студентов.',
    note: 'На оригинальной карте отмечены офисы и финансовые службы рядом с корпусом No.5.',
  },
  {
    id: 'south-gate',
    title: 'Южные ворота',
    cn: '南门',
    en: 'South Gate',
    category: 'meeting',
    x: 54.0,
    y: 85.0,
    description: 'Южный выход к Chengfu Road. Потенциальная точка сбора.',
  },
  {
    id: 'west-gate',
    title: 'Западные ворота',
    cn: '西门',
    en: 'West Gate',
    category: 'meeting',
    x: 12.0,
    y: 56.0,
    description: 'Западный вход/выход кампуса.',
  },
  {
    id: 'southwest-gate',
    title: 'Юго-западные ворота',
    cn: '西南门',
    en: 'Southwest Gate',
    category: 'meeting',
    x: 10.4,
    y: 85.2,
    description: 'Юго-западный выход к остановкам общественного транспорта.',
  },
];

let campusMapFilter = 'all';
let campusMapQuery = '';

function campusMapCategoryLabel(category) {
  return (CAMPUS_MAP_CATEGORIES.find(item => item.id === category) || {}).label || category;
}

function campusMapEscape(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function campusMapFilteredPoints() {
  const q = campusMapQuery.trim().toLowerCase();
  return CAMPUS_POINTS.filter(point => {
    const categoryOk = campusMapFilter === 'all' || point.category === campusMapFilter;
    if (!categoryOk) return false;
    if (!q) return true;
    return [point.title, point.cn, point.en, point.description, point.note]
      .some(value => String(value || '').toLowerCase().includes(q));
  });
}

function initCampusMap() {
  const root = document.getElementById('campusMapRoot');
  if (!root) return;

  const mode = campusMapAssetMode();
  const points = campusMapFilteredPoints();
  root.innerHTML = `
    <div class="campus-map-panel">
      <div class="campus-map-head">
        <div>
          <div class="campus-map-kicker">${mode === 'genshin' ? 'LIYUE CAMPUS ATLAS' : 'CAMPUS NETWORK MAP'}</div>
          <div class="campus-map-title">Beijing Language and Culture University</div>
        </div>
        <button class="campus-map-mode" type="button" onclick="toggleCampusMapOriginal()">${mode === 'original' ? 'THEME' : 'ORIGINAL'}</button>
      </div>
      <div class="campus-map-search">
        <i class="ti ti-search"></i>
        <input id="campusMapSearch" type="text" placeholder="Поиск: столовая, библиотека, ворота..." value="${campusMapEscape(campusMapQuery)}">
      </div>
      <div class="campus-map-filters">
        ${CAMPUS_MAP_CATEGORIES.map(category => `
          <button type="button" class="${campusMapFilter === category.id ? 'active' : ''}" onclick="setCampusMapFilter('${category.id}')">${campusMapEscape(category.label)}</button>
        `).join('')}
      </div>
      <div class="campus-map-scroll">
        <div class="campus-map-stage">
          <img src="${CAMPUS_MAP_ASSETS[mode] || CAMPUS_MAP_ASSETS.cyberpunk}" alt="Campus map">
          ${points.map(point => `
            <button class="campus-map-pin ${campusMapEscape(point.category)}" style="left:${point.x}%;top:${point.y}%;" type="button" onclick="openCampusMapPoint('${campusMapEscape(point.id)}')" aria-label="${campusMapEscape(point.title)}">
              <span></span>
            </button>
          `).join('')}
        </div>
      </div>
      <div class="campus-map-list">
        ${points.length ? points.map(point => `
          <button type="button" class="campus-map-row ${campusMapEscape(point.category)}" onclick="openCampusMapPoint('${campusMapEscape(point.id)}')">
            <span class="campus-map-row-dot"></span>
            <span>
              <b>${campusMapEscape(point.title)}</b>
              <small>${campusMapEscape(point.cn)} · ${campusMapEscape(point.en)} · ${campusMapCategoryLabel(point.category)}</small>
            </span>
          </button>
        `).join('') : '<div class="campus-map-empty">Ничего не найдено</div>'}
      </div>
    </div>
    <div id="campusMapPopup" class="campus-map-popup" style="display:none;"></div>
  `;

  const search = document.getElementById('campusMapSearch');
  if (search) {
    search.addEventListener('input', () => {
      campusMapQuery = search.value || '';
      window.clearTimeout(search._campusMapTimer);
      search._campusMapTimer = window.setTimeout(initCampusMap, 180);
    });
  }
}

function setCampusMapFilter(filter) {
  campusMapFilter = filter || 'all';
  initCampusMap();
}

function toggleCampusMapOriginal() {
  const current = campusMapAssetMode();
  const forced = document.body.dataset.campusMapMode;
  if (forced === 'original') {
    delete document.body.dataset.campusMapMode;
  } else {
    document.body.dataset.campusMapMode = current;
    document.body.dataset.campusMapMode = 'original';
  }
  initCampusMap();
}

function campusMapAssetMode() {
  const forced = document.body.dataset.campusMapMode;
  if (forced === 'original') return 'original';
  const theme = String(currentThemePath || localStorage.getItem('zhidao_theme') || '').toLowerCase();
  if (theme.includes('genshin')) return 'genshin';
  return 'cyberpunk';
}

function openCampusMapPoint(id) {
  const point = CAMPUS_POINTS.find(item => item.id === id);
  const popup = document.getElementById('campusMapPopup');
  if (!point || !popup) return;
  popup.innerHTML = `
    <div class="campus-map-popup-backdrop" onclick="closeCampusMapPoint()"></div>
    <div class="campus-map-popup-card ${campusMapEscape(point.category)}">
      <button class="campus-map-popup-close" type="button" onclick="closeCampusMapPoint()">×</button>
      <div class="campus-map-popup-category">${campusMapCategoryLabel(point.category)}</div>
      <h3>${campusMapEscape(point.title)}</h3>
      <div class="campus-map-popup-cn">${campusMapEscape(point.cn)} · ${campusMapEscape(point.en)}</div>
      <p>${campusMapEscape(point.description)}</p>
      ${point.note ? `<div class="campus-map-popup-note">${campusMapEscape(point.note)}</div>` : ''}
    </div>
  `;
  popup.style.display = 'block';
}

function closeCampusMapPoint() {
  const popup = document.getElementById('campusMapPopup');
  if (popup) popup.style.display = 'none';
}
