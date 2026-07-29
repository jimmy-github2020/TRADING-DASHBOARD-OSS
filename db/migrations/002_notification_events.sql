CREATE TABLE IF NOT EXISTS notification_events (
  id BIGSERIAL PRIMARY KEY,
  channel TEXT NOT NULL,
  event_type TEXT NOT NULL,
  symbol TEXT,
  provider TEXT,
  timeframe TEXT,
  payload JSONB NOT NULL,
  sent_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notification_events_cooldown
  ON notification_events (event_type, provider, symbol, timeframe, created_at DESC);
