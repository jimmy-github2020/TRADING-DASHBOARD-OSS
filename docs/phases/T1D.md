# Phase T1D 實作記錄

最後更新時間：2026-06-19

## 目標

建立通知系統基礎，支援 LINE Messaging API、Telegram Bot API、訊號掃描、cooldown、防重複推播與 audit log。T1D 預設 dry-run，避免未設定 token 時誤發通知。

## 已完成

- 新增 migration：`db/migrations/002_notification_events.sql`。
- 新增 worker 設定：
  - `LINE_CHANNEL_ACCESS_TOKEN`
  - `LINE_USER_ID`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `NOTIFICATION_DRY_RUN`
  - `NOTIFICATION_COOLDOWN_HOURS`
- 新增訊號掃描：
  - RSI(14) < 30
  - RSI(14) > 70
  - MACD bullish cross
  - Bollinger upper break
  - Bollinger lower break
  - VIX > 30
- 新增通知 client：
  - LINE Messaging API push message
  - Telegram Bot API sendMessage
  - dry-run mode
- 新增 cooldown：
  - 預設 4 小時
  - 依 `event_type/provider/symbol/timeframe` 防重複
- 新增 CLI：

```powershell
docker compose exec -T worker python main.py notify-scan --timeframe 1d --limit 200 --dry-run
```

## 訊息語氣規則

通知只能使用：

- 條件觸發
- 列入觀察
- 市場波動風險升高
- 本訊息僅供研究與紀錄，非投資建議

禁止輸出：

- 買點
- 賣點
- 目標價
- 正式投資建議
- 保證型語句

## 驗收結果

最後驗收時間：2026-06-19 17:36 Asia/Taipei

已執行：

```powershell
docker compose build worker
docker compose up -d worker
docker compose exec -T worker python -m compileall .
docker compose exec -T postgres psql -U trading -d trading_dashboard -f /docker-entrypoint-initdb.d/002_notification_events.sql
docker compose exec -T worker python main.py notify-scan --timeframe 1d --limit 200 --dry-run
```

驗收結果：

| 項目 | 結果 |
| --- | --- |
| `002_notification_events.sql` | 成功建立 table 與 index |
| `notify-scan --dry-run` | 成功 |
| scanned symbols | 23 |
| triggered events | 2 |
| delivered dry-run channel events | 4 |
| `notification_events` 寫入 | 4 筆 |
| 第二次 dry-run cooldown | `skipped_cooldown=2`, `delivered_events=0` |

本次 dry-run 觸發：

- `BZ=F`：`rsi_oversold`
- `2330.TW`：`macd_bullish_cross`

## 已知限制

- T1D 尚未建立 Flex Message 卡片格式。
- T1D 尚未建立前端通知設定 UI。
- 預設 dry-run，實送需明確設定 token 並將 `NOTIFICATION_DRY_RUN=false`。
