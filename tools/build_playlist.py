"""Пересобирает playlist.json по содержимому папки с музыкой.

Запуск:

    .\\.venv-web\\Scripts\\python.exe tools\\build_playlist.py

Правило, ради которого скрипт вообще написан: он **не затирает названия,
проставленные вручную**. Новые файлы дописываются, исчезнувшие убираются,
всё остальное остаётся как было. Иначе одна перегенерация стирает вечер
работы над подписями.

Теги ID3 читаются напрямую, без внешних зависимостей: в проекте сознательно
нет пакетов сверх необходимого, а нужны отсюда ровно два поля.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from urllib.parse import quote, unquote

AUDIO_DIR = Path(__file__).resolve().parents[1] / "zhidao_v4" / "static" / "app" / "assets" / "audio"
MANIFEST = AUDIO_DIR / "playlist.json"
EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
# Safari не играет ogg/opus, а половина участников придёт с iPhone.
UNSUPPORTED_ON_SAFARI = {".ogg", ".opus"}


def _decode(raw: bytes) -> str:
    """Текстовый фрейм ID3v2: первый байт — кодировка."""
    if not raw:
        return ""
    enc, body = raw[0], raw[1:]
    try:
        if enc == 0:
            text = body.decode("latin-1")
        elif enc == 1:
            text = body.decode("utf-16")
        elif enc == 2:
            text = body.decode("utf-16-be")
        else:
            text = body.decode("utf-8")
    except (UnicodeDecodeError, LookupError):
        return ""
    return text.split("\x00")[0].strip()


def read_id3(path: Path) -> tuple[str, str]:
    """Возвращает (название, исполнитель) из ID3v2. Пустые строки, если нет."""
    try:
        with path.open("rb") as fh:
            head = fh.read(10)
            if len(head) < 10 or head[:3] != b"ID3":
                return "", ""
            # Размер записан синхробезопасно: четыре байта по 7 значащих бит,
            # старший бит всегда нулевой. Это 28 бит, а не 32 — собирать их
            # обычной распаковкой нельзя.
            b0, b1, b2, b3 = (b & 0x7F for b in head[6:10])
            size = (b0 << 21) | (b1 << 14) | (b2 << 7) | b3
            body = fh.read(size)
    except OSError:
        return "", ""

    title = artist = ""
    pos, major = 0, head[3]
    id_len, size_len = (3, 3) if major == 2 else (4, 4)
    while pos + id_len + size_len <= len(body):
        frame_id = body[pos:pos + id_len]
        if not frame_id.strip(b"\x00"):
            break
        if major == 2:
            frame_size = int.from_bytes(body[pos + 3:pos + 6], "big")
            header = 6
        else:
            raw_size = body[pos + 4:pos + 8]
            if major == 4:
                frame_size = struct.unpack(">I", bytes(b & 0x7F for b in raw_size))[0]
            else:
                frame_size = struct.unpack(">I", raw_size)[0]
            header = 10
        payload = body[pos + header:pos + header + frame_size]
        if frame_id in (b"TIT2", b"TT2"):
            title = _decode(payload)
        elif frame_id in (b"TPE1", b"TP1"):
            artist = _decode(payload)
        pos += header + frame_size
        if title and artist:
            break
    return title, artist


def from_filename(stem: str) -> tuple[str, str]:
    """`Исполнитель - Название` — самая частая раскладка, разбираем её."""
    for sep in (" — ", " – ", " - "):
        if sep in stem:
            artist, title = stem.split(sep, 1)
            return title.strip(), artist.strip()
    return stem.strip(), ""


def main() -> int:
    if not AUDIO_DIR.is_dir():
        print(f"Нет папки {AUDIO_DIR}", file=sys.stderr)
        return 1

    previous: dict[str, dict] = {}
    shuffle = False
    note = ""
    if MANIFEST.is_file():
        try:
            old = json.loads(MANIFEST.read_text(encoding="utf-8"))
            shuffle = bool(old.get("shuffle", False))
            note = old.get("note", "")
            for entry in old.get("tracks", []):
                if isinstance(entry, dict) and entry.get("src"):
                    # В манифесте имя закодировано, на диске — нет. Сопоставлять
                    # надо по настоящему имени, иначе записи не найдутся и
                    # правки названий вручную будут затёрты при каждом запуске.
                    previous[unquote(Path(entry["src"]).name)] = entry
        except (OSError, json.JSONDecodeError) as err:
            print(f"Старый манифест не прочитан ({err}), собираю заново.", file=sys.stderr)

    files = sorted(p for p in AUDIO_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in EXTENSIONS)

    tracks, added, kept, warned = [], [], 0, []
    for path in files:
        name = path.name
        if path.suffix.lower() in UNSUPPORTED_ON_SAFARI:
            warned.append(name)
        old_entry = previous.get(name)
        # Пробелы и кириллица в имени файла кодируются: браузеры обычно
        # справляются сами, но «обычно» — не то слово, на которое стоит
        # опираться в адресе.
        src = f"./assets/audio/{quote(name)}"
        if old_entry:
            # Название могло быть поправлено руками — оставляем как есть.
            entry = dict(old_entry)
            entry["src"] = src
            entry["bytes"] = path.stat().st_size
            kept += 1
        else:
            title, artist = read_id3(path)
            if not title:
                title, artist_guess = from_filename(path.stem)
                artist = artist or artist_guess
            entry = {
                "id": path.stem,
                "title": title,
                "artist": artist,
                "src": src,
                "bytes": path.stat().st_size,
            }
            added.append(f"{artist + ' — ' if artist else ''}{title}")
        tracks.append(entry)

    dropped = [n for n in previous if n not in {p.name for p in files}]

    MANIFEST.write_text(
        json.dumps({"note": note or "Собирается скриптом tools/build_playlist.py.",
                    "shuffle": shuffle, "tracks": tracks},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")

    total = sum(t["bytes"] for t in tracks)
    print(f"Треков в манифесте: {len(tracks)} ({total / 1048576:.1f} МБ)")
    if added:
        print(f"Добавлено {len(added)}:")
        for line in added:
            print(f"   {line}")
    if kept:
        print(f"Сохранено без изменений: {kept}")
    if dropped:
        print(f"Убрано (файлов больше нет): {', '.join(dropped)}")
    if warned:
        print("\nВНИМАНИЕ: Safari не играет эти форматы, на iPhone они молчат:")
        for line in warned:
            print(f"   {line}")
    if tracks:
        heavy = [t for t in tracks if t["bytes"] > 5 * 1048576]
        if heavy:
            print(f"\nКрупных файлов (больше 5 МБ): {len(heavy)}. Приложение "
                  "работает на мобильном интернете в Китае — для фоновой "
                  "музыки хватает 128 kbps.")
        print("\nМанифест запрашивается с cache: no-cache, поэтому поднимать "
              "?v= ради него не нужно — обновится сам.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
