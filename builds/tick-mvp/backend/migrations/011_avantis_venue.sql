ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_active_venue_check;

ALTER TABLE users
    ADD CONSTRAINT users_active_venue_check
    CHECK (active_venue IN ('gtrade', 'flash', 'avantis'));
