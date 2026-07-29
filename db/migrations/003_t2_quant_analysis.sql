CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS strategies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  conditions JSONB NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol VARCHAR NOT NULL,
  strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
  triggered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  direction VARCHAR NOT NULL CHECK (direction IN ('long', 'short', 'neutral')),
  price NUMERIC NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_strategies_active
  ON strategies (is_active, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_strategy_time
  ON signals (strategy_id, triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_time
  ON signals (symbol, triggered_at DESC);
