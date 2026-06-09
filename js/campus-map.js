const CAMPUS_MAP_ASSETS = {
  cyberpunk: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/cyberpunk_map.png',
  genshin: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/genshin_map.png',
  original: 'https://raw.githubusercontent.com/maruchoatomoshi/zhidao-protocol/main/blcu_map.png',
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

const CAMPUS_MAP_EDITOR_OWNER_ID = 389741116;
const CAMPUS_MAP_EDITOR_STORAGE_KEY = 'zhidao_campus_map_editor_v1';
const CAMPUS_MAP_EDITOR_CLOUD_KEY = 'campus_map_editor_v1';

const CAMPUS_POINTS = [
  {
    id: 'classroom-1',
    title: 'Учебный корпус No.1',
    label: '教1楼',
    cn: '教1楼',
    en: 'Classroom Building No.1',
    category: 'study',
    x: 78.0,
    y: 28.0,
    labelPos: 'up',
    description: 'Учебный корпус в северо-восточной части кампуса.',
  },
  {
    id: 'classroom-2',
    title: 'Учебный корпус No.2',
    label: '教2楼',
    cn: '教2楼',
    en: 'Classroom Building No.2',
    category: 'study',
    x: 82.3,
    y: 50.0,
    labelPos: 'up',
    description: 'Крупный учебный корпус в восточной части кампуса.',
  },
  {
    id: 'publishing-house',
    title: 'Издательство',
    label: '出版社',
    cn: '出版社',
    en: 'Publishing House',
    category: 'study',
    x: 86.0,
    y: 60.0,
    labelPos: 'down',
    description: 'Издательство',
  },
  {
    id: 'classroom-3',
    title: 'Учебный корпус No.3',
    label: '教3楼',
    cn: '教3楼',
    en: 'Classroom Building No.3',
    category: 'study',
    x: 58.5,
    y: 47.0,
    labelPos: 'up',
    description: 'Учебный корпус в центрально-восточной части карты.',
  },
  {
    id: 'classroom-4',
    title: 'Учебный корпус No.4',
    label: '教4楼',
    cn: '教4楼',
    en: 'Classroom Building No.4',
    category: 'study',
    x: 68.0,
    y: 47.0,
    labelPos: 'up',
    description: 'Учебный корпус рядом с No.3 и Run Run Shaw Teaching Building.',
  },
  {
    id: 'classroom-5',
    title: 'Администрация',
    label: '办公楼',
    cn: '办公楼',
    en: 'Administrative / Classroom Building',
    category: 'important',
    x: 60.0,
    y: 35.0,
    labelPos: 'up',
    description: 'Административные точки для иностранных студентов рядом с корпусом No.5.',
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
    label: '图书馆',
    cn: '图书馆',
    en: 'Library',
    category: 'study',
    x: 48.9,
    y: 33.5,
    labelPos: 'right',
    description: 'Библиотека кампуса. Хороший ориентир в центральной части.',
  },
  {
    id: 'conference-center',
    title: 'Конференц-центр',
    label: '会议中心',
    cn: '会议中心',
    en: 'Conference Center',
    category: 'study',
    x: 48.9,
    y: 21.3,
    labelPos: 'up',
    description: 'Конференц-центр рядом с библиотекой.',
  },
  {
    id: 'auditorium',
    title: 'Актовый зал',
    label: '礼堂',
    cn: '礼堂',
    en: 'Auditorium',
    category: 'important',
    x: 50.0,
    y: 55.0,
    labelPos: 'up',
    description: 'Актовый зал в центральной части кампуса.',
  },
  {
    id: 'student-service-center',
    title: 'Магазин',
    label: '超市和咖啡店',
    cn: '超市和咖啡店',
    en: 'Shop and Coffee',
    category: 'food',
    x: 14.0,
    y: 33.0,
    labelPos: 'up',
    description: 'Магазин, кофейня, блинчики',
  },
  {
    id: 'pickup-point',
    title: 'ПВЗ',
    label: 'ПВЗ',
    cn: 'ПВЗ',
    en: 'Pickup Point',
    category: 'important',
    x: 14.5,
    y: 40.0,
    labelPos: 'right',
    description: 'Пункт выдачи заказов',
  },
  {
    id: 'international-office',
    title: 'Банк',
    label: '银行',
    cn: '银行',
    en: 'Bank',
    category: 'important',
    x: 50.0,
    y: 70.0,
    labelPos: 'left',
    description: 'Ориентир в виде банка. В этом же здании находится автомат для пополнения интернета и Старбакс',
  },
  {
    id: 'dining-1',
    title: 'Столовая No.1',
    label: '食堂',
    cn: '食堂',
    en: 'Dining Hall No.1',
    category: 'food',
    x: 50.0,
    y: 60.0,
    labelPos: 'down',
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
    label: '学生宿舍',
    cn: '学生宿舍',
    en: 'Student Dormitories',
    category: 'dorm',
    x: 65.4,
    y: 64.0,
    labelPos: 'up',
    description: 'Зона студенческих общежитий в южной части восточного блока.',
  },
  {
    id: 'expert-building',
    title: 'Expert Building',
    label: '专家宿舍',
    cn: '专家宿舍',
    en: 'Expert Building',
    category: 'dorm',
    x: 75.0,
    y: 64.0,
    labelPos: 'up',
    description: 'Жилой корпус / экспертное общежитие.',
  },
  {
    id: 'dorm-west',
    title: 'Общаги',
    label: '宿舍楼',
    cn: '宿舍楼',
    en: 'Dormitory Buildings',
    category: 'dorm',
    x: 18.5,
    y: 62.8,
    labelPos: 'right',
    description: 'Группа общежитий в западной части кампуса.',
  },
  {
    id: 'our-dorm',
    title: 'Наша общага',
    label: 'Наша общага',
    cn: '宿舍',
    en: 'ZHIDAO Dormitory',
    category: 'dorm',
    x: 5.0,
    y: 40.0,
    labelPos: 'up',
    labelDx: 0,
    labelDy: 0,
    description: 'Наша общага. Здесь спим и рейджбайтим друг друга',
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
    label: '足球场',
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
    label: '排球场',
    cn: '排球场',
    en: 'Volleyball Court',
    category: 'sport',
    x: 27.1,
    y: 40.0,
    labelPos: 'up',
    description: 'Спортивная площадка западнее центральной дороги.',
  },
  {
    id: 'basketball-court',
    title: 'Баскетбольная площадка',
    label: '篮球场',
    cn: '篮球场',
    en: 'Basketball Court',
    category: 'sport',
    x: 27.1,
    y: 48.0,
    labelPos: 'up',
    description: 'Спортивная площадка западнее центральной дороги.',
  },
  {
    id: 'tennis-court',
    title: 'Теннисный корт',
    label: '网球场',
    cn: '网球场',
    en: 'Tennis Court',
    category: 'sport',
    x: 37.6,
    y: 48.0,
    labelPos: 'up',
    description: 'Теннисная зона рядом с баскетбольной площадкой.',
  },
  {
    id: 'sports-hall',
    title: 'Спортивный корпус',
    label: '体育',
    cn: '逸夫体育馆',
    en: 'Run Run Shaw Hall of Sports Activities',
    category: 'sport',
    x: 30.3,
    y: 23.0,
    labelPos: 'up',
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
    label: '南门',
    cn: '南门',
    en: 'South Gate',
    category: 'meeting',
    x: 54.0,
    y: 71.0,
    labelPos: 'up',
    description: 'Южный выход к Chengfu Road. Потенциальная точка сбора.',
  },
  {
    id: 'bus-meeting-point',
    title: 'Точка сбора на поездки',
    label: 'Точка сбора',
    cn: '集合点',
    en: 'Trip Meeting Point',
    category: 'meeting',
    x: 54.0,
    y: 63.5,
    labelPos: 'right',
    description: 'Потенциальная точка сбора до автобуса',
  },
  {
    id: 'east-gate',
    title: 'Восточные ворота',
    label: '东门',
    cn: '东门',
    en: 'East Gate',
    category: 'meeting',
    x: 90.3,
    y: 28.0,
    labelPos: 'right',
    description: 'Восточный вход/выход',
  },
  {
    id: 'west-gate',
    title: 'Западные ворота',
    label: '西门',
    cn: '西门',
    en: 'West Gate',
    category: 'meeting',
    x: 11.4,
    y: 44.0,
    labelPos: 'down',
    description: 'Западный вход/выход кампуса.',
  },
  {
    id: 'southwest-gate',
    title: 'Юго-западные ворота',
    label: '南西门',
    cn: '西南门',
    en: 'Southwest Gate',
    category: 'meeting',
    x: 10.0,
    y: 71.0,
    labelPos: 'down',
    description: 'Юго-западный выход к остановкам общественного транспорта.',
  },
];

const CAMPUS_MAP_DISPLAY_FIXES = {
  'банк': {
    label: '银行',
    cn: '银行',
    en: 'Bank',
    category: 'important',
    description: 'Ориентир в виде банка. В этом же здании находится автомат для пополнения интернета и Старбакс',
  },
  'макдональдс': {
    label: '麦当劳和蜜雪',
    cn: '麦当劳和蜜雪',
    en: 'McDonalds / Mixue',
    category: 'food',
    description: 'Райское место. Ещё есть кофейня и магазин.',
  },
  'магазин': {
    label: '超市和咖啡店',
    cn: '超市和咖啡店',
    en: 'Shop and Coffee',
    category: 'food',
    description: 'Магазин, кофейня, блинчики',
  },
  'пвз': {
    label: 'ПВЗ',
    cn: 'ПВЗ',
    en: 'Pickup Point',
    category: 'important',
    description: 'Пункт выдачи заказов',
  },
  'медпункт / больница': {
    label: '校医院',
    cn: '校医院',
    en: 'Hospital',
    category: 'important',
    description: 'Важная точка для медицинских вопросов.',
  },
  'медпункт': {
    label: '校医院',
    cn: '校医院',
    en: 'Hospital',
    category: 'important',
    description: 'Важная точка для медицинских вопросов.',
  },
};

const CAMPUS_MAP_FAVORITES_STORAGE_KEY = 'zhidao_campus_map_favorites_v1';

let campusMapFilter = 'all';
let campusMapQuery = '';
let campusMapEditorEnabled = false;
let campusMapEditorSelectionId = '';
let campusMapEditorCursor = null;
let campusMapEditorAutosaveTimer = null;
let campusMapEditorCloudLoaded = false;
let campusMapGlobalLoaded = false;
let campusMapFavorites = null;
let campusMapFavoritesOnly = false;
let campusMapRouteMode = false;
let campusMapRouteFrom = '';
let campusMapRouteTo = '';

function campusMapCategoryLabel(category) {
  return (CAMPUS_MAP_CATEGORIES.find(item => item.id === category) || {}).label || category;
}

function campusMapLoadFavorites() {
  if (campusMapFavorites) return campusMapFavorites;
  try {
    const raw = JSON.parse(localStorage.getItem(CAMPUS_MAP_FAVORITES_STORAGE_KEY) || '[]');
    campusMapFavorites = Array.isArray(raw) ? raw.filter(id => typeof id === 'string') : [];
  } catch (e) {
    campusMapFavorites = [];
  }
  return campusMapFavorites;
}

function campusMapIsFavorite(id) {
  return campusMapLoadFavorites().includes(id);
}

function toggleCampusMapFavorite(event, id) {
  if (event) event.stopPropagation();
  const list = campusMapLoadFavorites();
  const idx = list.indexOf(id);
  if (idx >= 0) list.splice(idx, 1);
  else list.push(id);
  try { localStorage.setItem(CAMPUS_MAP_FAVORITES_STORAGE_KEY, JSON.stringify(list)); } catch (e) {}
  if (campusMapFavoritesOnly && idx >= 0 && !list.length) campusMapFavoritesOnly = false;
  initCampusMap();
}

function toggleCampusMapFavoritesOnly() {
  campusMapFavoritesOnly = !campusMapFavoritesOnly;
  initCampusMap();
}

function toggleCampusMapRouteMode() {
  campusMapRouteMode = !campusMapRouteMode;
  if (!campusMapRouteMode) {
    campusMapRouteFrom = '';
    campusMapRouteTo = '';
  }
  initCampusMap();
}

function clearCampusMapRoute() {
  campusMapRouteFrom = '';
  campusMapRouteTo = '';
  initCampusMap();
}

function campusMapHandleRoutePick(id) {
  if (!campusMapRouteFrom || (campusMapRouteFrom && campusMapRouteTo)) {
    campusMapRouteFrom = id;
    campusMapRouteTo = '';
  } else if (id === campusMapRouteFrom) {
    campusMapRouteFrom = '';
  } else {
    campusMapRouteTo = id;
  }
  initCampusMap();
}

function campusMapRouteEstimate(from, to) {
  const dx = Number(from.x || 0) - Number(to.x || 0);
  const dy = Number(from.y || 0) - Number(to.y || 0);
  const pct = Math.sqrt(dx * dx + dy * dy);
  const meters = Math.round(pct * 6.5);
  const minutes = Math.max(1, Math.round(meters / 75));
  return { meters, minutes };
}

function campusMapCanEdit() {
  return Number(typeof currentUserId !== 'undefined' ? currentUserId : 0) === CAMPUS_MAP_EDITOR_OWNER_ID
    && !!(typeof isArchitect !== 'undefined' && isArchitect);
}

function campusMapPointTitleKey(point) {
  return String(point && point.title || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function campusMapNormalizeEditorEdits(value) {
  const parsed = value && typeof value === 'object' ? value : {};
  return {
    overrides: parsed.overrides && typeof parsed.overrides === 'object' ? parsed.overrides : {},
    custom: Array.isArray(parsed.custom) ? parsed.custom.filter(point => point && point.id) : [],
    updatedAt: Number(parsed.updatedAt || 0),
  };
}

function campusMapHasEditorEdits(edits) {
  return !!(edits && (Object.keys(edits.overrides || {}).length || (edits.custom || []).length));
}

function campusMapEditorCloudStorage() {
  try {
    return window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.CloudStorage
      ? window.Telegram.WebApp.CloudStorage
      : null;
  } catch (e) {
    return null;
  }
}

function campusMapApiBase() {
  return typeof API_URL === 'string' && API_URL ? API_URL : '';
}

function campusMapLoadEditorEdits() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CAMPUS_MAP_EDITOR_STORAGE_KEY) || '{}');
    return campusMapNormalizeEditorEdits(parsed);
  } catch (e) {
    return { overrides: {}, custom: [], updatedAt: 0 };
  }
}

