BEGIN;

CREATE TABLE IF NOT EXISTS instruments (
  id BIGSERIAL PRIMARY KEY,
  canonical_symbol VARCHAR(64) NOT NULL,
  market VARCHAR(20) NOT NULL,
  exchange VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN',
  security_type VARCHAR(32) NOT NULL,
  name_zh VARCHAR(255),
  name_en VARCHAR(255),
  currency VARCHAR(12),
  timezone VARCHAR(64),
  sector VARCHAR(128),
  industry VARCHAR(128),
  listing_status VARCHAR(20) NOT NULL DEFAULT 'active',
  listed_at DATE,
  delisted_at DATE,
  is_active BOOLEAN NOT NULL DEFAULT true,
  source VARCHAR(40) NOT NULL,
  source_updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT instruments_listing_status_check
    CHECK (listing_status IN ('active', 'inactive', 'suspended', 'delisted', 'unknown'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_instruments_market_symbol
  ON instruments (market, canonical_symbol);

CREATE INDEX IF NOT EXISTS idx_instruments_search
  ON instruments (market, security_type, is_active, canonical_symbol);

CREATE INDEX IF NOT EXISTS idx_instruments_exchange
  ON instruments (exchange, is_active);

CREATE TABLE IF NOT EXISTS instrument_provider_symbols (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
  provider VARCHAR(40) NOT NULL,
  provider_symbol VARCHAR(64) NOT NULL,
  is_primary BOOLEAN NOT NULL DEFAULT true,
  is_active BOOLEAN NOT NULL DEFAULT true,
  valid_from DATE,
  valid_to DATE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT instrument_provider_symbols_validity_check
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_instrument_provider_symbol
  ON instrument_provider_symbols (provider, provider_symbol)
  WHERE is_active = true;

CREATE UNIQUE INDEX IF NOT EXISTS uq_instrument_primary_provider
  ON instrument_provider_symbols (instrument_id, provider)
  WHERE is_primary = true AND is_active = true;

CREATE INDEX IF NOT EXISTS idx_instrument_provider_lookup
  ON instrument_provider_symbols (instrument_id, provider, is_active);

INSERT INTO instruments (
  canonical_symbol,
  market,
  exchange,
  security_type,
  name_en,
  currency,
  timezone,
  listing_status,
  is_active,
  source,
  source_updated_at
)
SELECT DISTINCT ON (s.symbol)
  CASE
    WHEN s.symbol LIKE '%.TWO' THEN LEFT(s.symbol, LENGTH(s.symbol) - 4)
    WHEN s.symbol LIKE '%.TW' THEN LEFT(s.symbol, LENGTH(s.symbol) - 3)
    ELSE s.symbol
  END,
  CASE
    WHEN s.asset_class = 'crypto' THEN 'CRYPTO'
    WHEN s.currency = 'TWD'
      OR s.timezone = 'Asia/Taipei'
      OR s.symbol LIKE '%.TW'
      OR s.symbol LIKE '%.TWO'
      THEN 'TW'
    WHEN s.currency = 'USD' THEN 'US'
    ELSE 'GLOBAL'
  END,
  COALESCE(NULLIF(TRIM(s.exchange), ''), 'UNKNOWN'),
  CASE
    WHEN s.asset_class = 'equity' THEN 'stock'
    ELSE s.asset_class
  END,
  s.name,
  s.currency,
  s.timezone,
  CASE WHEN s.is_active THEN 'active' ELSE 'inactive' END,
  s.is_active,
  'legacy_symbols',
  s.updated_at
FROM symbols s
ORDER BY s.symbol, s.is_active DESC, s.updated_at DESC
ON CONFLICT (market, canonical_symbol) DO UPDATE
SET exchange = CASE
      WHEN instruments.exchange = 'UNKNOWN' THEN EXCLUDED.exchange
      ELSE instruments.exchange
    END,
    name_en = COALESCE(instruments.name_en, EXCLUDED.name_en),
    currency = COALESCE(instruments.currency, EXCLUDED.currency),
    timezone = COALESCE(instruments.timezone, EXCLUDED.timezone),
    is_active = instruments.is_active OR EXCLUDED.is_active,
    listing_status = CASE
      WHEN instruments.is_active OR EXCLUDED.is_active THEN 'active'
      ELSE instruments.listing_status
    END,
    source_updated_at = GREATEST(instruments.source_updated_at, EXCLUDED.source_updated_at),
    updated_at = now();

INSERT INTO instruments (
  canonical_symbol,
  market,
  exchange,
  security_type,
  name_zh,
  name_en,
  currency,
  timezone,
  listing_status,
  is_active,
  source,
  source_updated_at
)
SELECT
  CASE
    WHEN h.symbol LIKE '%.TWO' THEN LEFT(h.symbol, LENGTH(h.symbol) - 4)
    WHEN h.symbol LIKE '%.TW' THEN LEFT(h.symbol, LENGTH(h.symbol) - 3)
    ELSE h.symbol
  END,
  CASE
    WHEN h.symbol LIKE '%.TW' OR h.symbol LIKE '%.TWO' THEN 'TW'
    ELSE 'GLOBAL'
  END,
  'UNKNOWN',
  CASE WHEN h.category = 'ETF' THEN 'etf' ELSE 'stock' END,
  h.name_zh,
  h.name_en,
  CASE WHEN h.symbol LIKE '%.TW' OR h.symbol LIKE '%.TWO' THEN 'TWD' ELSE NULL END,
  CASE WHEN h.symbol LIKE '%.TW' OR h.symbol LIKE '%.TWO' THEN 'Asia/Taipei' ELSE NULL END,
  'active',
  true,
  'portfolio_holdings',
  h.updated_at
FROM portfolio_holdings h
ON CONFLICT (market, canonical_symbol) DO UPDATE
SET name_zh = COALESCE(instruments.name_zh, EXCLUDED.name_zh),
    name_en = COALESCE(instruments.name_en, EXCLUDED.name_en),
    security_type = CASE
      WHEN instruments.security_type IN ('stock', 'etf') THEN EXCLUDED.security_type
      ELSE instruments.security_type
    END,
    currency = COALESCE(instruments.currency, EXCLUDED.currency),
    timezone = COALESCE(instruments.timezone, EXCLUDED.timezone),
    updated_at = now();

INSERT INTO instrument_provider_symbols (
  instrument_id,
  provider,
  provider_symbol,
  is_primary,
  is_active,
  metadata
)
SELECT
  i.id,
  s.provider,
  s.symbol,
  true,
  s.is_active,
  jsonb_build_object('migrated_from', 'symbols')
FROM symbols s
JOIN instruments i
  ON i.canonical_symbol = CASE
      WHEN s.symbol LIKE '%.TWO' THEN LEFT(s.symbol, LENGTH(s.symbol) - 4)
      WHEN s.symbol LIKE '%.TW' THEN LEFT(s.symbol, LENGTH(s.symbol) - 3)
      ELSE s.symbol
    END
 AND i.market = CASE
      WHEN s.asset_class = 'crypto' THEN 'CRYPTO'
      WHEN s.currency = 'TWD'
        OR s.timezone = 'Asia/Taipei'
        OR s.symbol LIKE '%.TW'
        OR s.symbol LIKE '%.TWO'
        THEN 'TW'
      WHEN s.currency = 'USD' THEN 'US'
      ELSE 'GLOBAL'
    END
ON CONFLICT (provider, provider_symbol) WHERE is_active = true DO UPDATE
SET instrument_id = EXCLUDED.instrument_id,
    is_active = EXCLUDED.is_active,
    updated_at = now();

INSERT INTO instrument_provider_symbols (
  instrument_id,
  provider,
  provider_symbol,
  is_primary,
  is_active,
  metadata
)
SELECT
  i.id,
  'yfinance',
  h.symbol,
  true,
  true,
  jsonb_build_object('migrated_from', 'portfolio_holdings')
FROM portfolio_holdings h
JOIN instruments i
  ON i.canonical_symbol = CASE
      WHEN h.symbol LIKE '%.TWO' THEN LEFT(h.symbol, LENGTH(h.symbol) - 4)
      WHEN h.symbol LIKE '%.TW' THEN LEFT(h.symbol, LENGTH(h.symbol) - 3)
      ELSE h.symbol
    END
 AND i.market = CASE
      WHEN h.symbol LIKE '%.TW' OR h.symbol LIKE '%.TWO' THEN 'TW'
      ELSE 'GLOBAL'
    END
ON CONFLICT (provider, provider_symbol) WHERE is_active = true DO NOTHING;

ALTER TABLE portfolio_holdings
  ADD COLUMN IF NOT EXISTS instrument_id BIGINT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'portfolio_holdings_instrument_id_fkey'
  ) THEN
    ALTER TABLE portfolio_holdings
      ADD CONSTRAINT portfolio_holdings_instrument_id_fkey
      FOREIGN KEY (instrument_id) REFERENCES instruments(id) ON DELETE RESTRICT;
  END IF;
END
$$;

UPDATE portfolio_holdings h
SET instrument_id = i.id
FROM instruments i
WHERE h.instrument_id IS NULL
  AND i.canonical_symbol = CASE
    WHEN h.symbol LIKE '%.TWO' THEN LEFT(h.symbol, LENGTH(h.symbol) - 4)
    WHEN h.symbol LIKE '%.TW' THEN LEFT(h.symbol, LENGTH(h.symbol) - 3)
    ELSE h.symbol
  END
  AND i.market = CASE
    WHEN h.symbol LIKE '%.TW' OR h.symbol LIKE '%.TWO' THEN 'TW'
    ELSE 'GLOBAL'
  END;

CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_instrument_id
  ON portfolio_holdings (instrument_id);

COMMIT;
