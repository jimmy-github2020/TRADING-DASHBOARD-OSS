# Phase T2E 實作記錄

最後更新時間：2026-06-24

## 目標

建立板塊輪動分析，使用美股 SPDR sector ETF 和 `SPY` benchmark 判斷近期相對強弱。

## 前置資料

已建立並保留補抓腳本：

```text
apps/worker/backfill_sector_etfs.py
```

本階段驗收前 DB 已確認以下標的各有 180 筆日線：

- `XLK`
- `XLF`
- `XLV`
- `XLE`
- `XLY`
- `XLP`
- `XLI`
- `XLB`
- `XLU`
- `XLRE`
- `XLC`
- `SPY`

## 後端

新增 `GET /api/v1/analysis/sector-rotation`。

Query:

- `period`：`7`、`30`、`90`，也相容 `7d`、`30d`、`90d`。
- `benchmark`：預設 `SPY`。

計算欄位：

- `period_return_pct`：期間報酬率。
- `relative_return_pct`：相對 benchmark 超額報酬。
- `momentum_score`：日對數報酬均值乘以 `sqrt(period)`。
- `volatility_pct`：日對數報酬標準差乘以 `sqrt(252)`。
- `sharpe_ratio`：`momentum_score / volatility` 的簡化版本。
- `rs_score`：`(1 + sector_return) / (1 + benchmark_return)`。

回傳依 `rs_score` 由高到低排序。

Redis 快取 10 分鐘：

```text
sector_rotation:{period}:{benchmark}
```

## 前端

更新 `/analysis` 頁面，於波動率排行下方新增「板塊輪動」區塊：

- 泡泡圖：
  - X 軸：`relative_return_pct`
  - Y 軸：`momentum_score`
  - 泡泡大小：`volatility_pct`
  - 泡泡顏色：`rs_score > 1.01` 綠色、`< 0.99` 紅色，其餘灰色
  - 泡泡文字顯示中文板塊名稱
  - tooltip 顯示期間報酬、相對報酬、Sharpe、波動率
- 排行表格：
  - rank
  - 板塊
  - rs_score
  - period_return_pct
  - relative_return_pct
  - sharpe_ratio
- 與 T2C/T2D 共用 7/30/90 period selector。
- loading skeleton 和 friendly error state 沿用既有風格。

## 決策

- T2E 先固定使用 SPDR sector ETF universe，不與一般 watchlist 混在一起。
- benchmark 允許 `SPY` 或 sector ETF，若不在清單內回傳 400。
- `rs_score` 使用報酬倍率相除，而不是單純相減；單純相減已另外回傳於 `relative_return_pct`。

## 驗收項目

- `docker compose build api web`
- `docker compose run --rm --no-deps api python -m compileall .`
- `docker compose run --rm --no-deps web npm run build`
- `GET /api/v1/analysis/sector-rotation?period=30` 回傳 11 筆。
- `rs_score` 依高到低排序。
- 第二次同參數確認 `meta.cache = hit`。
- `/analysis` 頁面可開啟。
- `docker compose ps` 服務皆 healthy。

## 已知問題

- 若尚未執行 sector ETF backfill，endpoint 會回傳資料不足錯誤；需先執行 `apps/worker/backfill_sector_etfs.py`。