function campusMapSaveEditorEdits(edits) {
  const normalized = { ...campusMapNormalizeEditorEdits(edits), updatedAt: Date.now() };
  const data = JSON.stringify(normalized);
  localStorage.setItem(CAMPUS_MAP_EDITOR_STORAGE_KEY, data);
  campusMapSaveEditorCloudEdits(normalized);
  campusMapSaveGlobalEdits(normalized);
}

async function campusMapLoadGlobalOnce() {
  if (campusMapGlobalLoaded) return;
  campusMapGlobalLoaded = true;

  try {
    const apiBase = campusMapApiBase();
    if (!apiBase) return;
    const response = await fetch(`${apiBase}/api/campus-map`);
    if (!response.ok) return;
    const globalEdits = campusMapNormalizeEditorEdits(await response.json());
    const localEdits = campusMapLoadEditorEdits();

    if (campusMapHasEditorEdits(globalEdits) && (!campusMapHasEditorEdits(localEdits) || globalEdits.updatedAt > localEdits.updatedAt)) {
      localStorage.setItem(CAMPUS_MAP_EDITOR_STORAGE_KEY, JSON.stringify(globalEdits));
      initCampusMap();
      return;
    }

    if (campusMapCanEdit() && campusMapHasEditorEdits(localEdits) && localEdits.updatedAt >= globalEdits.updatedAt) {
      campusMapSaveGlobalEdits(localEdits);
    }
  } catch (e) {}
}

