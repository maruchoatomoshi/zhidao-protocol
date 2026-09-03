-- ZHIDAO Protocol V4 foundation.
-- All names are prefixed with v4_ so this migration can safely coexist with
-- an intact Legacy Travel database.

CREATE TABLE v4_identity_providers (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    )
);

INSERT INTO v4_identity_providers(code, display_name, is_enabled) VALUES
    ('local', 'ZHIDAO account', 1),
    ('telegram', 'Telegram', 1),
    ('max', 'MAX', 0);

CREATE TABLE v4_accounts (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('pending', 'active', 'disabled')),
    locale TEXT NOT NULL DEFAULT 'ru',
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    updated_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    disabled_at TEXT,
    CHECK (length(trim(public_id)) >= 8),
    CHECK (length(trim(display_name)) >= 1),
    CHECK (status = 'disabled' OR disabled_at IS NULL)
);

CREATE TABLE v4_external_identities (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    provider_code TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    provider_username TEXT,
    verified_at TEXT,
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    metadata_json TEXT,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (provider_code) REFERENCES v4_identity_providers(code) ON DELETE RESTRICT,
    UNIQUE (provider_code, provider_subject),
    UNIQUE (account_id, provider_code),
    CHECK (length(trim(provider_subject)) >= 1),
    CHECK (metadata_json IS NULL OR json_valid(metadata_json))
);

CREATE INDEX v4_external_identities_account_idx
    ON v4_external_identities(account_id);

CREATE TABLE v4_seasons (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'closed', 'archived')),
    starts_on TEXT,
    ends_on TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    theme_key TEXT,
    created_by_account_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    updated_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    activated_at TEXT,
    closed_at TEXT,
    archived_at TEXT,
    metadata_json TEXT,
    FOREIGN KEY (created_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (length(trim(code)) >= 2),
    CHECK (length(trim(name)) >= 1),
    CHECK (starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on),
    CHECK (metadata_json IS NULL OR json_valid(metadata_json))
);

CREATE TABLE v4_season_memberships (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    member_number INTEGER,
    profile_name TEXT,
    status TEXT NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'active', 'completed', 'withdrawn')),
    joined_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    metadata_json TEXT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    UNIQUE (season_id, account_id),
    UNIQUE (id, season_id),
    CHECK (member_number IS NULL OR member_number > 0),
    CHECK (profile_name IS NULL OR length(trim(profile_name)) >= 1),
    CHECK (metadata_json IS NULL OR json_valid(metadata_json))
);

CREATE UNIQUE INDEX v4_season_member_number_uq
    ON v4_season_memberships(season_id, member_number)
    WHERE member_number IS NOT NULL;

CREATE INDEX v4_season_memberships_account_idx
    ON v4_season_memberships(account_id, season_id);

CREATE TABLE v4_roles (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    is_system INTEGER NOT NULL DEFAULT 1 CHECK (is_system IN (0, 1))
);

INSERT INTO v4_roles(code, display_name, description) VALUES
    ('participant', 'Участник', 'Профиль, сезонные активности, коллекция и рейтинг'),
    ('operator', 'Оператор', 'Безопасные типовые операции поездки'),
    ('architect', 'Архитектор', 'Сложная настройка событий, контента и экономики'),
    ('system_admin', 'Системный администратор', 'Роли, сезоны и техническая конфигурация');

CREATE TABLE v4_role_assignments (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    role_code TEXT NOT NULL,
    season_id INTEGER,
    granted_by_account_id INTEGER,
    granted_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    revoked_at TEXT,
    reason TEXT,
    FOREIGN KEY (account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (role_code) REFERENCES v4_roles(code) ON DELETE RESTRICT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (granted_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);

CREATE UNIQUE INDEX v4_active_global_role_uq
    ON v4_role_assignments(account_id, role_code)
    WHERE season_id IS NULL AND revoked_at IS NULL;

CREATE UNIQUE INDEX v4_active_season_role_uq
    ON v4_role_assignments(account_id, role_code, season_id)
    WHERE season_id IS NOT NULL AND revoked_at IS NULL;

CREATE INDEX v4_role_assignments_season_idx
    ON v4_role_assignments(season_id, role_code, account_id);

CREATE TABLE v4_groups (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    capacity INTEGER,
    created_by_account_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    updated_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    UNIQUE (season_id, code),
    UNIQUE (id, season_id),
    CHECK (length(trim(code)) >= 1),
    CHECK (length(trim(name)) >= 1),
    CHECK (capacity IS NULL OR capacity > 0)
);

CREATE TABLE v4_group_memberships (
    id INTEGER PRIMARY KEY,
    season_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    season_membership_id INTEGER NOT NULL,
    membership_role TEXT NOT NULL DEFAULT 'member'
        CHECK (membership_role IN ('member', 'leader', 'operator')),
    joined_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    left_at TEXT,
    FOREIGN KEY (group_id, season_id) REFERENCES v4_groups(id, season_id) ON DELETE RESTRICT,
    FOREIGN KEY (season_membership_id, season_id)
        REFERENCES v4_season_memberships(id, season_id) ON DELETE RESTRICT,
    CHECK (left_at IS NULL OR left_at >= joined_at)
);

CREATE UNIQUE INDEX v4_active_group_membership_uq
    ON v4_group_memberships(group_id, season_membership_id)
    WHERE left_at IS NULL;

CREATE UNIQUE INDEX v4_one_active_participant_group_uq
    ON v4_group_memberships(season_id, season_membership_id)
    WHERE left_at IS NULL AND membership_role IN ('member', 'leader');

CREATE INDEX v4_group_memberships_member_idx
    ON v4_group_memberships(season_membership_id, left_at);

CREATE TABLE v4_audit_log (
    id INTEGER PRIMARY KEY,
    occurred_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    ),
    actor_account_id INTEGER,
    season_id INTEGER,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    request_id TEXT,
    before_json TEXT,
    after_json TEXT,
    metadata_json TEXT,
    FOREIGN KEY (actor_account_id) REFERENCES v4_accounts(id) ON DELETE RESTRICT,
    FOREIGN KEY (season_id) REFERENCES v4_seasons(id) ON DELETE RESTRICT,
    CHECK (length(trim(action)) >= 1),
    CHECK (length(trim(entity_type)) >= 1),
    CHECK (before_json IS NULL OR json_valid(before_json)),
    CHECK (after_json IS NULL OR json_valid(after_json)),
    CHECK (metadata_json IS NULL OR json_valid(metadata_json))
);

CREATE INDEX v4_audit_log_entity_idx
    ON v4_audit_log(entity_type, entity_id, occurred_at);

CREATE INDEX v4_audit_log_actor_idx
    ON v4_audit_log(actor_account_id, occurred_at);

CREATE TRIGGER v4_audit_log_no_update
BEFORE UPDATE ON v4_audit_log
BEGIN
    SELECT RAISE(ABORT, 'v4_audit_log is append-only');
END;

CREATE TRIGGER v4_audit_log_no_delete
BEFORE DELETE ON v4_audit_log
BEGIN
    SELECT RAISE(ABORT, 'v4_audit_log is append-only');
END;
