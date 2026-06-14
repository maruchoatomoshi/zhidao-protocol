#!/usr/bin/env python3
"""
Сопоставление списка детей, едущих в поездку, со списком expected_students в БД.
Запуск на сервере: python3 compare_students.py
"""
import re
import sqlite3

DB_PATH = "/root/zhidao.db"

TRIP_LIST = """
Гончаров Тимофей
Евстигнеева Настя
Котлячков Никита
Кудашова Анастасия
Кулаков Владимир
Лебедев Матвей
Сурина Ксения
Уткина Алиса
Федосова Александра
Фоменко Виктория
Холоша Ксения
Шелякина Ульяна
Шелякина Полина
Языкова Вера
Еремин Арсений
Живаева Тамара
Зеленова Ангелина Мирослава
Казенова Полина
Каминская Кристина
Каминский Олег
Кисимов Федор
Клочай Алина
Козлова Александра
Королева Алиса
Краснов Алексей
Кулешова Виктория
Кулешова Анастасия
Любимова Валерия
Айвазов Арсен
Албу Александр
Анисимова Кристина
Афанасьева Ирина
Ахметова Карина
Башилова Василиса
Болотникова Евгения
Бородин Станислав
Будаева Елизавета
Бурлакова Елизавета
Васильчиков Николай
Гильмутдинова Варвара
Горьковенко Алена
Гусаров Сергей
Лайков Артем
Бортников Сергей
Евтухова Мария
Королева Валерия
Рыжкова Арина
Рычкин Мирослав
Савкова Анна
Семенов Артем
Скрипин Захар
Смирнова Александра
Соколов Александр
Спирин Дмитрий
Терехова Стефания
Уланов Матвей
Хорбенко Маргарита
Макарова Мария
Малютин Георгий
Метелев Алексей
Минаева Алиса
Мокрецова Мария
Немтырев Геннадий
Нуштаев Михаил
Пан Юлия
Рванцева Дарья
Резанова Екатерина
Серегин Роман
Федянин Ярослав
Гостев Семен
Дюзйол Алина
Кулаков Георгий
Куприна Елизавета
Лавринов Тимур
Левицкая Анастасия
Мироненко Андрей
Мироненко Владимир
Островкин Илья
Павлов Григорий
Павлов Георгий
Пинчук Андрей
Чумаков Александр
Шакиров Мухамедали
Шакирова Олия
Шарина Мария
Бычков Алексей
""".strip().splitlines()


def normalize(value):
    text = str(value or "").replace("\t", " ").replace("Ё", "Е").replace("ё", "е")
    return re.sub(r"\s+", " ", text.strip()).lower()


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT full_name, normalized_name, telegram_id, status FROM expected_students")
    db_rows = c.fetchall()
    db_by_norm = {row[1]: row for row in db_rows}

    trip_norm = {}
    for name in TRIP_LIST:
        name = name.strip()
        if not name:
            continue
        trip_norm[normalize(name)] = name

    print(f"В списке поездки: {len(trip_norm)} имён")
    print(f"В expected_students: {len(db_rows)} имён")
    print()

    missing_in_db = []
    found = []
    for norm, original in trip_norm.items():
        if norm in db_by_norm:
            found.append((original, db_by_norm[norm]))
        else:
            missing_in_db.append(original)

    extra_in_db = []
    for norm, row in db_by_norm.items():
        if norm not in trip_norm:
            extra_in_db.append(row)

    print(f"✅ Совпало: {len(found)}")
    print()
    print(f"❌ Есть в списке поездки, НЕТ в expected_students ({len(missing_in_db)}):")
    for name in missing_in_db:
        print(f"   - {name}")
    print()
    print(f"⚠️  Есть в expected_students, НЕТ в списке поездки ({len(extra_in_db)}):")
    for full_name, norm, telegram_id, status in extra_in_db:
        bound = f"telegram_id={telegram_id}" if telegram_id else "не привязан"
        print(f"   - {full_name} ({bound}, status={status})")

    # Дубликаты внутри списка поездки (после нормализации)
    seen = {}
    dupes = []
    for name in TRIP_LIST:
        name = name.strip()
        if not name:
            continue
        norm = normalize(name)
        if norm in seen:
            dupes.append((seen[norm], name))
        else:
            seen[norm] = name
    if dupes:
        print()
        print(f"🔁 Дубликаты в списке поездки ({len(dupes)}):")
        for a, b in dupes:
            print(f"   - '{a}' / '{b}'")


if __name__ == "__main__":
    main()