async function campusMapSaveGlobalEdits(edits) {
  if (!campusMapCanEdit()) return;
  try {
    const apiBase = campusMapApiBase();
    if (!apiBase) return;
    const normalized = { ...campusMapNormalizeEditorEdits(edits), updatedAt: Number(edits && edits.updatedAt || 0) || Date.now() };
    await fetch(`${apiBase}/api/admin/campus-map`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-admin-id': String(currentUserId),
      },
      body: JSON.stringify(normalized),
    });
  } catch (e) {}
}

function campusMapSaveEditorCloudEdits(edits) {
  const cloud = campusMapEditorCloudStorage();
  if (!cloud || !campusMapCanEdit()) return;
  try {
    cloud.setItem(CAMPUS_MAP_EDITOR_CLOUD_KEY, JSON.stringify(campusMapNormalizeEditorEdits(edits)));
  } catch (e) {}
}

function campusMapLoadEditorCloudOnce() {
  if (!campusMapCanEdit() || campusMapEditorCloudLoaded) return;
  campusMapEditorCloudLoaded = true;
  const cloud = campusMapEditorCloudStorage();
  if (!cloud) return;

  try {
    cloud.getItem(CAMPUS_MAP_EDITOR_CLOUD_KEY, (err, value) => {
      if (err) return;
      let cloudEdits = { overrides: {}, custom: [], updatedAt: 0 };
      try {
        cloudEdits = campusMapNormalizeEditorEdits(JSON.parse(value || '{}'));
      } catch (e) {}

      const localEdits = campusMapLoadEditorEdits();
      if (campusMapHasEditorEdits(cloudEdits) && (!campusMapHasEditorEdits(localEdits) || cloudEdits.updatedAt > localEdits.updatedAt)) {
        localStorage.setItem(CAMPUS_MAP_EDITOR_STORAGE_KEY, JSON.stringify(cloudEdits));
        initCampusMap();
      } else if (campusMapHasEditorEdits(localEdits)) {
        campusMapSaveEditorEdits(localEdits);
      }
    });
  } catch (e) {}
}

