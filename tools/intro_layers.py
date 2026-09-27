"""Слои заставки: разрезает логотип дракона на части для анимации.

Логотип — одна плоская картинка (assets/zhidao-dragon-logo.png). Чтобы
заставка двигала дракона, надпись и квадраты отдельно, генератор вырезает их
в собственные слои, а под ними дорисовывает шар (фон), иначе при движении
слоя на его месте была бы дыра:

- dragon — дракон с жемчужиной: GrabCut по серебру в зоне головы;
- text   — надпись ZHIDAO PROTOCOL: серебро букв плюс их тёмная обводка;
- pix    — белые «пиксели» слева от Z;
- glass  — два стеклянных квадрата справа;
- plate  — шар без всего этого; дыры заполнены размытием от краёв, а обод
  шара восстановлен по кругу (в полярных координатах) от чистых участков;
- logo   — исходный логотип целиком: в конце заставки подменяет слои, так что
  последний кадр в точности равен логотипу, а швы слоёв не видны никогда.

Рядом пишется intro-layers.css — где каждый слой лежит внутри квадрата
логотипа, в процентах. Руками эти файлы не правят: перезапуск генератора
сотрёт правки.

Нужны opencv-python-headless, scipy, numpy и Pillow — только для генерации;
приложению и тестам они не нужны:

    python tools/intro_layers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "zhidao_v4/static/app"
SOURCE = APP / "assets/zhidao-dragon-logo.png"
TARGET = APP / "assets/intro"
CSS = APP / "intro-layers.css"

N = 800                      # сторона рабочего квадрата, px
CENTER = (0.499, 0.500)      # центр шара, доля стороны (измерено по альфе)
DISC_R = 0.485               # радиус шара с ободом
QUALITY = 88
ORDER = ("plate", "dragon", "pix", "text", "glass")


def build():
    import cv2
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    src = np.asarray(Image.open(SOURCE).convert("RGBA").resize((N, N), Image.LANCZOS))
    rgb8, al8 = src[..., :3].copy(), src[..., 3]
    yy, xx = np.mgrid[0:N, 0:N] / N
    hsv = cv2.cvtColor(rgb8, cv2.COLOR_RGB2HSV).astype(float) / 255
    sat, val = hsv[..., 1], hsv[..., 2]
    dist = np.hypot(xx - CENTER[0], yy - CENTER[1])

    # --- дракон: GrabCut, затравки — серебро в зоне головы и точки на теле ---
    old = np.hypot(xx - 0.49, yy - 0.505)
    mask = np.full((N, N), cv2.GC_PR_BGD, np.uint8)
    mask[al8 < 20] = cv2.GC_BGD
    zone = (xx > 0.22) & (xx < 0.88) & (yy < 0.67)
    silver = (sat < 0.28) & (val > 0.5)
    rim = (old > 0.40) & (old < 0.47)
    horn = (yy < 0.27) & (xx > 0.5)
    mask[zone & silver & ~(rim & ~horn)] = cv2.GC_PR_FGD
    mask[(sat > 0.5) & (val > 0.5) & ~zone] = cv2.GC_BGD
    mask[(xx < 0.4) & (yy < 0.36) & (xx + yy < 0.62)] = cv2.GC_BGD   # солнечный блик
    for x, y, r in [(0.43, 0.40, 0.05), (0.335, 0.53, 0.06), (0.52, 0.47, 0.04), (0.55, 0.58, 0.03),
                    (0.30, 0.42, 0.025), (0.47, 0.33, 0.02), (0.62, 0.11, 0.01), (0.57, 0.22, 0.015)]:
        mask[np.hypot(xx - x, yy - y) < r] = cv2.GC_FGD
    mask[yy > 0.68] = cv2.GC_BGD
    cv2.setRNGSeed(7)
    cv2.grabCut(cv2.cvtColor(rgb8, cv2.COLOR_RGB2BGR), mask, None,
                np.zeros((1, 65)), np.zeros((1, 65)), 6, cv2.GC_INIT_WITH_MASK)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    dragon = np.zeros_like(fg)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 400:
            dragon[lab == i] = 255
    bluish = (rgb8[..., 2].astype(int) - rgb8[..., 0].astype(int)) > 28
    dragon[(xx > 0.64) & (xx < 0.84) & (yy > 0.09) & (yy < 0.24) & bluish] = 0   # осколок неба между рогами
    dragon = cv2.morphologyEx(dragon, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # --- надпись: серебро букв, дорастить в тёмную обводку, залить дыры ---
    band = (xx > 0.17) & (xx < 0.9) & (yy > 0.685) & (yy < 0.9) & (old < 0.45)
    core = ((sat < 0.3) & (val > 0.55) & band).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(core)
    core = np.isin(lab, [i for i in range(1, n) if st[i, 4] >= 12]).astype(np.uint8)
    grown = core.copy()
    for _ in range(6):
        d = cv2.dilate(grown, np.ones((3, 3), np.uint8))
        grown = np.where((d > 0) & ((val < 0.5) | (core > 0)), 1, grown).astype(np.uint8)
    grown = cv2.dilate(grown, np.ones((3, 3), np.uint8))
    text = ndimage.binary_fill_holes(grown).astype(np.uint8) * 255

    # --- пиксели слева от Z ---
    p = ((xx > 0.1) & (xx < 0.32) & (yy > 0.59) & (yy < 0.75) & (sat < 0.3) & (val > 0.72)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(p)
    pix = np.zeros_like(p)
    for i in range(1, n):
        if st[i, 4] > 20 and max(st[i, 2], st[i, 3]) < 0.05 * N:
            pix[lab == i] = 255
    pix = cv2.dilate(pix, np.ones((3, 3), np.uint8))
    text[pix > 0] = 0

    # --- стеклянные квадраты ---
    glass = np.zeros((N, N), np.uint8)
    cv2.rectangle(glass, (int(.814 * N), int(.425 * N)), (int(.918 * N), int(.523 * N)), 255, -1)
    cv2.rectangle(glass, (int(.884 * N), int(.352 * N)), (int(.967 * N), int(.458 * N)), 255, -1)
    glass[al8 < 128] = 0

    base = {"dragon": dragon, "text": text, "pix": pix, "glass": glass}
    kernel = lambda k: np.ones((k, k), np.uint8)  # noqa: E731
    # Слой несёт свою обводку; дыра под ним — с запасом.
    layer = {k: cv2.dilate(m, kernel({"dragon": 3, "text": 7, "pix": 3, "glass": 3}[k])) for k, m in base.items()}
    holes = {k: cv2.dilate(m, kernel({"dragon": 7, "text": 17, "pix": 7, "glass": 5}[k])) for k, m in base.items()}
    horns = (yy < 0.3) & (xx > 0.48)   # светлый кант рогов у обода тоньше маски
    holes["dragon"] = np.where(horns, cv2.dilate(holes["dragon"], kernel(11)), holes["dragon"])
    hole = np.zeros((N, N), np.uint8)
    for m in holes.values():
        hole |= (m > 0).astype(np.uint8)
    hole = cv2.dilate(hole, kernel(7))

    # --- фон: заполнение пирамидой (push-pull) + обод по кругу ---
    rgb = rgb8.astype(np.float32) / 255
    al = al8.astype(np.float32) / 255
    known = ((hole == 0) & (al > 0.98)).astype(np.float32)

    def pushpull(img, w):
        if min(img.shape[:2]) <= 2:
            s = (img * w[..., None]).sum((0, 1)) / max(w.sum(), 1e-6)
            return np.broadcast_to(s, img.shape).copy()
        h, wd = img.shape[:2]
        size = ((wd + 1) // 2, (h + 1) // 2)
        small_wi = cv2.resize(img * w[..., None], size, interpolation=cv2.INTER_AREA)
        small_w = cv2.resize(w, size, interpolation=cv2.INTER_AREA)
        small = np.where(small_w[..., None] > 1e-6, small_wi / np.maximum(small_w[..., None], 1e-6), 0)
        up = cv2.resize(pushpull(small, np.clip(small_w * 4, 0, 1)), (wd, h), interpolation=cv2.INTER_LINEAR)
        return img * w[..., None] + up * (1 - w[..., None])

    fill = pushpull(rgb.copy(), known)
    c, radius, angles = (CENTER[0] * N, CENTER[1] * N), 0.5 * N, 1440
    polar = cv2.warpPolar(np.dstack([rgb, known]).astype(np.float32), (int(radius), angles), c, radius,
                          cv2.WARP_POLAR_LINEAR)
    prgb, pk = polar[..., :3], polar[..., 3]
    ang = np.arange(angles)
    for rr in range(int(0.40 * N), min(int(0.49 * N), polar.shape[1])):
        ok = pk[:, rr] > 0.99
        if ok.sum() < 10 or ok.all():
            continue
        for ch in range(3):
            v = prgb[:, rr, ch]
            prgb[~ok, rr, ch] = np.interp(ang[~ok], np.concatenate([ang[ok] - angles, ang[ok], ang[ok] + angles]),
                                          np.concatenate([v[ok]] * 3))
    ring_fill = cv2.warpPolar(prgb, (N, N), c, radius, cv2.WARP_POLAR_LINEAR + cv2.WARP_INVERSE_MAP)
    ring = cv2.GaussianBlur(((dist > 0.405) & (dist < 0.49)).astype(np.float32), (0, 0), 3)[..., None]
    grain = np.random.default_rng(7).normal(0, 0.008, (N, N, 1)).astype(np.float32)
    soft = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 2)[..., None]
    plate = rgb * (1 - soft) + np.clip(fill * (1 - ring) + ring_fill * ring + grain, 0, 1) * soft
    plate_a = np.where((hole > 0) & (dist > DISC_R + 0.002), 0, al).astype(np.float32)
    plate_a = np.minimum(plate_a, cv2.GaussianBlur(plate_a, (0, 0), 0.8) + (dist < DISC_R - 0.003))

    TARGET.mkdir(parents=True, exist_ok=True)
    boxes = {}

    def save(name, colour, alpha, crop=True):
        arr = np.dstack([np.clip(colour, 0, 1), np.clip(alpha, 0, 1)])
        img = Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA")
        box = img.getbbox() if crop else (0, 0, N, N)
        box = (max(box[0] - 2, 0), max(box[1] - 2, 0), min(box[2] + 2, N), min(box[3] + 2, N))
        img.crop(box).save(TARGET / f"{name}.webp", quality=QUALITY, method=6)
        boxes[name] = box

    save("plate", plate, plate_a, crop=False)
    for name, m in layer.items():
        save(name, rgb, cv2.GaussianBlur((m > 0).astype(np.float32), (0, 0), 0.6) * al)
    save("logo", rgb, al, crop=False)
    return boxes


def css(boxes) -> str:
    lines = ["/* Сгенерировано tools/intro_layers.py — не править руками.",
             "   Где лежит каждый слой заставки внутри квадрата логотипа, в процентах. */"]
    for name in (*ORDER, "logo"):
        x0, y0, x1, y1 = boxes[name]
        lines.append(f".app-intro .intro-{name} {{ left: {x0 / N * 100:.3f}%; top: {y0 / N * 100:.3f}%; "
                     f"width: {(x1 - x0) / N * 100:.3f}%; height: {(y1 - y0) / N * 100:.3f}%; }}")
    return "\n".join(lines) + "\n"


def main() -> int:
    boxes = build()
    CSS.write_text(css(boxes), encoding="utf-8")
    total = sum((TARGET / f"{n}.webp").stat().st_size for n in (*ORDER, "logo"))
    print(f"записано {TARGET.relative_to(ROOT)}/*.webp ({total // 1024} КБ) и {CSS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
