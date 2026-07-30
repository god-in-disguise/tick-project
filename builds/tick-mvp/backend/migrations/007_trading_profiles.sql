ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_trading_mode TEXT NOT NULL DEFAULT 'live';

CREATE TABLE IF NOT EXISTS trading_profiles (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    mode TEXT NOT NULL,
    current_season INTEGER NOT NULL DEFAULT 1,
    starting_balance_usd NUMERIC,
    balance_usd NUMERIC,
    reset_count INTEGER NOT NULL DEFAULT 0,
    last_reset_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, mode),
    CHECK (mode IN ('live', 'demo')),
    CHECK (current_season > 0),
    CHECK (balance_usd IS NULL OR balance_usd >= 0)
);

CREATE TABLE IF NOT EXISTS demo_profile_resets (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES trading_profiles(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    ended_season INTEGER NOT NULL,
    starting_balance_usd NUMERIC NOT NULL,
    ending_balance_usd NUMERIC NOT NULL,
    realized_pnl_usd NUMERIC NOT NULL,
    trade_count INTEGER NOT NULL,
    win_count INTEGER NOT NULL,
    reset_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (profile_id, ended_season)
);

INSERT INTO trading_profiles (
    id,
    user_id,
    mode,
    current_season,
    starting_balance_usd,
    balance_usd
)
SELECT
    'profile_live_' || md5(id),
    id,
    'live',
    1,
    NULL,
    NULL
FROM users
ON CONFLICT (user_id, mode) DO NOTHING;

INSERT INTO trading_profiles (
    id,
    user_id,
    mode,
    current_season,
    starting_balance_usd,
    balance_usd
)
SELECT
    'profile_demo_' || md5(id),
    id,
    'demo',
    1,
    1000,
    1000
FROM users
ON CONFLICT (user_id, mode) DO NOTHING;

ALTER TABLE quotes
    ADD COLUMN IF NOT EXISTS trading_mode TEXT NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS profile_season INTEGER NOT NULL DEFAULT 1;

ALTER TABLE trade_intents
    ADD COLUMN IF NOT EXISTS trading_mode TEXT NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS profile_season INTEGER NOT NULL DEFAULT 1;

ALTER TABLE execution_attempts
    ADD COLUMN IF NOT EXISTS trading_mode TEXT NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS profile_season INTEGER NOT NULL DEFAULT 1;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS trading_mode TEXT NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS profile_season INTEGER NOT NULL DEFAULT 1;

ALTER TABLE ledger_events
    ADD COLUMN IF NOT EXISTS trading_mode TEXT NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS profile_season INTEGER NOT NULL DEFAULT 1;

ALTER TABLE trade_intents
    DROP CONSTRAINT IF EXISTS trade_intents_user_id_idempotency_key_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_intents_profile_idempotency
    ON trade_intents (user_id, trading_mode, profile_season, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_profiles_user_mode
    ON trading_profiles (user_id, mode);

CREATE INDEX IF NOT EXISTS idx_demo_profile_resets_user_time
    ON demo_profile_resets (user_id, reset_at DESC);

CREATE INDEX IF NOT EXISTS idx_positions_profile_status
    ON positions (user_id, trading_mode, profile_season, status);

CREATE INDEX IF NOT EXISTS idx_trade_intents_profile_created
    ON trade_intents (user_id, trading_mode, profile_season, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_execution_attempts_profile_created
    ON execution_attempts (user_id, trading_mode, profile_season, created_at DESC);
