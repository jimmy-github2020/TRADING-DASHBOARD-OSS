CREATE TABLE IF NOT EXISTS daily_notes (
  id SERIAL PRIMARY KEY,
  note_date DATE NOT NULL UNIQUE,
  content TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_daily_notes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS daily_notes_set_updated_at ON daily_notes;

CREATE TRIGGER daily_notes_set_updated_at
BEFORE UPDATE ON daily_notes
FOR EACH ROW
EXECUTE FUNCTION update_daily_notes_updated_at();
