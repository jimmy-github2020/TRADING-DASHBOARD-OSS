CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS symbols (
  symbol TEXT NOT NULL,
  provider TEXT NOT NULL,
  name TEXT,
  asset_class TEXT NOT NULL,
  exchange TEXT,
  currency TEXT,
  timezone TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, provider)
);

CREATE TABLE IF NOT EXISTS market_ohlcv (
  time TIMESTAMPTZ NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  provider TEXT NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, timeframe, provider, time)
);

SELECT create_hypertable('market_ohlcv', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_market_ohlcv_symbol_time
  ON market_ohlcv (symbol, timeframe, provider, time DESC);

CREATE TABLE IF NOT EXISTS data_ingestion_runs (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  symbol TEXT,
  timeframe TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  rows_inserted INTEGER NOT NULL DEFAULT 0,
  rows_updated INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  message TEXT
);

CREATE TABLE IF NOT EXISTS provider_errors (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  symbol TEXT,
  timeframe TEXT,
  error_type TEXT NOT NULL,
  error_message TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
