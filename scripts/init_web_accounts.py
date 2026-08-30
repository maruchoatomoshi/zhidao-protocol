"""Create or rotate the two standalone website accounts."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zhidao_web


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize ZHIDAO website accounts")
    parser.add_argument("--teacher-login", default="architect")
    parser.add_argument("--teacher-name", default="Марк Альбертович")
    parser.add_argument("--student-login", default="operator")
    parser.add_argument("--student-name", default="Оператор")
    args = parser.parse_args()

    teacher_password = getpass.getpass("Пароль Архитектора: ")
    teacher_confirm = getpass.getpass("Повторите пароль Архитектора: ")
    if teacher_password != teacher_confirm:
        raise SystemExit("Пароли Архитектора не совпадают")
    student_pin = getpass.getpass("PIN ученика (минимум 4 символа): ")
    student_confirm = getpass.getpass("Повторите PIN ученика: ")
    if student_pin != student_confirm:
        raise SystemExit("PIN ученика не совпадает")

    zhidao_web.init_db()
    zhidao_web.create_or_update_user(
        args.teacher_login,
        args.teacher_name,
        "teacher",
        teacher_password,
    )
    zhidao_web.create_or_update_user(
        args.student_login,
        args.student_name,
        "student",
        student_pin,
    )
    print("Аккаунты созданы. Секреты не записывались в репозиторий.")


if __name__ == "__main__":
    main()
