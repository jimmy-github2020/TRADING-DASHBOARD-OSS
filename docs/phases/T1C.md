# Phase T1C 實作記錄

最後更新時間：2026-06-19

## 目標

建立第一版可使用的前端交易儀表板，串接 T1B API 與 WebSocket，顯示 watchlist、K 線、技術指標與市場 snapshot。

## 已完成

- 將 T0 health page 改為儀表板主頁。
- 串接 `GET /health`。
- 串接 `GET /api/v1/symbols`。
- 串接 `GET /api/v1/quotes/snapshot`。
- 串接 `GET /api/v1/quotes/ohlcv`。
- 串接 `GET /api/v1/indicators`。
- 串接 `WS /ws/quotes`：
  - 連線狀態顯示
  - ping/pong
  - snapshot message 更新 watchlist
- 使用 `lightweight-charts` v5 建立：
  - candlestick series
  - EMA 20 line overlay
  - volume histogram
- 建立 dashboard layout：
  - Header：Logo、API 狀態、WS 狀態、時間、refresh、通知與設定 icon
  - Watchlist：symbol、name、price、change %
  - Main chart：symbol detail、timeframe switch、quote metrics、K 線圖
  - Indicator panel：RSI/MACD/BB/KD/EMA/ATR/OBV
  - Market strip：主要 snapshot tiles
- 深色專業儀表板風格。
- 平板與窄螢幕 responsive layout。

## 實作檔案

- `apps/web/app/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/package.json`

## 設計決策

### Lightweight Charts v5

使用 v5 ESM API：

```ts
chart.addSeries(CandlestickSeries, options)
chart.addSeries(LineSeries, options)
chart.addSeries(HistogramSeries, options)
```

避免使用 v4 的 `addCandlestickSeries` API。

### Snapshot 更新

頁面會：

- 每 15 秒重新讀取 health、symbols、snapshot。
- WebSocket 收到 snapshot 時更新 watchlist 與市場條。

### 指標顯示

T1C 顯示 T1B 已提供的指標值。若資料量不足，例如 BB(20) 或 KD(9,3) 週期不夠，UI 顯示 `-`。

## 驗收結果

最後驗收時間：2026-06-19 17:13 Asia/Taipei

| 項目 | 結果 |
| --- | --- |
| `docker compose build web` | 通過 |
| `docker compose up -d web` | 通過，web healthy |
| `docker compose exec -T web npm run build` | 通過 |
| `GET http://localhost:3100` | HTTP 200 |
| HTML contains `TRADING DASHBOARD` | 通過 |
| `GET /api/v1/quotes/snapshot` | 通過，Redis snapshot 24 筆 |
| API / Web containers | healthy |

## 已知限制

- 目前沒有可用的 in-app browser screenshot 工具，因此 T1C 以 Next production build、HTTP 200 與 API 驗證替代視覺截圖驗收。
- K 線圖目前包含 EMA 20 overlay 與 volume histogram，RSI/MACD 仍以右側數值 panel 顯示；後續可在圖表區加入真正的副圖 pane。
- Watchlist 依 `symbols` 表顯示，symbols 數量取決於 T1A ingestion 是否已跑過對應 universe。
- T1C 尚未加入使用者自訂 watchlist 儲存。
