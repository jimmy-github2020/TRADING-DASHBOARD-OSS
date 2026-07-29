# Phase T1A 實作記錄

最後更新時間：2026-06-19

## 目標

建立市場資料入庫服務，讓 worker 能從資料 provider 抓取 OHLCV，寫入 TimescaleDB，並記錄 ingestion 品質與錯誤。

## 已完成

- 建立 worker provider abstraction。
- 建立 `YFinanceProvider`。
- 建立 `BinanceProvider`。
- 建立 `MarketRepository`，負責 symbols、market_ohlcv、data_ingestion_runs、provider_errors。
- 建立 `QuoteCache`，將最新 snapshot 寫入 Redis。
- 建立 `MarketIngestionService`，串接 provider、DB 與 Redis。
- `main.py` 支援：
  - scheduler 模式
  - `run-once`
  - `run-batch`
- APScheduler 加入：
  - 每 15 分鐘 snapshot refresh
  - 每日 06:00 UTC daily refresh

## Provider Universe

### yfinance

- 指數：`^GSPC`, `^NDX`, `^DJI`, `^TWII`, `000001.SS`, `^HSI`
- 商品：`GC=F`, `SI=F`, `CL=F`, `BZ=F`, `HG=F`
- 情緒/利率：`^VIX`, `DX-Y.NYB`, `^TNX`, `^IRX`
- 台股權值股：`2330.TW`, `2317.TW`, `2454.TW`, `2382.TW`, `2308.TW`

### Binance

- `BTCUSDT`
- `ETHUSDT`
- `BNBUSDT`

## 支援 Timeframe

- `1d`
- `1h`

## 預設抓取筆數

最後更新時間：2026-06-19

預設 ingestion limit 已調整為 200。

適用範圍：

- `run-once` 未指定 `--limit` 時使用 200。
- `run-once --all-symbols` 未指定 `--limit` 時使用 200。
- `run-batch --mode daily` 使用 200。
- `run-batch --mode snapshot` 使用 200，yfinance 1h period 使用 `60d`，避免 1h 資料不足。

重抓全部 symbols 的 1d 歷史資料：

```powershell
docker compose exec -T worker python main.py run-once --all-symbols --timeframe 1d
```

## 資料寫入策略

`market_ohlcv` 沿用 T0 schema：

```text
PRIMARY KEY (symbol, timeframe, provider, time)
```

寫入使用 upsert：

- 新 K 線：insert
- 已存在但 OHLCV 變更：update
- 完全相同：略過

每次 ingestion 會建立一筆 `data_ingestion_runs`，成功時寫入 `rows_inserted`、`rows_updated` 與 `rows_seen`；失敗時寫入 `provider_errors`，並將 run 標示為 `error`。

## Redis Snapshot

Redis key 格式：

```text
quotes:snapshot:{provider}:{symbol}:{timeframe}
```

內容包含：

- symbol
- provider
- timeframe
- price
- change
- change_pct
- volume
- candle_time
- cached_at

Redis 只是最新報價快取，不是歷史資料真相來源。

## 手動驗收命令

```powershell
docker compose exec -T worker python main.py run-once --provider yfinance --symbol ^GSPC --timeframe 1d --period 5d --limit 5
docker compose exec -T worker python main.py run-once --provider binance --symbol BTCUSDT --timeframe 1h --limit 5
```

## 驗收結果

最後驗收時間：2026-06-19 16:55 Asia/Taipei

| 項目 | 結果 |
| --- | --- |
| `docker compose build worker` | 通過 |
| `docker compose up -d worker` | 通過，worker healthy |
| `docker compose exec -T worker python -m compileall .` | 通過 |
| yfinance `^GSPC` `1d` `limit=5` | 成功，首次 insert 5 rows |
| Binance `BTCUSDT` `1h` `limit=5` | 成功，首次 insert 5 rows |
| 重跑 yfinance `^GSPC` | 成功，insert 0 rows、update 0 rows，無重複資料 |
| `market_ohlcv` | `yfinance/^GSPC/1d = 5`, `binance/BTCUSDT/1h = 5` |
| `data_ingestion_runs` | 3 筆 success，error_count 皆為 0 |
| Redis snapshot | 已建立 `quotes:snapshot:yfinance:^GSPC:1d` 與 `quotes:snapshot:binance:BTCUSDT:1h` |

## 補充驗收：limit=200

最後驗收時間：2026-06-19 17:25 Asia/Taipei

| 項目 | 結果 |
| --- | --- |
| 預設 ingestion limit | 已改為 200 |
| `run-once --all-symbols --timeframe 1d` | 成功，`success_count=23` |
| `market_ohlcv` yfinance symbols | 20 個 symbols，1d 筆數皆為 200 |
| `market_ohlcv` binance symbols | 3 個 symbols，1d 筆數皆為 200 |
| `/api/v1/indicators` BB Upper | 23 個 symbols 皆有值 |
| `/api/v1/indicators` K | 23 個 symbols 皆有值 |
| `/api/v1/indicators` D | 23 個 symbols 皆有值 |
| indicators missing count | 0 |

## 已知限制

- `yfinance` 適合開發與原型驗證，不應視為最終實盤級資料來源。
- 目前只支援 `1d` 與 `1h`。
- `run-batch --mode snapshot` 會對所有預設標的抓資料，可能受到 provider 速率限制。
- 尚未建立 T1B API 讀取 snapshot 與 OHLCV。
