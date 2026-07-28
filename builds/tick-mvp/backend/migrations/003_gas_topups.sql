CREATE TABLE IF NOT EXISTS gas_topups (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    wallet_id TEXT NOT NULL REFERENCES wallet_accounts(id),
    amount_native NUMERIC NOT NULL,
    status TEXT NOT NULL,
    nonce BIGINT,
    tx_hash TEXT,
    gas_cost_native NUMERIC,
    error TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gas_topups_wallet_created
    ON gas_topups (wallet_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_gas_topups_wallet_active
    ON gas_topups (wallet_id)
    WHERE status IN ('created', 'signed', 'broadcast', 'unknown');

CREATE INDEX IF NOT EXISTS idx_ledger_events_user_gas
    ON ledger_events (user_id, event_type, asset);
