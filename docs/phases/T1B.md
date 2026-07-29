# Phase T1B 實作記錄

最後更新時間：2026-06-19

## 目標

建立 FastAPI 行情 API，讓前端能讀取 symbols、最新 snapshot、歷史 OHLCV 與技術指標，並透過 WebSocket 接收 snapshot 推送。

## 已完成

- 新增 API settings。
- 新增 API response wrapper：`{data, meta, timestamp}`。
- 新增 Redis quote cache reader。
- 新增 TimescaleDB market repository。
- 新增技術指標計算：
  - RSI(14)
  - MACD(12,26,9)
  - BB(20,2)
  - KD(9,3)
  - EMA(20)
  - ATR(14)
  - OBV
- 新增 endpoints：
  - `GET /api/v1/symbols`
  - `GET /api/v1/quotes/snapshot`
  - `GET /api/v1/quotes/ohlcv`
  - `GET /api/v1/indicators`
- 更新 `/ws/quotes`：
  - `ping` 回 `pong`
  - 無 client message 時每 10 秒推送 snapshot

## API 設計

除 `/health` 外，成功回應統一為：

```json
{
  "data": {},
  "meta": {},
  "timestamp": "2026-06-19T08:00:00.000000+00:00"
}
```

錯誤目前沿用 FastAPI `detail` 格式。T1B 先保持簡單，T1C/T2 可再統一錯誤 envelope。

## Snapshot 來源策略

`GET /api/v1/quotes/snapshot`：

1. 優先讀 Redis `quotes:snapshot:keys`。
2. 若 Redis 沒有 snapshot，回退讀 TimescaleDB 每組 `(symbol, timeframe, provider)` 最新 K 線。

## 已知限制

- 指標目前用 pandas 在 API request時計算，適合 T1B/T1C 原型；若資料量變大，應移到 worker 預計算或 Redis cache。
- 目前 timeframe 僅支援 `1d` 與 `1h`。
- `GET /api/v1/indicators` 若資料少於部分指標所需週期，該指標可能回 `null`。
- WebSocket 目前推 snapshot，不做逐筆 tick。

## 驗收結果

最後驗收時間：2026-06-19 17:04 Asia/Taipei

| 項目 | 結果 |
| --- | --- |
| `docker compose build api` | 通過 |
| `docker compose up -d api web` | 通過，API healthy |
| `docker compose exec -T api python -m compileall .` | 通過 |
| `GET /health` | `status: ok`, `db: ok`, `redis: ok` |
| `GET /api/v1/symbols` | 通過，回傳 2 個 T1A 已入庫 symbols |
| `GET /api/v1/quotes/snapshot` | 通過，回傳 Redis snapshot |
| `GET /api/v1/quotes/ohlcv?symbol=^GSPC&timeframe=1d&provider=yfinance&limit=5` | 通過，回傳 5 根 K 線 |
| `GET /api/v1/indicators?symbol=BTCUSDT&timeframe=1h&provider=binance&limit=30` | 通過，回傳 RSI/MACD/EMA/ATR/OBV，長週期不足者為 `null` |
| `WS /ws/quotes` ping/pong | 通過 |
