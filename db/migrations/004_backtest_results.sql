CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS backtest_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  strategy_id TEXT,
  symbols TEXT[],
  start_date DATE,
  end_date DATE,
  timeframe TEXT,
  initial_capital DOUBLE PRECISION,
  commission DOUBLE PRECISION,
  total_return_pct DOUBLE PRECISION,
  annual_return_pct DOUBLE PRECISION,
  sharpe_ratio DOUBLE PRECISION,
  max_drawdown_pct DOUBLE PRECISION,
  win_rate DOUBLE PRECISION,
  total_trades INTEGER,
  avg_holding_days DOUBLE PRECISION,
  profit_factor DOUBLE PRECISION,
  equity_curve JSONB,
  trades JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_backtest_results_created_at
  ON backtest_results (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy_id
  ON backtest_results (strategy_id, created_at DESC);
