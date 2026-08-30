# ZHIDAO Legacy Travel — безопасный локальный запуск

Этот режим предназначен только для восстановления и тестирования старого
Travel-приложения. Он использует отдельную локальную SQLite и не обращается к
утраченному production-серверу.

## 1. Установка

```powershell
python -m venv .venv-travel
.\.venv-travel\Scripts\python.exe -m pip install -r requirements-travel.txt
```

## 2. Запуск API на временной базе

```powershell
New-Item -ItemType Directory -Force .codex-tmp\travel-local | Out-Null
$env:ZHIDAO_DB_PATH = (Join-Path (Get-Location) '.codex-tmp\travel-local\zhidao.db')
$env:ZHIDAO_API_ERROR_LOG = (Join-Path (Get-Location) '.codex-tmp\travel-local\api-error.log')
$env:TELEGRAM_AUTH_REQUIRED = '0'
$env:ZHIDAO_ENABLE_WAL_CHECKPOINT = '0'
.\.venv-travel\Scripts\python.exe -m uvicorn zhidao_api_ready:app --host 127.0.0.1 --port 8767
```

`TELEGRAM_AUTH_REQUIRED=0` допустим только на `127.0.0.1` для локальной
демонстрации. На тестовом или production-сервере должно быть `1`.

Проверка API:

```text
http://127.0.0.1:8767/api/health
```

## 3. Запуск старого frontend

Во втором окне PowerShell:

```powershell
.\.venv-travel\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1
```

Открыть демо-витрину:

```text
http://127.0.0.1:8766/index.html?demo=1&api=http://127.0.0.1:8767
```

Параметр `api` принимается только при открытии frontend с `localhost` или
`127.0.0.1`. Production-страница продолжает использовать прежний адрес API.

## 4. Проверки

```powershell
.\.venv-travel\Scripts\python.exe -m unittest tests.test_travel_startup -v
.\.venv-travel\Scripts\python.exe -m py_compile zhidao_api_ready.py zhidao_bot_ready.py
Get-ChildItem js -Filter *.js | ForEach-Object { node --check $_.FullName }
```

Локальная база является одноразовой. Она не содержит данных Beijing и не
должна использоваться как источник для будущей миграции.
