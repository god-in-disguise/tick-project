ALTER TABLE invite_codes
    ADD COLUMN IF NOT EXISTS display_name TEXT;
