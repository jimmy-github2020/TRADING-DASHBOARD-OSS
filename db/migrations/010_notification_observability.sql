CREATE TABLE IF NOT EXISTS notification_job_runs (
  id SERIAL PRIMARY KEY,
  job_name VARCHAR(80) NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ NOT NULL,
  duration_ms INTEGER NOT NULL,
  targets_scanned INTEGER NOT NULL DEFAULT 0,
  disabled_skipped_count INTEGER NOT NULL DEFAULT 0,
  frequency_skipped_count INTEGER NOT NULL DEFAULT 0,
  triggered_count INTEGER NOT NULL DEFAULT 0,
  dedup_skipped_count INTEGER NOT NULL DEFAULT 0,
  sent_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  final_status VARCHAR(30) NOT NULL,
  metadata_json JSONB
);

CREATE TABLE IF NOT EXISTS notification_runtime_events (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  job_name VARCHAR(80),
  notification_type VARCHAR(80) NOT NULL,
  status VARCHAR(30) NOT NULL,
  skip_reason VARCHAR(80),
  symbol VARCHAR(40),
  topic VARCHAR(120),
  message_preview TEXT,
  chat_id VARCHAR(50),
  dedup_key VARCHAR(220),
  metadata_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_notification_job_runs_finished_at
  ON notification_job_runs (finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_runtime_events_created_at
  ON notification_runtime_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_runtime_events_status
  ON notification_runtime_events (status, created_at DESC);
