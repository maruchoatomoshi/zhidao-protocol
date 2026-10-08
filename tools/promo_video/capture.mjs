/* Съёмка реальных экранов приложения для ролика. Ничего не рисуем и не подставляем:
   интерфейс -- настоящий, данные -- с локальных тестовых стендов (README.md).
   Стенд A (8795): рынок открыт, идёт раунд Протокола 60, лобби Зомби и Саботажа.
   Стенд B (8796): один безымянный участник -- для экрана REP без чужих имён и чисел. */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(here, "captures");
fs.mkdirSync(OUT, { recursive: true });
const EDGE = process.env.EDGE_PATH || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--force-color-profile=srgb"] });

async function open(base, user) {
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  await page.goto(`${base}/app/?design=xp`, { waitUntil: "domcontentloaded" });
  const status = await page.evaluate(async (u) => {
    const r = await fetch("/api/v4/auth/login", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ username: u, password: "preview-only-passphrase" }) });
    return r.status;
  }, user);
  if (status !== 200) throw new Error(`вход ${user}: ${status}`);
  await page.goto(`${base}/app/?design=xp`, { waitUntil: "domcontentloaded" });
  await sleep(6000);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "light";
    const style = document.createElement("style");
    // Служебные плашки, не относящиеся к экрану: нижняя панель и строка «Личный контур».
    style.textContent = ".app-dock, .terminal-footer { visibility: hidden !important; }";
    document.head.append(style);
  });
  return page;
}

async function shot(page, screen, selector, name, wait = 7000, before) {
  await page.evaluate((s) => window.showScreen(s), screen);
  await sleep(wait);
  if (before) await page.evaluate(before);
  const el = await page.$(selector);
  if (!el) throw new Error(`нет элемента ${selector} (${name})`);
  await el.evaluate((node) => node.scrollIntoView({ block: "start" }));
  await sleep(600);
  const file = path.join(OUT, `${name}.png`);
  await el.screenshot({ path: file });
  const box = await el.boundingBox();
  console.log("снято", name, Math.round(box.width * 3), "x", Math.round(box.height * 3));
}

const A = await open("http://127.0.0.1:8795", "case.student1");
// День, а не ночь: баннер «Сегодня» в этот момент снимается при дневном небе.
await shot(A, "schedule", '[data-screen="schedule"]', "today", 6000, () => { const c = document.querySelector(".journey-card"); if (c) c.dataset.phase = "day"; });
await shot(A, "games", '[data-screen="games"]', "events", 7000);
await shot(A, "campus-map", '[data-screen="campus-map"] .campus-map', "map", 9000);
await shot(A, "cases", '[data-screen="cases"]', "cases", 7000);
// Игровой экран: открываем плитку Протокола 60 и ждём вопрос.
await A.evaluate(() => window.showScreen("games"));
await sleep(3000);
await A.evaluate(() => document.querySelector('.catalog-tile[data-key="royale"]')?.click());
await sleep(9000);
{
  const win = await A.$("#royaleWindow");
  if (!win) throw new Error("окно Протокола 60 не открылось");
  await win.evaluate((node) => node.scrollIntoView({ block: "start" }));
  await sleep(800);
  await win.screenshot({ path: path.join(OUT, "royale.png") });
  const box = await win.boundingBox();
  console.log("снято royale", Math.round(box.width * 3), "x", Math.round(box.height * 3));
}
await A.close();

const B = await open("http://127.0.0.1:8796", "promo.one");
await shot(B, "rating", '[data-screen="rating"] .rep-season', "rep", 9000);
await B.close();
await browser.close();
