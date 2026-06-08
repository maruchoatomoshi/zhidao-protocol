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
    label: 'Учебный 1',
    cn: '教1楼',
    en: 'Classroom Building No.1',
    category: 'study',
    x: 75.0,
    y: 37.8,
    labelPos: 'right',
    description: 'Учебный корпус в северо-восточной части кампуса.',
  },
  {
    id: 'classroom-2',
    title: 'Учебный корпус No.2',
    label: 'Учебный 2',
    cn: '教2楼',
    en: 'Classroom Building No.2',
    category: 'study',
    x: 82.3,
    y: 62.4,
    labelPos: 'up',
    description: 'Крупный учебный корпус в восточной части кампуса.',
  },
  {
    id: 'classroom-3',
    title: 'Учебный корпус No.3',
    label: 'Учебный 3',
    cn: '教3楼',
    en: 'Classroom Building No.3',
    category: 'study',
    x: 58.3,
    y: 58.1,
    labelPos: 'up',
    description: 'Учебный корпус в центрально-восточной части карты.',
  },
  {
    id: 'classroom-4',
    title: 'Учебный корпус No.4',
    label: 'Учебный 4',
    cn: '教4楼',
    en: 'Classroom Building No.4',
    category: 'study',
    x: 65.8,
    y: 58.1,
    labelPos: 'up',
    description: 'Учебный корпус рядом с No.3 и Run Run Shaw Teaching Building.',
  },
  {
    id: 'classroom-5',
    title: 'Учебный корпус No.5',
    label: 'Учебный 5',
    cn: '教5楼',
    en: 'Administrative / Classroom Building',
    category: 'study',
    x: 59.8,
    y: 39.4,
    labelPos: 'right',
    description: 'Корпус с административными и учебными помещениями.',
  },
  {
    id: 'run-run-shaw-teaching',
    title: 'Run Run Shaw Teaching Building',
    label: 'Run Run Shaw',
    cn: '逸夫教学楼',
    en: 'Run Run Shaw Teaching Building',
    category: 'study',
    x: 73.1,
    y: 59.8,
    labelPos: 'left',
    description: 'Учебный корпус между No.4 и No.2.',
  },
  {
    id: 'library',
    title: 'Библиотека',
    label: 'Библиотека',
    cn: '图书馆',
    en: 'Library',
    category: 'study',
    x: 48.0,
    y: 42.5,
    labelPos: 'right',
    description: 'Библиотека кампуса. Хороший ориентир в центральной части.',
  },
  {
    id: 'conference-center',
    title: 'Конференц-центр',
    label: 'Конф. центр',
    cn: '会议中心',
    en: 'Conference Center',
    category: 'study',
    x: 47.8,
    y: 32.7,
    labelPos: 'right',
    description: 'Конференц-центр рядом с библиотекой.',
  },
  {
    id: 'auditorium',
    title: 'Актовый зал',
    label: 'Актовый зал',
    cn: '礼堂',
    en: 'Auditorium',
    category: 'important',
    x: 45.6,
    y: 64.4,
    labelPos: 'right',
    description: 'Актовый зал в центральной части кампуса.',
  },
  {
    id: 'student-service-center',
    title: 'Центр обслуживания иностранных студентов',
    label: 'Сервис-центр',
    cn: '中国留学服务中心',
    en: 'International Student Service Center',
    category: 'important',
    x: 14.5,
    y: 44.8,
    labelPos: 'right',
    description: 'Сервисный центр в западной части кампуса.',
  },
  {
    id: 'international-office',
    title: 'Офисы иностранных студентов',
    label: 'Офисы',
    cn: '留学生办公室',
    en: 'International Student Office',
    category: 'important',
    x: 60.0,
    y: 42.1,
    labelPos: 'left',
    description: 'Административные точки для иностранных студентов рядом с корпусом No.5.',
    note: 'На оригинальной карте рядом отмечены офисы, финансы и банк.',
  },
  {
    id: 'dining-1',
    title: 'Столовая No.1',
    label: 'Столовая 1',
    cn: '第一食堂',
    en: 'Dining Hall No.1',
    category: 'food',
    x: 49.0,
    y: 73.2,
    labelPos: 'up',
    description: 'Одна из основных столовых кампуса.',
  },
  {
    id: 'dining-2',
    title: 'Столовая No.2',
    label: 'Столовая 2',
    cn: '第二食堂',
    en: 'Dining Hall No.2',
    category: 'food',
    x: 42.6,
    y: 73.0,
    labelPos: 'left',
    description: 'Столовая рядом с южной частью центрального блока.',
  },
  {
    id: 'dining-3',
    title: 'Столовая No.3',
    label: 'Столовая 3',
    cn: '第三食堂',
    en: 'Dining Hall No.3',
    category: 'food',
    x: 6.8,
    y: 44.7,
    labelPos: 'right',
    description: 'Столовая в западной части кампуса.',
  },
  {
    id: 'student-dormitories',
    title: 'Студенческие общежития',
    label: 'Общежития',
    cn: '学生宿舍',
    en: 'Student Dormitories',
    category: 'dorm',
    x: 65.4,
    y: 74.5,
    labelPos: 'up',
    description: 'Зона студенческих общежитий в южной части восточного блока.',
  },
  {
    id: 'expert-building',
    title: 'Expert Building',
    label: 'Expert',
    cn: '专家宿舍',
    en: 'Expert Building',
    category: 'dorm',
    x: 78.8,
    y: 74.7,
    labelPos: 'up',
    description: 'Жилой корпус / экспертное общежитие.',
  },
  {
    id: 'dorm-west',
    title: 'Западные общежития',
    label: 'Общ. 11-15',
    cn: '宿舍区',
    en: 'Dormitory Buildings',
    category: 'dorm',
    x: 16.0,
    y: 65.0,
    labelPos: 'right',
    description: 'Группа общежитий в западной части кампуса.',
  },
  {
    id: 'dorm-south',
    title: 'Южные общежития',
    label: 'Общ. 5-10',
    cn: '宿舍区',
    en: 'Dormitory Buildings',
    category: 'dorm',
    x: 30.8,
    y: 75.1,
    labelPos: 'up',
    description: 'Группа общежитий в южной части центрального блока.',
  },
  {
    id: 'football-ground',
    title: 'Футбольное поле',
    label: 'Футбол',
    cn: '足球场',
    en: 'Football Ground',
    category: 'sport',
    x: 39.8,
    y: 36.9,
    labelPos: 'up',
    description: 'Крупная спортивная зона в центре кампуса.',
  },
  {
    id: 'volleyball-court',
    title: 'Волейбольная площадка',
    label: 'Волейбол',
    cn: '排球场',
    en: 'Volleyball Court',
    category: 'sport',
    x: 24.2,
    y: 51.5,
    labelPos: 'up',
    description: 'Спортивная площадка западнее центральной дороги.',
  },
  {
    id: 'basketball-court',
    title: 'Баскетбольная площадка',
    label: 'Баскетбол',
    cn: '篮球场',
    en: 'Basketball Court',
    category: 'sport',
    x: 27.1,
    y: 59.8,
    labelPos: 'up',
    description: 'Спортивная площадка западнее центральной дороги.',
  },
  {
    id: 'tennis-court',
    title: 'Теннисный корт',
    label: 'Теннис',
    cn: '网球场',
    en: 'Tennis Court',
    category: 'sport',
    x: 36.3,
    y: 59.6,
    labelPos: 'up',
    description: 'Теннисная зона рядом с баскетбольной площадкой.',
  },
  {
    id: 'sports-hall',
    title: 'Спортивный корпус',
    label: 'Спортзал',
    cn: '逸夫体育馆',
    en: 'Run Run Shaw Hall of Sports Activities',
    category: 'sport',
    x: 30.3,
    y: 37.0,
    labelPos: 'left',
    description: 'Спортивный корпус рядом с центральными площадками.',
  },
  {
    id: 'hospital',
    title: 'Медпункт / больница',
    label: 'Медпункт',
    cn: '校医院',
    en: 'Hospital',
    category: 'important',
    x: 6.4,
    y: 68.7,
    labelPos: 'right',
    description: 'Важная точка для медицинских вопросов.',
  },
  {
    id: 'south-gate',
    title: 'Южные ворота',
    label: 'Южные ворота',
    cn: '南门',
    en: 'South Gate',
    category: 'meeting',
    x: 54.0,
    y: 82.9,
    labelPos: 'up',
    description: 'Южный выход к Chengfu Road. Потенциальная точка сбора.',
  },
  {
    id: 'west-gate',
    title: 'Западные ворота',
    label: 'Западные ворота',
    cn: '西门',
    en: 'West Gate',
    category: 'meeting',
    x: 11.4,
    y: 53.6,
    labelPos: 'right',
    description: 'Западный вход/выход кампуса.',
  },
  {
    id: 'southwest-gate',
    title: 'Юго-западные ворота',
    label: 'Юго-запад',
    cn: '西南门',
    en: 'Southwest Gate',
    category: 'meeting',
    x: 10.8,
    y: 82.8,
    labelPos: 'right',
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
    return [point.title, point.label, point.cn, point.en, point.description, point.note]
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
            <button class="campus-map-pin ${campusMapEscape(point.category)} label-${campusMapEscape(point.labelPos || 'down')}" style="left:${point.x}%;top:${point.y}%;" type="button" onclick="openCampusMapPoint('${campusMapEscape(point.id)}')" aria-label="${campusMapEscape(point.title)}">
              <span></span>
              <em>${campusMapEscape(point.label || point.title)}</em>
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
  const forced = document.body.dataset.campusMapMode;
  if (forced === 'original') {
    delete document.body.dataset.campusMapMode;
  } else {
    document.body.dataset.campusMapMode = 'original';
  }
  initCampusMap();
}

function campusMapAssetMode() {
  const forced = document.body.dataset.campusMapMode;
  if (forced === 'original') return 'original';
  const themePath = typeof currentThemePath !== 'undefined' ? currentThemePath : '';
  const theme = String(themePath || localStorage.getItem('zhidao_theme') || '').toLowerCase();
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
