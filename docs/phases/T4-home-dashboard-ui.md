# T4 Home Dashboard UI 改善紀錄

最後更新時間：2026-06-25

## 目標

本次改善 Codex 版首頁的資訊密度與交易操作感，重點是讓 1280px 桌機 viewport 盡量維持一頁式閱讀：上方行情 tile 壓縮、左側 Watchlist 可獨立捲動、右側 chart 固定不跟著清單捲動。

## 已完成項目

- 首頁上方新增 compact「主要指數」與「商品 / 匯率」兩列行情 tile。
- 主要指數包含：`^DJI`, `^GSPC`, `^IXIC`, `^SOX`, `^TWII`, `^TWOII`。
- 商品 / 匯率包含：`BZ=F`, `GC=F`, `TWD=X`, `^N225`, `^VIX`, `BTCUSDT`, `ETHUSDT`。
- 兩列行情區固定約 150px 高度；tile 高度 64px，縮 padding 但保留價格字體可讀性。
- 新增 `portfolio_holdings` migration，初始化 36 檔持倉。
- Watchlist 改由 `GET /api/v1/portfolio/holdings` 讀取，依 `ETF` 與 `股票` 分組。
- Watchlist 顯示中文名稱、symbol、最新價格與漲跌幅，英文名稱保留在 hover tooltip。
- 上方行情 tile 已顯示的 symbol 從 Watchlist 排除，避免重複顯示 VIX、主要指數、BTC/ETH。
- Watchlist 頂部新增 symbol 搜尋框，可按需查詢單一標的並加入 Watchlist。
- 新增 `GET /api/v1/market/quote`，優先讀 TimescaleDB，缺資料時暫時 Yahoo Finance fallback。
- 新增 `POST /api/v1/portfolio/holdings`，搜尋加入的新標的以 `owned=false` 寫入 DB。
- 右側 detail panel 改為 summary bar、chart、indicator grid 的固定版面。
- `lightweight-charts` volume pane 維持 22% stretch factor，K 線主 pane 維持主要視覺。

## 版面決策

- 使用 `100dvh` 與 `overflow: hidden` 固定整體首頁高度，避免 body scroll。
- `watchlist-panel` 內部自行 `overflow-y: auto`，持倉清單超過一頁時只捲左側。
- `chart-panel` 固定高度並隱藏 overflow，避免右側圖表跟著左側清單位移。
- 小螢幕時上方行情區可在自己的 150px 容器內捲動；主體仍維持左側清單與右側圖表並排，避免右側圖表掉到頁面下方。

## 已知限制

- Yahoo fallback 目前只用於首頁行情 tile 與搜尋預覽；完整 OHLCV chart 仍依賴 `market_ohlcv` 已入庫資料。
- 新增的觀察標的會寫入 `portfolio_holdings`，但尚未自動排入 worker 歷史資料補抓流程。
- 手機寬度下 13 個上方 tile 會在行情區內捲動，否則無法同時滿足 2 欄 RWD 與 150px 高度限制。

## 驗收

- `docker compose run --rm --no-deps web npm run build` 通過。
- `docker compose run --rm --no-deps api python -m compileall .` 通過。
- `docker compose build web` 通過。
- `docker compose build api` 通過。
- `GET /api/v1/portfolio/holdings` 回傳 36 筆，ETF 12 筆、股票 24 筆。
- `GET /api/v1/market/quote` 對 13 個上方 tile symbol 回傳 13 筆資料。
- `http://localhost:3100/` 回 200。
- Docker Compose services：web、api、postgres、redis 均為 healthy。
