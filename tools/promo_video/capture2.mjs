/* Вторая съёмка: целые экраны телефона (шапка, окно игры, нижняя панель) для рамок с наклоном, Flip 3D и склеек.
   Стенд A (8795): student2 с коллекцией имплантов и тремя попытками; student1 -- «живой» в раунде Протокола 60. */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(here, "captures");
fs.mkdirSync(OUT, { recursive: true });
const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--force-color-profile=srgb", "--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });

async function open(user, base = "http://127.0.0.1:8795") {
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  await page.goto(`${base}/app/?design=xp`, { waitUntil: "domcontentloaded" });
  const status = await page.evaluate(async (u) => (await fetch("/api/v4/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: u, password: "preview-only-passphrase" }) })).status, user);
  if (status !== 200) throw new Error(`вход ${user}: ${status}`);
  await page.goto(`${base}/app/?design=xp`, { waitUntil: "domcontentloaded" });
  await sleep(6000);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "light";
    // CSP не пускает инлайновые <style>, а CSSOM-правка стиля элемента проходит.
    document.querySelectorAll(".terminal-footer").forEach((n) => n.style.setProperty("display", "none", "important"));
  });
  return page;
}
const snap = async (page, name) => { await page.screenshot({ path: path.join(OUT, `${name}.png`) }); console.log("снято", name); };
const show = async (page, screen, wait = 3500) => { await page.evaluate((s) => window.showScreen(s), screen); await sleep(wait); };
const openGame = async (page, key, wait = 4500) => {
  await show(page, "games", 1500);
  await page.evaluate((k) => document.querySelector(`.catalog-tile[data-key="${k}"]`)?.click(), key);
  await sleep(wait);
};

const P = await open("case.student2");
// Размеры шапки и нижней панели нужны композиции, чтобы собрать «прокручиваемый» экран из полос.
const meta = await P.evaluate(() => {
  const r = (sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, height: b.height }; };
  return { viewport: [innerWidth, innerHeight], header: r(".app-header") || r("header"), dock: r(".app-dock") };
});
console.log("meta", JSON.stringify(meta));
fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 2));

for (const s of ["schedule", "games", "rating", "cases", "collection", "implants", "shop", "more", "meet", "workshop", "profile"]) {
  await show(P, s); await snap(P, `v-${s}`);
}
await show(P, "collection");
const cells = await P.evaluate(() => {
  const out = [];
  for (const name of ["Цайшэнь", "Гуаньси", "Цзинь", "Кои", "Панда", "Цилинь", "Тайцзи", "Терракота", "Чжуцюэ"]) {
    const hit = [...document.querySelectorAll("*")].filter((e) => e.children.length === 0 && e.textContent.trim().startsWith(name))[0];
    let n = hit;
    while (n && n.parentElement && !(n.getBoundingClientRect().width > 85 && n.getBoundingClientRect().height > 85)) n = n.parentElement;
    if (n) { const b = n.getBoundingClientRect(); out.push({ name, x: b.left, y: b.top, w: b.width, h: b.height }); }
  }
  return out;
});
meta.collection = cells; fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify(meta, null, 2));
await show(P, "campus-model", 12000); await snap(P, "v-model");
await show(P, "campus-map", 9000); await snap(P, "v-map");
for (const k of ["agent", "capture", "table", "zombie", "sabotage"]) { await openGame(P, k); await snap(P, `g-${k}`); }
await openGame(P, "market", 4000);
await snap(P, "g-market-door");
await P.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => /выйти на рынок/i.test(x.textContent)); b?.click(); });
await sleep(5000); await snap(P, "g-market");
await P.close();

const Q = await open("case.student1", "http://127.0.0.1:8797");
await openGame(Q, "royale", 9000); await Q.evaluate(() => document.activeElement && document.activeElement.blur()); await sleep(600); await snap(Q, "g-royale");
await Q.close();
await browser.close();
