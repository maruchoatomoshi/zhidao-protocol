"""Seasonal cases. All writes run inside the caller's BEGIN IMMEDIATE.

The public catalogue is also the server's rules source, not a second set of
probabilities. Only this module rolls rewards. No legacy database is touched.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from functools import lru_cache
from pathlib import Path

from .seasons import normalize_idempotency_key

RULES_PATH = Path(__file__).parent / 'static/app/assets/cases/cases.json'
STAFF_ROLES = ('operator', 'architect', 'system_admin')


class CaseError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@lru_cache(maxsize=1)
def rules():
    data = json.loads(RULES_PATH.read_text(encoding='utf-8'))
    codes = set()
    for tier in data['tiers']:
        if type(tier['weight']) is not int or tier['weight'] <= 0:
            raise ValueError('Invalid case tier weight')
        for prize in tier['prizes']:
            if prize['code'] in codes or type(prize['weight']) is not int or prize['weight'] <= 0:
                raise ValueError('Invalid or duplicate case prize')
            codes.add(prize['code'])
            if prize['reward']['kind'] not in ('none', 'stars', 'scan', 'item'):
                raise ValueError('Unknown case reward')
            reward = prize['reward']
            if reward['kind'] in ('stars', 'scan') and (type(reward.get('amount')) is not int or reward['amount'] <= 0):
                raise ValueError('Reward amounts must be positive integers')
            if reward['kind'] == 'item' and reward.get('effect_state') not in ('active', 'pending'):
                raise ValueError('Invalid effect state')
    if data['scan_cap'] != 7 or data['scan_cost'] != 1:
        raise ValueError('Unsupported wallet constraints')
    data['rules_version'] = hashlib.sha256(encoded(data).encode()).hexdigest()[:16]
    return data


def items_by_code():
    return {p['code']: p for t in rules()['tiers'] for p in t['prizes']}


def weighted(values):
    ticket = secrets.randbelow(sum(v['weight'] for v in values))
    for value in values:
        ticket -= value['weight']
        if ticket < 0:
            return value
    raise AssertionError('Unreachable weighted selection')


def can_manage(conn, account_id, season_id):
    # Read grants inside the operation transaction, not from stale client state.
    return conn.execute('''SELECT 1 FROM v4_role_assignments
        WHERE account_id=? AND role_code IN ('operator','architect','system_admin')
        AND revoked_at IS NULL AND (season_id IS NULL OR season_id=?)''',
        (account_id, season_id)).fetchone() is not None


def authorize(conn, account_id, season_id, *, manage=False, write=False):
    season = conn.execute('SELECT * FROM v4_seasons WHERE id=?', (season_id,)).fetchone()
    if not season:
        raise CaseError('Сезон не найден.', 404)
    active = conn.execute("SELECT 1 FROM v4_accounts WHERE id=? AND status='active'", (account_id,)).fetchone()
    if not active:
        raise CaseError('Аккаунт недоступен.', 403)
    if manage:
        if not can_manage(conn, account_id, season_id):
            raise CaseError('Нет прав организатора этого сезона.', 403)
    else:
        member = conn.execute('SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?',
                              (season_id, account_id)).fetchone()
        if not member or member['status'] not in ('active', 'completed') or (write and member['status'] != 'active'):
            raise CaseError('Вы не активный участник этого сезона. Обратитесь к организатору.', 403)
    if write and season['status'] != 'active':
        raise CaseError('Сезон не активен: изменения недоступны.', 409)
    return season


def contexts(conn, account_id):
    result = []
    for season in conn.execute('SELECT id, name, status FROM v4_seasons ORDER BY id DESC'):
        member = conn.execute('SELECT status FROM v4_season_memberships WHERE season_id=? AND account_id=?',
                              (season['id'], account_id)).fetchone()
        manage = can_manage(conn, account_id, season['id'])
        if manage or (member and member['status'] in ('active', 'completed')):
            result.append({**dict(season), 'can_manage': manage,
                           'can_play': bool(member and member['status'] == 'active' and season['status'] == 'active'),
                           'is_member': bool(member and member['status'] in ('active', 'completed'))})
    return {'seasons': result}


def wallet(conn, account_id, season_id):
    row = conn.execute('SELECT stars, scans FROM v4_case_wallets WHERE season_id=? AND account_id=?',
                       (season_id, account_id)).fetchone()
    return dict(row) if row else {'stars': 0, 'scans': 0}


def inventory(conn, account_id, season_id):
    catalogue = items_by_code()
    return [{**dict(row), 'name_ru': catalogue[row['item_code']]['name_ru']}
            for row in conn.execute('''SELECT item_code, quantity, effect_state FROM v4_case_inventory
                WHERE season_id=? AND account_id=? AND quantity>0 ORDER BY item_code''', (season_id, account_id))]


def history(conn, account_id, season_id, before=None):
    rows = conn.execute('''SELECT * FROM v4_economy_operations WHERE season_id=? AND account_id=?
        AND operation='case.open' AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT 50''',
        (season_id, account_id, before, before)).fetchall()
    return {'items': [operation_view(row) for row in rows],
            'next_before': rows[-1]['id'] if len(rows) == 50 else None}


def operation_view(row):
    value = dict(row)
    value['details'] = json.loads(value.pop('details_json'))
    return value


def state(conn, account_id, season_id):
    season = authorize(conn, account_id, season_id)
    return {'season_id': season_id, 'season_status': season['status'],
            **wallet(conn, account_id, season_id), 'inventory': inventory(conn, account_id, season_id),
            'history': history(conn, account_id, season_id), 'rules_version': rules()['rules_version']}


def replay(conn, account_id, operation, key, payload):
    key = normalize_idempotency_key(key)
    digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
    old = conn.execute('''SELECT request_hash, response_json FROM v4_idempotency_keys
        WHERE account_id=? AND operation=? AND idempotency_key=?''', (account_id, operation, key)).fetchone()
    if old and old['request_hash'] != digest:
        raise CaseError('Этот ключ уже использован для другого запроса.', 409)
    return key, digest, json.loads(old['response_json']) if old else None


def finish(conn, actor, season_id, operation, key, digest, response, request_id):
    serialized = encoded(response)
    conn.execute('''INSERT INTO v4_idempotency_keys(account_id, operation, idempotency_key,
        request_hash, response_status, response_json) VALUES (?,?,?,?,200,?)''',
        (actor, operation, key, digest, serialized))
    conn.execute('''INSERT INTO v4_audit_log(actor_account_id, season_id, action, entity_type,
        entity_id, request_id, after_json, metadata_json) VALUES (?,?,?,'case',?,?,?,?)''',
        (actor, season_id, operation, str(response.get('opening_id', season_id)), request_id,
         serialized, encoded({'idempotency_key': key})))


def ensure_wallet(conn, account_id, season_id):
    conn.execute('INSERT OR IGNORE INTO v4_case_wallets(season_id,account_id) VALUES (?,?)', (season_id, account_id))


def record(conn, actor, account_id, season_id, operation, before, after, details):
    # Кейсы REP не меняют, но журнал хранит REP после операции: иначе строка
    # кейса после первой оценки дневника показывала бы в rep_after ложный ноль.
    rep = conn.execute('SELECT rep FROM v4_case_wallets WHERE season_id=? AND account_id=?',
                       (season_id, account_id)).fetchone()
    cursor = conn.execute('''INSERT INTO v4_economy_operations(season_id,account_id,actor_account_id,
        operation,stars_delta,scans_delta,rep_delta,stars_after,scans_after,rep_after,details_json)
        VALUES (?,?,?,?,?,?,0,?,?,?,?)''',
        (season_id, account_id, actor, operation, after['stars']-before['stars'], after['scans']-before['scans'],
         after['stars'], after['scans'], rep['rep'] if rep else 0, encoded(details)))
    return cursor.lastrowid


def open_case(conn, actor, season_id, key, request_id=None):
    authorize(conn, actor, season_id)
    key, digest, old = replay(conn, actor, 'case.open', key, {'season_id': season_id})
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, write=True)
    before = wallet(conn, actor, season_id)
    if before['scans'] < rules()['scan_cost']:
        raise CaseError('Нет попыток. Их выдаёт организатор.', 409)
    ensure_wallet(conn, actor, season_id)
    tier = weighted(rules()['tiers'])
    prize = weighted(tier['prizes'])
    guard_used = False
    if prize['code'] == 'empty':
        guard = conn.execute('''SELECT quantity FROM v4_case_inventory
            WHERE season_id=? AND account_id=? AND item_code='fate_guard' ''', (season_id, actor)).fetchone()
        if guard and guard['quantity'] > 0:
            conn.execute('''UPDATE v4_case_inventory SET quantity=quantity-1
                WHERE season_id=? AND account_id=? AND item_code='fate_guard' ''', (season_id, actor))
            prize = weighted([p for p in tier['prizes'] if p['code'] != 'empty'])
            guard_used = True
    after = {'stars': before['stars'], 'scans': before['scans'] - rules()['scan_cost']}
    reward = prize['reward']
    if reward['kind'] == 'stars':
        after['stars'] += reward['amount']
    elif reward['kind'] == 'scan':
        after['scans'] = min(rules()['scan_cap'], after['scans'] + reward['amount'])
    elif reward['kind'] == 'item':
        conn.execute('''INSERT INTO v4_case_inventory(season_id,account_id,item_code,quantity,effect_state)
            VALUES (?,?,?,1,?) ON CONFLICT(season_id,account_id,item_code)
            DO UPDATE SET quantity=quantity+1''',
            (season_id, actor, prize['code'], reward['effect_state']))
    conn.execute('UPDATE v4_case_wallets SET stars=?,scans=? WHERE season_id=? AND account_id=?',
                 (after['stars'], after['scans'], season_id, actor))
    details = {'prize': prize, 'tier': tier['code'], 'guard_used': guard_used,
               'rules_version': rules()['rules_version']}
    opening_id = record(conn, actor, actor, season_id, 'case.open', before, after, details)
    response = {'opening_id': opening_id, 'season_id': season_id, **after, **details}
    finish(conn, actor, season_id, 'case.open', key, digest, response, request_id)
    return response, False


def roster(conn, actor, season_id):
    authorize(conn, actor, season_id, manage=True)
    members = conn.execute('''SELECT a.id, a.display_name, COALESCE(w.scans,0) AS scans
        FROM v4_season_memberships m JOIN v4_accounts a ON a.id=m.account_id
        LEFT JOIN v4_case_wallets w ON w.season_id=m.season_id AND w.account_id=m.account_id
        WHERE m.season_id=? AND m.status='active' AND a.status='active' ORDER BY a.display_name,a.id''', (season_id,)).fetchall()
    groups = conn.execute("SELECT id,name FROM v4_groups WHERE season_id=? AND status='active' ORDER BY name", (season_id,)).fetchall()
    return {'members': [dict(r) for r in members], 'groups': [dict(r) for r in groups]}


def grant(conn, actor, season_id, key, account_ids, group_id, amount, reason, request_id=None):
    authorize(conn, actor, season_id, manage=True)
    account_ids = sorted(set(account_ids))
    reason = reason.strip()
    if bool(account_ids) == bool(group_id) or not 1 <= amount <= 7 or not 1 <= len(reason) <= 300:
        raise CaseError('Выберите участников или одну группу, 1–7 попыток и укажите причину.')
    payload = {'season_id': season_id, 'account_ids': account_ids, 'group_id': group_id, 'amount': amount, 'reason': reason}
    key, digest, old = replay(conn, actor, 'case.grant', key, payload)
    if old is not None:
        return old, True
    authorize(conn, actor, season_id, manage=True, write=True)
    if group_id:
        group = conn.execute("SELECT id FROM v4_groups WHERE id=? AND season_id=? AND status='active'", (group_id, season_id)).fetchone()
        if not group:
            raise CaseError('Группа недоступна в этом сезоне.', 404)
        account_ids = [r['account_id'] for r in conn.execute('''SELECT m.account_id FROM v4_group_memberships gm
            JOIN v4_season_memberships m ON m.id=gm.season_membership_id
            JOIN v4_accounts a ON a.id=m.account_id
            WHERE gm.group_id=? AND gm.season_id=? AND gm.left_at IS NULL
            AND gm.membership_role IN ('member','leader') AND m.status='active' AND a.status='active'
            ORDER BY m.account_id''', (group_id, season_id))]
    if not account_ids:
        raise CaseError('Нет активных участников для выдачи.')
    for target in account_ids:
        authorize(conn, target, season_id, write=True)
    results = []
    for target in account_ids:
        before = wallet(conn, target, season_id)
        ensure_wallet(conn, target, season_id)
        after = {**before, 'scans': min(7, before['scans'] + amount)}
        conn.execute('UPDATE v4_case_wallets SET scans=? WHERE season_id=? AND account_id=?', (after['scans'], season_id, target))
        delta = after['scans']-before['scans']
        record(conn, actor, target, season_id, 'case.grant', before, after,
               {'requested': amount, 'granted': delta, 'reason': reason, 'group_id': group_id})
        results.append({'account_id': target, 'requested': amount, 'granted': delta, 'scans': after['scans']})
    response = {'season_id': season_id, 'results': results, 'reason': reason}
    finish(conn, actor, season_id, 'case.grant', key, digest, response, request_id)
    return response, False
