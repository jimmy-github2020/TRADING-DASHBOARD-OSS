# Instrument Catalog

T8-1 introduces a canonical instrument catalog without replacing the existing
`symbols` table or changing current dashboard behavior.

## Tables

- `instruments` stores one provider-neutral canonical record per market and
  symbol. Taiwan securities use their exchange-native code (for example,
  `2330`).
- `instrument_provider_symbols` maps provider-specific identifiers to an
  instrument, such as Yahoo Finance's `2330.TW`.
- `portfolio_holdings.instrument_id` links existing holdings to the catalog
  while preserving the legacy `symbol` column.

The migration seeds the catalog from both `symbols` and `portfolio_holdings`.
Existing tracked symbols retain their provider mapping. Portfolio holdings that
are not currently tracked receive a yfinance mapping so later phases can opt
them into ingestion.

## Compatibility

- `/api/v1/symbols` continues to return the legacy tracked universe.
- Market OHLCV rows continue to use their existing symbol/provider keys.
- Dashboard watchlist behavior is unchanged in T8-1.
- New code should use `/api/v1/instruments` for catalog discovery and
  `/api/v1/instruments/resolve` for provider-symbol resolution.

## Follow-up

T8-2 and T8-3 will populate the catalog from official Taiwan and U.S. universe
sources. Later migrations can move OHLCV and watchlist ownership to
`instrument_id` after compatibility has been verified.

## Taiwan catalog synchronization

T8-2 synchronizes listed-company metadata from the TWSE and TPEx OpenAPI
endpoints. It writes only instrument metadata and provider mappings; it does not
enroll the full catalog into OHLCV ingestion.

Manual validation:

```bash
python main.py sync-instruments --source all --dry-run
```

Manual write:

```bash
python main.py sync-instruments --source all
```

The worker also runs the write job at 18:30 Asia/Taipei on weekdays. TWSE and
TPEx are isolated so one provider outage does not block the other. Each write
attempt is recorded in `instrument_sync_runs`.

T8-3 adds the Nasdaq Trader symbol directory without enrolling the U.S.
catalog in OHLCV ingestion. Nasdaq-listed and other-listed files are fetched
independently. Exchange-native symbols remain canonical, while provider
differences such as `BRK.B` to Yahoo Finance's `BRK-B` are represented by
provider mappings.

```bash
python main.py sync-instruments --market us --source all --dry-run
python main.py sync-instruments --market us --source all
```

The U.S. metadata job runs Tuesday through Saturday at 07:30 Asia/Taipei.

## Storage controls

Watchlist items use one of four tracking tiers:

- `catalog`: metadata only, no market-data ingestion.
- `quote`: five recent daily rows, refreshed with the snapshot cycle.
- `daily`: up to one year (260 rows) of daily OHLCV.
- `intraday`: daily data plus up to 200 hourly rows.

`GET /api/v1/instruments/stats` reports catalog counts, effective tracking
tiers, recent sync runs, actual PostgreSQL relation sizes, and a conservative
projection using 768 bytes per tracked OHLCV row. The estimate intentionally
overstates typical compressed TimescaleDB usage and should be used as a guard,
not as an exact storage forecast.
