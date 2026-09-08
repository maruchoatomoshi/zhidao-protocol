"""Disposable loopback-only case preview. Never accepts a real database path.

Run: python -m tools.preview_v4_cases --port 8784
Local test logins: case.student / case.operator; password: preview-only-passphrase
Closing the process discards the database. All content belongs to test accounts.
"""
import argparse
import tempfile
from pathlib import Path
from unittest.mock import patch

import uvicorn

from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4 import cases
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations


def seed(path):
    apply_migrations(path)
    conn = connect_database(path)
    try:
        with immediate_transaction(conn):
            staff = provision_local_account(conn, username='case.operator', password='preview-only-passphrase', display_name='Организатор · тест', role_code='system_admin')['id']
            student = provision_local_account(conn, username='case.student', password='preview-only-passphrase', display_name='Участник · тест', role_code='participant')['id']
            conn.execute("INSERT INTO v4_seasons(id,code,name,status) VALUES (1,'case-preview','Хайнань · тестовый сезон','active')")
            conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (student,))
            conn.execute("INSERT INTO v4_groups(id,season_id,code,name) VALUES (1,1,'preview','Тестовая группа')")
            conn.execute("INSERT INTO v4_group_memberships(season_id,group_id,season_membership_id) SELECT 1,1,id FROM v4_season_memberships WHERE season_id=1")
            for tier in cases.rules()['tiers']:
                for prize in tier['prizes']:
                    cases.grant(conn, staff, 1, 'seed-grant-' + prize['code'], [student], None, 7, 'Только тестовый просмотр')
                    with patch('zhidao_v4.cases.weighted', side_effect=[tier, prize]):
                        cases.open_case(conn, student, 1, 'seed-open-' + prize['code'])
            cases.grant(conn, staff, 1, 'seed-final-grant', [student], None, 7, 'Попытки для проверки интерфейса')
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8784)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='zhidao-cases-preview-') as directory:
        path = Path(directory) / 'preview.sqlite'
        seed(path)
        uvicorn.run(create_app(path, cookie_secure=False), host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
