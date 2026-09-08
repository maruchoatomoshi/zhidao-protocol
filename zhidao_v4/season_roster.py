"""Explicit, dry-run-first seasonal enrollment for existing local accounts.

Like provision/roles, this is a short manual maintenance transaction, never
a bot/background writer. It does not issue currency or attempts.
"""
import argparse
import json

from .auth import utc_text
from .cases import CaseError, encoded
from .db import connect_database, immediate_transaction


def configure(conn, *, season_code, actor_id, account_ids, group_code=None,
              group_name=None, activate=False, apply=False):
    actor = conn.execute("SELECT 1 FROM v4_accounts a JOIN v4_role_assignments r ON r.account_id=a.id WHERE a.id=? AND a.status='active' AND r.role_code='system_admin' AND r.season_id IS NULL AND r.revoked_at IS NULL", (actor_id,)).fetchone()
    if not actor:
        raise CaseError('An active global system_admin actor is required', 403)
    season = conn.execute('SELECT * FROM v4_seasons WHERE code=?', (season_code,)).fetchone()
    if not season or season['status'] not in ('draft', 'active'):
        raise CaseError('An existing draft or active season is required')
    if bool(group_code) != bool(group_name):
        raise CaseError('Pass both group-code and group-name')
    group = conn.execute('SELECT * FROM v4_groups WHERE season_id=? AND code=?', (season['id'], group_code)).fetchone() if group_code else None
    if group and (group['status'] != 'active' or group['name'] != group_name):
        raise CaseError('Existing group differs; refusing to overwrite it')
    accounts = []
    for account_id in sorted(set(account_ids)):
        account = conn.execute("SELECT id,display_name FROM v4_accounts WHERE id=? AND status='active'", (account_id,)).fetchone()
        member = conn.execute('SELECT * FROM v4_season_memberships WHERE season_id=? AND account_id=?', (season['id'], account_id)).fetchone()
        if not account or (member and member['status'] not in ('invited', 'active')):
            raise CaseError(f'Account {account_id} unavailable or membership already ended')
        if member and group_code:
            previous = conn.execute("SELECT group_id FROM v4_group_memberships WHERE season_membership_id=? AND left_at IS NULL AND membership_role IN ('member','leader')", (member['id'],)).fetchone()
            if previous and (not group or previous['group_id'] != group['id']):
                raise CaseError(f'Account {account_id} already belongs to another group; refusing to move it')
        accounts.append(dict(account))
    report = {'apply': apply, 'season_id': season['id'], 'season_code': season_code,
              'activate': activate, 'accounts': accounts, 'group': group_code, 'starting_stars': 0, 'starting_scans': 0}
    if not apply:
        return report
    now = utc_text()
    if group_code and not group:
        gid = conn.execute('INSERT INTO v4_groups(season_id,code,name,created_by_account_id) VALUES (?,?,?,?)', (season['id'], group_code, group_name, actor_id)).lastrowid
    else:
        gid = group['id'] if group else None
    for account in accounts:
        conn.execute("INSERT INTO v4_season_memberships(season_id,account_id,status,joined_at) VALUES (?,?,'active',?) ON CONFLICT(season_id,account_id) DO UPDATE SET status='active',joined_at=COALESCE(v4_season_memberships.joined_at,excluded.joined_at)", (season['id'], account['id'], now))
        if gid:
            mid = conn.execute('SELECT id FROM v4_season_memberships WHERE season_id=? AND account_id=?', (season['id'], account['id'])).fetchone()['id']
            conn.execute('''INSERT INTO v4_group_memberships(season_id,group_id,season_membership_id)
                SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM v4_group_memberships
                WHERE group_id=? AND season_membership_id=? AND left_at IS NULL)''', (season['id'], gid, mid, gid, mid))
    if activate and season['status'] == 'draft':
        conn.execute("UPDATE v4_seasons SET status='active',activated_at=?,updated_at=?,revision=revision+1 WHERE id=?", (now, now, season['id']))
    conn.execute("INSERT INTO v4_audit_log(actor_account_id,season_id,action,entity_type,entity_id,after_json) VALUES (?,?,'season.roster_configured','season',?,?)", (actor_id, season['id'], str(season['id']), encoded(report)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--season', required=True)
    parser.add_argument('--actor-id', type=int, required=True)
    parser.add_argument('--account-ids', type=int, nargs='+', required=True)
    parser.add_argument('--group-code')
    parser.add_argument('--group-name')
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Write the previously reviewed configuration; otherwise dry-run')
    args = parser.parse_args()
    conn = connect_database(args.db)
    try:
        with immediate_transaction(conn):
            result = configure(conn, season_code=args.season, actor_id=args.actor_id,
                account_ids=args.account_ids, group_code=args.group_code, group_name=args.group_name,
                activate=args.activate, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
