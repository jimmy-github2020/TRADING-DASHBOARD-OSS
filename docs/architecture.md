# 架構說明

最後更新時間：2026-07-29

## 目前階段

目前已包含 T8 證券主檔、自訂清單、分層追蹤，以及既有行情、
技術分析、回測、通知 dry-run 與 AI market brief 功能。

## Workspace

Clone the repository to any local directory and run commands from its root.

## Monorepo 結構

```text
TRADING-DASHBOARD
├── apps
│   ├── web
│   ├── api
│   └── worker
├── packages
│   ├── indicators
│   └── strategies
├── db
│   └── migrations
├── docs
│   └── phases
├── data
│   ├── postgres
│   └── redis
├── docker-compose.yml
├── Makefile
└── .env.example
```

## 服務

| Service | Role | Port |
| --- | --- | --- |
| web | Next.js 前端健康狀態頁 | 3100 |
| api | FastAPI health 與 WebSocket 骨架 | 8011 external / 8001 internal |
| worker | APScheduler worker 骨架 | 無外部 port |
| postgres | TimescaleDB | 5442 |
| redis | Redis cache/pubsub | 6380 |

## Docker 隔離策略

本專案使用獨立 Docker Compose project、network、volume 與 container name：

- `trading-dashboard`
- `trading_dashboard_net`
- `trading_dashboard_postgres_data`
- `trading_dashboard_redis_data`

這些命名避免與 HYMOVER 或舊 workspace 衝突。

## 資料層

T0 建立四張核心表：

- `symbols`
- `market_ohlcv`
- `data_ingestion_runs`
- `provider_errors`

`market_ohlcv` 使用 TimescaleDB hypertable，primary key 是：

```text
(symbol, timeframe, provider, time)
```

後續 T1A 必須沿用這個 schema，不另建簡化版 OHLCV 表。

## T1A Ingestion Flow

最後更新時間：2026-06-19

```text
APScheduler / manual CLI
  -> MarketIngestionService
    -> Provider adapter (yfinance / binance)
    -> market_ohlcv upsert
    -> data_ingestion_runs update
    -> provider_errors on failure
    -> Redis latest snapshot cache
```

T1A 的歷史資料真相來源是 TimescaleDB 的 `market_ohlcv`。Redis 只保存最新 snapshot，供 T1B API 加速讀取使用。

Provider 初版：

- `YFinanceProvider`: index、commodity、VIX、DXY、yield、台股權值股。
- `BinanceProvider`: `BTCUSDT`、`ETHUSDT`、`BNBUSDT`。

目前支援 timeframe：

- `1d`
- `1h`

## T1B API Flow

最後更新時間：2026-06-19

```text
Web / API client
  -> FastAPI
    -> Redis snapshot cache for latest quotes
    -> TimescaleDB for symbols and OHLCV
    -> pandas indicator calculation for T1B prototype
```

T1B endpoints：

- `GET /api/v1/symbols`
- `GET /api/v1/quotes/snapshot`
- `GET /api/v1/quotes/ohlcv`
- `GET /api/v1/indicators`
- `WS /ws/quotes`

## T1C Web Flow

最後更新時間：2026-06-19

```text
Next.js dashboard
  -> GET /health
  -> GET /api/v1/symbols
  -> GET /api/v1/quotes/snapshot
  -> GET /api/v1/quotes/ohlcv
  -> GET /api/v1/indicators
  -> WS /ws/quotes
```

T1C 使用 `lightweight-charts` v5：

- candlestick main series
- EMA 20 line overlay
- volume histogram

目前 UI 採桌面優先設計，並支援平板與窄螢幕堆疊版面。

## T1D Notification Flow

最後更新時間：2026-06-19

```text
Worker notify-scan / scheduler
  -> load recent OHLCV from TimescaleDB
  -> scan RSI / MACD / Bollinger / VIX conditions
  -> cooldown check in notification_events
  -> dry-run record or LINE / Telegram delivery
  -> notification_events audit record
```

T1D 預設 `NOTIFICATION_DRY_RUN=true`。訊息語氣固定為「條件觸發、列入觀察、風險升高」，不得輸出買賣建議。

## T2A Quant Analysis Backend Flow

最後更新時間：2026-06-22

```text
Strategies JSONB
  -> worker strategy scanner / POST /api/v1/signals/scan
  -> recent market_ohlcv daily candles
  -> RSI / MACD / MA cross / Bollinger / KD condition evaluation
  -> signals table
```

T2A 先完成後端基礎與 API，前端策略編輯器、相關性矩陣、波動率排行拆到後續 T2B/T2C，避免一次改動過大。

## T2B Strategies UI Flow

最後更新時間：2026-06-22

```text
Next.js /strategies
  -> React Query polling every 60 seconds
  -> GET /api/v1/strategies
  -> GET /api/v1/signals
  -> POST /api/v1/strategies
  -> PATCH /api/v1/strategies/{strategy_id}/active
  -> DELETE /api/v1/strategies/{strategy_id}
  -> POST /api/v1/signals/scan
```

T2B 不修改 T2A 後端。策略編輯器會將視覺化條件序列化成 T2A scanner 已支援的 `conditions` JSONB 格式。

## T2C Correlation Matrix Flow

最後更新時間：2026-06-23

```text
Next.js /analysis
  -> React Query staleTime 10 minutes
  -> GET /api/v1/analysis/correlation
  -> Redis cache correlation:{sorted_symbols}:{period}
  -> TimescaleDB market_ohlcv daily close
  -> pandas / numpy log returns
  -> Pearson correlation matrix
```

