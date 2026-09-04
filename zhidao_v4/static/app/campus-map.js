"use strict";

/* ===========================================================================
   Кампус — векторная карта
   ---------------------------------------------------------------------------
   Рисует campus.geojson как SVG. Провайдера карт нет намеренно: ключ AMap
   требует китайской верификации личности, и решение обходиться без него
   зафиксировано в CLAUDE_HANDOFF_HAINAN_V4_2026-09-03.md §7.

   Все координаты — WGS-84, ровно как их отдаёт GPS телефона. Поэтому отметка
   «где я» ложится на карту без единого преобразования. Если когда-нибудь
   появится подложка AMap или Baidu, конвертировать в GCJ-02 нужно будет
   здесь, в одном месте, а не в данных.
   =========================================================================== */

const CAMPUS_SOURCE = "./assets/maps/campus.geojson?v=20260904-labels3";

/* Плоская проекция в метры. Для площадки 1.2 x 1.4 км искажение
   пренебрежимо, а читается она несравнимо проще Меркатора. */
const METRES_PER_DEG_LAT = 110540;
const METRES_PER_DEG_LON = 111320;

const campusState = {
  data: null,
  origin: null,      // {lat, lon} — точка отсчёта проекции
  bounds: null,      // показанный экстент в метрах
  campusBounds: null,
  campusBoundary: null,
  exploredBounds: null,
  exploredRegion: null,  // контур подготовленной области, не прямоугольник
  labelNodes: [],    // подписи, которым нужен пересчёт размера при зуме
  view: { x: 0, y: 0, scale: 1 },
  selected: null,
  watchId: null,
  me: null,          // последняя позиция от GPS
};

function project(lon, lat, origin) {
  const k = Math.cos((origin.lat * Math.PI) / 180);
  return {
    x: (lon - origin.lon) * METRES_PER_DEG_LON * k,
    y: -(lat - origin.lat) * METRES_PER_DEG_LAT,
  };
}

function polygonArea(ring, origin) {
  // Формула шнурков по спроецированным метрам.
  let a = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const p = project(ring[i][0], ring[i][1], origin);
    const q = project(ring[i + 1][0], ring[i + 1][1], origin);
    a += p.x * q.y - q.x * p.y;
  }
  return Math.abs(a) / 2;
}

function ringsOf(feature) {
  const g = feature.geometry;
  if (!g) return [];
  return g.type === "Polygon" ? g.coordinates : [g.coordinates];
}

function boundsOf(features, origin) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  features.forEach((f) => {
    ringsOf(f).forEach((ring) => {
      ring.forEach(([lon, lat]) => {
        const p = project(lon, lat, origin);
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
      });
    });
  });
  return { minX, minY, maxX, maxY };
}

function expandBounds(bounds, amount) {
  return {
    minX: bounds.minX - amount,
    minY: bounds.minY - amount,
    maxX: bounds.maxX + amount,
    maxY: bounds.maxY + amount,
  };
}

function includeAnchorPoints(bounds, points, origin) {
  const next = { ...bounds };
  points.forEach((anchor) => {
    const coordinates = Array.isArray(anchor) ? anchor : anchor?.coordinates;
    if (!Array.isArray(coordinates) || coordinates.length < 2) return;
    const q = project(coordinates[0], coordinates[1], origin);
    next.minX = Math.min(next.minX, q.x);
    next.minY = Math.min(next.minY, q.y);
    next.maxX = Math.max(next.maxX, q.x);
    next.maxY = Math.max(next.maxY, q.y);
  });
  return next;
}

function insideBounds(point, bounds) {
  return point.x >= bounds.minX && point.x <= bounds.maxX
    && point.y >= bounds.minY && point.y <= bounds.maxY;
}

function coordinateInPolygon(lon, lat, feature) {
  if (!feature || feature.geometry.type !== "Polygon") return false;
  const ring = feature.geometry.coordinates[0];
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses = (yi > lat) !== (yj > lat)
      && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

/* Подготовленная область — объединение контура кампуса и следов самих
   построек с отступом. Прямоугольник здесь не годится: габариты кампуса
   1.2 x 1.4 км, и в углы такого прямоугольника попадают чужие дороги —
   в том числе деревня на северо-востоке. Ребёнок читает светлое как
   «сюда можно». */
function ringToRegionRing(points) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  points.forEach(([x, y]) => {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  });
  return { points, bounds: { minX, minY, maxX, maxY } };
}

function pointInRingPoints(point, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    const crosses = (yi > point.y) !== (yj > point.y)
      && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function distanceToRingPoints(point, points) {
  let best = Infinity;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    const [x1, y1] = points[j];
    const [x2, y2] = points[i];
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = dx * dx + dy * dy;
    const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((point.x - x1) * dx + (point.y - y1) * dy) / len));
    best = Math.min(best, Math.hypot(point.x - (x1 + t * dx), point.y - (y1 + t * dy)));
    if (best === 0) return 0;
  }
  return best;
}

function regionContains(point, region) {
  if (!region) return false;
  const pad = region.padding;
  return region.rings.some((ring) => {
    const b = ring.bounds;
    // Дешёвый отсев по габаритам кольца до дорогого замера расстояния.
    if (point.x < b.minX - pad || point.x > b.maxX + pad
      || point.y < b.minY - pad || point.y > b.maxY + pad) return false;
    if (pointInRingPoints(point, ring.points)) return true;
    return pad > 0 && distanceToRingPoints(point, ring.points) <= pad;
  });
}