function campusMapAllPoints() {
  const edits = campusMapLoadEditorEdits();
  const base = CAMPUS_POINTS.map(point => ({
    ...point,
    ...(edits.overrides[point.id] || {}),
    isCustom: false,
  }));
  const custom = edits.custom
    .filter(point => point && point.id)
    .map(point => ({ ...point, isCustom: true }));
  return [...base, ...custom].map(campusMapApplyDisplayFix);
}

function campusMapApplyDisplayFix(point) {
  const fix = CAMPUS_MAP_DISPLAY_FIXES[campusMapPointTitleKey(point)];
  return fix ? { ...point, ...fix } : point;
}

function campusMapCatalogPoints(points) {
  const result = [];
  const byTitle = new Map();
  (points || []).forEach(point => {
    const key = campusMapPointTitleKey(point) || point.id;
    const existingIndex = byTitle.get(key);
    if (existingIndex === undefined) {
      byTitle.set(key, result.length);
      result.push(point);
      return;
    }

    if (point.isCustom && !result[existingIndex].isCustom) {
      result[existingIndex] = point;
    }
  });
  return result;
}

function campusMapFindPoint(id) {
  return campusMapAllPoints().find(item => item.id === id);
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
  return campusMapAllPoints().filter(point => {
    if (campusMapFavoritesOnly && !campusMapIsFavorite(point.id)) return false;
    const categoryOk = campusMapFilter === 'all' || point.category === campusMapFilter;
    if (!categoryOk) return false;
    if (!q) return true;
    return [point.title, point.label, point.cn, point.en, point.description, point.note]
      .some(value => String(value || '').toLowerCase().includes(q));
  });
}

