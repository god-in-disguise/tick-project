ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_venue TEXT NOT NULL DEFAULT 'gtrade';

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_active_venue_check;

ALTER TABLE users
    ADD CONSTRAINT users_active_venue_check
    CHECK (active_venue IN ('gtrade', 'flash'));

CREATE INDEX IF NOT EXISTS idx_wallet_accounts_user_chain_status
    ON wallet_accounts (user_id, chain_id, status);
