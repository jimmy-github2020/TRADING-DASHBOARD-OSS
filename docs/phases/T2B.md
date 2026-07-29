# Phase T2B 實作記錄

最後更新時間：2026-06-22

## 目標

建立 `/strategies` 前端策略條件編輯器，讓使用者可以建立策略、管理啟用狀態、刪除策略、查看最近 signals，並手動觸發 T2A 的 strategy scan。

## 已完成

- 新增 `/strategies` 頁面。
- 新增 React Query provider，集中管理策略與 signals API 狀態。
- 策略清單支援：
  - 顯示策略名稱。
  - 將 JSONB conditions 轉為人類可讀摘要。
  - 啟用 / 停用 toggle。
  - 刪除前確認。
  - 每 60 秒自動 refetch。
- 策略列可展開查看最近 10 筆 signals：
  - symbol
  - direction
  - price
  - triggered_at
- 新增策略編輯器支援：
  - 策略名稱。
  - AND / OR 邏輯切換。
  - 多條件視覺化區塊。
  - 條件新增與刪除。
  - RSI 數值比較。
  - MACD / MA / Bollinger / KD 事件型條件。
- 新增「立即掃描」按鈕，呼叫 `POST /api/v1/signals/scan`。
- 操作成功或失敗以 toast 顯示。
- 增加桌機與手機響應式版面。

## 條件格式決策

Perplexity 草稿中的 JSONB 範例使用 `rules`：

```json
{
  "logic": "AND",
  "rules": []
}
```

但 T2A 後端目前實際支援的是 `conditions`：

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

因本階段限制是不修改 T2A 後端，T2B 前端儲存時會序列化為 T2A 實際支援的格式。摘要顯示邏輯保留對 `rules` 的兼容處理，方便後續若要升級策略 schema 時逐步銜接。

## API 使用

- `GET /api/v1/strategies`
- `POST /api/v1/strategies`
- `PATCH /api/v1/strategies/{strategy_id}/active`
- `DELETE /api/v1/strategies/{strategy_id}`
- `GET /api/v1/signals?limit=200`
- `POST /api/v1/signals/scan`

## 待驗收

- 可新增策略並存入 DB。
- 策略清單正確顯示 conditions 摘要。
- 啟用 / 停用可即時反映。
- 刪除策略有確認提示。
- 展開策略可看到最近 signals。
- 手動掃描可觸發並顯示 scanned_symbols / triggered_signals / errors。
- `docker compose build web` 通過。
- 桌機 1280px 與手機 375px 可正常操作。

## 後續階段

- T2C：相關性矩陣 `/analysis`。
- T2D：波動率排行。
