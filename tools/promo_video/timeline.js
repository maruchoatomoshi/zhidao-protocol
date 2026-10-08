/* Таймлайн ролика. seek(t) -- чистая функция времени: ставит стили всем слоям, ничего не анимирует само.
   Рендер (render.mjs) вызывает seek(i / 30) и снимает кадр. */
(() => {
  const $ = (s) => document.querySelector(s);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const pr = (t, a, b) => clamp((t - a) / (b - a));
  const lerp = (a, b, x) => a + (b - a) * x;
  const eO = (x) => 1 - Math.pow(1 - x, 3);
  const eIO = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const eBack = (x) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
  const win = (t, a, b, fi = 0.3, fo = 0.3) => Math.min(pr(t, a, a + fi), 1 - pr(t, b - fo, b)); // 0..1..0

  /* «Спокойная остановка»: время для декоративного движения замедляется до нуля к концу. */
  const calm = (t) => (t < 23 ? t : 23 + 2 * ((t - 23) / 2) - Math.pow((t - 23) / 2, 2) * 1);

  function put(el, o) {
    const s = el.style;
    const x = o.x ?? 0, y = o.y ?? 0, sc = o.s ?? 1, r = o.r ?? 0;
    s.transform = `translate(${x}px, ${y}px) rotate(${r}deg) scale(${sc})${o.ry ? ` rotateY(${o.ry}deg)` : ""}`;
    if (o.o !== undefined) { s.opacity = String(o.o); s.visibility = o.o <= 0.002 ? "hidden" : "visible"; }
    if (o.w !== undefined) s.width = `${o.w}px`;
    if (o.h !== undefined) s.height = `${o.h}px`;
  }

  /* Рамка экрана: crop = [x, y, w, h] в пикселях снимка, w -- ширина рамки на сцене. */
  function card(el, o) {
    const img = el.querySelector("img");
    const nat = { w: img.naturalWidth, h: img.naturalHeight };
    const [cx, cy, cw, ch] = o.crop;
    const k = o.w / cw;
    const h = ch * k;
    put(el, { x: o.x, y: o.y, s: o.s, r: o.r, o: o.o, w: o.w, h });
    img.style.width = `${nat.w * k}px`;
    img.style.height = `${nat.h * k}px`;
    img.style.left = `${-cx * k}px`;
    img.style.top = `${-cy * k}px`;
    return { k, h };
  }

  /* --- псевдослучайные пузыри и стеклянные квадраты (детерминированно) ---------------------- */
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const bubbles = [];
  function makeBubbles(layer, n, front) {
    for (let i = 0; i < n; i++) {
      const el = document.createElement("div");
      el.className = "bub";
      const size = front ? 24 + rnd() * 70 : 40 + rnd() * 150;
      el.style.width = el.style.height = `${size}px`;
      $(layer).append(el);
      bubbles.push({ el, size, x0: rnd() * 1080, sp: 70 + rnd() * 120, ph: rnd() * 2600, wob: 0.6 + rnd() * 1.1, amp: 14 + rnd() * 40, front });
    }
  }
  makeBubbles("#bubBack", 22, false);
  makeBubbles("#bubFront", 9, true);

  const squares = [];
  [[90, 330, 0, 90], [880, 250, 1, 70], [130, 1130, 1, 60], [900, 1010, 0, 110], [820, 560, 1, 54], [200, 600, 0, 48]].forEach(([x, y, g, size], i) => {
    const el = document.createElement("div");
    el.className = "sq" + (g ? " g" : "");
    el.style.width = el.style.height = `${size}px`;
    $("#sqLayer").append(el);
    squares.push({ el, x, y, ph: i * 1.3 });
  });

  /* --- загрузчик ------------------------------------------------------------------------- */
  const SEG = 14;
  for (let i = 0; i < SEG; i++) $("#bar1").append(document.createElement("i"));
  const barSegs = [...document.querySelectorAll("#bar1 i")];

  /* --- коллекция ------------------------------------------------------------------------- */
  const IMPLANTS = ["biancai", "diplomat", "koi", "jinchan", "qilin", "zhuque"];
  const SLOT = { w: 276, h: 360, gx: 26, gy: 26, x0: 70 + 6 + 30, y0: 340 + 6 + 88 + 28 };
  const slotPos = (i) => ({ x: SLOT.x0 + (i % 3) * (SLOT.w + SLOT.gx), y: SLOT.y0 + Math.floor(i / 3) * (SLOT.h + SLOT.gy) });
  const slots = [], icards = [];
  IMPLANTS.forEach((name, i) => {
    const s = document.createElement("div"); s.className = "slot"; $("#slots").append(s); slots.push(s);
    const c = document.createElement("div"); c.className = "icard";
    c.innerHTML = `<img src="/zhidao_v4/static/app/assets/implants/${name}.webp" alt=""><div class="glint"></div>`;
    $("#icards").append(c); icards.push(c);
  });
  document.querySelectorAll("#slots, #icards, #sqLayer, #bubBack, #bubFront").forEach((n) => { n.style.left = "0"; n.style.top = "0"; });

  /* --- подписи --------------------------------------------------------------------------- */
  function cap(el, a, b, fi = 0.35, fo = 0.3) {
    const v = win(cur, a, b, fi, fo);
    const rise = (1 - eO(pr(cur, a, a + fi))) * 36;
    put(el, { y: rise, s: lerp(0.94, 1, eO(clamp(v))), o: clamp(v) });
  }

  let cur = 0;
  const SCAN = { crop: [60, 243, 1002, 555], w: 960 };

  function seek(t) {
    cur = t;
    const tb = calm(t);

    /* === фоны === */
    put($("#bgNight"), { o: 1 });
    put($("#nightRays"), { o: 0.9 * (1 - pr(t, 3.6, 5)), r: 0 });
    $("#nightRays").style.transform = `rotate(${t * 3}deg)`;
    $("#nightRays").style.transformOrigin = "540px 780px";

    const reveal = eIO(pr(t, 3.55, 5.0));
    const photo = $("#bgPhoto");
    photo.style.clipPath = reveal >= 1 ? "none" : `circle(${reveal * 2300}px at 540px 780px)`;
    photo.style.visibility = reveal <= 0 ? "hidden" : "visible";
    const blur = lerp(0, 9, eIO(pr(t, 7.4, 8.6)));
    const pan = pr(t, 3.6, 22);
    const imgEl = $("#photo");
    imgEl.style.transform = `translate(${lerp(-1750, -2250, pan)}px, 0) scale(${lerp(1.08, 1.32, pan)})`;
    imgEl.style.filter = blur > 0.05 ? `blur(${blur}px) saturate(1.1)` : "saturate(1.1)";
    put($("#veil"), { o: lerp(0, 0.85, eIO(pr(t, 7.4, 8.6))) });

    const skyIn = eIO(pr(t, 21.6, 22.3));
    put($("#bgSky"), { o: skyIn });
    put($("#skyRays"), { o: skyIn * 0.8 });
    $("#skyRays").style.transform = `rotate(${(tb - 21) * 1.2}deg)`;
    $("#skyRays").style.transformOrigin = "200px 100px";

    /* кольцо света на границе раскрытия */
    const ringR = reveal * 2300;
    put($("#ringReveal"), { x: 540 - ringR, y: 780 - ringR, o: reveal > 0 && reveal < 1 ? 0.9 * (1 - reveal * 0.6) : 0 });
    $("#ringReveal").style.width = $("#ringReveal").style.height = `${ringR * 2}px`;

    /* === стеклянные квадраты: запуск и финал === */
    const sqVis = Math.max(win(t, 0.4, 3.9, 0.8, 0.5), win(t, 21.7, 26, 0.7, 0.01));
    squares.forEach((q, i) => {
      const fl = Math.sin(tb * 1.1 + q.ph) * 18;
      put(q.el, { x: q.x, y: q.y + fl, r: Math.sin(tb * 0.7 + q.ph) * 12, s: 0.9 + 0.1 * Math.sin(tb * 0.9 + q.ph), o: clamp(sqVis) * (t < 5 ? 0.9 : 0.8) });
    });

    /* === пузыри === */
    const bubVis = t < 3.6 ? 0.45 : 1;
    const bubOp = t < 4 ? 0.5 * pr(t, 0.5, 1.5) : t > 21.6 ? 1 : 1;
    bubbles.forEach((b) => {
      const L = 2500;
      const y = 2150 - ((tb * b.sp + b.ph) % L);
      const x = b.x0 + Math.sin(tb * b.wob + b.ph) * b.amp - b.size / 2;
      const o = (b.front ? 0.85 : 0.9) * (t < 4 ? bubOp : 1) * bubVis;
      put(b.el, { x, y, o: o * clamp(Math.min((2150 - y) / 150, (y + b.size + 40) / 150)) });
    });

    /* === сцена 1: запуск (0-4) === */
    {
      const inP = eBack(pr(t, 0.2, 1.3));
      const outP = eIO(pr(t, 3.3, 4.2));
      const sc = lerp(0.7, 1, inP) * lerp(1, 1.7, outP);
      const o = clamp(pr(t, 0.2, 0.9)) * (1 - pr(t, 3.5, 4.0));
      const L = { x: 220, y: 470 + Math.sin(tb * 1.6) * 8, w: 640, h: 640 };
      put($("#logo1"), { x: L.x, y: L.y, w: L.w, h: L.h, s: sc, o });
      put($("#sheen1"), { x: L.x, y: L.y, w: L.w, h: L.h, s: sc, o });
      const sweep = (a, b) => (t >= a && t <= b ? 1 - eIO(pr(t, a, b)) : 1.0);
      const p = t < 2.6 ? sweep(1.3, 2.3) : sweep(2.9, 3.7);
      $("#sheen1").style.backgroundPosition = `${p * 100}% 0`;
      put($("#glow1"), { s: lerp(0.6, 1.08, eO(pr(t, 0, 2))) * lerp(1, 1.5, outP), o: 0.9 * clamp(pr(t, 0, 1)) * (1 - pr(t, 3.5, 4.0)) });

      const barO = clamp(pr(t, 0.9, 1.3)) * (1 - pr(t, 3.4, 3.8));
      put($("#bar1"), { y: (1 - eO(pr(t, 0.9, 1.4))) * 30, o: barO });
      const fill = eIO(pr(t, 1.2, 3.3)) * SEG;
      barSegs.forEach((seg, i) => { const v = clamp(fill - i); seg.style.opacity = String(v); });
      cap($("#cap1"), 1.3, 3.9);
    }

    /* === сцена 2: окно в Хайнань (4-8) и сцена 3: экраны (8-13) === */
    {
      // дом: окно выезжает, затем камера наезжает на «Мой день»
      const open = eBack(pr(t, 4.9, 5.7));
      const morph = eIO(pr(t, 7.5, 8.3));
      const crop0 = [0, 0, 1122, 905], crop1 = [0, 600, 1122, 660];
      const crop = crop0.map((v, i) => lerp(v, crop1[i], morph));
      const y = lerp(300, 560, morph);
      const out = eIO(pr(t, 9.4, 10.1));
      const bobS = 1 + 0.03 * pr(t, 8.3, 9.7);
      card($("#cToday"), { crop, w: 920, x: lerp(80, -1250, out), y, s: lerp(0.8, 1, open) * bobS, r: out * -4, o: clamp(pr(t, 4.9, 5.4)) * (1 - pr(t, 10, 10.2)) });
      cap($("#cap2"), 5.4, 7.9);

      // события
      const inE = eIO(pr(t, 9.4, 10.1)), outE = eIO(pr(t, 11.1, 11.8));
      card($("#cEvents"), { crop: [0, 233, 1122, 938], w: 920, x: inE < 1 ? lerp(1250, 80, inE) : lerp(80, -1250, outE), y: 400, s: 1 + 0.03 * pr(t, 10.1, 11.3), r: inE < 1 ? (1 - inE) * 4 : outE * -4, o: clamp(pr(t, 9.4, 9.6)) * (1 - pr(t, 11.9, 12.1)) });

      // кампус
      const inM = eIO(pr(t, 11.1, 11.8)), outM = eIO(pr(t, 12.8, 13.4));
      card($("#cMap"), { crop: [0, 90, 1122, 970], w: 920, x: inM < 1 ? lerp(1250, 80, inM) : lerp(80, -1250, outM), y: 420, s: 1 + 0.03 * pr(t, 11.8, 13), r: inM < 1 ? (1 - inM) * 4 : outM * -4, o: clamp(pr(t, 11.1, 11.3)) * (1 - pr(t, 13.4, 13.5)) });

      cap($("#cap3a"), 8.05, 9.7, 0.3, 0.2);
      cap($("#cap3b"), 9.7, 11.4, 0.3, 0.2);
      cap($("#cap3c"), 11.4, 13.1, 0.3, 0.2);
    }

    /* === сцена 4: игры и REP (13-18) === */
    {
      for (let i = 0; i < 4; i++) {
        const a = 13.1 + i * 0.17;
        const inP = eBack(pr(t, a, a + 0.65));
        const outP = eIO(pr(t, 14.7 + i * 0.05, 15.3 + i * 0.05));
        const x = lerp(1250, i % 2 ? 130 : 90, inP) - outP * 1400;
        put($(`#cv${i}`), { x, y: 280 + i * 262, r: (i % 2 ? 1.4 : -1.4) * (1 - outP * 0.5), s: 1, o: clamp(pr(t, a, a + 0.12)) * (1 - pr(t, 15.2, 15.45)) });
      }
      const inR = eIO(pr(t, 14.8, 15.4)), outR = eIO(pr(t, 16.3, 16.9));
      card($("#cRoyale"), { crop: [0, 150, 1170, 1270], w: 880, x: inR < 1 ? lerp(1250, 100, inR) : lerp(100, -1250, outR), y: 300, s: 1 + 0.025 * pr(t, 15.4, 16.5), r: inR < 1 ? (1 - inR) * 4 : outR * -4, o: clamp(pr(t, 14.8, 15)) * (1 - pr(t, 16.9, 17)) });
      const inP = eIO(pr(t, 16.3, 16.9)), outP = eIO(pr(t, 17.9, 18.5));
      card($("#cRep"), { crop: [0, 0, 1122, 1264], w: 900, x: inP < 1 ? lerp(1250, 90, inP) : lerp(90, -1250, outP), y: 310, s: 1 + 0.025 * pr(t, 16.9, 18), r: inP < 1 ? (1 - inP) * 4 : outP * -4, o: clamp(pr(t, 16.3, 16.5)) * (1 - pr(t, 18.5, 18.6)) });

      cap($("#cap4"), 13.2, 18.2, 0.35, 0.3);
      const words = document.querySelectorAll("#cap4 .w");
      const act = t < 14.85 ? 0 : t < 16.5 ? 1 : 2;
      words.forEach((w, i) => { w.style.opacity = i === act ? "1" : "0.5"; w.style.textShadow = i === act ? "0 0 22px rgba(190,240,255,.95), 0 3px 0 rgba(0,50,130,.55), 0 6px 16px rgba(0,40,110,.6)" : ""; });
    }

    /* === сцена 5: скан кейса и коллекция (18-21.7) === */
    {
      const inC = eBack(pr(t, 18.2, 18.9));
      const outC = eIO(pr(t, 19.75, 20.3));
      const caseY = 470;
      const { k } = card($("#cCase"), { crop: SCAN.crop, w: SCAN.w, x: 60, y: caseY, s: lerp(0.8, 1, inC) * lerp(1, 0.6, outC), o: clamp(pr(t, 18.2, 18.6)) * (1 - pr(t, 19.9, 20.3)) });
      const fx = (cx, cy) => ({ x: (cx - SCAN.crop[0]) * k, y: (cy - SCAN.crop[1]) * k });
      // луч сверху вниз по кейсу
      const scan = pr(t, 18.55, 19.5);
      const topY = (345 - SCAN.crop[1]) * k, botY = (705 - SCAN.crop[1]) * k;
      const by = lerp(topY - 150, botY, eIO(scan));
      put($("#beam"), { y: by, o: scan > 0 && scan < 1 ? 0.95 : 0 });
      // кольца вокруг кейса
      const c = fx(559, 531);
      for (let i = 0; i < 3; i++) {
        const p = pr(t, 18.7 + i * 0.28, 19.7 + i * 0.28);
        const r = lerp(60, 330, eO(p));
        const ring = $(`#ring${i}`);
        ring.style.width = ring.style.height = `${r * 2}px`;
        put(ring, { x: c.x - r, y: c.y - r, o: p > 0 && p < 1 ? 0.85 * (1 - p) : 0 });
      }
      // три шага: связь, скан, сигнал
      [[56, 382], [399, 721], [737, 1062]].forEach(([x0, x1], i) => {
        const a = fx(x0, 720), b = fx(x1, 782);
        const el = $(`#hi${i}`);
        const v = win(t, 18.7 + i * 0.32, 19.5 + i * 0.32, 0.15, 0.4);
        put(el, { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y, o: clamp(v) });
      });

      // альбом
      const albIn = eBack(pr(t, 19.45, 20.2));
      const albOut = eIO(pr(t, 21.35, 21.95));
      put($("#album"), { y: (1 - albIn) * 420, s: lerp(1, 0.94, albOut), o: clamp(pr(t, 19.45, 19.8)) * (1 - albOut) });
      slots.forEach((s, i) => {
        const p = slotPos(i);
        put(s, { x: p.x, y: p.y + (1 - albIn) * 420, s: lerp(1, 0.94, albOut), o: clamp(pr(t, 19.6 + i * 0.04, 19.9 + i * 0.04)) * (1 - albOut) });
      });
      // карточки вылетают из кейса и садятся в слоты
      const origin = { x: 540 - SLOT.w / 2, y: caseY + 270 - SLOT.h / 2 };
      icards.forEach((el, i) => {
        const a = 19.65 + i * 0.09, b = a + 0.7;
        const p = pr(t, a, b);
        const dst = slotPos(i);
        const e = eO(p);
        const arc = Math.sin(p * Math.PI) * -150;
        const x = lerp(origin.x, dst.x, e) + Math.sin(i * 2.1) * 90 * (1 - e);
        const y = lerp(origin.y, dst.y, e) + arc;
        const land = Math.sin(clamp((p - 0.82) / 0.18) * Math.PI);
        const sc = lerp(0.28, 1, eBack(clamp(p * 1.25))) + land * 0.05;
        const ry = (1 - eO(clamp(p * 1.3))) * (i % 2 ? 70 : -70);
        const rot = (1 - e) * (i % 2 ? 22 : -22);
        put(el, { x, y, s: sc, r: rot, ry, o: clamp(p * 6) * (1 - albOut) });
        const g = el.querySelector(".glint");
        const gp = pr(t, b - 0.05, b + 0.6);
        g.style.opacity = gp > 0 && gp < 1 ? "1" : "0";
        g.style.backgroundPosition = `${(1 - gp) * 100}% 0`;
      });
      cap($("#cap5"), 18.15, 21.55, 0.35, 0.3);
    }

    /* === сцена 6: финал (21.6-25) === */
    {
      const flash = Math.max(0, 1 - Math.abs(t - 21.85) / 0.45);
      put($("#flash"), { o: flash * 0.95 });
      const inL = eBack(pr(t, 21.8, 22.5));
      const L = { x: 250, y: 310 + Math.sin(tb * 1.4) * 9 * (1 - pr(t, 23, 25)), w: 580, h: 580 };
      const o = clamp(pr(t, 21.8, 22.2));
      put($("#logo2"), { x: L.x, y: L.y, w: L.w, h: L.h, s: lerp(0.8, 1, inL), o });
      put($("#sheen2"), { x: L.x, y: L.y, w: L.w, h: L.h, s: lerp(0.8, 1, inL), o });
      const sp = pr(t, 22.3, 23.1);
      $("#sheen2").style.backgroundPosition = `${(1 - eIO(sp)) * 100}% 0`;
      const showT = (id, a, rise) => { const p = eBack(pr(cur, a, a + 0.45)); put($(id), { y: (1 - p) * rise, s: lerp(0.9, 1, p), o: clamp(pr(cur, a, a + 0.25)) }); };
      showT("#title6", 22.15, 50);
      showT("#sub6", 22.35, 40);
      showT("#cta6", 22.55, 50);
    }
  }

  window.seek = seek;
  window.ready = (async () => {
    await document.fonts.load('700 80px "PT Sans"', "Твоя поездка");
    await document.fonts.load('400 40px "PT Sans"', "Твоя поездка");
    await document.fonts.ready;
    await Promise.all([...document.images].map((i) => (i.complete ? Promise.resolve() : new Promise((r) => { i.onload = i.onerror = r; }))));
    await Promise.all([...document.images].map((i) => i.decode().catch(() => {})));
    seek(0);
    return true;
  })();
})();