T2C 只實作相關性矩陣。波動率排行保留 `/analysis` 頁面的 T2D 佔位區塊。

## T2D Volatility Ranking Flow

最後更新時間：2026-06-24

```text
Next.js /analysis
  -> selected symbols + shared period selector
  -> GET /api/v1/analysis/volatility
  -> Redis cache volatility:{symbols_hash}:{period}:{annualize}
  -> TimescaleDB market_ohlcv daily close
  -> numpy log returns
  -> daily stddev or annualized stddev
  -> ranked bar chart
```

T2D 將 `/analysis` 的波動率佔位區塊替換為實際排行。前端與 T2C 共用標的選擇器和 7/30/90 區間 selector，並新增 annualize toggle。

## T2E Sector Rotation Flow

最後更新時間：2026-06-24

```text
Backfill sector ETFs
  -> apps/worker/backfill_sector_etfs.py
  -> TimescaleDB market_ohlcv

Next.js /analysis
  -> shared 7/30/90 period selector
  -> GET /api/v1/analysis/sector-rotation
  -> Redis cache sector_rotation:{period}:{benchmark}
  -> TimescaleDB sector ETF daily close
  -> relative return / momentum / volatility / Sharpe / RS score
  -> bubble chart + ranking table
```

T2E 使用 SPDR sector ETF 作為初版板塊輪動 universe，預設 benchmark 為 `SPY`。

## T2F Stock Ranking Flow

最後更新時間：2026-06-24

```text
Next.js /analysis
  -> shared 7/30/90 period selector
  -> GET /api/v1/analysis/stock-ranking
  -> Redis cache stock_ranking:{symbols_hash}:{period}:{benchmark}
  -> TimescaleDB watchlist daily close
  -> momentum / low volatility / relative strength / trend factors
  -> composite score
  -> ranking table + top 3 radar chart
```

T2F 完成 T2 量化分析頁最後一個模組。T2 現包含策略編輯器、訊號掃描、相關性矩陣、波動率排行、板塊輪動與多因子選股排行。

## T3 Backtest Flow

最後更新時間：2026-06-24

```text
Next.js /backtest
  -> GET /api/v1/strategies
  -> POST /api/v1/backtest/run
  -> GET /api/v1/backtest/list
  -> GET /api/v1/backtest/{backtest_id}
  -> FastAPI BacktestEngine
  -> TimescaleDB market_ohlcv + strategies
  -> pandas / numpy vectorized signal + portfolio simulation
  -> TimescaleDB backtest_results
```

T3 新增回測系統，讓 T2 策略可以套用到歷史 OHLCV 資料，產生總報酬、年化報酬、Sharpe Ratio、最大回撤、勝率、交易次數、平均持倉天數、Profit Factor、資產曲線與交易明細。

本階段先保留 `BacktestEngine` 邊界，核心以 pandas / numpy 實作向量化訊號與逐筆持倉模擬。原因是 `vectorbt` 在 Python 3.12 / NumPy 2.x 組合上容易受到 numba 相容性限制；後續若固定 Python 3.11 與相容套件版本，可在不更動 API 與前端的情況下替換引擎。

## T4 AI Market Brief Flow

最後更新時間：2026-06-25

```text
Next.js /ai-brief
  -> GET /api/v1/ai/market-brief/latest
  -> GET /api/v1/ai/market-brief/history
  -> POST /api/v1/ai/market-brief
  -> FastAPI MarketBriefService
  -> TimescaleDB market_ohlcv + ai_market_briefs
  -> T2 sector rotation / stock ranking analyzers
  -> Redis ai_market_brief:{context_hash}
  -> OpenAI chat completions
```

T4 將原規劃的「投資建議 / 預判」收斂為 AI Market Brief 盤面摘要。摘要只描述近期價格變動、技術面觀察、VIX、板塊輪動與選股排行現象，不輸出買賣建議。API 與前端固定顯示免責聲明：「⚠️ 本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。」

若 `AI_BRIEF_ENABLED=false` 或缺少 `OPENAI_API_KEY`，API 會回 `503`，前端顯示功能未啟用，不會嘗試產生摘要。
## T4 Home Dashboard UI Flow

最後更新時間：2026-06-25

```text
Next.js /
  -> GET /api/v1/market/quote for headline tiles
  -> GET /api/v1/portfolio/holdings for grouped watchlist
  -> GET /api/v1/quotes/ohlcv for selected symbol chart
  -> GET /api/v1/indicators for selected symbol indicator grid
  -> POST /api/v1/portfolio/holdings when adding a searched symbol
  -> TimescaleDB portfolio_holdings + market_ohlcv
  -> Yahoo Finance fallback only when headline/search quote is missing in DB
```

首頁改成固定 viewport 版面：上方為 compact 主要指數與商品 / 匯率 tile；下方主體維持左側 Watchlist 可獨立捲動、右側 chart 與 indicators 固定不隨頁面捲動。Watchlist 初始資料來自 `portfolio_holdings`，包含 36 檔持倉並分成 `ETF` 與 `股票` group。上方 tile 已顯示的 symbol 會從 Watchlist 排除，避免 VIX、主要指數、BTC/ETH 等重複出現。

`portfolio_holdings` 由 `db/migrations/006_portfolio_holdings.sql` 建立與初始化。搜尋新增標的採按需查詢，不預載全市場資料；使用者輸入 symbol 後先查行情，確認後寫入 DB，並以 `owned=false` 標記為觀察標的。
