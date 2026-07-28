CREATE TABLE IF NOT EXISTS market_price_bars_1s (
    venue TEXT NOT NULL,
    market TEXT NOT NULL,
    bucket_at TIMESTAMPTZ NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    sample_count INTEGER NOT NULL,
    first_sequence BIGINT NOT NULL,
    last_sequence BIGINT NOT NULL,
    source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (venue, market, bucket_at)
);

CREATE INDEX IF NOT EXISTS idx_market_price_bars_1s_market_time
    ON market_price_bars_1s (market, bucket_at DESC);