function boundsOfRegion(region) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  region.rings.forEach((ring) => {
    minX = Math.min(minX, ring.bounds.minX);
    minY = Math.min(minY, ring.bounds.minY);
    maxX = Math.max(maxX, ring.bounds.maxX);
    maxY = Math.max(maxY, ring.bounds.maxY);
  });
  return expandBounds({ minX, minY, maxX, maxY }, region.padding);
}

function featureIsExplored(feature, origin, region) {
  if (typeof feature.properties.explored === "boolean") return feature.properties.explored;
  const c = centroidOf(feature);
  return regionContains(project(c.lon, c.lat, origin), region);
}

function featureTouchesExplored(feature, origin, region) {
  return ringsOf(feature).some((ring) => ring.some(([lon, lat]) => (
    regionContains(project(lon, lat, origin), region)
  )));
}

const REGION_EXCLUDED = new Set(["road"]);

function rectRingPoints(b) {
  return [[b.minX, b.minY], [b.maxX, b.minY], [b.maxX, b.maxY], [b.minX, b.maxY]];
}

function computeFrame(features, data) {
  let sumLat = 0;
  let sumLon = 0;
  let n = 0;
  features.forEach((f) => {
    ringsOf(f).forEach((ring) => {
      ring.forEach(([lon, lat]) => {
        sumLat += lat;
        sumLon += lon;
        n += 1;
      });
    });
  });
  const origin = { lat: sumLat / n, lon: sumLon / n };

  // По умолчанию кадрируем по официальной границе кампуса. Если данные задают
  // режим исследования, светлая область строится как интерфейсный конверт
  // ключевых объектов. Это не выдаётся за административную границу.
  const frameSource = features.filter((f) => f.properties.category === "boundary");
  const extentOf = frameSource.length ? frameSource : features;
  const campusBounds = boundsOf(extentOf, origin);
  const exploration = data.exploration || null;
  const coreIds = new Set(exploration?.core_feature_ids || []);
  const coreFeatures = features.filter((f) => coreIds.has(f.properties.id));

  const openRegion = {
    rings: [ringToRegionRing(rectRingPoints(campusBounds))],
    padding: 0,
  };

  if (!exploration) {
    return {
      origin, bounds: campusBounds, campusBounds,
      exploredBounds: campusBounds, exploredRegion: openRegion, exploration: null,
    };
  }

  if (coreIds.size === 0 || coreFeatures.length !== coreIds.size) {
    console.warn("Campus exploration configuration is incomplete; using the full campus frame.");
    return {
      origin, bounds: campusBounds, campusBounds,
      exploredBounds: campusBounds, exploredRegion: openRegion, exploration: null,
    };
  }

  const padding = Number(exploration.padding_metres) || 55;
  const unknownBand = Number(exploration.unknown_band_metres) || 125;
  // Кольца области: контур кампуса, следы всех построек и точки-якоря.
  // Постройки входят потому, что два объекта — актовый зал и жилая зона —
  // лежат снаружи OSM-контура на 61 и 110 м, и без них ушли бы в туман.
  const regionSources = coreFeatures.concat(
    features.filter((f) => !REGION_EXCLUDED.has(f.properties.category))
  );
  const rings = [];
  regionSources.forEach((f) => {
    ringsOf(f).forEach((ring) => {
      if (ring.length < 3) return;
      rings.push(ringToRegionRing(ring.map(([lon, lat]) => {
        const q = project(lon, lat, origin);
        return [q.x, q.y];
      })));
    });
  });
  (exploration.anchor_points || []).forEach((anchor) => {
    const c = Array.isArray(anchor) ? anchor : anchor?.coordinates;
    if (!Array.isArray(c) || c.length < 2) return;
    const q = project(c[0], c[1], origin);
    rings.push(ringToRegionRing([
      [q.x - 1, q.y - 1], [q.x + 1, q.y - 1], [q.x + 1, q.y + 1], [q.x - 1, q.y + 1],
    ]));
  });
  const exploredRegion = { rings, padding };
  const exploredBounds = boundsOfRegion(exploredRegion);
  const bounds = expandBounds(exploredBounds, unknownBand);
  return { origin, bounds, campusBounds, exploredBounds, exploredRegion, exploration };
}

/* Порядок рисования: границы под всем, дороги над ними, здания сверху.
   Иначе здание окажется под дорогой и станет некликабельным. */
const DRAW_ORDER = [
  // Земля: территория, участки институтов, жилые зоны, парки — фон.
  "boundary", "grounds", "living-zone", "park",
  // Дороги поверх земли, но под постройками.
  "road", "sport",
  // Постройки — самый верхний слой, они и должны читаться как объекты.
  "building", "civic", "academic", "library", "dorm", "food",
];

/* Подписи только у именованных объектов и только у крупных: подписать
   четырнадцать одинаковых общежитий значит залить карту словом «Общежитие». */
