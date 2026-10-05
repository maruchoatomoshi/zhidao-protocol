# Макет кампуса (3D)

Экран «Ещё → Макет» (`zhidao_v4/static/app/campus-model.*`). Это объёмная
иллюстрация, **не карта**: модель из Blender (`game_assets/hainan_campus`, v02)
условная, на экране это сказано прямо. Не выдавать за геодезию.

## Что где

- `diorama.src.mjs` — сцена на three.js (колпак, свет, время суток, ракурсы).
- `build.mjs` — собирает всё в один обычный скрипт
  `zhidao_v4/static/app/campus-diorama.js`. Так нужно, потому что CSP
  приложения (`script-src 'self'`) запрещает import map и inline-скрипты.
- `campus-model.js` / `campus-model.css` — экран и кнопки; бандл и модель
  подгружаются только при первом открытии экрана.
- `assets/campus/campus-diorama.glb` — модель (~2,8 МБ).

## Пересобрать бандл

```bash
cd tools/diorama && npm install && npm run build
python tools/stamp_assets.py
```

## Пересобрать модель

1. Blender 5.x в фоне: импорт `game_assets/hainan_campus/unity_handoff/hainan-campus-v02-geometry.fbx`,
   экспорт GLB (`export_vertex_color=NONE`, Y-up). Исходные `.blend` и FBX не
   менять — писать в новый файл.
2. Сжать: `npx @gltf-transform/cli optimize in.glb out.glb --compress quantize --texture-compress false --simplify false --palette false`.
   **`--palette false` обязателен**: палитра превращает цвета в текстуру, а
   CSP (`img-src 'self' data:`) не пускает blob-картинки, из которых three.js
   собирает встроенные текстуры, — макет станет белым.
3. Положить в `assets/campus/campus-diorama.glb`, затем `python tools/stamp_assets.py`.

Рамка обрезки (`CX, CZ, HX, HZ` в `diorama.src.mjs`) подобрана по габаритам
модели: здания x −146…210, z −98…110; море севернее z −112.