function campusMapEditorPanel() {
  if (!campusMapCanEdit()) return '';
  const point = campusMapEditorSelectionId ? campusMapFindPoint(campusMapEditorSelectionId) : null;
  const cursor = campusMapEditorCursor || point || { x: 50, y: 50 };
  const title = point && point.title || '';
  const label = point && point.label || '';
  const category = point && point.category || 'important';
  const labelPos = point && point.labelPos || 'right';
  const labelDx = Number(point && point.labelDx || 0);
  const labelDy = Number(point && point.labelDy || 0);
  const description = point && point.description || '';
  const selectedLabel = point
    ? `${campusMapEscape(point.label || point.title)} · ${Number(point.x).toFixed(1)} / ${Number(point.y).toFixed(1)}`
    : 'Кликни по карте или выбери точку';

  return `
    <div class="campus-map-editor ${campusMapEditorEnabled ? 'active' : ''}">
      <div class="campus-map-editor-top">
        <div>
          <b>Редактор Архитектора</b>
          <small>${selectedLabel}</small>
        </div>
        <button type="button" onclick="toggleCampusMapEditor()">${campusMapEditorEnabled ? 'выкл' : 'вкл'}</button>
      </div>
      ${campusMapEditorEnabled ? `
        <div class="campus-map-editor-grid">
          <label>Название<input id="campusEditTitle" value="${campusMapEscape(title)}" placeholder="Название в карточке"></label>
          <label>Подпись<input id="campusEditLabel" value="${campusMapEscape(label)}" placeholder="Короткая подпись"></label>
          <label>X<input id="campusEditX" type="number" step="0.1" value="${Number(cursor.x || 0).toFixed(1)}"></label>
          <label>Y<input id="campusEditY" type="number" step="0.1" value="${Number(cursor.y || 0).toFixed(1)}"></label>
          <label>Тип
            <select id="campusEditCategory">
              ${CAMPUS_MAP_CATEGORIES.filter(item => item.id !== 'all').map(item => `
                <option value="${item.id}" ${category === item.id ? 'selected' : ''}>${campusMapEscape(item.label)}</option>
              `).join('')}
            </select>
          </label>
          <label>Подпись
            <select id="campusEditLabelPos">
              ${['up', 'down', 'left', 'right'].map(pos => `<option value="${pos}" ${labelPos === pos ? 'selected' : ''}>${pos}</option>`).join('')}
            </select>
          </label>
          <label>Label X<input id="campusEditLabelDx" type="number" step="1" value="${labelDx}"></label>
          <label>Label Y<input id="campusEditLabelDy" type="number" step="1" value="${labelDy}"></label>
        </div>
        <label class="campus-map-editor-description">Описание<textarea id="campusEditDescription" rows="2">${campusMapEscape(description)}</textarea></label>
        <div class="campus-map-editor-actions">
          <button type="button" onclick="saveCampusMapEditorPoint()">Сохранить</button>
          <button type="button" onclick="newCampusMapEditorPoint()">Новая</button>
          <button type="button" onclick="removeCampusMapEditorPoint()">Сброс/удалить</button>
          <button type="button" onclick="copyCampusMapEditorExport()">JSON</button>
        </div>
      ` : ''}
    </div>
  `;
}

