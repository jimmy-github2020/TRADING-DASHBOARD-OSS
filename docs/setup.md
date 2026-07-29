# 環境設定

最後更新時間：2026-07-29

## 必要工具

- Docker Desktop
- Docker Compose v2
- Node.js 20.9+，本機開發 web 時使用
- Python 3.12，本機開發 api/worker 時使用

## 啟動步驟

1. Clone 並確認 workspace：

```powershell
git clone https://github.com/jimmy-github2020/TRADING-DASHBOARD-OSS.git
Set-Location TRADING-DASHBOARD-OSS
git rev-parse --show-toplevel
```

2. 建立環境檔：

```powershell
Copy-Item .env.example .env
```

保留 `ENABLE_LIVE_TRADING=false`、`NOTIFICATION_DRY_RUN=true`、
`NEWS_API_ENABLED=false` 與 `UDN_RSS_ENABLED=false`，直到你已閱讀
服務條款並明確決定啟用。

3. 啟動服務：

```powershell
docker compose up -d
```

4. 檢查服務：

```powershell
docker compose ps
```

5. 開啟頁面：

- http://localhost:3100
- http://localhost:8011/health

## Migration

Postgres 第一次初始化 container 時會自動執行：

```text
db/migrations/001_init.sql
```

若需要手動重跑：

```powershell
docker compose exec -T postgres psql -U trading -d trading_dashboard -f /docker-entrypoint-initdb.d/001_init.sql
```

## 連接埠

| Service | External Port |
| --- | --- |
| Web | 3100 |
| API | 8011 |
| Postgres | 5442 |
| Redis | 6380 |

## 注意事項

- `.env` 不要 commit。
- `data/postgres` 與 `data/redis` 只保留 `.gitkeep`。
- T0 不需要 API key。
- `ENABLE_LIVE_TRADING=false` 必須維持預設關閉。
- API 原規劃外部 port 是 8001，但本機已有既有服務占用，因此 T0 實作使用 8011 對外、8001 對容器內。

## T1A 手動資料入庫

最後更新時間：2026-06-19

重建 worker：

```powershell
docker compose build worker
docker compose up -d worker
```

手動抓一個 yfinance 標的：

```powershell
docker compose exec -T worker python main.py run-once --provider yfinance --symbol ^GSPC --timeframe 1d
```

手動抓一個 Binance 標的：

```powershell
docker compose exec -T worker python main.py run-once --provider binance --symbol BTCUSDT --timeframe 1h
```

手動抓全部預設 symbols 的 200 根日線：

```powershell
docker compose exec -T worker python main.py run-once --all-symbols --timeframe 1d
```

查入庫資料：

```powershell
docker compose exec -T postgres psql -U trading -d trading_dashboard -c "select provider, symbol, timeframe, count(*) from market_ohlcv group by 1,2,3 order by 1,2,3;"
```

查 ingestion 記錄：

```powershell
docker compose exec -T postgres psql -U trading -d trading_dashboard -c "select id, provider, symbol, timeframe, status, rows_inserted, rows_updated, error_count from data_ingestion_runs order by id desc limit 10;"
```

## T1D notification dry-run

Last updated: 2026-06-19

Apply notification migration:

```powershell
Get-Content -Path db\migrations\002_notification_events.sql -Encoding UTF8 | docker compose exec -T postgres psql -U trading -d trading_dashboard
```

Run notification scan in dry-run mode:

```powershell
docker compose exec -T worker python main.py notify-scan --timeframe 1d --limit 200 --dry-run
```

Check notification events:

```powershell
docker compose exec -T postgres psql -U trading -d trading_dashboard -c "select channel, event_type, symbol, provider, timeframe, status, created_at from notification_events order by id desc limit 20;"
```
