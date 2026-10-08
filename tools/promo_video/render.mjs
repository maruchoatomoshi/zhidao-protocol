/* Рендер ролика: HTML-композиция (index.html + timeline.js) -> кадры 1080x1920 через Edge -> MP4 25 с, 30 к/с.
   Использование:
     node render.mjs                      полный рендер в out/ZHIDAO-promo-25s.mp4
     node render.mjs --keys 0.5,2,3.5     только PNG-кадры этих секунд в out/keys/ (для проверки) */
import puppeteer from "puppeteer-core";
import ffmpegPath from "ffmpeg-static";
import { spawn } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const OUT = path.join(here, "out");
fs.mkdirSync(OUT, { recursive: true });
const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const FPS = 30, SECONDS = 25, W = 1080, H = 1920;
const keysArg = process.argv.indexOf("--keys");
const keys = keysArg > 0 ? process.argv[keysArg + 1].split(",").map(Number) : null;

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".json": "application/json" };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let file = path.join(root, rel.startsWith("/tools/promo_video/") ? rel : rel);
  // Ролик лежит в tools/promo_video, но ссылается и на ресурсы приложения от корня репозитория.
  if (rel === "/" || rel === "/index.html") file = path.join(here, "index.html");
  else if (!rel.startsWith("/zhidao_v4/") && !rel.startsWith("/tools/")) file = path.join(here, rel);
  if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end("not found"); return; }
  res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await puppeteer.launch({ executablePath: EDGE, headless: true, args: ["--no-sandbox", "--force-color-profile=srgb", "--hide-scrollbars", "--font-render-hinting=none"] });
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
page.on("pageerror", (e) => console.error("pageerror:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.error("console:", m.text()); });
await page.goto(`${base}/`, { waitUntil: "networkidle0" });
await page.evaluate(() => window.ready);

if (keys) {
  fs.rmSync(path.join(OUT, "keys"), { recursive: true, force: true });
  fs.mkdirSync(path.join(OUT, "keys"), { recursive: true });
  for (const t of keys) {
    await page.evaluate((x) => window.seek(x), t);
    await page.screenshot({ path: path.join(OUT, "keys", `t${String(Math.round(t * 100)).padStart(5, "0")}.png`) });
    console.log("кадр", t);
  }
} else {
  const mp4 = path.join(OUT, "ZHIDAO-promo-25s.mp4");
  const ff = spawn(ffmpegPath, ["-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", "-r", String(FPS), mp4], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((r) => ff.on("close", r));
  const total = FPS * SECONDS;
  const started = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate((x) => window.seek(x), i / FPS);
    const buf = await page.screenshot({ type: "jpeg", quality: 97 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (i % 50 === 0) console.log(`кадр ${i}/${total}  ${Math.round((Date.now() - started) / 1000)} с`);
  }
  ff.stdin.end();
  await done;
  console.log("готово:", mp4);
}
await browser.close();
server.close();
