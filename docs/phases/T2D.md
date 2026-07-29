# Phase T2D 實作記錄

最後更新時間：2026-06-24

## 目標

在 `/analysis` 頁面補上波動率排行，讓 T2C 的相關性矩陣旁邊能同步觀察各標的近期風險、區間報酬與最大回撤。

## 後端

新增 `GET /api/v1/analysis/volatility`。

Query:

- `symbols`：逗號分隔標的；未提供時使用預設 8 檔。
- `period`：`7`、`30`、`90`，也相容 `7d`、`30d`、`90d`。
- `annualize`：預設 `true`。

計算方式：

1. 從 TimescaleDB `market_ohlcv` 讀取各標的最近 N+1 根日線收盤價。
2. 使用 `log(close_t / close_t-1)` 計算日對數報酬率。
3. 使用日報酬標準差作為原始波動率。
4. `annualize=true` 時乘以 `sqrt(252)`。
5. 同時計算：
   - `period_return_pct`
   - `max_drawdown_pct`
   - `rank`
6. Redis 快取 10 分鐘，key 格式為 `volatility:{symbols_hash}:{period}:{annualize}`。

## 前端

更新 `/analysis` 頁面：

- 移除 T2D 佔位區塊。
- 新增波動率排行 bar chart。
- 與 T2C 共用 selected symbols 與 period selector。
- 新增 annualize toggle。
- 依波動率由高到低排序。
- 顏色分層：
  - `> 40%`：紅色
  - `20% ~ 40%`：橙色
  - `< 20%`：綠色
- 每列顯示：
  - rank
  - symbol / friendly name
  - volatility
  - period return
  - max drawdown
- loading skeleton 與 T2C 視覺一致。
- API error / 空資料狀態使用 friendly error state。

## 決策

- `period` API 依規格使用 `7/30/90`，同時保留 `7d/30d/90d` 相容性，避免 T2C 既有前端型別需要大幅改動。
- volatility 的預設 symbols 與 `/analysis` 預設勾選 8 檔一致。
- 後端 symbol name 優先使用 `symbols` 表，若不存在則使用內建 friendly name fallback。

## 驗收項目

- `docker compose build api web`
- `docker compose run --rm --no-deps api python -m compileall .`
- `docker compose run --rm --no-deps web npm run build`
- `GET /api/v1/analysis/volatility?period=30`
- `GET /api/v1/analysis/volatility?period=30&annualize=false`
- 第二次同參數確認 `meta.cache = hit`
- annualized / raw ratio 約為 `sqrt(252)`
- `/analysis` 頁面可開啟且 bar chart 正確渲染
- `docker compose ps` 服務皆 healthy

## 已知問題

- 若本機 DB 尚未補齊某些 ETF 或外部標的，endpoint 會依設計回傳 400；需先執行 worker ingestion 補資料。
