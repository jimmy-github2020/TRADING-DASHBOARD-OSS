CREATE TABLE IF NOT EXISTS alert_rules (
  id SERIAL PRIMARY KEY,
  rule_key VARCHAR(80) UNIQUE NOT NULL,
  name VARCHAR(120) NOT NULL,
  category VARCHAR(30) NOT NULL,
  metric_source VARCHAR(40) NOT NULL,
  operator VARCHAR(30) NOT NULL,
  threshold_value NUMERIC(14,4),
  threshold_min NUMERIC(14,4),
  threshold_max NUMERIC(14,4),
  comparison_window VARCHAR(30) NOT NULL DEFAULT 'latest',
  enabled BOOLEAN NOT NULL DEFAULT true,
  severity VARCHAR(20) NOT NULL DEFAULT 'warning',
  notify_enabled BOOLEAN NOT NULL DEFAULT true,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO alert_rules (
  rule_key, name, category, metric_source, operator, threshold_value,
  threshold_min, threshold_max, comparison_window, enabled, severity,
  notify_enabled, description
)
VALUES
  (
    'twii_pct_move',
    'TWII 漲跌幅警示',
    'market',
    'twii',
    'outside_range',
    NULL,
    -2.0,
    2.0,
    '1d',
    true,
    'warning',
    true,
    '台灣加權指數單日漲跌幅超出設定區間時提醒。'
  ),
  (
    'vix_high',
    'VIX 高波動警示',
    'macro',
    'vix',
    'gte',
    25.0,
    NULL,
    NULL,
    'latest',
    true,
    'warning',
    true,
    'VIX 高於設定門檻時提醒市場波動升溫。'
  ),
  (
    'fear_greed_extreme',
    'Fear & Greed 極端警示',
    'macro',
    'fear_greed',
    'outside_range',
    NULL,
    20.0,
    80.0,
    'latest',
    true,
    'warning',
    true,
    'Fear & Greed 指數進入極端恐懼或極端貪婪區間時提醒。'
  ),
  (
    'oil_price_pct_move',
    '油價單日波動警示',
    'macro',
    'oil',
    'outside_range',
    NULL,
    -3.0,
    3.0,
    '1d',
    false,
    'info',
    true,
    'Brent 原油期貨單日波動超出設定區間時提醒，預設停用。'
  )
ON CONFLICT (rule_key) DO NOTHING;
