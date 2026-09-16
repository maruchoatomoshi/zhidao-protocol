repo: maruchoatomoshi/zhidao-protocol
branch: main
path: zhidao_v4

## Last sync
date: 2026-09-16T20:35:00Z

### Updated in this project
- Добавлены экраны входа и привязки MAX: два реальных отказа сервера, без выдуманного третьего.
- Пустые, ошибочные и офлайн-состояния главных экранов собраны на одном листе.
- Консоль вожатого: сводка, коды MAX, лист дневника, выдача попыток; расписание — выключено, функции на сервере нет.
- Новый словарь классов служебного контура — skins/staff.css.

## Screen map
| Экран / файл проекта | Источник в репозитории |
| --- | --- |
| tokens/palette.css, tokens/semantic.css | zhidao_v4/static/app/app.css, tokens.css |
| tokens/material.css | zhidao_v4/static/app/aero.css, tokens.css |
| tokens/luna.css, skins/luna.css | zhidao_v4/static/app/xp-home.css |
| tokens/night.css | zhidao_v4/static/app/tokens.css (:root[data-theme="dark"]) |
| skins/aqua.css | zhidao_v4/static/app/aero.css, app.css |
| skins/staff.css | zhidao_v4/static/app/auth.js, admin.js, diary.js |
| assets/ | zhidao_v4/static/app/assets/** |
| ui_kits/app/ | zhidao_v4/static/app/index.html, xp-home.css, aero-desktop.css |
| ui_kits/games/ | zhidao_v4/royale.py, capture.py, duels.py, static/app/games.css |
| ui_kits/sections/ | zhidao_v4/static/app/meet.css, trade.css, workshop.css, virus.css, story.css, campus-marks.css |
| ui_kits/onboarding/ | zhidao_v4/static/app/auth.js, index.html (#authGate), V4_AUTH.md |
| ui_kits/console/ | zhidao_v4/static/app/admin.js, diary.js, zhidao_v4/cases_api.py, diary_api.py |

## Sync history
- 2026-09-16T09:36:00Z — токены, скины, компоненты, кит мини-приложения, ассеты.
