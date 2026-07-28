CREATE TABLE IF NOT EXISTS invite_codes (
    id TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    redeemed_by_user_id TEXT REFERENCES users(id),
    redeemed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (code_hash)
);

CREATE INDEX IF NOT EXISTS ix_invite_codes_status_expires_at
    ON invite_codes (status, expires_at);