const LABEL_MIN_AREA = 1200;   // кв. метры
const LABEL_CATEGORIES = new Set([
  "academic", "library", "food", "sport", "civic", "dorm", "living-zone",
]);
// У этих категорий нет собственных имён ни в OSM, ни где-либо ещё. Подписываем
// их родовым словом — придумывать номера общежитиям значит сочинять данные.
const GENERIC_LABEL_CATEGORIES = new Set(["dorm", "living-zone"]);
// Здесь подписывается каждое здание, а не одно на категорию: четырнадцать
// общежитий — это четырнадцать разных мест, куда человек идёт спать.
const PER_BUILDING_LABELS = new Set(["dorm"]);
const LABEL_MIN_AREA_BY_CATEGORY = { dorm: 300 };
// Порог зума, ниже которого подпись прячется. Иначе четырнадцать одинаковых
// слов «Общежитие» заливают карту на общем плане.
const LABEL_MIN_SCALE = { dorm: 2.2 };
// Кто уступает место при наложении. Ориентиры, по которым человек себя находит,
// важнее родовых слов: столовую ищут, «Общежитие» просто подтверждает, что ты
// уже пришёл. Меньше число — выше приоритет.
const LABEL_PRIORITY = {
  group: 0, academic: 1, food: 2, civic: 3, sport: 4,
  library: 5, "living-zone": 6, road: 7, dorm: 8,
};
const IMPORTANT_ROAD_NAMES = new Set(["博学大道"]);

/* Подпись в две строки: русская и китайская помельче. Базовый размер хранится
   на узле, а на экране он держится постоянным — applyView делит его на масштаб.
   Иначе при зуме буквы растут вместе с картой и закрывают то, что подписывают. */
function appendLabel(layer, NS, opts) {
  const label = document.createElementNS(NS, "text");
  label.setAttribute("class", opts.className);
  label.setAttribute("x", opts.x.toFixed(1));
  label.setAttribute("y", opts.y.toFixed(1));
  label.setAttribute("text-anchor", "middle");
  label.dataset.baseSize = String(opts.size);
  label.dataset.priority = String(opts.priority ?? 9);
  if (opts.minScale) label.dataset.minScale = String(opts.minScale);

  const ru = document.createElementNS(NS, "tspan");
  ru.setAttribute("x", opts.x.toFixed(1));
  // Две строки поднимаем на пол-строки, чтобы блок остался по центру объекта.
  if (opts.zh) ru.setAttribute("dy", "-0.30em");
  ru.textContent = opts.ru;
  label.appendChild(ru);

  if (opts.zh) {
    const zh = document.createElementNS(NS, "tspan");
    zh.setAttribute("class", "campus-label-zh");
    zh.setAttribute("x", opts.x.toFixed(1));
    // em здесь считается от размера самой строки, поэтому отступ переживает зум.
    zh.setAttribute("dy", "1.45em");
    zh.textContent = opts.zh;
    label.appendChild(zh);
  }

  layer.appendChild(label);
  return label;
}

