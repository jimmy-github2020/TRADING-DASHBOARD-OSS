CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS ai_market_briefs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_text TEXT NOT NULL,
  data_snapshot JSONB,
  model TEXT DEFAULT 'gpt-4o-mini',
  tokens_used INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_market_briefs_created_at
  ON ai_market_briefs (created_at DESC);
