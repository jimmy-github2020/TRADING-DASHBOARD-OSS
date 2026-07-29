BEGIN;

CREATE TABLE IF NOT EXISTS instrument_sync_runs (
  id BIGSERIAL PRIMARY KEY,
  market VARCHAR(20) NOT NULL,
  source VARCHAR(40) NOT NULL,
  status VARCHAR(20) NOT NULL,
  rows_seen INTEGER NOT NULL DEFAULT 0,
  rows_inserted INTEGER NOT NULL DEFAULT 0,
  rows_updated INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CONSTRAINT instrument_sync_runs_status_check
    CHECK (status IN ('running', 'success', 'partial', 'failed', 'dry_run'))
);

CREATE INDEX IF NOT EXISTS idx_instrument_sync_runs_source_started
  ON instrument_sync_runs (market, source, started_at DESC);

COMMIT;