function buildSvg(host, data) {
  const features = data.features.slice().sort(
    (a, b) => DRAW_ORDER.indexOf(a.properties.category) - DRAW_ORDER.indexOf(b.properties.category)
  );
  const { origin, bounds, campusBounds, exploredBounds, exploredRegion, exploration } = computeFrame(features, data);
  campusState.origin = origin;
  campusState.bounds = bounds;
  campusState.campusBounds = campusBounds;
  campusState.campusBoundary = features.find(
    (f) => f.properties.category === "boundary" && f.geometry.type === "Polygon"
  ) || null;
  campusState.exploredBounds = exploredBounds;
  campusState.exploredRegion = exploredRegion;

  const w = bounds.maxX - bounds.minX;
  const h = bounds.maxY - bounds.minY;

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "campus-svg");
  svg.setAttribute("viewBox", `${bounds.minX} ${bounds.minY} ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "group");
  svg.setAttribute("aria-label", "Карта подготовленного сектора кампуса и неизведанных регионов");

  let explorationMaskId = null;
  let explorationClipId = null;
  if (exploration) {
    explorationMaskId = "campus-exploration-mask";
    explorationClipId = "campus-exploration-clip";
    const defs = document.createElementNS(NS, "defs");

    const mask = document.createElementNS(NS, "mask");
    mask.setAttribute("id", explorationMaskId);
    mask.setAttribute("maskUnits", "userSpaceOnUse");
    mask.setAttribute("x", bounds.minX);
    mask.setAttribute("y", bounds.minY);
    mask.setAttribute("width", w);
    mask.setAttribute("height", h);
    const maskOuter = document.createElementNS(NS, "rect");
    maskOuter.setAttribute("x", bounds.minX);
    maskOuter.setAttribute("y", bounds.minY);
    maskOuter.setAttribute("width", w);
    maskOuter.setAttribute("height", h);
    maskOuter.setAttribute("fill", "white");
    // Окно в тумане — не прямоугольник, а сами кольца области. Отступ даётся
    // толстой обводкой: она же скругляет стыки, поэтому светлое пятно читается
    // как территория, а не как аккуратная геометрия.
    const regionPath = (ring) => {
      const node = document.createElementNS(NS, "path");
      node.setAttribute("d", `M${ring.points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join("L")}Z`);
      return node;
    };
    mask.appendChild(maskOuter);
    exploredRegion.rings.forEach((ring) => {
      const node = regionPath(ring);
      node.setAttribute("fill", "black");
      node.setAttribute("stroke", "black");
      node.setAttribute("stroke-width", String(exploredRegion.padding * 2));
      node.setAttribute("stroke-linejoin", "round");
      node.setAttribute("stroke-linecap", "round");
      mask.appendChild(node);
    });
    defs.appendChild(mask);

    // clipPath игнорирует обводку, поэтому маршруты режутся по самим кольцам.
    // Туман всё равно рисуется поверх маршрута, так что это подстраховка.
    const clip = document.createElementNS(NS, "clipPath");
    clip.setAttribute("id", explorationClipId);
    clip.setAttribute("clipPathUnits", "userSpaceOnUse");
    exploredRegion.rings.forEach((ring) => clip.appendChild(regionPath(ring)));
    defs.appendChild(clip);
    svg.appendChild(defs);
  }

  const layer = document.createElementNS(NS, "g");
  layer.setAttribute("class", "campus-layer");
  svg.appendChild(layer);

  features.forEach((f) => {
    const p = f.properties;
    const isArea = f.geometry.type === "Polygon";
    const node = document.createElementNS(NS, isArea ? "path" : "polyline");
    const ring = isArea ? f.geometry.coordinates[0] : f.geometry.coordinates;
    const pts = ring.map(([lon, lat]) => {
      const q = project(lon, lat, origin);
      return `${q.x.toFixed(1)},${q.y.toFixed(1)}`;
    });

    if (isArea) {
      node.setAttribute("d", `M${pts.join("L")}Z`);
    } else {
      node.setAttribute("points", pts.join(" "));
    }
    const explored = featureIsExplored(f, origin, exploredRegion);
    node.setAttribute(
      "class",
      `campus-feat campus-${p.category}${explored ? "" : " is-unexplored"}`
    );
    node.dataset.featureId = p.id;
    const isBackdrop = ["road", "boundary", "grounds", "living-zone", "park"]
      .includes(p.category);
    if (!isBackdrop && explored) {
      node.dataset.interactive = "true";
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.setAttribute("aria-label", `${p.name_ru}. ${p.name_zh}`);
    } else if (!explored) {
      node.setAttribute("aria-hidden", "true");
    }
    layer.appendChild(node);
  });

  // Подписи поверх всего. Только именованные и только достаточно крупные:
  // четырнадцать одинаковых «Общежитий» превратили бы карту в кашу, для них
  // работает легенда и тап по объекту.
  const seenLabels = new Set();
  const groupedLabelFeatureIds = new Set(
    (data.landmark_groups || []).flatMap((group) => group.feature_ids || [])
  );
  features.forEach((f) => {
    const p = f.properties;
    if (groupedLabelFeatureIds.has(p.id)) return;
    const importantRoad = p.category === "road" && IMPORTANT_ROAD_NAMES.has(p.name_zh);
    const genericName = GENERIC_LABEL_CATEGORIES.has(p.category);
    if ((!p.named && !genericName) || (!LABEL_CATEGORIES.has(p.category) && !importantRoad)) return;
    if (importantRoad ? !featureTouchesExplored(f, origin, exploredRegion)
      : !featureIsExplored(f, origin, exploredRegion)) return;
    const labelKey = importantRoad ? `road:${p.name_zh}` : `${p.category}:${p.name_ru}`;
    if (!PER_BUILDING_LABELS.has(p.category)) {
      if (seenLabels.has(labelKey)) return;
      seenLabels.add(labelKey);
    }
    const ring = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates;
    const minArea = LABEL_MIN_AREA_BY_CATEGORY[p.category] ?? LABEL_MIN_AREA;
    if (f.geometry.type === "Polygon" && polygonArea(ring, origin) < minArea) return;

    const projected = ring.map(([lon, lat]) => project(lon, lat, origin));
    const labelPoints = importantRoad
      ? projected.filter((q) => regionContains(q, exploredRegion))
      : projected;
    let sx = 0;
    let sy = 0;
    labelPoints.forEach((q) => {
      sx += q.x;
      sy += q.y;
    });
    // Размер задаётся в пользовательских единицах, а они здесь метры: 11 единиц
    // при виде на 1250 м дают три пикселя на экране. Считаем от ширины кадра.
    const base = (bounds.maxX - bounds.minX) / 46;
    const size = p.category === "boundary" ? base * 1.25
      : p.category === "living-zone" ? base * 0.82
      : base;
    appendLabel(layer, NS, {
      className: `campus-label campus-label-${p.category}`,
      x: sx / labelPoints.length,
      y: sy / labelPoints.length,
      size,
      minScale: LABEL_MIN_SCALE[p.category] || 0,
      priority: LABEL_PRIORITY[p.category] ?? 9,
      ru: p.approximate ? `${p.name_ru} ?` : p.name_ru,
      zh: p.name_zh || "",
    });
  });

  (data.landmark_groups || []).forEach((group) => {
    const members = group.feature_ids.map(featureById).filter(Boolean);
    if (!members.length || !members.some((f) => featureIsExplored(f, origin, exploredRegion))) return;
    let lon = 0;
    let lat = 0;
    members.forEach((f) => {
      const c = centroidOf(f);
      lon += c.lon;
      lat += c.lat;
    });
    const q = project(lon / members.length, lat / members.length, origin);
    const mark = group.approximate || group.verified === false ? " ?" : "";
    appendLabel(layer, NS, {
      className: "campus-label campus-label-group",
      x: q.x,
      y: q.y,
      size: (bounds.maxX - bounds.minX) / 43,
      minScale: 0,
      priority: LABEL_PRIORITY.group,
      ru: `${group.name_ru}${mark}`,
      zh: group.name_zh || "",
    });
  });

  // Слой маршрута — под отметкой позиции, но над зданиями.
  const route = document.createElementNS(NS, "g");
  route.setAttribute("class", "campus-route");
  if (explorationClipId) route.setAttribute("clip-path", `url(#${explorationClipId})`);
  layer.appendChild(route);

  if (explorationMaskId) {
    const fog = document.createElementNS(NS, "rect");
    fog.setAttribute("class", "campus-unexplored-fog");
    fog.setAttribute("x", bounds.minX);
    fog.setAttribute("y", bounds.minY);
    fog.setAttribute("width", w);
    fog.setAttribute("height", h);
    fog.setAttribute("mask", `url(#${explorationMaskId})`);
    layer.appendChild(fog);

    const boundaryFeature = campusState.campusBoundary;
    if (boundaryFeature) {
      const edge = document.createElementNS(NS, "path");
      edge.setAttribute("class", "campus-exploration-edge");
      edge.setAttribute("d", `M${boundaryFeature.geometry.coordinates[0].map(([lon, lat]) => {
        const q = project(lon, lat, origin);
        return `${q.x.toFixed(1)},${q.y.toFixed(1)}`;
      }).join("L")}Z`);
      layer.appendChild(edge);
    }

    const unknownSize = Math.max(18, w / 58);
    const addUnknownLabel = (y, text) => {
      const label = document.createElementNS(NS, "text");
      label.setAttribute("class", "campus-unexplored-label");
      label.setAttribute("x", ((bounds.minX + bounds.maxX) / 2).toFixed(1));
      label.setAttribute("y", y.toFixed(1));
      label.dataset.baseSize = String(unknownSize);
      label.setAttribute("text-anchor", "middle");
      label.textContent = text;
      layer.appendChild(label);
    };
    addUnknownLabel(
      (bounds.minY + exploredBounds.minY) / 2,
      exploration.label_ru || "НЕИЗВЕДАННЫЕ РЕГИОНЫ"
    );
    addUnknownLabel(
      (exploredBounds.maxY + bounds.maxY) / 2,
      `${exploration.label_zh || "未探索区域"} · НЕ ПОДГОТОВЛЕНО`
    );
  }

  // Отметка «где я» — создаётся сразу, показывается после первого фикса GPS.
  const me = document.createElementNS(NS, "circle");
  me.setAttribute("class", "campus-me");
  me.setAttribute("r", "9");
  me.setAttribute("hidden", "hidden");
  layer.appendChild(me);

  campusState.labelNodes = Array.from(layer.querySelectorAll("text[data-base-size]"));

  host.innerHTML = "";
  host.appendChild(svg);
  // Только теперь: getBBox на неотрисованном дереве возвращает нули, и разбор
  // наложений принял бы все подписи за точку в начале координат.
  lastLabelScale = null;
  applyLabelScale(campusState.view.scale);
  return { svg, layer, me, route };
}

function featureById(id) {
  return campusState.data.features.find((f) => f.properties.id === id) || null;
}

function selectFeature(id, ui, options = {}) {
  const f = featureById(id);
  if (!f || !featureIsExplored(f, campusState.origin, campusState.exploredRegion)) return;
  campusState.selected = id;
  const preserveRoute = options.preserveRoute === true;
  if (!preserveRoute) clearRoute(ui);

  ui.svg.querySelectorAll(".campus-feat").forEach((n) => {
    n.classList.toggle("is-selected", n.dataset.featureId === id);
  });

  const p = f.properties;
  const card = document.querySelector("#campusInfo");
  if (!card) return;
  card.hidden = false;
  card.querySelector("[data-field=name-ru]").textContent = p.name_ru;
  card.querySelector("[data-field=name-zh]").textContent = p.name_zh;

  // Честность важнее вида: пока точка не сверена, так и написано.
  const badge = card.querySelector("[data-field=verified]");
  badge.textContent = p.verified ? "СВЕРЕНО" : "НЕ СВЕРЕНО";
  badge.classList.toggle("is-unverified", !p.verified);

  const dist = card.querySelector("[data-field=distance]");
  if (campusState.me) {
    dist.hidden = false;
    dist.textContent = `${Math.round(distanceToFeature(campusState.me, f))} м от вас`;
  } else {
    dist.hidden = true;
  }

  const btn = card.querySelector("#campusRouteBtn");
  const summary = card.querySelector("[data-field=route]");
  if (!btn) return;
  const start = startingPoint();
  btn.hidden = !start;
  if (start) btn.textContent = `Маршрут ${start.label}`;
  if (!preserveRoute) {
    summary.hidden = true;
    summary.className = "campus-route-summary";
    summary.textContent = "";
  }
  btn.onclick = () => {
    const currentStart = startingPoint();
    if (!currentStart) return;
    const dest = centroidOf(f);
    const r = drawRoute(ui, currentStart.point, [dest.lon, dest.lat]);
    summary.hidden = false;
    if (!r.ok) {
      summary.className = "campus-route-summary is-bad";
      summary.textContent = `Маршрут не построен: ${r.reason}.`;
      return;
    }
    const mins = Math.max(1, Math.round(r.total / WALK_SPEED_MS / 60));
    summary.className = "campus-route-summary";
    // Честно разделяем: по дорогам и по прямой, потому что тропинок в данных нет.
    summary.textContent = `${Math.round(r.total)} м, около ${mins} мин пешком. `
      + `Из них ${Math.round(r.offRoad)} м по прямой — внутренних дорожек в данных нет.`;
  };

  if (!preserveRoute) {
    requestAnimationFrame(() => card.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }
}

function centroidOf(feature) {
  const ring = feature.geometry.type === "Polygon"
    ? feature.geometry.coordinates[0]
    : feature.geometry.coordinates;
  let lon = 0;
  let lat = 0;
  ring.forEach((c) => {
    lon += c[0];
    lat += c[1];
  });
  return { lon: lon / ring.length, lat: lat / ring.length };
}

function distanceToFeature(from, feature) {
  const c = centroidOf(feature);
  const k = Math.cos((from.lat * Math.PI) / 180);
  const dx = (c.lon - from.lon) * METRES_PER_DEG_LON * k;
  const dy = (c.lat - from.lat) * METRES_PER_DEG_LAT;
  return Math.hypot(dx, dy);
}


/* ===========================================================================
   Маршруты
   ---------------------------------------------------------------------------
   Граф строится из дорожной сети OSM. Внутренних дорожек кампуса в данных нет,
   поэтому подход от дороги к зданию бывает длиной больше сотни метров. Рисуем
   его пунктиром и называем прямой — вести человека сплошной линией там, где мы
   не знаем тропы, было бы враньём.
   =========================================================================== */

const WALK_SPEED_MS = 1.35;        // ~4.9 км/ч, спокойный шаг

let routeGraph = null;

function nodeKey(c) {
  return `${c[0].toFixed(7)},${c[1].toFixed(7)}`;
}

function metresBetween(a, b) {
  const k = Math.cos((a[1] * Math.PI) / 180);
  return Math.hypot((a[0] - b[0]) * METRES_PER_DEG_LON * k,
                    (a[1] - b[1]) * METRES_PER_DEG_LAT);
}

function buildRouteGraph(features, origin, exploredRegion) {
  const adj = new Map();
  const pos = new Map();
  const link = (a, b) => {
    const ka = nodeKey(a);
    const kb = nodeKey(b);
    pos.set(ka, a);
    pos.set(kb, b);
    if (!adj.has(ka)) adj.set(ka, []);
    if (!adj.has(kb)) adj.set(kb, []);
    const w = metresBetween(a, b);
    adj.get(ka).push([kb, w]);
    adj.get(kb).push([ka, w]);
  };
  features.filter((f) => f.properties.category === "road").forEach((f) => {
    const cs = f.geometry.coordinates;
    for (let i = 0; i < cs.length - 1; i += 1) {
      const a = project(cs[i][0], cs[i][1], origin);
      const b = project(cs[i + 1][0], cs[i + 1][1], origin);
      if (regionContains(a, exploredRegion) && regionContains(b, exploredRegion)) {
        link(cs[i], cs[i + 1]);
      }
    }
  });
  return { adj, pos };
}

function nearestNode(point) {
  let best = null;
  let bestD = Infinity;
  routeGraph.pos.forEach((c, k) => {
    const d = metresBetween(point, c);
    if (d < bestD) {
      bestD = d;
      best = k;
    }
  });
  return { key: best, distance: bestD, coord: routeGraph.pos.get(best) };
}

function shortestPath(fromKey, toKey) {
  // Дейкстра на линейной очереди: 485 узлов, куча тут ничего не выиграет.
  const dist = new Map([[fromKey, 0]]);
  const prev = new Map();
  const done = new Set();
  while (true) {
    let cur = null;
    let curD = Infinity;
    dist.forEach((d, k) => {
      if (!done.has(k) && d < curD) {
        curD = d;
        cur = k;
      }
    });
    if (cur === null) return null;
    if (cur === toKey) break;
    done.add(cur);
    (routeGraph.adj.get(cur) || []).forEach(([nb, w]) => {
      if (done.has(nb)) return;
      const nd = curD + w;
      if (nd < (dist.has(nb) ? dist.get(nb) : Infinity)) {
        dist.set(nb, nd);
        prev.set(nb, cur);
      }
    });
  }
  const path = [toKey];
  while (path[0] !== fromKey) {
    const p = prev.get(path[0]);
    if (!p) return null;
    path.unshift(p);
  }
  return { path, length: dist.get(toKey) };
}

function clearRoute(ui) {
  ui.route.innerHTML = "";
}

function drawRoute(ui, from, to) {
  clearRoute(ui);
  const NS = "http://www.w3.org/2000/svg";

  const fromProjected = project(from[0], from[1], campusState.origin);
  const toProjected = project(to[0], to[1], campusState.origin);
  if (!regionContains(fromProjected, campusState.exploredRegion)
    || !regionContains(toProjected, campusState.exploredRegion)) {
    return { ok: false, reason: "одна из точек находится вне подготовленного сектора" };
  }

  const a = nearestNode(from);
  const b = nearestNode(to);
  if (!a.key || !b.key) return { ok: false, reason: "нет дорожной сети" };

  const found = shortestPath(a.key, b.key);
  if (!found) {
    // Две компоненты связности: путь между ними по данным не существует.
    return { ok: false, reason: "дороги между этими точками не связаны в данных" };
  }

  const line = (points, cls) => {
    const el = document.createElementNS(NS, "polyline");
    el.setAttribute("class", cls);
    el.setAttribute("points", points.map(([lon, lat]) => {
      const q = project(lon, lat, campusState.origin);
      return `${q.x.toFixed(1)},${q.y.toFixed(1)}`;
    }).join(" "));
    ui.route.appendChild(el);
  };

  line([from, a.coord], "route-leg");
  line(found.path.map((k) => routeGraph.pos.get(k)), "route-main");
  line([b.coord, to], "route-leg");

  const offRoad = a.distance + b.distance;
  return { ok: true, road: found.length, offRoad, total: found.length + offRoad };
}

function startingPoint() {
  if (!campusState.me) return null;
  const p = project(campusState.me.lon, campusState.me.lat, campusState.origin);
  if (!regionContains(p, campusState.exploredRegion)) return null;
  return { point: [campusState.me.lon, campusState.me.lat], label: "от вас" };
}

/* --- панорамирование и зум ------------------------------------------------ */

function applyView(ui) {
  const v = campusState.view;
  ui.layer.setAttribute("transform", `translate(${v.x} ${v.y}) scale(${v.scale})`);
  applyLabelScale(v.scale);
}

/* Подписи держат постоянный размер на экране: слой масштабируется, поэтому
   размер в единицах карты делится на тот же масштаб. Панорамирование масштаб
   не меняет, и тогда обход узлов пропускается — он идёт на каждый pointermove. */
let lastLabelScale = null;

function applyLabelScale(scale) {
  if (scale === lastLabelScale) return;
  lastLabelScale = scale;
  const nodes = campusState.labelNodes || [];
  const candidates = [];
  nodes.forEach((node) => {
    const base = Number(node.dataset.baseSize);
    const size = base / scale;
    node.setAttribute("font-size", size.toFixed(2));
    node.setAttribute("stroke-width", (size * 0.30).toFixed(2));
    const minScale = Number(node.dataset.minScale || 0);
    if (minScale && scale < minScale) {
      node.style.display = "none";
      return;
    }
    node.style.display = "";
    candidates.push(node);
  });
  declutterLabels(candidates, scale);
}

/* Разбор наложений: жадно, по приоритету. Подпись, перекрывающая уже принятую,
   прячется до следующего шага зума — на общем плане остаётся то, по чему
   ориентируются, вблизи проступает остальное. Считается только при смене
   масштаба: getBBox дёргает пересчёт вёрстки, на каждый pointermove это дорого. */
function declutterLabels(nodes, scale) {
  const sorted = nodes.slice().sort(
    (a, b) => Number(a.dataset.priority) - Number(b.dataset.priority)
  );
  const kept = [];
  const gap = 2 / scale;   // зазор в единицах карты, постоянный на экране
  sorted.forEach((node) => {
    let box;
    try {
      box = node.getBBox();
    } catch (err) {
      return;               // узел ещё не в отрисованном дереве
    }
    const rect = {
      x1: box.x - gap, y1: box.y - gap,
      x2: box.x + box.width + gap, y2: box.y + box.height + gap,
    };
    const clash = kept.some((r) => (
      rect.x1 < r.x2 && rect.x2 > r.x1 && rect.y1 < r.y2 && rect.y2 > r.y1
    ));
    if (clash) {
      node.style.display = "none";
      return;
    }
    kept.push(rect);
  });
}

function attachGestures(ui) {
  const svg = ui.svg;
  let dragging = false;
  let last = null;
  let pointers = new Map();
  let pinchStart = null;
  let tapTarget = null;
  let tapPointerId = null;
  let travelled = 0;
  let suppressClickUntil = 0;

  svg.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, e);
    if (pointers.size === 1) {
      dragging = true;
      last = { x: e.clientX, y: e.clientY };
      tapTarget = e.target;
      tapPointerId = e.pointerId;
      travelled = 0;
      svg.setPointerCapture(e.pointerId);
    } else if (pointers.size === 2) {
      dragging = false;
      tapTarget = null;
      tapPointerId = null;
      const [a, b] = [...pointers.values()];
      pinchStart = {
        dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY),
        scale: campusState.view.scale,
      };
    }
  });

  svg.addEventListener("pointermove", (e) => {
    if (pointers.has(e.pointerId)) pointers.set(e.pointerId, e);

    if (pointers.size === 2 && pinchStart) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      campusState.view.scale = clampScale(pinchStart.scale * (d / pinchStart.dist));
      applyView(ui);
      return;
    }
    if (!dragging || !last) return;
    const rect = svg.getBoundingClientRect();
    const vb = svg.viewBox.baseVal;
    const unitsPerPx = vb.width / rect.width;
    const dx = e.clientX - last.x;
    const dy = e.clientY - last.y;
    travelled += Math.hypot(dx, dy);
    campusState.view.x += dx * unitsPerPx;
    campusState.view.y += dy * unitsPerPx;
    last = { x: e.clientX, y: e.clientY };
    applyView(ui);
  });

  const release = (e, allowTap) => {
    const wasTap = allowTap && pointers.size === 1 && e.pointerId === tapPointerId
      && travelled < 7 && tapTarget;
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchStart = null;
    if (pointers.size === 0) {
      dragging = false;
      last = null;
    }
    if (allowTap) suppressClickUntil = performance.now() + 400;
    if (wasTap) activate(tapTarget);
    if (pointers.size === 0) {
      tapTarget = null;
      tapPointerId = null;
      travelled = 0;
    }
  };
  svg.addEventListener("pointerup", (e) => release(e, true));
  svg.addEventListener("pointercancel", (e) => release(e, false));

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    campusState.view.scale = clampScale(campusState.view.scale * (e.deltaY < 0 ? 1.12 : 0.89));
    applyView(ui);
  }, { passive: false });

  const activate = (target) => {
    const node = target.closest
      ? target.closest('.campus-feat[data-interactive="true"]')
      : null;
    if (node && node.dataset.featureId) selectFeature(node.dataset.featureId, ui);
  };
  svg.addEventListener("click", (e) => {
    if (performance.now() < suppressClickUntil) return;
    activate(e.target);
  });
  svg.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activate(e.target);
    }
  });
}