function initCampusMap() {
  const root = document.getElementById('campusMapRoot');
  if (!root) return;

  try {
    campusMapLoadGlobalOnce();
    campusMapLoadEditorCloudOnce();

    const mode = campusMapAssetMode();
    const points = campusMapFilteredPoints();
    const catalogPoints = campusMapCatalogPoints(points);
    const canEdit = campusMapCanEdit();
    const routeFromPoint = campusMapRouteFrom ? campusMapFindPoint(campusMapRouteFrom) : null;
    const routeToPoint = campusMapRouteTo ? campusMapFindPoint(campusMapRouteTo) : null;
    const routeEstimate = routeFromPoint && routeToPoint ? campusMapRouteEstimate(routeFromPoint, routeToPoint) : null;
    root.innerHTML = `
    <div class="campus-map-panel">
      <div class="campus-map-head">
        <div>
          <div class="campus-map-kicker">${mode === 'genshin' ? '校园地图 · LIYUE ATLAS' : '校园地图 · CAMPUS MAP'}</div>
          <div class="campus-map-title">北京语言大学</div>
        </div>
        <div class="campus-map-head-actions">
          ${canEdit ? `<button class="campus-map-mode editor" type="button" onclick="toggleCampusMapEditor()">${campusMapEditorEnabled ? 'EDITOR ON' : 'EDITOR'}</button>` : ''}
          <button class="campus-map-mode ${campusMapRouteMode ? 'active' : ''}" type="button" onclick="toggleCampusMapRouteMode()">МАРШРУТ</button>
          <button class="campus-map-mode ${campusMapFavoritesOnly ? 'active' : ''}" type="button" onclick="toggleCampusMapFavoritesOnly()">★ ИЗБРАННОЕ</button>
          <button class="campus-map-mode" type="button" onclick="toggleCampusMapOriginal()">${mode === 'original' ? 'THEME' : 'ORIGINAL'}</button>
        </div>
      </div>
      <div class="campus-map-search">
        <i class="ti ti-search"></i>
        <input id="campusMapSearch" type="text" placeholder="Поиск: столовая, библиотека, ворота..." value="${campusMapEscape(campusMapQuery)}">
      </div>
      <div class="campus-map-filters">
        ${CAMPUS_MAP_CATEGORIES.map(category => `
          <button type="button" class="cat-${category.id} ${campusMapFilter === category.id ? 'active' : ''}" onclick="setCampusMapFilter('${category.id}')">${campusMapEscape(category.label)}</button>
        `).join('')}
      </div>
      ${campusMapRouteMode ? `
        <div class="campus-map-route-bar">
          <div class="campus-map-route-points">
            <span class="campus-map-route-chip from ${routeFromPoint ? 'set' : ''}">A: ${routeFromPoint ? campusMapEscape(routeFromPoint.title) : 'выбери точку'}</span>
            <span class="campus-map-route-arrow">→</span>
            <span class="campus-map-route-chip to ${routeToPoint ? 'set' : ''}">B: ${routeToPoint ? campusMapEscape(routeToPoint.title) : 'выбери точку'}</span>
          </div>
          ${routeEstimate ? `<div class="campus-map-route-estimate">≈ ${routeEstimate.meters} м · ~${routeEstimate.minutes} мин пешком</div>` : '<div class="campus-map-route-estimate hint">Кликай по точкам на карте или в списке, чтобы построить маршрут</div>'}
          ${routeFromPoint || routeToPoint ? `<button type="button" class="campus-map-route-clear" onclick="clearCampusMapRoute()">Сбросить</button>` : ''}
        </div>
      ` : ''}
      ${campusMapEditorPanel()}
      <div class="campus-map-scroll">
        <div class="campus-map-stage ${campusMapEditorEnabled && canEdit ? 'editing' : ''}" onclick="handleCampusMapStageClick(event)">
          <img src="${CAMPUS_MAP_ASSETS[mode] || CAMPUS_MAP_ASSETS.cyberpunk}" alt="Campus map">
          ${routeFromPoint && routeToPoint ? `
            <svg class="campus-map-route-line" viewBox="0 0 100 100" preserveAspectRatio="none">
              <line x1="${routeFromPoint.x}" y1="${routeFromPoint.y}" x2="${routeToPoint.x}" y2="${routeToPoint.y}" />
            </svg>
          ` : ''}
          ${points.map(point => `
            <button class="campus-map-pin ${campusMapEscape(point.category)} label-${campusMapEscape(point.labelPos || 'down')} ${campusMapEditorSelectionId === point.id ? 'selected' : ''} ${campusMapRouteFrom === point.id ? 'route-from' : ''} ${campusMapRouteTo === point.id ? 'route-to' : ''}" style="left:${point.x}%;top:${point.y}%;--label-dx:${Number(point.labelDx || 0)}px;--label-dy:${Number(point.labelDy || 0)}px;" type="button" onclick="handleCampusMapPinClick(event, '${campusMapEscape(point.id)}')" aria-label="${campusMapEscape(point.title)}">
              <span></span>
              <em>${campusMapEscape(point.label || point.title)}</em>
            </button>
          `).join('')}
        </div>
      </div>
      <div class="campus-map-list">
        ${catalogPoints.length ? catalogPoints.map(point => `
          <button type="button" class="campus-map-row ${campusMapEscape(point.category)} ${campusMapRouteFrom === point.id ? 'route-from' : ''} ${campusMapRouteTo === point.id ? 'route-to' : ''}" onclick="${campusMapRouteMode ? `campusMapHandleRoutePick('${campusMapEscape(point.id)}')` : `openCampusMapPoint('${campusMapEscape(point.id)}')`}">
            <span class="campus-map-row-dot"></span>
            <span>
              <b>${campusMapEscape(point.title)}</b>
              <small>${campusMapEscape(point.cn)} · ${campusMapEscape(point.en)} · ${campusMapCategoryLabel(point.category)}</small>
            </span>
            <span class="campus-map-row-fav ${campusMapIsFavorite(point.id) ? 'on' : ''}" onclick="toggleCampusMapFavorite(event, '${campusMapEscape(point.id)}')">★</span>
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

    bindCampusMapEditorAutosave();
  } catch (e) {
    root.innerHTML = `
      <div class="campus-map-panel">
        <div class="campus-map-head">
          <div>
            <div class="campus-map-kicker">CAMPUS MAP SAFE MODE</div>
            <div class="campus-map-title">Карта временно недоступна</div>
          </div>
        </div>
        <div class="campus-map-empty">Ошибка карты изолирована. Остальное приложение должно работать.</div>
      </div>
    `;
  }
}

