# API 說明

最後更新時間：2026-06-19

## Base URL

```text
http://localhost:8011
```

## GET /health

檢查 API、Postgres 與 Redis 狀態。

Response:

```json
{
  "status": "ok",
  "timestamp": "2026-06-19T08:00:00.000000+00:00",
  "db": "ok",
  "redis": "ok"
}
```

若 DB 或 Redis 無法連線，`status` 會是 `error`，對應欄位也會顯示 `error`。

## Response Shape

除 `/health` 外，T1B API 成功回應統一格式：

```json
{
  "data": {},
  "meta": {},
  "timestamp": "2026-06-19T08:00:00.000000+00:00"
}
```

## GET /api/v1/symbols

回傳已啟用 symbols。

```text
GET /api/v1/symbols
```

## GET /api/v1/quotes/snapshot

回傳最新 snapshot。優先讀 Redis；若 Redis 無資料，回退到 DB 最新 K 線。

```text
GET /api/v1/quotes/snapshot
```

## GET /api/v1/quotes/ohlcv

從 TimescaleDB 取得 OHLCV。

Query:

- `symbol` required
- `timeframe` default `1d`，目前支援 `1d`, `1h`
- `provider` default `yfinance`，目前支援 `yfinance`, `binance`
- `limit` default `500`，範圍 `1` 到 `5000`

Example:

```text
GET /api/v1/quotes/ohlcv?symbol=^GSPC&timeframe=1d&provider=yfinance&limit=100
```

## GET /api/v1/indicators

用 OHLCV 計算技術指標。

Query:

- `symbol` required
- `timeframe` default `1d`
- `provider` default `yfinance`
- `limit` default `200`，範圍 `30` 到 `5000`

目前回傳：

- `rsi_14`
- `macd`
- `bb_20_2`
- `kd_9_3`
- `ema_20`
- `atr_14`
- `obv`

Example:

```text
GET /api/v1/indicators?symbol=BTCUSDT&timeframe=1h&provider=binance&limit=200
```

## GET /api/v1/analysis/correlation

最後更新時間：2026-06-23

計算多個標的日報酬率的 Pearson 相關係數矩陣。後端會讀取 TimescaleDB `market_ohlcv` 日線收盤價，使用 pandas + numpy 計算對數報酬率與相關係數，並以 Redis 快取 10 分鐘。

Query:

- `symbols` required，逗號分隔，至少 2 個標的
- `period` default `30d`，支援 `7d`, `30d`, `90d`

Example:

```text
GET /api/v1/analysis/correlation?symbols=0050.TW,2330.TW,^GSPC&period=30d
```

Response:

```json
{
  "data": {
    "symbols": ["0050.TW", "2330.TW", "^GSPC"],
    "matrix": [
      [1.0, 0.82, 0.65],
      [0.82, 1.0, 0.71],
      [0.65, 0.71, 1.0]
    ],
    "period": "30d",
    "calculated_at": "2026-06-23T14:00:00+00:00",
    "data_points": 30
  },
  "meta": {
    "cache": "miss"
  },
  "timestamp": "2026-06-23T14:00:00+00:00"
}
```

錯誤處理：

- 只傳入 1 個標的會回傳 400。
- 任一標的資料不足 5 筆會回傳 400。
- 指定期間內可對齊的日報酬資料不足 5 筆會回傳 400。

## GET /api/v1/analysis/volatility

最後更新時間：2026-06-24

計算多個標的的波動率排行。後端會讀取 TimescaleDB `market_ohlcv` 日線收盤價，計算日對數報酬率標準差；`annualize=true` 時乘以 `sqrt(252)` 換算成年化波動率百分比。結果以 Redis 快取 10 分鐘。

Query:

- `symbols` optional，逗號分隔；未提供時使用 `/analysis` 預設 8 檔。
- `period` default `30`，支援 `7`, `30`, `90`，也相容 `7d`, `30d`, `90d`。
- `annualize` default `true`。

Example:

```text
GET /api/v1/analysis/volatility?period=30
GET /api/v1/analysis/volatility?symbols=0050.TW,2330.TW,^GSPC&period=30&annualize=false
```

Response:

```json
{
  "data": {
    "symbols": ["0050.TW", "2330.TW", "^GSPC"],
    "period": "30",
    "annualize": true,
    "calculated_at": "2026-06-24T09:00:00+00:00",
    "data_points": 30,
    "items": [
      {
        "symbol": "^GSPC",
        "name": "S&P 500",
        "volatility_pct": 18.23,
        "rank": 1,
        "period_return_pct": 2.41,
        "max_drawdown_pct": -3.52
      }
    ]
  },
  "meta": {
    "cache": "miss"
  },
  "timestamp": "2026-06-24T09:00:00+00:00"
}
```

錯誤處理：

- 明確傳入少於 2 個標的會回傳 400。
- 任一標的資料不足 5 筆日報酬資料會回傳 400。

## GET /api/v1/analysis/sector-rotation

最後更新時間：2026-06-24

