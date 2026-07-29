CREATE TABLE IF NOT EXISTS app_settings (
  key VARCHAR(80) PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO app_settings (key, value, updated_at)
VALUES ('notification_dry_run', 'true'::jsonb, now())
ON CONFLICT (key) DO NOTHING;
