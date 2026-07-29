# T1-E K 線圖全面強化

最後更新時間：2026-06-26

## 實作範圍

- `/api/ohlcv` 與 `/api/v1/quotes/ohlcv` 支援 `5m` timeframe。
- `/api/ohlcv` 新增 `range` 參數，支援 `1d / 3d / 1w / 2w / 1m / 3m / 6m / 1y / 2y / 3y / 5y / 10y`。
- Yahoo fallback 會依 timeframe 對應合適的 Yahoo chart `range` 與 `interval`。
- 5m 與 1h 會依 Yahoo Finance 限制回傳 warning。
- 前端新增 Timeframe：`5m / 1H / 1D`。
- 前端新增 Range selector，依 timeframe 動態切換可選區間。
- 主 K 線圖新增 MA5 / MA10 / MA20 / MA60 疊圖 toggle。
- 主 K 線圖新增 Bollinger Bands toggle，包含 UB / MB / LB 與淡色區域。
- 5m 顯示延遲提示標籤。
- Indicators 區由文字 grid 改為固定高度 150px 的圖形化子圖。
- 指標 tab 支援 RSI / KD / MACD。
- 指標改由前端 candles 即時計算，切換 symbol、timeframe、range 時會完整重算。

## 設計決策

- T1-E 將指標圖形化計算移到前端，避免 5m timeframe 受既有 `/api/v1/indicators` endpoint 限制。
- 目前保留 `/api/v1/indicators` endpoint，不影響既有 API 使用者。
- 布林通道中軌使用 MA20 顏色；若 BB 開啟且 MA20 也開啟，主圖只渲染 BB 的中軌，避免 MA20 重疊。
- 5m 資料仍沿用 Yahoo fallback，因此 UI 明確提示延遲。

## 已知限制

- Lightweight Charts 原生不直接提供兩條線之間的 band fill，本次用極淡 AreaSeries 做視覺輔助，避免干擾 K 線。
- RSI / KD 的固定 0-100 軸目前以 guide line 呈現，未強制鎖死 price scale。
- KD 交叉圓點標記尚未加入，保留到後續小修或 T1-F。
- 本回合 Docker 指令受工具使用量限制，尚未能代跑 `docker compose build` 與瀏覽器實測。

## 驗收建議

```powershell
docker compose build api web
docker compose up -d api web
docker compose run --rm --no-deps web npm run build
curl "http://localhost:8011/api/ohlcv?symbol=2330.TW&interval=5m&range=1d&limit=120"
curl "http://localhost:8011/api/ohlcv?symbol=2330.TW&interval=1h&range=1m&limit=500"
curl "http://localhost:8011/api/ohlcv?symbol=2330.TW&interval=1d&range=1y&limit=260"
```

前端手動驗收：

- 切換 `5m / 1H / 1D` 後 K 線會重新載入。
- 切換 range 後 K 線與指標子圖會重新計算。
- MA20 / MA60 預設顯示，MA5 / MA10 預設關閉。
- BB toggle 可顯示 / 隱藏布林通道。
- 5m 會出現延遲提示。
- RSI / KD / MACD tab 可切換並顯示圖形。