計算美股板塊 ETF 相對 benchmark 的輪動排行。預設使用 `SPY` 作為 benchmark，回傳 11 個 SPDR sector ETF，不含 benchmark 本身。

Query:

- `period` default `30`，支援 `7`, `30`, `90`，也相容 `7d`, `30d`, `90d`。
- `benchmark` default `SPY`，必須是 `SPY` 或板塊 ETF 清單之一。

Example:

```text
GET /api/v1/analysis/sector-rotation?period=30
```

Response:

```json
{
  "data": {
    "period": "30",
    "benchmark": "SPY",
    "benchmark_return_pct": 2.1,
    "calculated_at": "2026-06-24T09:00:00+00:00",
    "data_points": 30,
    "items": [
      {
        "rank": 1,
        "symbol": "XLK",
        "sector_name": "科技",
        "period_return_pct": 6.12,
        "relative_return_pct": 4.02,
        "momentum_score": 0.0182,
        "volatility_pct": 23.45,
        "sharpe_ratio": 0.78,
        "rs_score": 1.0394
      }
    ]
  },
  "meta": {
    "cache": "miss"
  },
  "timestamp": "2026-06-24T09:00:00+00:00"
}
```

板塊清單：

- `XLK` 科技
- `XLF` 金融
- `XLV` 醫療
- `XLE` 能源
- `XLY` 非必需消費
- `XLP` 必需消費
- `XLI` 工業
- `XLB` 原物料
- `XLU` 公用事業
- `XLRE` 不動產
- `XLC` 通訊

## GET /api/v1/analysis/stock-ranking

最後更新時間：2026-06-24

計算多因子選股排行。預設使用 8 檔 watchlist 標的，並以 `^GSPC` 作為 benchmark。所有因子分數皆映射到 0 到 100 分，依 `composite_score` 由高到低排序。

Query:

- `symbols` optional，逗號分隔；未提供時使用預設 8 檔。
- `period` default `30`，支援 `7`, `30`, `90`，也相容 `7d`, `30d`, `90d`。
- `benchmark` default `^GSPC`。

Example:

```text
GET /api/v1/analysis/stock-ranking?period=30
GET /api/v1/analysis/stock-ranking?symbols=0050.TW,2330.TW,^GSPC&period=30&benchmark=^GSPC
```

Response:

```json
{
  "data": {
    "symbols": ["0050.TW", "006208.TW", "2330.TW"],
    "period": "30",
    "benchmark": "^GSPC",
    "benchmark_return_pct": 2.1,
    "calculated_at": "2026-06-24T09:00:00+00:00",
    "data_points": 30,
    "items": [
      {
        "symbol": "2330.TW",
        "name": "台積電",
        "composite_score": 86.4,
        "momentum_score": 91.2,
        "low_vol_score": 72.1,
        "rs_score": 88.7,
        "trend_score": 100.0,
        "rank": 1,
        "period_return_pct": 6.3,
        "volatility_pct": 24.5
      }
    ]
  },
  "meta": {
    "cache": "miss"
  },
  "timestamp": "2026-06-24T09:00:00+00:00"
}
```

因子權重：

- 動能：30%
- 低波動：20%
- 相對強弱：30%
- 趨勢：20%

## POST /api/v1/backtest/run

最後更新時間：2026-06-24

執行單次策略回測，策略來源為 T2A/T2B 的 `strategies` 表。

Request body:

```json
{
  "strategy_id": "uuid",
  "symbols": ["2330.TW", "0050.TW"],
  "start_date": "2025-06-24",
  "end_date": "2026-06-24",
  "timeframe": "1d",
  "initial_capital": 100000,
  "commission": 0.001
}
```

Response:

```json
{
  "data": {
    "id": "uuid",
    "strategy_id": "uuid",
    "symbols": ["2330.TW", "0050.TW"],
    "total_return_pct": 12.34,
    "annual_return_pct": 10.11,
    "sharpe_ratio": 1.25,
    "max_drawdown_pct": -8.4,
    "win_rate": 55.0,
    "total_trades": 12,
    "avg_holding_days": 8.5,
    "profit_factor": 1.8,
    "equity_curve": [
      { "timestamp": "2026-01-02T00:00:00+00:00", "value": 100000.0 }
    ],
    "trades": [
      {
        "symbol": "2330.TW",
        "entry_date": "2026-01-02T00:00:00+00:00",
        "exit_date": "2026-01-15T00:00:00+00:00",
        "holding_days": 13,
        "return_pct": 3.2
      }
    ]
  },
  "meta": {
    "created": true
  }
}
```

注意事項：

- `timeframe` 目前支援 `1d` / `1h`。
- `equity_curve` 的資料點對應回測期間內有市場資料的 K 線筆數。
- 若任一標的資料不足 30 根 K 線，回傳 `400`。
- 回測結果會寫入 `backtest_results`。

## GET /api/v1/backtest/{backtest_id}

最後更新時間：2026-06-24

查詢單次回測完整結果，包含 `equity_curve` 與 `trades`。

## GET /api/v1/backtest/list

最後更新時間：2026-06-24

查詢最近回測紀錄。

Query:

- `limit`：預設 20，範圍 1-100。

