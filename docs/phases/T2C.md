# Phase T2C 實作記錄

最後更新時間：2026-06-23

## 目標

建立量化分析頁面的第一個模組：相關性矩陣。使用日線收盤價計算日對數報酬率，再產生多標的 Pearson correlation heatmap。

## 後端

新增 `GET /api/v1/analysis/correlation`。

Query:

- `symbols`：逗號分隔標的，至少 2 個。
- `period`：`7d`、`30d`、`90d`，預設 `30d`。

計算方式：

1. 從 TimescaleDB `market_ohlcv` 讀取各標的最近 N+1 根日線收盤價。
2. 用 numpy 計算 `log(close_t / close_t-1)`。
3. 用 pandas pairwise Pearson correlation 產生矩陣。
4. Redis 快取 10 分鐘，key 格式為 `correlation:{sorted_symbols}:{period}`。

錯誤處理：

- 少於 2 個標的回 400。
- 任一標的資料不足 5 筆回 400。
- 可對齊的報酬率資料不足 5 筆回 400。

## 前端

新增 `/analysis` 頁面。

已完成：

- 頁面標題：量化分析。
- 相關性矩陣 section。
- 預設 8 個標的：
  - `0050.TW`
  - `2330.TW`
  - `^GSPC`
  - `^NDX`
  - `^VIX`
  - `GC=F`
  - `CL=F`
  - `DX-Y.NYB`
- 多選 checkbox 標的選擇器。
- 7 天 / 30 天 / 90 天 tab 切換。
- React Query 呼叫 correlation API，`staleTime` 10 分鐘。
- 純 CSS heatmap。
- hover tooltip 顯示標的配對與相關係數。
- loading skeleton。
- T2D 波動率排行佔位區塊。
- 全域導覽新增 `/analysis` 連結。

## 色彩規則

- `>= 0.7`：深紅 `#dc2626`
- `0.4 ~ 0.69`：淺紅 `#f87171`
- `0.1 ~ 0.39`：灰色 `#6b7280`
- `-0.1 ~ 0.09`：白灰 `#9ca3af`
- `-0.4 ~ -0.11`：淺藍 `#60a5fa`
- `<= -0.4`：深藍 `#2563eb`
- 對角線：`#1f2937`，顯示 `—`

## 驗收項目

- `GET /api/v1/analysis/correlation?symbols=0050.TW,2330.TW,^GSPC&period=30d` 回傳矩陣。
- 只傳入 1 個標的回傳 400。
- 第二次同參數呼叫回傳 `meta.cache = hit`。
- `/analysis` 頁面可開啟。
- 熱力表可依標的與 period 重新 fetch。
- `docker compose build api web` 通過。
- `npm run build` 無 TypeScript 錯誤。

## 後續

- T2D：波動率排行。