function clampScale(s) {
  return Math.min(8, Math.max(0.5, s));
}

/* --- геолокация ----------------------------------------------------------- */

function startLocating(ui, statusEl) {
  if (!navigator.geolocation) {
    statusEl.textContent = "GPS недоступен";
    return;
  }
  if (campusState.watchId !== null) {
    navigator.geolocation.clearWatch(campusState.watchId);
    campusState.watchId = null;
  }
  statusEl.textContent = "Ищем вас…";
  campusState.watchId = navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude, longitude, accuracy } = pos.coords;
      campusState.me = { lat: latitude, lon: longitude };
      const p = project(longitude, latitude, campusState.origin);
      ui.me.setAttribute("cx", p.x.toFixed(1));
      ui.me.setAttribute("cy", p.y.toFixed(1));
      ui.me.removeAttribute("hidden");
      const insideExplored = regionContains(p, campusState.exploredRegion);
      const insideCampus = campusState.campusBoundary
        ? coordinateInPolygon(longitude, latitude, campusState.campusBoundary)
        : insideBounds(p, campusState.campusBounds);
      ui.me.classList.toggle("is-outside-explored", !insideExplored);
      statusEl.textContent = insideExplored
        ? `Вы в изученной области · точность ${Math.round(accuracy)} м`
        : insideCampus
          ? `Вы в неизведанном регионе кампуса · точность ${Math.round(accuracy)} м`
          : `Вы вне области карты · точность ${Math.round(accuracy)} м`;
      if (campusState.selected) {
        selectFeature(campusState.selected, ui, { preserveRoute: insideExplored });
      }
    },
    (err) => {
      // Отказ в доступе — обычное дело, это не ошибка приложения.
      statusEl.textContent = err.code === err.PERMISSION_DENIED
        ? "Доступ к геопозиции закрыт"
        : "Не удалось определить позицию";
    },
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
  );
}


