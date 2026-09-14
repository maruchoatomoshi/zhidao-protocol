"""Package cover originals without changing their art or aspect ratio.

Requires Pillow already available in the local development environment.
Review is generated beside sources, never inside the participant application.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "art/game-covers"
OUTPUT = ROOT / "zhidao_v4/static/app/assets/games"
TITLES = {"spy": "Шпион Протокола", "cipher": "Шифровальщики", "outage": "Сбой системы",
          "agent": "Тайный агент", "smuggle": "Контрабанда", "royale": "Протокол 60",
          "market": "Рынок Контрабанды", "capture": "Захват кампуса", "sabotage": "Саботаж",
          "zombie": "Зомби-протокол"}

def main():
    cards = []
    for code, title in TITLES.items():
        approved = SOURCES / f"{code}-approved.png"
        source = approved if approved.exists() else SOURCES / f"{code}.png"
        output = OUTPUT / f"cover-{code}.webp"
        if source.exists():
            with Image.open(source) as image:
                image.thumbnail((960, 360), Image.Resampling.LANCZOS)
                image.convert("RGB").save(output, "WEBP", quality=84, method=6)
        with Image.open(output) as image:
            width, height = image.size
        size = output.stat().st_size
        assert size <= 150_000, (code, size)
        # Review copies are just original encoded bytes, not recompressed artwork.
        (SOURCES / output.name).write_bytes(output.read_bytes())
        cards.append(f'<figure><img src="{output.name}" width="{width}" height="{height}" '
                     f'loading="lazy" alt=""><figcaption>{title} <small>{size // 1024} КБ</small></figcaption></figure>')
        print(f"{code}: {width}x{height}, {size} bytes")
    (SOURCES / "review.html").write_text('''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ZHIDAO · Обложки на согласование</title>
<style>body{margin:0;padding:24px;background:#edf3f8;color:#19364d;font:16px/1.5 Tahoma,sans-serif}
main{max-width:1200px;margin:auto}h1{font-size:26px;font-weight:400}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px}
figure{margin:0;background:white;border:1px solid #9caebf;border-radius:6px;overflow:hidden}img{width:100%;height:auto;display:block}
figcaption{padding:12px}small{float:right;color:#46576d}</style><main><h1>Игры ZHIDAO · обложки</h1>
<p>Подборка для художественного согласования. Первые три — существующие, агент и таможня — ваши, остальные — новые.
Карта на иллюстрации Захвата основана на снимке карты приложения (© участники OpenStreetMap), но иллюстрация не предназначена для навигации. Новые варианты одобрены пользователем.</p>
<div class="grid">''' + ''.join(cards) + '</div></main></html>', encoding="utf-8")

if __name__ == "__main__":
    main()
