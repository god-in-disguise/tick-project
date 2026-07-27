ALTER TABLE quotes
    ADD COLUMN IF NOT EXISTS take_profit_usd NUMERIC,
    ADD COLUMN IF NOT EXISTS take_profit_price NUMERIC;

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS take_profit_price NUMERIC;