回傳資料為摘要格式，`equity_curve` 與 `trades` 會以空陣列回傳，前端點選歷史紀錄後再呼叫 `/api/v1/backtest/{backtest_id}` 載入完整內容。

## POST /api/v1/ai/market-brief

最後更新時間：2026-06-25

產生 AI Market Brief 盤面摘要。系統會自動從 DB 取得 watchlist 最近收盤價、板塊輪動、選股排行與 VIX 資料，組成 context 後呼叫 OpenAI。

需要環境變數：

- `AI_BRIEF_ENABLED=true`
- `OPENAI_API_KEY`
- `AI_BRIEF_MODEL`，預設 `gpt-4o-mini`

Response:

```json
{
  "data": {
    "id": "uuid",
    "brief_text": "繁體中文盤面摘要...\n\n⚠️ 本摘要由 AI 自動生成，僅供參考，不構成任何投資建議。",
    "generated_at": "2026-06-25T09:00:00+00:00",
    "data_snapshot": {
      "watchlist": [],
      "sector_rotation": {},
      "stock_ranking_top3": [],
      "vix": {}
    },
    "model": "gpt-4o-mini",
    "tokens_used": 820
  },
  "meta": {
    "cache": "miss"
  }
}
```

快取：

- Redis TTL 30 分鐘。
- key 依 data snapshot hash 產生，相同 context 不重複呼叫 OpenAI。

錯誤：

- `AI_BRIEF_ENABLED=false` 或缺少 `OPENAI_API_KEY` 時回 `503`。
- OpenAI API 失敗時回 `503`，服務不 crash。

## GET /api/v1/ai/market-brief/latest

最後更新時間：2026-06-25

回傳最近一次已儲存的 AI Market Brief，不重新生成。

## GET /api/v1/ai/market-brief/history

最後更新時間：2026-06-25

Query:

- `limit`：預設 5，範圍 1-20。

回傳最近 N 筆 AI Market Brief，供 `/ai-brief` 歷史列表使用。

## WebSocket /ws/quotes

T1B 提供 ping/pong 與每 10 秒 snapshot 推送。

Client message:

```text
ping
```

Server pong:

```json
{
  "type": "pong",
  "timestamp": "2026-06-19T08:00:00.000000+00:00"
}
```

## GET /api/v1/market/quote

最後更新時間：2026-06-25

回傳指定 symbols 的最新日線行情，供首頁上方「主要指數」與「商品 / 匯率」tile 使用。後端會先從 TimescaleDB `market_ohlcv` 取最新兩根日線計算漲跌與漲跌幅；若 DB 缺資料，會暫時使用 Yahoo Finance chart API fallback。

Query:

- `symbols` required，逗號分隔，例如 `^DJI,^GSPC,BTCUSDT`
- `timeframe` default `1d`

Example:

```text
GET /api/v1/market/quote?symbols=^DJI,^GSPC,^VIX,BTCUSDT&timeframe=1d
```

Response:

```json
{
  "data": [
    {
      "symbol": "^GSPC",
      "price": 7358.22,
      "change": -7.25,
      "change_pct": -0.098,
      "volume": 123456789,
      "timestamp": "2026-06-25T00:00:00+00:00",
      "source": "db"
    }
  ],
  "meta": {
    "count": 1,
    "timeframe": "1d",
    "source": "db+yahoo_fallback"
  }
}
```

注意：

- `yahoo_fallback` 是臨時補位，後續應移到 worker ingestion 流程，讓首頁行情固定走 DB / Redis。
- 若 fallback 也查不到資料，該 symbol 仍會回傳 `price: null`，前端顯示 `--`。

## GET /api/v1/portfolio/holdings

最後更新時間：2026-06-25

回傳目前持倉與觀察清單，供首頁左側 Watchlist 使用。初始 migration 會建立 36 檔持倉，分為 `ETF` 與 `股票` 兩組。

```text
GET /api/v1/portfolio/holdings
```

Response:

```json
{
  "data": [
    {
      "id": 1,
      "symbol": "2330.TW",
      "name_zh": "台積電",
      "name_en": "TSMC",
      "category": "股票",
      "shares": null,
      "cost_basis": null,
      "market_value": null,
      "pnl": null,
      "pnl_pct": null,
      "owned": true,
      "updated_at": "2026-06-25T12:00:00+00:00"
    }
  ],
  "meta": {
    "count": 36
  }
}
```

## POST /api/v1/portfolio/holdings

最後更新時間：2026-06-25

新增或更新單一 Watchlist symbol。首頁搜尋框會先查詢 `/api/v1/market/quote`，再用此 endpoint 寫入 `portfolio_holdings`，預設 `owned=false`、`category="觀察"`。

Request:

```json
{
  "symbol": "AAPL",
  "name_zh": "AAPL",
  "name_en": "AAPL",
  "category": "觀察",
  "owned": false
}
```

Server snapshot push:

```json
{
  "data": [],
  "meta": {
    "type": "snapshot"
  },
  "timestamp": "2026-06-19T08:00:00.000000+00:00"
}
```
