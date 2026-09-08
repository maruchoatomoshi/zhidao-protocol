from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from zhidao_v4 import cases
from zhidao_v4.api import create_app
from zhidao_v4.auth import provision_local_account
from zhidao_v4.db import connect_database, immediate_transaction
from zhidao_v4.migrations import apply_migrations
from zhidao_v4.season_roster import configure


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'cases.sqlite'
        apply_migrations(self.path)
        conn = connect_database(self.path)
        with immediate_transaction(conn):
            self.ids = {}
            for name, role in [('staff', 'operator'), ('alice', 'participant'), ('boris', 'participant')]:
                self.ids[name] = provision_local_account(conn, username=name, password='a secure testing password',
                    display_name=name, role_code=role)['id']
            conn.execute("INSERT INTO v4_seasons(id,code,name,status) VALUES (1,'hainan','Hainan','active'),(2,'other','Other','active')")
            for name in ('alice', 'boris'):
                conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (1,?,'active')", (self.ids[name],))
            conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status) VALUES (2,?,'active')", (self.ids['alice'],))
            conn.execute("INSERT INTO v4_groups(id,season_id,code,name) VALUES (1,1,'test','Test group')")
            conn.execute("INSERT INTO v4_group_memberships(season_id,group_id,season_membership_id) SELECT 1,1,id FROM v4_season_memberships WHERE season_id=1")
            # A legacy REP probe must remain untouched by all new operations.
            conn.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, rep INTEGER)')
            conn.execute('INSERT INTO users VALUES (1,123)')
        conn.close()
        self.app = create_app(self.path, cookie_secure=False)
        self.clients = {}
        self.tokens = {}
        for name in self.ids:
            client = TestClient(self.app)
            response = client.post('/api/v4/auth/login', json={'username': name, 'password': 'a secure testing password'})
            self.assertEqual(response.status_code, 200, response.text)
            self.clients[name] = client
            self.tokens[name] = response.json()['csrf_token']

    def tearDown(self):
        for client in self.clients.values():
            client.close()
        self.temp.cleanup()

    def headers(self, name, key=None):
        return {'X-CSRF-Token': self.tokens[name], 'X-Idempotency-Key': key or uuid.uuid4().hex}

    def grant(self, amount=1, name='alice', key=None, group=None, season=1, actor='staff'):
        return self.clients[actor].post(f'/api/v4/seasons/{season}/cases/admin/grants',
            headers=self.headers(actor, key), json={'account_ids': [] if group else [self.ids[name]],
                'group_id': group, 'amount': amount, 'reason': 'Test reward'})

    def open(self, name='alice', key=None, season=1):
        return self.clients[name].post(f'/api/v4/seasons/{season}/cases/open', headers=self.headers(name, key))

    def state(self, name='alice', season=1):
        return self.clients[name].get(f'/api/v4/seasons/{season}/cases/state').json()

    def sql(self, query, values=()):
        conn = connect_database(self.path)
        try:
            return conn.execute(query, values).fetchall()
        finally:
            conn.close()

    def test_empty_and_authentication_and_csrf(self):
        self.assertEqual(self.state()['stars'], 0)
        self.assertEqual(self.state()['scans'], 0)
        self.assertEqual(self.state()['inventory'], [])
        self.assertEqual(self.open().status_code, 409)
        anon = TestClient(self.app)
        for path in ['context', '../seasons/1/cases/state']:
            self.assertEqual(anon.get('/api/v4/cases/' + path).status_code in (401, 404), True)
        self.assertEqual(anon.get('/api/v4/seasons/1/cases/state').status_code, 401)
        self.assertEqual(anon.get('/api/v4/seasons/1/cases/inventory').status_code, 401)
        self.assertEqual(anon.get('/api/v4/seasons/1/cases/history').status_code, 401)
        self.assertEqual(anon.get('/api/v4/seasons/1/cases/admin/grants').status_code, 401)
        self.assertEqual(anon.get('/api/v4/cases/rules').status_code, 200)
        self.assertEqual(self.clients['alice'].post('/api/v4/seasons/1/cases/open').status_code, 403)
        self.assertEqual(self.clients['alice'].get('/api/v4/seasons/1/cases/state').headers['cache-control'], 'no-store')
        self.assertEqual(self.sql('SELECT COUNT(*) FROM v4_economy_operations')[0][0], 0)
        anon.close()

    def test_grant_cap_group_and_replay(self):
        self.assertEqual(self.grant(6).status_code, 200)
        result = self.grant(4, key='grant-replay', group=1)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([r['granted'] for r in result.json()['results']], [1, 4])
        again = self.grant(4, key='grant-replay', group=1)
        self.assertEqual(again.json(), result.json())
        self.assertEqual(again.headers['x-idempotent-replayed'], 'true')
        self.assertEqual(self.grant(3, key='grant-replay', group=1).status_code, 409)
        self.assertEqual(self.state()['scans'], 7)
        self.assertEqual(self.state('boris')['scans'], 4)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM v4_economy_operations')[0][0], 3)

    def test_all_prizes_and_weights(self):
        expected = {'gold': {'empty':40,'small':24,'medium':12,'fate_guard':10,'walk':8,'scan':5,'jackpot':1},
                    'purple': {'implant_qilin':85,'implant_caishen':75,'implant_guanxi':68,'implant_panda':64,'implant_shaolin':62,'implant_linguasoft':60},
                    'black': {'implant_red_dragon':1,'implant_terracota':1}}
        self.assertEqual([t['weight'] for t in cases.rules()['tiers']], [848,150,2])
        expected_stars = 0
        for tier in cases.rules()['tiers']:
            self.assertEqual({p['code']:p['weight'] for p in tier['prizes']}, expected[tier['code']])
            for prize in tier['prizes']:
                with self.subTest(prize=prize['code']):
                    self.grant(7)
                    with patch('zhidao_v4.cases.weighted', side_effect=[tier, prize]):
                        response = self.open()
                    self.assertEqual(response.status_code, 200, response.text)
                    expected_stars += {'small':30,'medium':60,'jackpot':100}.get(prize['code'], 0)
                    self.assertEqual(response.json()['stars'], expected_stars)
                    self.assertEqual(response.json()['scans'], 7 if prize['code']=='scan' else 6)
        self.assertEqual(self.state()['stars'], 190)
        self.assertEqual(len(self.state()['inventory']), 10)
        self.assertEqual(self.sql('SELECT rep FROM users')[0][0], 123)
        self.assertEqual(self.sql('PRAGMA foreign_key_check'), [])

    def test_guard_reroll_consumes_once(self):
        tier = cases.rules()['tiers'][0]
        prizes = {p['code']:p for p in tier['prizes']}
        self.grant(3)
        with patch('zhidao_v4.cases.weighted', side_effect=[tier,prizes['fate_guard']]):
            self.open()
        with patch('zhidao_v4.cases.weighted', side_effect=[tier,prizes['empty'],prizes['medium']]) as roll:
            response = self.open(key='guard-retry')
            self.assertNotIn('empty', [p['code'] for p in roll.call_args.args[0]])
        self.assertTrue(response.json()['guard_used'])
        self.assertEqual(response.json()['stars'], 60)
        self.assertEqual(self.state()['inventory'], [])
        with patch('zhidao_v4.cases.weighted', side_effect=AssertionError('must not reroll')):
            self.assertEqual(self.open(key='guard-retry').json(), response.json())
        self.assertEqual(self.state()['scans'], 1)

    def test_idempotent_after_restart_and_closed_season(self):
        self.grant(1)
        first = self.open(key='restart-key')
        self.assertEqual(first.status_code, 200)
        self.sql("UPDATE v4_seasons SET status='closed' WHERE id=1")
        fresh = TestClient(create_app(self.path, cookie_secure=False))
        fresh.cookies.update(self.clients['alice'].cookies)
        second = fresh.post('/api/v4/seasons/1/cases/open', headers=self.headers('alice','restart-key'))
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.open().status_code, 409)
        fresh.close()

    def test_concurrent_same_key_is_one_open(self):
        self.grant(7)
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.open(key='parallel-same'), range(8)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual(len({r.json()['opening_id'] for r in responses}), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM v4_economy_operations WHERE operation='case.open'")[0][0], 1)

    def test_concurrent_distinct_keys_cannot_overspend(self):
        self.grant(1)
        tier = cases.rules()['tiers'][0]
        prize = next(p for p in tier['prizes'] if p['code']=='small')
        def fixed(values):
            return tier if 'prizes' in values[0] else prize
        with patch('zhidao_v4.cases.weighted', side_effect=fixed), ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.open(), range(8)))
        self.assertEqual([r.status_code for r in responses].count(200), 1)
        self.assertEqual([r.status_code for r in responses].count(409), 7)
        self.assertEqual(self.state()['scans'], 0)
        self.assertEqual(self.state()['stars'], 30)

    def test_permissions_scope_disabled_and_withdrawn(self):
        self.assertEqual(self.grant(actor='alice').status_code, 403)
        self.assertEqual(self.clients['alice'].get('/api/v4/seasons/1/cases/admin/roster').status_code, 403)
        self.sql("UPDATE v4_role_assignments SET season_id=1 WHERE account_id=?", (self.ids['staff'],))
        self.assertEqual(self.grant().status_code, 200)
        self.assertEqual(self.grant(season=2).status_code, 403)
        self.sql("UPDATE v4_role_assignments SET revoked_at=granted_at WHERE account_id=?", (self.ids['staff'],))
        self.assertEqual(self.grant().status_code, 403)
        self.sql("UPDATE v4_season_memberships SET status='withdrawn' WHERE account_id=? AND season_id=1", (self.ids['alice'],))
        self.assertEqual(self.open().status_code, 403)
        self.assertEqual(self.clients['alice'].get('/api/v4/seasons/1/cases/inventory').status_code, 403)
        self.sql("UPDATE v4_accounts SET status='disabled' WHERE id=?", (self.ids['boris'],))
        self.assertEqual(self.clients['boris'].get('/api/v4/cases/context').status_code, 401)

    def test_season_and_participant_isolation(self):
        self.grant(4)
        self.assertEqual(self.state('boris')['scans'], 0)
        self.assertEqual(self.state(season=2)['scans'], 0)
        self.assertEqual(self.clients['boris'].get('/api/v4/seasons/2/cases/state').status_code, 403)
        first = self.open(key='cross-season-key')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.open(key='cross-season-key', season=2).status_code, 409)

    def test_rollback_when_ledger_fails(self):
        self.grant(1)
        with patch('zhidao_v4.cases.finish', side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError): self.open(key='rollback-test')
        self.assertEqual(self.state()['scans'], 1)
        self.assertEqual(self.state()['stars'], 0)
        self.assertEqual(self.state()['inventory'], [])
        self.assertEqual(self.state()['history']['items'], [])
        self.assertEqual(self.open(key='rollback-test').status_code, 200)

    def test_invalid_grants_are_atomic_and_ledger_immutable(self):
        self.assertEqual(self.grant(8).status_code, 422)
        self.assertEqual(self.grant(0).status_code, 422)
        self.assertEqual(self.grant(group=900).status_code, 404)
        self.assertEqual(self.grant(key='short').status_code, 400)
        response = self.clients['staff'].post('/api/v4/seasons/1/cases/admin/grants', headers=self.headers('staff'),
            json={'account_ids':[self.ids['alice'],9000], 'amount':1, 'reason':'atomic'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.state()['scans'], 0)
        self.grant()
        with self.assertRaises(sqlite3.IntegrityError): self.sql('DELETE FROM v4_economy_operations')
        with self.assertRaises(sqlite3.IntegrityError): self.sql('UPDATE v4_economy_operations SET scans_delta=9')

    def test_weighted_ticket_boundaries(self):
        choices = [{'weight':2,'code':'a'},{'weight':3,'code':'b'}]
        for ticket, expected in [(0,'a'),(1,'a'),(2,'b'),(4,'b')]:
            with patch('zhidao_v4.cases.secrets.randbelow', return_value=ticket):
                self.assertEqual(cases.weighted(choices)['code'], expected)

    def test_season_setup_requires_admin_dry_run_and_preserves_progress(self):
        conn = connect_database(self.path)
        kwargs = {'season_code': 'other', 'actor_id': self.ids['staff'],
                  'account_ids': [self.ids['boris']], 'group_code': 'new', 'group_name': 'New'}
        try:
            with self.assertRaises(cases.CaseError): configure(conn, **kwargs)
            conn.execute("UPDATE v4_role_assignments SET role_code='system_admin' WHERE account_id=?", (self.ids['staff'],))
            report = configure(conn, **kwargs)
            self.assertFalse(report['apply'])
            self.assertEqual(conn.execute('SELECT count(*) FROM v4_season_memberships WHERE season_id=2').fetchone()[0], 1)
            with immediate_transaction(conn): configure(conn, **kwargs, apply=True)
            self.assertEqual(self.state('boris', 2)['scans'], 0)
            self.grant(3, name='boris', season=2)
            with immediate_transaction(conn): configure(conn, **kwargs, apply=True)
            self.assertEqual(self.state('boris', 2)['scans'], 3)
            self.assertEqual(conn.execute('SELECT count(*) FROM v4_group_memberships WHERE season_id=2').fetchone()[0], 1)
            kwargs['group_code'] = 'another'
            with self.assertRaises(cases.CaseError):
                with immediate_transaction(conn): configure(conn, **kwargs, apply=True)
        finally:
            conn.close()

    def test_concurrent_grants_and_pagination(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: self.grant(2, key='concurrent-grant'), range(8)))
        self.assertTrue(all(r.status_code == 200 for r in replies))
        self.assertEqual(self.state()['scans'], 2)
        self.assertEqual(self.sql("SELECT count(*) FROM v4_economy_operations WHERE operation='case.grant'")[0][0], 1)
        for _ in range(51): self.grant(1)
        first = self.clients['staff'].get('/api/v4/seasons/1/cases/admin/grants').json()
        second = self.clients['staff'].get(f"/api/v4/seasons/1/cases/admin/grants?before={first['next_before']}").json()
        self.assertEqual(len(first['items']), 50)
        self.assertEqual(len(second['items']), 2)
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})


if __name__ == '__main__':
    unittest.main()
