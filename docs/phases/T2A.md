# Phase T2A 實作記錄

最後更新時間：2026-06-22

## 目標

建立量化分析的後端基礎：strategies / signals schema、策略條件掃描器、手動掃描 API 與 worker 排程。

## 已完成

- 建立 branch：`feature/t2-quant-analysis`
- 新增 migration：`db/migrations/003_t2_quant_analysis.sql`
- 新增資料表：
  - `strategies`
  - `signals`
- Worker 新增 `StrategyScanner`
- Worker 新增 CLI：

```powershell
docker compose exec -T worker python main.py strategy-scan --timeframe 1d --limit 120
```

- Worker scheduler 每 15 分鐘執行一次 strategy scan。
- FastAPI 新增 endpoints：
  - `GET /api/v1/strategies`
  - `POST /api/v1/strategies`
  - `PATCH /api/v1/strategies/{strategy_id}/active`
  - `DELETE /api/v1/strategies/{strategy_id}`
  - `GET /api/v1/signals`
  - `POST /api/v1/signals/scan`
  - `POST /api/signals/scan`，相容 Perplexity 草稿路徑

## 支援條件

策略 JSONB 格式：

```json
{
  "logic": "AND",
  "direction": "neutral",
  "conditions": [
    {
      "type": "rsi",
      "period": 14,
      "operator": "<",
      "value": 30
    }
  ]
}
```

目前支援：

- `rsi`: RSI(n) `<`, `<=`, `>`, `>=`, `==` 指定值
- `macd_cross`: `bullish` / `bearish`
- `ma_cross`: short MA 上穿/下穿 long MA
- `bollinger_break`: upper / lower
- `kd_cross`: bullish / bearish

## 錯誤處理

- 單一 symbol 掃描失敗會寫入 `provider_errors`。
- 失敗不會中斷整批掃描。

## 驗收結果

最後驗收時間：2026-06-22 16:40 Asia/Taipei

| 項目 | 結果 |
| --- | --- |
| `docker compose build api worker` | 通過 |
| `docker compose up -d api worker` | 通過 |
| `003_t2_quant_analysis.sql` | 成功套用 |
| `docker compose exec -T api python -m compileall .` | 通過 |
| `docker compose exec -T worker python -m compileall .` | 通過 |
| `POST /api/v1/strategies` | 通過 |
| `GET /api/v1/strategies` | 通過，conditions 回傳為 JSON object |
| `POST /api/v1/signals/scan` | 通過，scanned_symbols=23, scanned_strategies=1, triggered_signals=23, errors=0 |
| `worker strategy-scan` | 通過，scanned_symbols=23, scanned_strategies=1, triggered_signals=23, errors=0 |
| `GET /api/v1/signals` | 通過 |

驗收時建立的 smoke strategy 已停用，避免排程持續產生測試訊號。

## 延後項目

以下 Perplexity 草稿中的項目拆到後續批次：

- T2B：前端 `/strategies` 策略條件編輯器
- T2C：相關性矩陣 `/analysis`
- T2D：波動率排行

## 注意事項

- `ENABLE_LIVE_TRADING=false` 維持不變。
- T2A 沒有修改 T1 資料抓取、行情 API、K 線圖或通知語氣。
