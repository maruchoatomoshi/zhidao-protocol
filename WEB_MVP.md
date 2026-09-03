# ZHIDAO Learning Web MVP

> Статус с 2026-08-30: разработка заморожена как отдельный учебный прототип.
> Этот контур не является основой Travel V4 и не должен автоматически
> объединяться с Hainan Season. Дальнейшая работа над Learning ведётся отдельно.

Автономная веб-версия не использует Telegram для входа и не изменяет старую
базу `/root/zhidao.db`. Travel Season продолжает жить в старом `index.html`.

## Локальный запуск (PowerShell)

```powershell
python -m venv .venv-web
.\.venv-web\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv-web\Scripts\python.exe scripts\init_web_accounts.py
$env:ZHIDAO_COOKIE_SECURE='0'
.\.venv-web\Scripts\python.exe -m uvicorn zhidao_web:app --host 127.0.0.1 --port 8765
```

Открыть:

- ученик: `http://127.0.0.1:8765/`;
- Архитектор: `http://127.0.0.1:8765/teacher`;
- API health: `http://127.0.0.1:8765/api/health`.

Для просмотра интерфейса без входа и без доступа к данным используется
безопасная витрина: `http://127.0.0.1:8765/?preview=1`. Она содержит только
встроенные демонстрационные данные.

## Production

Использовать HTTPS и перед запуском установить:

```text
ZHIDAO_WEB_DB_PATH=/var/lib/zhidao-learning/zhidao_web.db
ZHIDAO_UPLOAD_PATH=/var/lib/zhidao-learning/uploads
ZHIDAO_COOKIE_SECURE=1
ZHIDAO_SESSION_DAYS=7
ZHIDAO_TRAVEL_URL=https://maruchoatomoshi.github.io/zhidao-protocol/
```

Аккаунты можно создать интерактивным скриптом или однократно через env:

```text
ZHIDAO_TEACHER_USERNAME
ZHIDAO_TEACHER_PASSWORD
ZHIDAO_TEACHER_NAME
ZHIDAO_STUDENT_USERNAME
ZHIDAO_STUDENT_PIN
ZHIDAO_STUDENT_NAME
```

Не хранить реальные пароли и PIN в `.env` внутри репозитория.

## Проверки

```powershell
.\.venv-web\Scripts\python.exe -m unittest tests.test_web_learning_flow -v
Get-ChildItem web\js -Filter *.js | ForEach-Object { node --check $_.FullName }
python -m py_compile zhidao_web.py
git diff --check
```

Проверяется полный цикл двух занятий, голосовой файл, разделение ролей, CSRF,
однократная награда, открытие второй миссии и переход на уровень 2.