const LEGEND_LABELS = {
  academic: "Учебные", library: "Библиотека", dorm: "Общежития",
  food: "Еда", sport: "Спорт", grounds: "Территории институтов",
  "living-zone": "Жилые зоны", civic: "Общественные", park: "Парк",
};

function buildLegend(data) {
  const host = document.querySelector("#campusLegend");
  if (!host) return;
  const present = new Set(
    data.features
      .filter((f) => featureIsExplored(f, campusState.origin, campusState.exploredRegion))
      .map((f) => f.properties.category)
  );
  host.innerHTML = "";
  Object.keys(LEGEND_LABELS).forEach((cat) => {
    if (!present.has(cat)) return;
    const item = document.createElement("span");
    item.className = "campus-legend-item";
    item.innerHTML = `<i class="campus-swatch campus-swatch-${cat}"></i>${LEGEND_LABELS[cat]}`;
    host.appendChild(item);
  });
  if (data.exploration) {
    const item = document.createElement("span");
    item.className = "campus-legend-item";
    item.innerHTML = '<i class="campus-swatch campus-swatch-unexplored"></i>Неизведано';
    host.appendChild(item);
  }
}

/* --- инициализация -------------------------------------------------------- */

async function initCampusMap() {
  const host = document.querySelector("#campusCanvas");
  if (!host || campusState.data) return;

  let data;
  try {
    const res = await fetch(CAMPUS_SOURCE);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    host.innerHTML = '<p class="campus-error">Не удалось загрузить данные карты.</p>';
    return;
  }
  campusState.data = data;

  const ui = buildSvg(host, data);
  routeGraph = buildRouteGraph(data.features, campusState.origin, campusState.exploredRegion);
  applyView(ui);
  attachGestures(ui);

  const status = document.querySelector("#campusStatus");
  const locate = document.querySelector("#campusLocate");
  if (locate && status) {
    locate.addEventListener("click", () => startLocating(ui, status));
  }

  buildLegend(data);

  const count = data.features.length;
  const missing = (data.missing || []).length;
  const note = document.querySelector("#campusSourceNote");
  if (note) {
    note.textContent = `${count} объектов · ${missing} не найдено · ` +
      "светлый сектор — подготовленная часть данных, не административная граница · " +
      "основа © участники OpenStreetMap, ODbL · приблизительные объекты отмечены «?» · " +
      "ничего не сверено на местности";
  }
}

window.initCampusMap = initCampusMap;
