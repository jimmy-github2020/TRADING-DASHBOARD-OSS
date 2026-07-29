BEGIN;

CREATE TABLE IF NOT EXISTS watchlists (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  slug VARCHAR(120) NOT NULL UNIQUE,
  description TEXT,
  is_default BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlists_default
  ON watchlists (is_default)
  WHERE is_default = true;

CREATE TABLE IF NOT EXISTS watchlist_items (
  id BIGSERIAL PRIMARY KEY,
  watchlist_id BIGINT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  instrument_id BIGINT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
  tracking_tier VARCHAR(20) NOT NULL DEFAULT 'quote',
  sort_order INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT watchlist_items_tracking_tier_check
    CHECK (tracking_tier IN ('catalog', 'quote', 'daily', 'intraday')),
  CONSTRAINT uq_watchlist_item UNIQUE (watchlist_id, instrument_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_active
  ON watchlist_items (watchlist_id, is_active, sort_order, id);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_tracking
  ON watchlist_items (tracking_tier, is_active, instrument_id);

INSERT INTO watchlists (name, slug, description, is_default)
VALUES (
  '我的觀察清單',
  'default',
  '由既有持股與觀察標的建立的預設清單',
  true
)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO watchlist_items (
  watchlist_id,
  instrument_id,
  tracking_tier,
  sort_order,
  notes
)
SELECT
  w.id,
  h.instrument_id,
  CASE WHEN h.owned THEN 'daily' ELSE 'quote' END,
  ROW_NUMBER() OVER (ORDER BY h.category, h.id),
  CASE WHEN h.owned THEN '由既有持股匯入' ELSE '由既有觀察標的匯入' END
FROM portfolio_holdings h
CROSS JOIN watchlists w
WHERE w.slug = 'default'
  AND h.instrument_id IS NOT NULL
ON CONFLICT (watchlist_id, instrument_id) DO NOTHING;

COMMIT;