function setCampusMapFilter(filter) {
  campusMapFilter = filter || 'all';
  initCampusMap();
}

function toggleCampusMapEditor() {
  if (!campusMapCanEdit()) return;
  campusMapEditorEnabled = !campusMapEditorEnabled;
  if (!campusMapEditorEnabled) campusMapEditorSelectionId = '';
  initCampusMap();
}

function handleCampusMapPinClick(event, id) {
  if (event) event.stopPropagation();
  if (campusMapRouteMode) {
    campusMapHandleRoutePick(id);
    return;
  }
  if (campusMapEditorEnabled && campusMapCanEdit()) {
    const point = campusMapFindPoint(id);
    campusMapEditorSelectionId = id;
    campusMapEditorCursor = point ? { x: Number(point.x || 0), y: Number(point.y || 0) } : campusMapEditorCursor;
    initCampusMap();
    return;
  }
  openCampusMapPoint(id);
}

function handleCampusMapStageClick(event) {
  if (!campusMapEditorEnabled || !campusMapCanEdit() || !event) return;
  if (event.target && event.target.closest && event.target.closest('.campus-map-pin')) return;
  const stage = event.currentTarget;
  const rect = stage.getBoundingClientRect();
  const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
  const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
  campusMapEditorCursor = { x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
  if (campusMapEditorSelectionId) {
    saveCampusMapEditorPoint({ x: campusMapEditorCursor.x, y: campusMapEditorCursor.y, silent: true });
    return;
  }
  initCampusMap();
}

function campusMapEditorValue(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function campusMapEditorNumber(id, fallback = 0) {
  const value = Number(campusMapEditorValue(id));
  return Number.isFinite(value) ? value : fallback;
}

function campusMapEditorPayload(existing) {
  const x = Number(campusMapEditorNumber('campusEditX', existing && existing.x || 50).toFixed(1));
  const y = Number(campusMapEditorNumber('campusEditY', existing && existing.y || 50).toFixed(1));
  const title = campusMapEditorValue('campusEditTitle').trim() || existing && existing.title || 'Новая точка';
  const label = campusMapEditorValue('campusEditLabel').trim() || title;
  return {
    id: existing && existing.id || `custom-${Date.now()}`,
    title,
    label,
    cn: existing && existing.cn || '',
    en: existing && existing.en || '',
    category: campusMapEditorValue('campusEditCategory') || existing && existing.category || 'important',
    x,
    y,
    labelPos: campusMapEditorValue('campusEditLabelPos') || existing && existing.labelPos || 'right',
    labelDx: Math.round(campusMapEditorNumber('campusEditLabelDx', existing && existing.labelDx || 0)),
    labelDy: Math.round(campusMapEditorNumber('campusEditLabelDy', existing && existing.labelDy || 0)),
    description: campusMapEditorValue('campusEditDescription').trim() || existing && existing.description || 'Точка на карте кампуса.',
  };
}

function campusMapApplyPayloadPatch(payload, patch) {
  const next = { ...payload };
  if (patch && Object.prototype.hasOwnProperty.call(patch, 'x')) next.x = Number(Number(patch.x).toFixed(1));
  if (patch && Object.prototype.hasOwnProperty.call(patch, 'y')) next.y = Number(Number(patch.y).toFixed(1));
  return next;
}

function bindCampusMapEditorAutosave() {
  if (!campusMapEditorEnabled || !campusMapCanEdit()) return;
  const fields = [
    'campusEditTitle',
    'campusEditLabel',
    'campusEditX',
    'campusEditY',
    'campusEditCategory',
    'campusEditLabelPos',
    'campusEditLabelDx',
    'campusEditLabelDy',
    'campusEditDescription',
  ];

  fields.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(eventName, () => {
      window.clearTimeout(campusMapEditorAutosaveTimer);
      campusMapEditorAutosaveTimer = window.setTimeout(() => saveCampusMapEditorPoint({ silent: true, keepFocus: true }), 350);
    });
  });
}

