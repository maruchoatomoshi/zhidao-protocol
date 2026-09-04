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

const CAMPUS_SOURCE = "./assets/maps/campus.geojson";

/* Плоская проекция в метры. Для площадки 1.2 x 1.4 км искажение
   пренебрежимо, а читается она несравнимо проще Меркатора. */
const METRES_PER_DEG_LAT = 110540;
const METRES_PER_DEG_LON = 111320;

const campusState = {
  data: null,
  origin: null,      // {lat, lon} — точка отсчёта проекции
  bounds: null,      // экстент в метрах
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

function ringsOf(feature) {
  const g = feature.geometry;
  if (!g) return [];
  return g.type === "Polygon" ? g.coordinates : [g.coordinates];
}

function computeFrame(features) {
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

  // Кадрируем по границе территории, а не по всем объектам. Иначе школа в
  // 1.3 км и длинные проспекты растягивают экстент, и сам кампус съёживается
  // в угол — ровно это и произошло на первом прогоне.
  const frameSource = features.filter((f) => f.properties.category === "boundary");
  const extentOf = frameSource.length ? frameSource : features;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  extentOf.forEach((f) => {
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
  return { origin, bounds: { minX, minY, maxX, maxY } };
}

/* Порядок рисования: границы под всем, дороги над ними, здания сверху.
   Иначе здание окажется под дорогой и станет некликабельным. */
const DRAW_ORDER = ["boundary", "road", "school", "civic", "sport", "food", "academic"];

function buildSvg(host, data) {
  const features = data.features.slice().sort(
    (a, b) => DRAW_ORDER.indexOf(a.properties.category) - DRAW_ORDER.indexOf(b.properties.category)
  );
  const { origin, bounds } = computeFrame(features);
  campusState.origin = origin;
  campusState.bounds = bounds;

  const pad = 40;
  const w = bounds.maxX - bounds.minX + pad * 2;
  const h = bounds.maxY - bounds.minY + pad * 2;

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "campus-svg");
  svg.setAttribute("viewBox", `${bounds.minX - pad} ${bounds.minY - pad} ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Карта кампуса");

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
    node.setAttribute("class", `campus-feat campus-${p.category}`);
    node.dataset.featureId = p.id;
    if (p.category !== "road" && p.category !== "boundary") {
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.setAttribute("aria-label", `${p.name_ru}. ${p.name_zh}`);
    }
    layer.appendChild(node);
  });

  // Отметка «где я» — создаётся сразу, показывается после первого фикса GPS.
  const me = document.createElementNS(NS, "circle");
  me.setAttribute("class", "campus-me");
  me.setAttribute("r", "9");
  me.setAttribute("hidden", "hidden");
  layer.appendChild(me);

  host.innerHTML = "";
  host.appendChild(svg);
  return { svg, layer, me };
}

function featureById(id) {
  return campusState.data.features.find((f) => f.properties.id === id) || null;
}

function selectFeature(id, ui) {
  const f = featureById(id);
  if (!f) return;
  campusState.selected = id;

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

/* --- панорамирование и зум ------------------------------------------------ */

function applyView(ui) {
  const v = campusState.view;
  ui.layer.setAttribute("transform", `translate(${v.x} ${v.y}) scale(${v.scale})`);
}

function attachGestures(ui) {
  const svg = ui.svg;
  let dragging = false;
  let last = null;
  let pointers = new Map();
  let pinchStart = null;

  svg.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, e);
    if (pointers.size === 1) {
      dragging = true;
      last = { x: e.clientX, y: e.clientY };
      svg.setPointerCapture(e.pointerId);
    } else if (pointers.size === 2) {
      dragging = false;
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
    campusState.view.x += (e.clientX - last.x) * unitsPerPx;
    campusState.view.y += (e.clientY - last.y) * unitsPerPx;
    last = { x: e.clientX, y: e.clientY };
    applyView(ui);
  });

  const release = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinchStart = null;
    if (pointers.size === 0) {
      dragging = false;
      last = null;
    }
  };
  svg.addEventListener("pointerup", release);
  svg.addEventListener("pointercancel", release);

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    campusState.view.scale = clampScale(campusState.view.scale * (e.deltaY < 0 ? 1.12 : 0.89));
    applyView(ui);
  }, { passive: false });

  const activate = (target) => {
    const node = target.closest ? target.closest(".campus-feat") : null;
    if (node && node.dataset.featureId) selectFeature(node.dataset.featureId, ui);
  };
  svg.addEventListener("click", (e) => activate(e.target));
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
  statusEl.textContent = "Ищем вас…";
  campusState.watchId = navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude, longitude, accuracy } = pos.coords;
      campusState.me = { lat: latitude, lon: longitude };
      const p = project(longitude, latitude, campusState.origin);
      ui.me.setAttribute("cx", p.x.toFixed(1));
      ui.me.setAttribute("cy", p.y.toFixed(1));
      ui.me.removeAttribute("hidden");
      const inside = p.x >= campusState.bounds.minX && p.x <= campusState.bounds.maxX
        && p.y >= campusState.bounds.minY && p.y <= campusState.bounds.maxY;
      statusEl.textContent = inside
        ? `Вы на карте · точность ${Math.round(accuracy)} м`
        : "Вы вне кампуса";
      if (campusState.selected) selectFeature(campusState.selected, ui);
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
  applyView(ui);
  attachGestures(ui);

  const status = document.querySelector("#campusStatus");
  const locate = document.querySelector("#campusLocate");
  if (locate && status) {
    locate.addEventListener("click", () => startLocating(ui, status));
  }

  const count = data.features.length;
  const missing = (data.missing || []).length;
  const note = document.querySelector("#campusSourceNote");
  if (note) {
    note.textContent = `${count} объектов · ${missing} не найдено · ` +
      "геометрия © участники OpenStreetMap, ODbL · ничего не сверено на местности";
  }
}

window.initCampusMap = initCampusMap;
