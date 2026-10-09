/* Таймлайн ролика v2: seek(t) -- чистая функция времени, ничего не анимируется само.
   Экраны телефона, окна XP, Flip 3D, курсор, кинетический текст, аэро-декор и вспышки
   собираются из реальных снимков приложения (captures/) и ресурсов приложения. */
(() => {
  const W = 1080, H = 1920;
  const A = "/zhidao_v4/static/app/assets/", C = "captures/";
  const SW = 900, K = SW / 390, SH = Math.round(844 * K), B = 22;       // экран телефона в пикселях сцены
  const $ = (s) => document.querySelector(s);
  const world = $("#world"), ui = $("#ui");

  /* ---------- математика ---------- */
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const pr = (t, a, b) => clamp((t - a) / (b - a));
  const lerp = (a, b, x) => a + (b - a) * x;
  const eO = (x) => 1 - Math.pow(1 - x, 3);
  const eI = (x) => x * x * x;
  const eIO = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const eBack = (x) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  const win = (t, a, b, fi = 0.3, fo = 0.3) => Math.min(pr(t, a, a + fi), 1 - pr(t, b - fo, b));
  const calm = (t) => (t < 23 ? t : 23 + (t - 23) - Math.pow((t - 23) / 2, 2));   // декор плавно замирает к концу
  let seed = 11;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };

  const mk = (cls, parent, html = "", tag = "div") => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html) n.innerHTML = html;
    (parent || world).append(n);
    return n;
  };
  const Z = (n, z) => { n.style.zIndex = String(z); return n; };

  /* Универсальная трансформация: сдвиг, перспектива, поворот, масштаб, якорь, размытие, прозрачность. */
  function T(n, o) {
    const s = n.style;
    let tr = `translate(${o.x || 0}px, ${o.y || 0}px)`;
    if (o.rx || o.ry) tr += ` perspective(${o.pp || 1900}px)`;
    if (o.rx) tr += ` rotateX(${o.rx}deg)`;
    if (o.ry) tr += ` rotateY(${o.ry}deg)`;
    if (o.r) tr += ` rotate(${o.r}deg)`;
    const sx = o.sx ?? o.s ?? 1, sy = o.sy ?? o.s ?? 1;
    if (sx !== 1 || sy !== 1) tr += ` scale(${sx}, ${sy})`;
    if (o.tx || o.ty) tr += ` translate(${-(o.tx || 0)}px, ${-(o.ty || 0)}px)`;
    s.transform = tr;
    if (o.o !== undefined) { s.opacity = String(o.o); s.visibility = o.o < 0.004 ? "hidden" : "visible"; }
    if (o.w !== undefined) s.width = `${o.w}px`;
    if (o.h !== undefined) s.height = `${o.h}px`;
    s.filter = o.blur > 0.4 ? `blur(${o.blur.toFixed(1)}px)` : "";
  }
  const hide = (n) => { n.style.opacity = "0"; n.style.visibility = "hidden"; };

  /* ---------- фоны ---------- */
  const bgNight = $("#bgNight"), nightRays = $("#nightRays"), bgPhoto = $("#bgPhoto"), photo = $("#photo"),
    veil = $("#veil"), bgSky = $("#bgSky"), skyRays = $("#skyRays");

  /* ---------- декор: сферы, пузыри, квадраты, блёстки ---------- */
  const orbs = [], bubbles = [], squares = [], sparks = [];
  [[90, 1570, 200, 205, true], [960, 330, 150, 175, true], [-40, 760, 150, 150, true], [990, 1240, 120, 185, false],
    [180, 420, 110, 160, false], [880, 860, 90, 120, false], [140, 1060, 80, 190, false], [760, 1520, 100, 130, false], [500, 300, 70, 200, false]]
    .forEach(([x, y, size, hue, front], i) => {
      const n = mk("orb", front ? ui : world);
      n.style.width = n.style.height = `${size}px`;
      n.style.background = `radial-gradient(circle at 50% 62%, hsl(${hue},92%,64%), hsl(${hue},90%,38%) 72%, hsl(${hue},95%,26%) 100%)`;
      n.style.boxShadow = `0 22px 44px rgba(0,50,130,.35), inset 0 -${size * 0.12}px ${size * 0.2}px rgba(255,255,255,.4), inset 0 ${size * 0.04}px ${size * 0.08}px rgba(255,255,255,.5)`;
      Z(n, front ? 45 : 6);
      orbs.push({ n, x, y, size, ph: i * 1.7, front });
    });
  const mkBubbles = (n, front) => {
    for (let i = 0; i < n; i++) {
      const size = front ? 26 + rnd() * 70 : 40 + rnd() * 150;
      const el = mk("bub", front ? ui : world);
      el.style.width = el.style.height = `${size}px`;
      Z(el, front ? 46 : 7);
      bubbles.push({ el, size, x0: rnd() * W, sp: 70 + rnd() * 130, ph: rnd() * 2600, wob: 0.6 + rnd() * 1.1, amp: 14 + rnd() * 40, front });
    }
  };
  mkBubbles(20, false); mkBubbles(9, true);
  [[90, 330, 0, 90], [880, 250, 1, 70], [130, 1130, 1, 60], [900, 1010, 0, 110], [820, 560, 1, 54], [200, 600, 0, 48]].forEach(([x, y, g, size], i) => {
    const el = mk("sq" + (g ? " g" : ""), world);
    el.style.width = el.style.height = `${size}px`;
    Z(el, 8); squares.push({ el, x, y, ph: i * 1.3 });
  });
  [[210, 260], [840, 420], [120, 980], [960, 1180], [520, 520], [700, 1420], [330, 1300], [930, 700], [60, 1500], [620, 240]].forEach(([x, y], i) => {
    const el = mk("spark", ui); Z(el, 47); sparks.push({ el, x, y, ph: i * 2.3 });
  });

  /* вспышки-блики объектива, световые полосы, ленты-«свуши» */
  const flares = [[90, 255], [150, 200], [100, 170], [70, 160], [130, 190]].map(([size, hue]) => {
    const n = mk("flare", ui); n.style.width = n.style.height = `${size}px`;
    n.style.background = `radial-gradient(circle, hsla(${hue},100%,85%,.75) 0, hsla(${hue},100%,70%,.25) 55%, transparent 70%)`;
    Z(n, 48); return { n, size };
  });
  const streaks = [0, 1, 2].map(() => { const n = mk("streak", ui); n.style.width = "1300px"; Z(n, 49); return n; });
  const swooshes = [
    { d: "M-200 1500 C 100 1000, 520 1750, 760 1050 S 1200 520, 1400 700", c1: "#ffffff", c2: "#6fd0ff", w: 46 },
    { d: "M-200 400 C 260 760, 560 140, 900 520 S 1250 1000, 1400 1380", c1: "#ffffff", c2: "#7ce8ff", w: 34 },
  ].map((o, i) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "swoosh"); svg.setAttribute("width", W); svg.setAttribute("height", H); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = `<defs><linearGradient id="sw${i}" x1="0" x2="1"><stop offset="0" stop-color="${o.c1}" stop-opacity="0"/><stop offset=".5" stop-color="${o.c2}" stop-opacity=".95"/><stop offset="1" stop-color="${o.c1}" stop-opacity="0"/></linearGradient>
      <filter id="swb${i}"><feGaussianBlur stdDeviation="3"/></filter></defs>
      <path d="${o.d}" pathLength="1" fill="none" stroke="url(#sw${i})" stroke-width="${o.w}" stroke-linecap="round" filter="url(#swb${i})"/>`;
    ui.append(svg); Z(svg, 44);
    return { svg, path: svg.querySelector("path") };
  });
  function swoosh(i, t, a, b) {
    const p = pr(t, a, b), s = swooshes[i];
    const head = lerp(-0.45, 1.45, eIO(p));
    s.path.setAttribute("stroke-dasharray", "0.45 3");
    s.path.setAttribute("stroke-dashoffset", String(0.45 - head));
    s.svg.style.opacity = p > 0 && p < 1 ? "1" : "0";
  }
  function streakAt(i, t, a, b, y, tilt = -4) {
    const p = pr(t, a, b), n = streaks[i];
    T(n, { x: lerp(-1300, 1100, eIO(p)), y: y + p * 30, r: tilt, o: p > 0 && p < 1 ? Math.sin(p * Math.PI) : 0 });
  }
  function lensFlare(t, a, b, y0, y1) {
    const p = pr(t, a, b), v = Math.sin(p * Math.PI);
    const sx = lerp(-100, 1180, eIO(p)), sy = lerp(y0, y1, p);
    flares.forEach((f, i) => {
      const k = [0, 0.35, 0.75, 1.1, 1.5][i];
      const x = lerp(sx, W - sx, k * 0.5) - f.size / 2, y = lerp(sy, H - sy, k * 0.5) - f.size / 2;
      T(f.n, { x, y, s: 0.6 + v * 0.7, o: v * (i === 0 ? 1 : 0.7) });
    });
  }

  /* ---------- логотип ---------- */
  const logoBox = (id, z) => {
    const l = mk("logo", world); l.innerHTML = `<img src="${A}zhidao-dragon-logo.png" alt="">`; l.id = id; Z(l, z);
    const sh = mk("sheen", world); sh.id = id + "Sheen"; Z(sh, z + 1);
    return { l, sh };
  };
  const logo1 = logoBox("logo1", 12), logo2 = logoBox("logo2", 12);
  const glow1 = mk("", world); glow1.style.cssText += ";width:1100px;height:1100px;border-radius:50%;background:radial-gradient(circle,rgba(120,205,255,.85),rgba(40,120,240,.3) 45%,transparent 70%)"; Z(glow1, 11);
  const shocks = [0, 1, 2].map(() => Z(mk("shock", world), 13));
  const boot = Z(mk("", world), 13); boot.id = "boot";
  const blocks = [0, 1, 2].map(() => mk("", boot, "", "i"));

  /* ---------- рабочий стол Хайнаня ---------- */
  const icons = [["desktop-map", "Карта"], ["desktop-collection", "Коллекция"], ["desktop-group", "Встречи"], ["desktop-forge", "Мастерская"], ["desktop-shield", "Антивирус"]]
    .map(([f, label], i) => {
      const n = mk("dicon", world, `<img src="${A}icons/${f}.svg" alt=""><span>${label}</span>`); Z(n, 14);
      return { n, i };
    });
  const taskbar = Z(mk("", world, `<div id="start"><img src="${A}zhidao-dragon-logo-256.png" alt="">Пуск</div><div id="tray"><img src="${A}icons/desktop-bell.svg" alt=""><img src="${A}icons/desktop-megaphone.svg" alt=""><img src="${A}icons/desktop-weather.svg" alt=""></div>`), 30);
  taskbar.id = "taskbar";
  const balloon = Z(mk("", world, `<b>Протокол 60 — идёт</b><span>Зайди, пока идёт раунд</span>`), 31); balloon.id = "balloon";

  /* ---------- окно XP с обрезкой снимка ---------- */
  const crops = [];
  function Crop(src, rect, w) {
    const n = mk("xpcard", world); const img = mk("", n, "", "img"); img.src = C + src;
    const k = w / rect[2];
    n.style.width = `${w}px`; n.style.height = `${rect[3] * k}px`;
    const o = { root: n, img, w, h: rect[3] * k, off: 0,
      ready() { img.style.width = `${img.naturalWidth * k}px`; img.style.height = `${img.naturalHeight * k}px`; img.style.left = `${-rect[0] * k}px`; img.style.top = `${-rect[1] * k}px`; } };
    crops.push(o); return o;
  }

  /* ---------- телефон ---------- */
  const PW = SW + 2 * B, PH = SH + 2 * B;
  const HDR = 84, DOCKH = 66, DOCK_TOP = 844 - DOCKH;                    // css-пиксели фиксированных полос приложения
  function Phone(kind, o) {
    const root = mk("phone", world); root.style.width = `${PW}px`; root.style.height = `${PH}px`;
    mk("pbezel", root);
    const scr = mk("pscreen", root); scr.style.cssText += `;left:${B}px;top:${B}px;width:${SW}px;height:${SH}px`;
    const img = (src, parent, extra = "") => { const i = mk("", parent, "", "img"); i.src = C + src; i.style.cssText += `;position:absolute;left:0;top:0;width:${SW}px;height:${SH}px;${extra}`; return i; };
    let content = null;
    if (kind === "view") img(o.src, scr);
    else {
      const top = mk("band", scr); top.style.height = `${HDR * K}px`; top.style.top = "0"; img(o.header, top);
      const body = mk("band", scr); body.style.top = `${HDR * K}px`; body.style.height = `${(DOCK_TOP - HDR) * K}px`;
      content = mk("", body, "", "img"); content.src = C + o.content; content.style.cssText += `;position:absolute;left:${8 * K}px;top:0;width:${374 * K}px`;
      const dock = mk("band", scr); dock.style.top = `${DOCK_TOP * K}px`; dock.style.height = `${DOCKH * K}px`;
      img(o.dock, dock, `top:${-DOCK_TOP * K}px`);
    }
    const gloss = mk("pgloss", root);
    const fx = mk("", scr); fx.style.cssText += ";position:absolute;inset:0;pointer-events:none";
    return { root, scr, content, gloss, fx, kind, off: B,
      setScroll(px) { if (content) content.style.top = `${(8 - px) * K - 0}px`; } };
  }

  const P = {
    today: Phone("scroll", { header: "v-schedule.png", dock: "v-schedule.png", content: "today.png" }),
    events: Phone("scroll", { header: "v-schedule.png", dock: "v-games.png", content: "events.png" }),
    map: Phone("scroll", { header: "v-map.png", dock: "v-more.png", content: "map.png" }),
    model: Phone("view", { src: "v-model.png" }),
    meet: Phone("view", { src: "v-meet.png" }),
    table: Phone("view", { src: "g-table.png" }),
    royale: Phone("view", { src: "g-royale.png" }),
    market: Phone("view", { src: "g-market.png" }),
    zombie: Phone("view", { src: "g-zombie.png" }),
    sabotage: Phone("view", { src: "g-sabotage.png" }),
    capture: Phone("view", { src: "g-capture.png" }),
    cases: Phone("view", { src: "v-cases.png" }),
    collection: Phone("view", { src: "v-collection.png" }),
  };
  Object.values(P).forEach((p, i) => Z(p.root, 20 + i));
  const rep = Crop("rep.png", [0, 0, 1122, 1264], 880); Z(rep.root, 34);
  const homeWin = Crop("today.png", [0, 0, 1122, 905], 780); Z(homeWin.root, 21);

  /* реальные снимки для кольца Flip 3D */
  const flipSrc = ["v-collection.png", "v-implants.png", "v-workshop.png", "v-shop.png", "v-profile.png"];
  const FW = 560, FH = Math.round(FW * 2532 / 1170);
  const flip = flipSrc.map((src, i) => {
    const n = Z(mk("flipcard", world), 36 + i); n.style.width = `${FW}px`; n.style.height = `${FH}px`;
    const im = mk("", n, "", "img"); im.src = C + src; im.style.cssText += `;position:absolute;left:0;top:0;width:${FW - 16}px;height:${FH - 16}px`;
    return { n, i };
  });

  /* имплантов в коллекции -- реальные иллюстрации каталога */
  const IMPL = ["qilin", "terracota", "zhuque", "panda", "koi", "jinchan"];
  const impl = IMPL.map((c) => { const im = mk("impl", world, "", "img"); im.src = `${A}implants/${c}.webp`; im.style.width = "300px"; Z(im, 60); return im; });
  const glints = [];

  /* ---------- курсор ---------- */
  const cursor = Z(mk("", ui), 70); cursor.id = "cursor";
  cursor.innerHTML = `<svg width="60" height="80" viewBox="0 0 30 40"><path d="M2 2 L2 31 L9.5 24 L14.5 36 L20 33.5 L15 22 L25 22 Z" fill="#fff" stroke="#111" stroke-width="2.4" stroke-linejoin="round"/></svg>`;
  const ripples = [0, 1, 2, 3, 4].map(() => Z(mk("ripple", ui), 69));

  /* ---------- кинетический текст ---------- */
  const caps = [];
  function Cap(lines, o) {
    const root = mk("cap " + (o.cls || ""), ui); Z(root, 62); root.style.top = `${o.top}px`; root.style.left = "40px";
    const words = [];
    lines.forEach((line) => {
      const row = mk("crow", root);
      line.split(" ").forEach((w) => { const k = mk("kw", row); k.dataset.t = w; mk("", k, w, "b"); words.push(k); });
    });
    const cp = { root, words, a: o.a, b: o.b, times: o.times, stag: o.stag ?? 0.1 };
    caps.push(cp); return cp;
  }
  function drawCap(c, t) {
    c.words.forEach((w, i) => {
      const ts = c.times ? c.times[i] : c.a + i * c.stag;
      const pin = pr(t, ts, ts + 0.45), pout = pr(t, c.b - 0.32 + i * 0.03, c.b + i * 0.03);
      if (t < ts - 0.01 || t > c.b + 0.4) { hide(w); return; }
      const ei = eBack(pin), eo = eI(pout);
      const sc = lerp(0.25, 1, ei) * lerp(1, 1.3, eo);
      const rot = lerp(i % 2 ? 14 : -14, 0, eO(pin));
      const bob = Math.sin(t * 2.2 + i) * 4 * pin * (1 - pout);
      T(w, { y: lerp(90, 0, eO(pin)) - 70 * eo + bob, r: rot, s: sc, o: clamp(pin * 2.4) * (1 - clamp(pout * 1.4)), blur: lerp(14, 0, pin) + 14 * pout });
    });
  }
  Cap(["Твоя поездка", "начинается здесь"], { top: 1450, a: 1.05, b: 3.5, stag: 0.14 });
  Cap(["Хайнань.", "Больше, чем поездка"], { top: 1440, a: 4.25, b: 7.0, stag: 0.16, cls: "xs" });
  Cap(["Твой день"], { top: 120, a: 7.05, b: 8.75 });
  Cap(["Твои события"], { top: 120, a: 8.75, b: 10.4 });
  Cap(["Твой кампус"], { top: 120, a: 10.4, b: 11.85 });
  Cap(["Знакомься. Играй.", "Действуй."], { top: 70, a: 11.95, b: 17.4, cls: "small", times: [11.95, 13.1, 15.65] });
  Cap(["Собери историю", "своей поездки"], { top: 60, a: 17.6, b: 21.2, stag: 0.14, cls: "md" });

  /* ---------- финал, вспышка, мозаика ---------- */
  const title6 = Z(mk("", ui), 62); title6.id = "title6"; title6.textContent = "ZHIDAO Protocol"; title6.style.top = "880px";
  const sub6 = Z(mk("", ui), 62); sub6.id = "sub6"; sub6.textContent = "Больше, чем поездка"; sub6.style.top = "1045px";
  const cta6 = Z(mk("", ui), 62); cta6.id = "cta6"; cta6.textContent = "Открывай в MAX"; cta6.style.top = "1190px";
  const flash = Z(mk("", ui), 90); flash.id = "flash";
  const ringReveal = Z(mk("", world), 15); ringReveal.id = "ringReveal";
  const mosaic = Z(mk("", ui), 80); mosaic.id = "mosaic";
  const COLS = 8, ROWS = 13, TS = 135, TH = 148;
  const tiles = [];
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) { const n = mk("", mosaic); n.style.width = `${TS - 6}px`; n.style.height = `${TH - 6}px`; tiles.push({ n, r, c }); }
  function mosaicWave(t, a, b, dir = 1) {
    const p = pr(t, a, b);
    tiles.forEach(({ n, r, c }) => {
      const d = (dir > 0 ? c + r * 0.6 : (COLS - c) + (ROWS - r) * 0.6) / (COLS + ROWS * 0.6);
      const q = clamp((p - d * 0.55) / 0.45);
      const v = Math.sin(q * Math.PI);
      T(n, { x: c * TS + 3, y: r * TH + 3, s: lerp(0.2, 1.04, v), o: q > 0 && q < 1 ? 0.95 * clamp(v * 2) : 0 });
    });
  }

  /* ---------- камера: кадры экранов ---------- */
  const D0 = { fx: 450, fy: 520, z: 1, sx: 540, top: 300, dy: 0, rx: 0, ry: 0, rz: 0, scroll: 0 };
  function camAt(frames, t, ox = 0) {
    const fin = (c) => ({ ...c, sy: c.top - c.dy + (c.fy + ox) * c.z });
    const f = frames.map(([tt, o]) => [tt, { ...D0, ...o }]);
    if (t <= f[0][0]) return fin(f[0][1]);
    if (t >= f[f.length - 1][0]) return fin(f[f.length - 1][1]);
    let i = 0; while (t > f[i + 1][0]) i++;
    const p = eIO(pr(t, f[i][0], f[i + 1][0])), a = f[i][1], b = f[i + 1][1], out = {};
    for (const k in a) out[k] = lerp(a[k], b[k], p);
    return fin(out);
  }
  const DIR = { R: { x: 1300, ry: -40, r: 7 }, L: { x: -1300, ry: 40, r: -7 }, U: { y: -1600, rx: 32 }, D: { y: 1600, rx: -32 }, Z: { s: -0.45 }, FR: { ry: 90 }, FL: { ry: -90 } };
  const shots = [], shotById = {}, drawn = {};
  function Shot(id, obj, a, b, enter, exit, cam, fxFn) { const s = { id, obj, a, b, enter, exit, cam, fx: fxFn }; shots.push(s); shotById[id] = s; return s; }
  function drawShot(s, t) {
    const o = s.obj, root = o.root;
    if (t < s.a - 0.02 || t > s.b + 0.02) { hide(root); return; }
    const c = camAt(s.cam, t, s.obj.off || 0);
    const pin = eO(pr(t, s.a, s.a + 0.42)), pout = eI(pr(t, s.b - 0.34, s.b));
    const ei = DIR[s.enter] || {}, ex = DIR[s.exit] || {};
    const lin = 1 - pin;
    const off = (d, k) => ({ x: (d.x || 0) * k, y: (d.y || 0) * k, rx: (d.rx || 0) * k, ry: (d.ry || 0) * k, r: (d.r || 0) * k, s: (d.s || 0) * k });
    const ai = off(ei, lin), ao = off(ex, pout);
    const ox = o.off || 0;
    T(root, {
      x: c.sx + ai.x + ao.x, y: c.sy + ai.y + ao.y, rx: c.rx + ai.rx + ao.rx, ry: c.ry + ai.ry + ao.ry, r: c.rz + ai.r + ao.r,
      s: c.z * (1 + ai.s + ao.s), tx: c.fx + ox, ty: c.fy + ox,
      o: (s.enter === "FR" ? clamp(pin * 2 - 0.4) : clamp(pin * 3)) * (s.exit === "FL" ? 1 - clamp((pout - 0.55) * 4) : 1 - clamp((pout - 0.82) * 6)),
      blur: 22 * lin * lin + 22 * pout * pout,
    });
    if (o.setScroll) o.setScroll(c.scroll);
    if (o.gloss) o.gloss.style.backgroundPosition = `${lerp(110, -10, pr(t, s.a, s.b))}% 0`;
    if (s.fx) s.fx(t, o, c);
  }
  const at = (c, lx, ly) => [c.sx + c.z * (lx - c.fx), c.sy + c.z * (ly - c.fy)];     // точка экрана телефона -> сцена (без учёта наклона)

  /* кадры: Сегодня -> Ивенты -> Карта -> Модель */
  Shot("today", P.today, 6.95, 8.85, "R", "L", [
    [6.95, { ry: -10, rx: 4, rz: -2, fy: 500, z: 0.96 }], [7.8, { ry: -4, rx: 2, rz: 0, fy: 500, z: 1.0 }],
    [8.1, { ry: 0, fy: 600, z: 1.03, scroll: 0 }], [8.7, { ry: 3, fy: 650, z: 1.06, scroll: 215 }]]);
  Shot("events", P.events, 8.55, 10.45, "R", "L", [
    [8.55, { ry: 10, rx: 4, rz: 2, fy: 560, z: 0.96 }], [9.35, { ry: 3, rx: 1, rz: 0, fy: 560, z: 1.0 }],
    [9.75, { fx: 330, fy: 520, z: 1.22, ry: 0, scroll: 0 }], [10.35, { fx: 330, fy: 640, z: 1.16, scroll: 90 }]]);
  Shot("map", P.map, 10.15, 11.4, "R", "FL", [
    [10.15, { ry: -8, rx: 3, fy: 700, z: 0.96 }], [11.3, { ry: 0, fy: 740, z: 1.04 }]]);
  Shot("model", P.model, 11.1, 12.35, "FR", "L", [
    [11.1, { fy: 1010, z: 0.98, ry: 0 }], [12.3, { fy: 1010, z: 1.08, ry: -4, rz: 1 }]]);

  /* игры и разделы */
  Shot("meet", P.meet, 11.95, 12.85, "U", "L", [[11.95, { fy: 800, z: 0.98, ry: 6, rz: -2 }], [12.8, { fy: 760, z: 1.06, ry: 0 }]]);
  Shot("table", P.table, 12.55, 13.5, "R", "D", [[12.55, { fy: 700, z: 0.98, ry: -8, rx: 3, rz: 2 }], [13.45, { fy: 760, z: 1.06, ry: -2 }]]);
  Shot("royale", P.royale, 13.15, 14.45, "Z", "R", [[13.15, { fy: 700, z: 0.98, ry: 5 }], [13.75, { fx: 450, fy: 640, z: 1.08, ry: 0 }], [14.35, { z: 1.1, ry: -3 }]]);
  Shot("market", P.market, 14.1, 15.05, "L", "U", [[14.1, { fy: 760, z: 1.0, ry: 8, rz: -1 }], [15.0, { fy: 820, z: 1.08, ry: 0 }]]);
  Shot("zombie", P.zombie, 14.75, 15.55, "D", "R", [[14.75, { fy: 800, z: 1.0, ry: -6, rx: 3 }], [15.5, { fy: 760, z: 1.08, ry: 0 }]]);
  Shot("sabotage", P.sabotage, 15.25, 16.0, "L", "R", [[15.25, { fy: 760, z: 1.0, ry: 8 }], [15.95, { fy: 700, z: 1.08, ry: 0 }]]);
  Shot("capture", P.capture, 15.7, 16.75, "R", "L", [[15.7, { fy: 800, z: 1.0, ry: -8, rz: 2 }], [16.7, { fy: 760, z: 1.08, ry: 0 }]]);
  Shot("rep", rep, 16.4, 17.65, "Z", "U", [[16.4, { fx: 440, fy: 500, z: 1.0, ry: 5 }], [17.6, { fx: 440, fy: 560, z: 1.08, ry: -3 }]]);

  /* кейс: скан, вспышка, коллекция */
  const caseFx = {
    beam: mk("fxbeam", P.cases.fx), flash: mk("fxflash", P.cases.fx),
    rings: [0, 1, 2].map(() => mk("fxring", P.cases.fx)),
  };
  const CASE_C = [450, 667];                                           // центр ящика на экране «Кейсы» (px экрана телефона)
  Shot("cases", P.cases, 17.3, 18.75, "R", "FL", [
    [17.3, { fx: 450, fy: 700, z: 1.0, dy: 200, ry: -8, rx: 3, rz: 2 }], [17.9, { fx: 450, fy: 780, z: 1.28, dy: 560, ry: 0, rx: 0, rz: 0 }], [18.6, { fx: 450, fy: 760, z: 1.34, dy: 580 }]],
  (t) => {
    const scan = pr(t, 18.0, 18.7);
    T(caseFx.beam, { y: lerp(420, 930, eIO(scan)) - 140, o: scan > 0 && scan < 1 ? 1 : 0 });
    caseFx.rings.forEach((r, i) => {
      const p = pr(t, 18.05 + i * 0.22, 18.9 + i * 0.22), rad = lerp(80, 520, eO(p));
      r.style.width = r.style.height = `${rad * 2}px`;
      T(r, { x: CASE_C[0] - rad, y: CASE_C[1] - rad, o: p > 0 && p < 1 ? 0.9 * (1 - p) : 0 });
    });
    T(caseFx.flash, { o: Math.max(0, 1 - Math.abs(t - 18.6) / 0.22) });
  });
  Shot("collection", P.collection, 18.55, 19.85, "FR", "D", [[18.55, { fx: 450, fy: 840, z: 1.0, ry: 0 }], [19.8, { fx: 450, fy: 880, z: 1.22, ry: -2, rz: 1 }]]);

  /* ---------- курсор: траектории ---------- */
  const CURSOR = [
    { a: 4.85, b: 6.85, pts: () => [[4.85, 980, 1650], [5.5, 1000, 1240], [5.95, 976, 947], [6.5, 1010, 1060]], clicks: [6.0] },
    { a: 13.55, b: 14.4, pts: () => { const p1 = at(drawn.royale, 560, 1010); return [[13.55, 900, 1500], [13.9, p1[0], p1[1]], [14.35, p1[0] + 60, p1[1] - 80]]; }, clicks: [13.92] },
    { a: 17.45, b: 18.35, pts: () => { const p1 = at(drawn.cases, 450, 1210); return [[17.45, 900, 1420], [17.95, p1[0], p1[1]], [18.3, p1[0] + 70, p1[1] + 40]]; }, clicks: [17.98] },
    { a: 22.9, b: 25.5, pts: () => [[22.9, 940, 1650], [23.5, 900, 1340], [23.62, 862, 1302], [24.2, 930, 1400], [25, 930, 1400]], clicks: [23.66] },
  ];
  const rippleSpots = [];
  CURSOR.forEach((s) => s.clicks.forEach((c) => rippleSpots.push({ c, s })));
  function drawCursor(t) {
    const seg = CURSOR.find((s) => t >= s.a && t <= s.b);
    if (!seg) hide(cursor);
    else {
      const pts = seg.pts();
      let i = 0; while (i < pts.length - 2 && t > pts[i + 1][0]) i++;
      const p0 = pts[i], p1 = pts[i + 1], p = eIO(pr(t, p0[0], p1[0]));
      const down = seg.clicks.some((c) => t > c - 0.02 && t < c + 0.12);
      T(cursor, { x: lerp(p0[1], p1[1], p), y: lerp(p0[2], p1[2], p), s: down ? 0.86 : 1, o: win(t, seg.a, seg.b, 0.2, 0.25) });
    }
    rippleSpots.forEach(({ c, s }, i) => {
      const r = ripples[i], p = pr(t, c, c + 0.55);
      if (!(p > 0 && p < 1)) { hide(r); return; }
      const pts = s.pts();
      const near = pts.reduce((best, q) => (Math.abs(q[0] - c) < Math.abs(best[0] - c) ? q : best), pts[0]);
      const rad = lerp(14, 110, eO(p));
      r.style.width = r.style.height = `${rad * 2}px`;
      T(r, { x: near[1] - rad, y: near[2] - rad, o: 1 - p });
    });
  }

  /* ---------- блеск по ячейкам реальной коллекции ---------- */
  function drawGlints(t) {
    const cells = window.__cells || [];
    if (glints.length < cells.length) cells.forEach(() => glints.push(mk("glint", P.collection.fx)));
    cells.forEach((c, i) => {
      const g = glints[i];
      const a = 18.95 + i * 0.1, p = pr(t, a, a + 0.55);
      g.style.left = `${c.x * K}px`; g.style.top = `${c.y * K}px`; g.style.width = `${c.w * K}px`; g.style.height = `${c.h * K}px`;
      g.style.setProperty("--gp", `${(1 - p) * 100}%`);
      g.style.opacity = p > 0 && p < 1 ? "1" : "0";
    });
  }

  /* ---------- декор: кадр времени ---------- */
  function drawDecor(t) {
    const tb = calm(t);
    const vis = pr(t, 3.7, 4.6), early = win(t, 0.3, 3.7, 0.8, 0.4);
    orbs.forEach((o) => {
      const x = o.x + Math.sin(tb * 0.5 + o.ph) * 38, y = o.y + Math.cos(tb * 0.42 + o.ph) * 34;
      T(o.n, { x: x - o.size / 2, y: y - o.size / 2, s: 0.92 + 0.08 * Math.sin(tb * 0.8 + o.ph), o: (o.front ? 0.92 : 0.8) * vis, blur: o.front ? 4 : 0 });
    });
    bubbles.forEach((b) => {
      const L = 2500, y = 2150 - ((tb * b.sp + b.ph) % L), x = b.x0 + Math.sin(tb * b.wob + b.ph) * b.amp - b.size / 2;
      const o = (b.front ? 0.85 : 0.9) * (t < 3.6 ? 0.45 * pr(t, 0.5, 1.5) : 1);
      T(b.el, { x, y, o: o * clamp(Math.min((2150 - y) / 150, (y + b.size + 40) / 150)) });
    });
    const sqVis = Math.max(early, win(t, 21.4, 26, 0.7, 0.01));
    squares.forEach((q) => {
      T(q.el, { x: q.x, y: q.y + Math.sin(tb * 1.1 + q.ph) * 18, r: Math.sin(tb * 0.7 + q.ph) * 12, s: 0.9 + 0.1 * Math.sin(tb * 0.9 + q.ph), o: clamp(sqVis) * 0.85 });
    });
    sparks.forEach((s) => {
      const v = Math.pow(Math.max(0, Math.sin(tb * 2.4 + s.ph)), 3);
      T(s.el, { x: s.x - 35, y: s.y - 35, s: 0.4 + v * 0.9, r: tb * 20 + s.ph * 10, o: v * 0.95 * clamp(pr(t, 0.4, 1.2)) });
    });
    swoosh(0, t, 3.6, 4.5); swoosh(1, t, 21.2, 22.3);
    streakAt(0, t, 6.9, 7.45, 640, -6); streakAt(1, t, 11.7, 12.2, 1100, 5); streakAt(2, t, 17.1, 17.6, 520, -3);
    lensFlare(t, 3.4, 4.6, 520, 360);
  }

  /* ---------- один кадр ---------- */
  function seek(t) {
    const tb = calm(t);
    /* камера: лёгкая тряска на ударах */
    const hits = [4.0, 7.2, 8.75, 10.2, 11.95, 13.15, 14.1, 15.7, 17.3, 18.6, 21.85];
    let shake = 0; hits.forEach((h) => { if (t > h) shake += 9 * Math.exp(-(t - h) * 9); });
    T(world, { x: Math.sin(t * 61) * shake, y: Math.cos(t * 53) * shake, r: Math.sin(t * 47) * shake * 0.04, s: 1 + shake * 0.0012 });

    /* фоны */
    T(bgNight, { o: 1 });
    nightRays.style.opacity = String(0.9 * (1 - pr(t, 3.5, 4.8))); nightRays.style.transform = `rotate(${t * 4}deg)`;
    const reveal = eIO(pr(t, 3.5, 4.9));
    bgPhoto.style.clipPath = reveal >= 1 ? "none" : `circle(${reveal * 2300}px at 540px 800px)`;
    bgPhoto.style.visibility = reveal <= 0 ? "hidden" : "visible";
    const pan = pr(t, 3.5, 22), blur = lerp(0, 7, eIO(pr(t, 6.7, 7.6)));
    photo.style.transform = `translate(${lerp(-1750, -2400, pan)}px, 0) scale(${lerp(1.06, 1.36, pan)})`;
    photo.style.filter = blur > 0.05 ? `blur(${blur}px) saturate(1.12)` : "saturate(1.12)";
    veil.style.opacity = String(lerp(0, 0.7, eIO(pr(t, 6.7, 7.6))));
    const sky = eIO(pr(t, 21.3, 22.0));
    bgSky.style.opacity = String(sky); skyRays.style.opacity = String(sky * 0.85); skyRays.style.transform = `rotate(${(tb - 21) * 1.4}deg)`;
    const rr = reveal * 2300;
    ringReveal.style.width = ringReveal.style.height = `${rr * 2}px`;
    T(ringReveal, { x: 540 - rr, y: 800 - rr, o: reveal > 0 && reveal < 1 ? 0.9 * (1 - reveal * 0.5) : 0 });

    drawDecor(t);

    /* === Сцена 1: запуск (0-3.7) === */
    {
      const inP = eO(pr(t, 0.15, 1.3)), outP = eIO(pr(t, 3.15, 4.1));
      const sc = lerp(2.3, 1, inP) * lerp(1, 1.9, outP);
      const o = clamp(pr(t, 0.15, 0.7)) * (1 - pr(t, 3.5, 4.0));
      const lb = { x: 220, y: 410 + Math.sin(tb * 1.6) * 8, w: 640, h: 640, s: sc, o, blur: lerp(26, 0, inP) + 8 * outP };
      T(logo1.l, lb); T(logo1.sh, lb);
      const sp = t < 2.5 ? 1 - eIO(pr(t, 1.2, 2.1)) : 1 - eIO(pr(t, 2.65, 3.3));
      logo1.sh.style.backgroundPosition = `${sp * 100}% 0`;
      T(glow1, { x: -10, y: 230, s: lerp(0.5, 1.1, eO(pr(t, 0, 1.6))) * lerp(1, 1.6, outP), o: 0.95 * clamp(pr(t, 0, 0.8)) * (1 - pr(t, 3.5, 4.1)) });
      shocks.forEach((n, i) => {
        const p = pr(t, 0.7 + i * 0.22, 1.7 + i * 0.22), r = lerp(160, 720, eO(p));
        n.style.width = n.style.height = `${r * 2}px`;
        T(n, { x: 540 - r, y: 730 - r, o: p > 0 && p < 1 ? 0.9 * (1 - p) : 0 });
      });
      T(boot, { x: 220, y: 1190 + (1 - eO(pr(t, 0.9, 1.5))) * 40, o: clamp(pr(t, 0.9, 1.3)) * (1 - pr(t, 3.2, 3.6)) });
      blocks.forEach((n, i) => {
        let ph = ((t - 1.0) * 0.85 - i * 0.12) % 1; if (ph < 0) ph += 1;
        n.style.left = `${lerp(-70, 650, ph)}px`; n.style.opacity = t > 1.0 ? "1" : "0";
      });
    }

    /* === Сцена 2: рабочий стол и окно «Хайнань» (3.6-7.2) === */
    {
      icons.forEach(({ n, i }) => {
        const a = 4.35 + i * 0.13, p = eBack(pr(t, a, a + 0.5));
        T(n, { x: 40, y: 230 + i * 205 + Math.sin(tb * 1.2 + i) * 3, s: lerp(0.2, 1, p) * (1 + (i === 0 && t > 5.4 && t < 5.9 ? 0.12 : 0)), o: clamp(pr(t, a, a + 0.2)) * (1 - pr(t, 6.7, 7.1)) });
      });
      T(taskbar, { y: lerp(130, 0, eO(pr(t, 4.2, 4.8))), o: clamp(pr(t, 4.2, 4.5)) * (1 - pr(t, 6.9, 7.3)) });
      const open = eBack(pr(t, 5.05, 5.75)), out = eIO(pr(t, 6.85, 7.35));
      T(homeWin.root, { x: 270, y: 380 + lerp(70, 0, eO(pr(t, 5.05, 5.75))), s: lerp(0.35, 1, open) * lerp(1, 1.15, out), o: clamp(pr(t, 5.05, 5.35)) * (1 - pr(t, 6.9, 7.3)), blur: 12 * out });
      const bp = eBack(pr(t, 6.15, 6.6));
      T(balloon, { x: 420, y: 1648 + (1 - bp) * 30, s: lerp(0.4, 1, bp), o: clamp(pr(t, 6.15, 6.35)) * (1 - pr(t, 6.9, 7.2)) });
    }

    /* === экраны телефона, окна, Flip 3D === */
    shots.forEach((s) => drawShot(s, t));
    shots.forEach((s) => { drawn[s.id] = camAt(s.cam, clamp(t, s.a, s.b), s.obj.off || 0); });

    /* всплеск имплантов из ящика */
    impl.forEach((im, i) => {
      const a = 18.55 + i * 0.07, p = pr(t, a, a + 0.85), ang = (i / impl.length) * Math.PI * 2 + 0.5;
      const r = lerp(0, 430 + (i % 2) * 120, eO(p));
      const cx = 540 + Math.cos(ang) * r, cy = 800 + Math.sin(ang) * r * 1.1 - Math.sin(p * Math.PI) * 120;
      T(im, { x: cx - 150, y: cy - 150, r: lerp(-60, 25, p) * (i % 2 ? 1 : -1), s: lerp(0.2, 0.9, eBack(clamp(p * 1.3))) * lerp(1, 0.5, eI(pr(t, a + 0.55, a + 0.85))), o: clamp(p * 5) * (1 - pr(t, a + 0.55, a + 0.85)) });
    });

    /* Flip 3D: кольцо разделов приложения */
    {
      const fa = 19.55, fb = 21.35;
      const prog = lerp(0, 2.6, eIO(pr(t, fa + 0.25, fb - 0.2)));
      const fin = eO(pr(t, fa, fa + 0.45)), fout = eI(pr(t, fb - 0.35, fb));
      const n = flip.length, R = 560;
      flip.forEach(({ n: el, i }) => {
        const th = ((i - prog) / n) * Math.PI * 2;
        const x = Math.sin(th) * R, depth = (Math.cos(th) + 1) / 2;
        el.style.zIndex = String(36 + Math.round(depth * 10));
        T(el, { x: 260 + x * 0.9, y: 340 - (1 - depth) * 60 + (1 - fin) * 500 - fout * 400, ry: -Math.sin(th) * 52, rx: 4, r: -3, s: lerp(0.62, 1.12, depth) * lerp(0.8, 1, fin) * (1 + fout * 0.2), o: clamp(fin * 1.5) * (1 - fout) * lerp(0.55, 1, depth), pp: 2100 });
      });
    }

    drawGlints(t);
    drawCursor(t);
    caps.forEach((c) => drawCap(c, t));

    /* === Сцена 6: финал (21.3-25) === */
    {
      T(flash, { o: Math.max(0, 1 - Math.abs(t - 21.55) / 0.5) * 0.95 });
      const inL = eBack(pr(t, 21.55, 22.35));
      const lb = { x: 250, y: 250 + Math.sin(tb * 1.4) * 9 * (1 - pr(t, 23, 25)), w: 580, h: 580, s: lerp(0.5, 1, inL), r: lerp(-14, 0, eO(pr(t, 21.55, 22.35))), o: clamp(pr(t, 21.55, 21.95)), blur: lerp(14, 0, pr(t, 21.55, 21.95)) };
      T(logo2.l, lb); T(logo2.sh, lb);
      logo2.sh.style.backgroundPosition = `${(1 - eIO(pr(t, 22.3, 23.1))) * 100}% 0`;
      const show = (n, a, rise, extra = {}) => { const p = eBack(pr(t, a, a + 0.5)); T(n, { y: (1 - p) * rise, s: lerp(0.7, 1, p), o: clamp(pr(t, a, a + 0.22)), blur: lerp(10, 0, pr(t, a, a + 0.3)), ...extra }); };
      show(title6, 21.95, 60); show(sub6, 22.2, 50);
      const press = t > 23.62 && t < 23.8 ? 0.95 : 1;
      show(cta6, 22.4, 60, { s: Math.min(press, lerp(0.7, 1, eBack(pr(t, 22.4, 22.9)))) });
    }
    mosaicWave(t, 11.7, 12.35, 1);
    mosaicWave(t, 17.0, 17.65, -1);
  }

  window.seek = seek;
  window.ready = (async () => {
    await document.fonts.load('700 80px "PT Sans"', "Твоя поездка");
    await document.fonts.ready;
    try { const r = await fetch(C + "meta.json"); const m = await r.json(); window.__cells = m.collection || []; } catch (_) { window.__cells = []; }
    await Promise.all([...document.images].map((i) => (i.complete ? Promise.resolve() : new Promise((r) => { i.onload = i.onerror = r; }))));
    await Promise.all([...document.images].map((i) => i.decode().catch(() => {})));
    crops.forEach((c) => c.ready());
    seek(0);
    return true;
  })();
})();
