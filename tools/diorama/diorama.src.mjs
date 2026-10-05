import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/* Макет кампуса: низкополигональная модель Blender v02 в стеклянном колпаке.
   Это иллюстрация, а не геодезическая карта -- настоящая карта кампуса лежит
   отдельно (campus-map.js). Окружение сцены обрезается квадратом, море и горы
   за его пределами не рисуются. */

// Границы по реальным габаритам модели: здания x -146..210, z -98..110, море
// севернее z -112. Центр и полуразмеры прямоугольного колпака.
const CX = 32, CZ = -14, HX = 188, HZ = 136;
const WORLD_CLIP = [
  new THREE.Plane(new THREE.Vector3(1, 0, 0), HX - CX),
  new THREE.Plane(new THREE.Vector3(-1, 0, 0), CX + HX),
  new THREE.Plane(new THREE.Vector3(0, 0, 1), HZ - CZ),
  new THREE.Plane(new THREE.Vector3(0, 0, -1), CZ + HZ),
];

const MOODS = {
  morning: { sun: 0xffd9a8, sunI: 2.6, sky: 0xbfe0f2, ground: 0xf3e2c8, hemiI: 1.0, fog: 0xe9f1f0, dir: [-120, 90, 80], win: 0.0, exposure: 1.0 },
  day:     { sun: 0xfff6e2, sunI: 3.2, sky: 0xcfe9ff, ground: 0xdfe8d0, hemiI: 1.15, fog: 0xe3f0f8, dir: [90, 160, 60], win: 0.0, exposure: 1.05 },
  evening: { sun: 0xff9a52, sunI: 2.4, sky: 0xf2b88a, ground: 0x8a6a74, hemiI: 0.85, fog: 0xf0c9a8, dir: [160, 50, -40], win: 0.9, exposure: 1.0 },
  night:   { sun: 0xa9bcff, sunI: 0.9, sky: 0x6580c4, ground: 0x253257, hemiI: 0.7, fog: 0x1b2540, dir: [-80, 120, -60], win: 1.9, exposure: 1.0 },
};

const VIEWS = {
  overview: { pos: [CX + 300, 330, CZ + 430], target: [CX, 6, CZ + 8] },
  plaza: { pos: [70, 52, 150], target: [8, 10, -8] },
  dorms: { pos: [250, 110, 190], target: [112, 12, 50] },
  sports: { pos: [-40, 70, 100], target: [-95, 2, -38] },
  coast: { pos: [60, 48, -190], target: [30, 2, -60] },
};

function lerp(a, b, t) { return a + (b - a) * t; }

