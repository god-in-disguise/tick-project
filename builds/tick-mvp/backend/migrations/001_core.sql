CREATE TABLE IF NOT EXISTS wallet_accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chain_id INTEGER NOT NULL,
    address TEXT NOT NULL,
    wallet_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chain_id, address)
);

CREATE TABLE IF NOT EXISTS quotes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    ticket_usd NUMERIC NOT NULL,
    leverage NUMERIC NOT NULL,
    notional_usd NUMERIC NOT NULL,
    max_loss_usd NUMERIC,
    estimated_open_cost_usd NUMERIC NOT NULL DEFAULT 0,
    estimated_close_cost_usd NUMERIC NOT NULL DEFAULT 0,
    estimated_round_trip_cost_usd NUMERIC NOT NULL DEFAULT 0,
    liquidation_price NUMERIC,
    stop_loss_price NUMERIC,
    opening_allowed BOOLEAN NOT NULL DEFAULT false,
    risk_decision_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_intents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    quote_id TEXT REFERENCES quotes(id),
    position_id TEXT,
    market TEXT NOT NULL,
    side TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS execution_attempts (
    id TEXT PRIMARY KEY,
    trade_intent_id TEXT NOT NULL REFERENCES trade_intents(id),
    user_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    nonce BIGINT,
    tx_hash TEXT,
    raw_tx_ref TEXT,
    error TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    status TEXT NOT NULL,
    quote_id TEXT REFERENCES quotes(id),
    open_intent_id TEXT REFERENCES trade_intents(id),
    close_intent_id TEXT REFERENCES trade_intents(id),
    ticket_usd NUMERIC NOT NULL,
    leverage NUMERIC NOT NULL,
    notional_usd NUMERIC NOT NULL,
    entry_price NUMERIC,
    stop_loss_price NUMERIC,
    liquidation_price NUMERIC,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS venue_events (
    id TEXT PRIMARY KEY,
    position_id TEXT REFERENCES positions(id),
    execution_attempt_id TEXT REFERENCES execution_attempts(id),
    venue TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    chain_id INTEGER,
    block_number BIGINT,
    block_hash TEXT,
    transaction_hash TEXT,
    log_index INTEGER,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chain_id, transaction_hash, log_index)
);

CREATE TABLE IF NOT EXISTS reconciliations (
    id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL REFERENCES positions(id),
    status TEXT NOT NULL,
    venue_realized_pnl_usd NUMERIC,
    wallet_delta_usd NUMERIC,
    difference_usd NUMERIC,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ledger_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    position_id TEXT REFERENCES positions(id),
    event_type TEXT NOT NULL,
    asset TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    source TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_intents_user_created
    ON trade_intents (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_execution_attempts_intent
    ON execution_attempts (trade_intent_id);

CREATE INDEX IF NOT EXISTS idx_positions_user_status
    ON positions (user_id, status);

CREATE INDEX IF NOT EXISTS idx_venue_events_position
    ON venue_events (position_id, observed_at DESC);

