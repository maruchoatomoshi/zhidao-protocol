#!/usr/bin/env python3
"""
Массовое создание пользователей VPN (Marzban) для списка детей, едущих в поездку.

Запуск на сервере: python3 create_marzban_users.py
Требуются переменные окружения MARZBAN_USER / MARZBAN_PASS (как у бота),
либо задайте их прямо в этом файле перед запуском.

Скрипт:
  1. Берёт список имён из compare_students.py (TRIP_LIST).
  2. Транслитерирует имя+фамилию в username (латиница, нижний регистр).
  3. Создаёт пользователя в Marzban с настройками VLESS REALITY без flow
     (как у рабочего markmobile/vlad_ova: security=reality, sni=www.microsoft.com,
     fp=chrome, flow="").
  4. Печатает итоговую таблицу "ФИО -> username -> ссылка".
"""
import os
import re
import sys
import requests

from compare_students import TRIP_LIST

MARZBAN_URL = os.getenv("MARZBAN_URL", "http://127.0.0.1:8000")
MARZBAN_USER = os.getenv("MARZBAN_USER", "")
MARZBAN_PASS = os.getenv("MARZBAN_PASS", "")

# Тег inbound'а, под который выпускаем пользователей.
# Проверьте через GET /api/inbounds, что тег называется именно так.
INBOUND_TAG = os.getenv("MARZBAN_INBOUND_TAG", "VLESS TCP REALITY")

TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text):
    result = []
    for ch in text.lower():
        if ch in TRANSLIT_MAP:
            result.append(TRANSLIT_MAP[ch])
        elif ch.isalnum():
            result.append(ch)
        else:
            result.append(" ")
    return "".join(result)


def make_username(full_name, used):
    parts = full_name.strip().split()
    base = "_".join(transliterate(p) for p in parts if p)
    base = re.sub(r"\s+", "", base)
    base = re.sub(r"[^a-z0-9_]", "", base)
    username = base
    i = 2
    while username in used:
        username = f"{base}{i}"
        i += 1
    used.add(username)
    return username


def get_token():
    r = requests.post(
        f"{MARZBAN_URL}/api/admin/token",
        data={"username": MARZBAN_USER, "password": MARZBAN_PASS},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def create_user(token, username):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "username": username,
        "proxies": {
            "vless": {"flow": ""}
        },
        "inbounds": {
            "vless": [INBOUND_TAG]
        },
        "expire": 0,
        "data_limit": 0,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
    }
    r = requests.post(f"{MARZBAN_URL}/api/user", json=payload, headers=headers, timeout=15)
    if r.status_code == 409:
        # уже существует — забираем существующего
        r = requests.get(f"{MARZBAN_URL}/api/user/{username}", headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    if not MARZBAN_USER or not MARZBAN_PASS:
        print("Не заданы MARZBAN_USER / MARZBAN_PASS (env)", file=sys.stderr)
        sys.exit(1)

    token = get_token()

    used = set()
    results = []
    for raw_name in TRIP_LIST:
        name = raw_name.strip()
        if not name:
            continue
        username = make_username(name, used)
        try:
            data = create_user(token, username)
        except requests.HTTPError as e:
            print(f"ОШИБКА для {name} ({username}): {e} -> {e.response.text}", file=sys.stderr)
            continue

        links = data.get("links") or []
        link = links[0] if links else (data.get("subscription_url") or "")
        results.append((name, username, link))
        print(f"{name:35s} -> {username:30s} -> {link}")

    print()
    print(f"Готово: {len(results)} пользователей создано/проверено.")


if __name__ == "__main__":
    main()