export async function mount(container, options) {
  const opts = Object.assign({ model: "", motion: true, onProgress: null, skyTarget: null }, options);
  const skyEl = opts.skyTarget || container;
  const canvas = document.createElement("canvas");
  canvas.className = "diorama-canvas";
  container.append(canvas);

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.localClippingEnabled = true;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const small = Math.min(container.clientWidth || 800, window.innerWidth) < 600;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 5, 2000);
  camera.position.set(...VIEWS.overview.pos);
  const fit = () => {};

  const controls = new OrbitControls(camera, canvas);
  controls.target.set(...VIEWS.overview.target);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 60;
  controls.maxDistance = 720;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.enablePan = false;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 0.35;

  const hemi = new THREE.HemisphereLight(0xffffff, 0xffffff, 1);
  const sun = new THREE.DirectionalLight(0xffffff, 3);
  sun.castShadow = true;
  sun.shadow.mapSize.set(small ? 1024 : 2048, small ? 1024 : 2048);
  const sc = sun.shadow.camera;
  sc.left = -HX * 1.15; sc.right = HX * 1.15; sc.top = HX * 1.15; sc.bottom = -HX * 1.15;
  sc.near = 10; sc.far = 700;
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.6;
  scene.add(hemi, sun, sun.target);

  // Основание и колпак: плита, тонкий кант и стеклянный короб.
  const plinth = new THREE.Mesh(
    new THREE.BoxGeometry(HX * 2 + 26, 16, HZ * 2 + 26),
    new THREE.MeshStandardMaterial({ color: 0x2a2f38, roughness: 0.55, metalness: 0.2 }));
  plinth.position.set(CX, -9.2, CZ);
  plinth.receiveShadow = true;
  const rim = new THREE.Mesh(
    new THREE.BoxGeometry(HX * 2 + 8, 3, HZ * 2 + 8),
    new THREE.MeshStandardMaterial({ color: 0xcfd6dc, roughness: 0.3, metalness: 0.6 }));
  rim.position.set(CX, -2.4, CZ);
  const caseHeight = 120;
  const glass = new THREE.Mesh(
    new THREE.BoxGeometry(HX * 2 + 4, caseHeight, HZ * 2 + 4),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.05, depthWrite: false, side: THREE.DoubleSide, fog: false }));
  glass.position.set(CX, caseHeight / 2 - 1, CZ);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(glass.geometry),
    new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55 }));
  edges.position.copy(glass.position);
  // Подложка цвета травы: в модели земля нарезана кусками, и между ними
  // иначе видно плиту основания.
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(HX * 2, HZ * 2),
    new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(0.18, 0.4, 0.035, THREE.LinearSRGBColorSpace), roughness: 0.9 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(CX, -0.5, CZ);
  ground.receiveShadow = true;
  scene.add(plinth, rim, ground, glass, edges);

  const windowMats = [];
  const gltf = await new Promise((resolve, reject) => {
    new GLTFLoader().load(opts.model, resolve, (e) => { if (opts.onProgress && e.total) opts.onProgress(e.loaded / e.total); }, reject);
  });
  const model = gltf.scene;
  model.traverse((obj) => {
    if (!obj.isMesh) return;
    obj.castShadow = true;
    obj.receiveShadow = true;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    mats.forEach((m) => {
      m.clippingPlanes = WORLD_CLIP;
      m.clipShadows = true;
      m.side = THREE.DoubleSide;
      if (/glass|window/i.test(m.name)) {
        m.emissive = new THREE.Color(0xffd27a);
        m.emissiveIntensity = 0;
        windowMats.push(m);
      }
    });
  });
  scene.add(model);

  let mood = "day";
  let moodFrom = null;
  let moodT = 1;
  const cur = { sunI: 3, hemiI: 1, win: 0, exposure: 1, sun: new THREE.Color(), sky: new THREE.Color(), ground: new THREE.Color(), fog: new THREE.Color(), dir: new THREE.Vector3() };

  function applyMood(k) {
    const m = MOODS[k];
    cur.sun.set(m.sun); cur.sky.set(m.sky); cur.ground.set(m.ground); cur.fog.set(m.fog);
    cur.dir.set(...m.dir);
    cur.sunI = m.sunI; cur.hemiI = m.hemiI; cur.win = m.win; cur.exposure = m.exposure;
    paint();
  }
  function paint() {
    sun.color.copy(cur.sun); sun.intensity = cur.sunI;
    sun.position.set(CX + cur.dir.x, cur.dir.y, CZ + cur.dir.z);
    sun.target.position.set(CX, 0, CZ); sun.target.updateMatrixWorld();
    hemi.color.copy(cur.sky); hemi.groundColor.copy(cur.ground); hemi.intensity = cur.hemiI;
    scene.fog = new THREE.Fog(cur.fog, 520, 1400);
    renderer.toneMappingExposure = cur.exposure;
    windowMats.forEach((m) => { m.emissiveIntensity = cur.win; });
    glass.material.color.copy(cur.sky).lerp(new THREE.Color(0xffffff), 0.6);
    edges.material.color.copy(cur.sky).lerp(new THREE.Color(0xffffff), 0.7);
    skyEl.style.setProperty("--diorama-sky", "#" + cur.sky.getHexString());
    skyEl.style.setProperty("--diorama-fog", "#" + cur.fog.getHexString());
  }
  function setMood(k) {
    if (!MOODS[k] || k === mood) return;
    const from = { sunI: cur.sunI, hemiI: cur.hemiI, win: cur.win, exposure: cur.exposure, sun: cur.sun.clone(), sky: cur.sky.clone(), ground: cur.ground.clone(), fog: cur.fog.clone(), dir: cur.dir.clone() };
    mood = k;
    const to = MOODS[k];
    const toC = { sun: new THREE.Color(to.sun), sky: new THREE.Color(to.sky), ground: new THREE.Color(to.ground), fog: new THREE.Color(to.fog), dir: new THREE.Vector3(...to.dir) };
    moodFrom = { from, to, toC };
    moodT = opts.motion ? 0 : 1;
    if (!opts.motion) finishMood();
    wake();
  }
  function finishMood() {
    const { to, toC } = moodFrom;
    cur.sun.copy(toC.sun); cur.sky.copy(toC.sky); cur.ground.copy(toC.ground); cur.fog.copy(toC.fog); cur.dir.copy(toC.dir);
    cur.sunI = to.sunI; cur.hemiI = to.hemiI; cur.win = to.win; cur.exposure = to.exposure;
    moodFrom = null;
    paint();
  }
  function stepMood(dt) {
    if (!moodFrom) return;
    moodT = Math.min(1, moodT + dt / 0.9);
    const e = moodT * moodT * (3 - 2 * moodT);
    const { from, to, toC } = moodFrom;
    cur.sun.copy(from.sun).lerp(toC.sun, e); cur.sky.copy(from.sky).lerp(toC.sky, e);
    cur.ground.copy(from.ground).lerp(toC.ground, e); cur.fog.copy(from.fog).lerp(toC.fog, e);
    cur.dir.copy(from.dir).lerp(toC.dir, e);
    cur.sunI = lerp(from.sunI, to.sunI, e); cur.hemiI = lerp(from.hemiI, to.hemiI, e);
    cur.win = lerp(from.win, to.win, e); cur.exposure = lerp(from.exposure, to.exposure, e);
    paint();
    if (moodT >= 1) finishMood();
  }

  // На узком экране отъезжаем дальше, чтобы макет влезал по ширине.
  const viewScale = () => (camera.aspect < 1.5 ? Math.min(3, 1.5 / camera.aspect) : 1);
  let flight = null;
  function setView(k) {
    const v = VIEWS[k];
    if (!v) return;
    const target = new THREE.Vector3(...v.target);
    const pos = new THREE.Vector3(...v.pos);
    pos.sub(target).multiplyScalar(viewScale()).add(target);
    if (!opts.motion) {
      camera.position.copy(pos); controls.target.copy(target); controls.update(); wake(); return;
    }
    flight = { t: 0, p0: camera.position.clone(), p1: pos, t0: controls.target.clone(), t1: target };
    wake();
  }
  function stepFlight(dt) {
    if (!flight) return;
    flight.t = Math.min(1, flight.t + dt / 1.1);
    const e = flight.t * flight.t * (3 - 2 * flight.t);
    camera.position.lerpVectors(flight.p0, flight.p1, e);
    controls.target.lerpVectors(flight.t0, flight.t1, e);
    if (flight.t >= 1) flight = null;
  }

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w < 2 || h < 2) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.fov = w / h < 0.9 ? 44 : 32;
    camera.updateProjectionMatrix();
    wake();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(container);

  let raf = 0;
  let last = performance.now();
  let idleSince = performance.now();
  let visible = true;
  const io = new IntersectionObserver((entries) => { visible = entries[0].isIntersecting; if (visible) wake(); });
  io.observe(container);
  controls.addEventListener("start", () => { controls.autoRotate = false; wake(); });
  controls.addEventListener("change", wake);

  function wake() {
    idleSince = performance.now();
    if (!raf && visible && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(frame); }
  }
  function frame(now) {
    raf = 0;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    stepFlight(dt);
    stepMood(dt);
    controls.update();
    renderer.render(scene, camera);
    const busy = flight || moodFrom || controls.autoRotate || now - idleSince < 1200;
    if (busy && visible && !document.hidden) raf = requestAnimationFrame(frame);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });

  applyMood("day");
  resize();
  setView("overview");
  wake();

  return {
    setMood, setView,
    tick(dt) { stepFlight(dt); stepMood(dt); controls.update(); renderer.render(scene, camera); },
    setSpin(on) { controls.autoRotate = Boolean(on) && opts.motion; wake(); },
    dispose() {
      cancelAnimationFrame(raf); raf = 0; ro.disconnect(); io.disconnect(); controls.dispose();
      renderer.dispose(); canvas.remove();
    },
  };
}

window.ZhidaoDiorama = { mount };
