# T1-D 每日筆記持久化

最後更新時間：2026-06-26

## 實作範圍

- 新增 `daily_notes` 資料表，每天一筆筆記，使用 `note_date DATE UNIQUE` 保證日期唯一。
- 新增 `GET /api/notes/{date}` 與 `POST /api/notes/{date}`，供首頁右欄每日筆記讀寫。
- 保留 `/api/v1/notes/{date}` 相容路由，回傳專案標準 `data/meta/timestamp` 格式。
- 將首頁右欄「每日筆記」由 in-memory textarea 改為 DB 持久化。
- 新增日期選擇器，可直接輸入日期或點開瀏覽器原生月曆選日期。
- 新增前一天、後一天、今天快捷按鈕。
- 輸入停止 1.5 秒後自動儲存，顯示「編輯中 / 儲存中 / 已儲存 / 儲存失敗」狀態。

## API

### GET /api/notes/{date}

日期格式為 `YYYY-MM-DD`。若該日沒有資料，回傳空內容。

```json
{
  "note_date": "2026-06-26",
  "content": "",
  "created_at": null,
  "updated_at": null
}
```

### POST /api/notes/{date}

```json
{
  "content": "今日觀察、操作記錄..."
}
```

回傳：

```json
{
  "id": 1,
  "note_date": "2026-06-26",
  "content": "今日觀察、操作記錄...",
  "created_at": "2026-06-26T08:00:00+00:00",
  "updated_at": "2026-06-26T08:01:30+00:00"
}
```

## 決策原因

- 每日筆記是交易紀律與盤後檢討的一部分，重新整理後不可遺失，因此改由 PostgreSQL 保存。
- 使用原生 `input type="date"`，可以同時支援鍵盤輸入與月曆選擇，不額外引入日期套件。
- `/api/notes` 採直接 JSON，符合右欄筆記的輕量讀寫需求；`/api/v1/notes` 保留標準 API response，方便未來若要整合到統一 client。

## 已知問題

- 目前沒有使用者登入與權限分流，筆記屬於本機單人使用情境。
- Docker migration 已新增，但既有資料庫 volume 需要手動執行 `db/migrations/007_daily_notes.sql` 才會建立資料表。
- 目前受工具使用量限制，尚未能在本回合替使用者實際執行 Docker DB migration 與 API 驗收。

## 驗收指令

```powershell
Get-Content db\migrations\007_daily_notes.sql | docker compose exec -T postgres psql -U trading -d trading_dashboard -v ON_ERROR_STOP=1
docker compose build api web
docker compose up -d api web
docker compose exec -T api python -m compileall .
docker compose run --rm --no-deps web npm run build
```

API 驗收：

```powershell
curl http://localhost:8011/api/notes/2026-06-26
curl -X POST http://localhost:8011/api/notes/2026-06-26 -H "Content-Type: application/json" -d "{\"content\":\"測試每日筆記\"}"
curl http://localhost:8011/api/notes/2026-06-26
docker compose exec -T postgres psql -U trading -d trading_dashboard -c "SELECT note_date, content, updated_at FROM daily_notes ORDER BY note_date DESC LIMIT 5;"
```
