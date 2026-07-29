# Phase T2F 實作記錄

最後更新時間：2026-06-24

## 目標

建立多因子選股排行，將 watchlist 標的依動能、低波動、相對強弱與趨勢分數整合成綜合排名。

## 後端

新增 `GET /api/v1/analysis/stock-ranking`。

Query:

- `symbols`：逗號分隔標的；未提供時使用預設 8 檔。
- `period`：`7`、`30`、`90`，也相容 `7d`、`30d`、`90d`。
- `benchmark`：預設 `^GSPC`。

預設標的：

- `0050.TW`
- `006208.TW`
- `2330.TW`
- `2317.TW`
- `2882.TW`
- `^GSPC`
- `^VIX`
- `GC=F`

## 因子設計

- `momentum_score`：期間 log return，全體 min-max 標準化到 0–100。
- `low_vol_score`：年化波動率倒數，全體 min-max 標準化到 0–100。
- `rs_score`：相對 benchmark 超額報酬，全體 min-max 標準化到 0–100。
- `trend_score`：收盤價高於 MA20 得 100，低於 MA20 得 0；資料不足得 50。
- `composite_score`：四項加權平均：
  - momentum 30%
  - low volatility 20%
  - relative strength 30%
  - trend 20%

若某一因子所有標的數值相同，該因子給中性分數 50。

Redis 快取 10 分鐘：

```text
stock_ranking:{symbols_hash}:{period}:{benchmark}
```

## 前端

更新 `/analysis` 頁面，於板塊輪動下方新增「選股排行」區塊：

- 排行表格：
  - rank
  - 標的名稱 / 代碼
  - 綜合評分
  - 動能
  - 低波動
  - 相對強弱
  - 趨勢
- 每個因子用 progress bar 顯示：
  - `> 70` 綠色
  - `40–70` 黃色
  - `< 40` 紅色
- 第一名高亮。
- 點擊任一列可展開 period return 與 volatility。
- 雷達圖顯示前三名標的：
  - 動能
  - 低波動
  - 相對強弱
  - 趨勢

## 驗收項目

- `docker compose build api web`
- `docker compose run --rm --no-deps api python -m compileall .`
- `docker compose run --rm --no-deps web npm run build`
- `GET /api/v1/analysis/stock-ranking?period=30` 回傳 8 筆。
- `composite_score` 依高到低排序。
- 所有分數在 0–100 範圍內。
- 第二次同參數確認 `meta.cache = hit`。
- 標的數少於 2 時回傳 400。
- `/analysis` 頁面可開啟。
- `docker compose ps` 服務皆 healthy。

## 已知問題

- T2F 的 `trend_score` 初版使用簡單 MA20 二元判斷，後續可改為價格距離 MA、MA slope 或多均線排列來提高細緻度。
- `^VIX` 是風險/波動指標，不是股票；目前依使用者指定納入預設 8 檔，後續若做實際選股可考慮分離為風險因子。
