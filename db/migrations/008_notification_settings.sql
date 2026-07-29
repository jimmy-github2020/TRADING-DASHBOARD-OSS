CREATE TABLE IF NOT EXISTS notification_settings (
  id SERIAL PRIMARY KEY,
  chat_id VARCHAR(50) UNIQUE NOT NULL,
  morning_brief BOOLEAN NOT NULL DEFAULT true,
  midday_flash BOOLEAN NOT NULL DEFAULT true,
  closing_report BOOLEAN NOT NULL DEFAULT true,
  alerts_enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS price_alerts (
  id SERIAL PRIMARY KEY,
  chat_id VARCHAR(50) NOT NULL,
  symbol VARCHAR(20) NOT NULL,
  alert_type VARCHAR(20) NOT NULL CHECK (alert_type IN ('above', 'below')),
  threshold NUMERIC(12, 4) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  triggered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id SERIAL PRIMARY KEY,
  chat_id VARCHAR(50) NOT NULL,
  notification_type VARCHAR(50) NOT NULL,
  message_preview TEXT,
  status VARCHAR(20) NOT NULL CHECK (status IN ('sent', 'failed', 'dry_run')),
  error_message TEXT,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_price_alerts_active_symbol
  ON price_alerts (is_active, symbol);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_chat_sent_at
  ON notification_deliveries (chat_id, sent_at DESC);