function saveCampusMapEditorPoint(options = {}) {
  if (!campusMapCanEdit()) return;
  const edits = campusMapLoadEditorEdits();
  const existing = campusMapEditorSelectionId ? campusMapFindPoint(campusMapEditorSelectionId) : null;
  const payload = campusMapApplyPayloadPatch(campusMapEditorPayload(existing), options);

  if (existing && existing.isCustom || payload.id.startsWith('custom-')) {
    edits.custom = edits.custom.filter(point => point.id !== payload.id);
    edits.custom.push({ ...payload, isCustom: undefined });
  } else {
    edits.overrides[payload.id] = payload;
  }

  campusMapSaveEditorEdits(edits);
  campusMapEditorSelectionId = payload.id;
  campusMapEditorCursor = { x: payload.x, y: payload.y };
  if (!options.silent && typeof showToast === 'function') showToast('Точка карты сохранена');
  if (!options.keepFocus) initCampusMap();
}

function newCampusMapEditorPoint() {
  if (!campusMapCanEdit()) return;
  campusMapEditorSelectionId = '';
  campusMapEditorCursor = campusMapEditorCursor || { x: 50, y: 50 };
  initCampusMap();
}

function removeCampusMapEditorPoint() {
  if (!campusMapCanEdit() || !campusMapEditorSelectionId) return;
  const edits = campusMapLoadEditorEdits();
  const existing = campusMapFindPoint(campusMapEditorSelectionId);
  if (existing && existing.isCustom) {
    edits.custom = edits.custom.filter(point => point.id !== campusMapEditorSelectionId);
  } else {
    delete edits.overrides[campusMapEditorSelectionId];
  }
  campusMapSaveEditorEdits(edits);
  campusMapEditorSelectionId = '';
  if (typeof showToast === 'function') showToast('Локальная правка карты сброшена');
  initCampusMap();
}

function copyCampusMapEditorExport() {
  if (!campusMapCanEdit()) return;
  const data = JSON.stringify(campusMapLoadEditorEdits(), null, 2);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(data).then(() => {
      if (typeof showToast === 'function') showToast('JSON карты скопирован');
    }).catch(() => window.prompt('JSON карты', data));
  } else {
    window.prompt('JSON карты', data);
  }
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
  const point = campusMapFindPoint(id);
  const popup = document.getElementById('campusMapPopup');
  if (!point || !popup) return;
  popup.innerHTML = `
    <div class="campus-map-popup-backdrop" onclick="closeCampusMapPoint()"></div>
    <div class="campus-map-popup-card ${campusMapEscape(point.category)}">
      <button class="campus-map-popup-close" type="button" onclick="closeCampusMapPoint()">×</button>
      <button class="campus-map-popup-fav ${campusMapIsFavorite(point.id) ? 'on' : ''}" type="button" onclick="toggleCampusMapFavorite(event, '${campusMapEscape(point.id)}'); openCampusMapPoint('${campusMapEscape(point.id)}')">★</button>
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
