.PHONY: dev down logs migrate test

dev:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/001_init.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/002_notification_events.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/003_t2_quant_analysis.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/004_backtest_results.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/005_ai_market_briefs.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/006_portfolio_holdings.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/007_daily_notes.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/008_notification_settings.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/013_instrument_catalog.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/014_instrument_sync_runs.sql
	docker compose exec -T postgres psql -U $${POSTGRES_USER:-trading} -d $${POSTGRES_DB:-trading_dashboard} -f /docker-entrypoint-initdb.d/015_watchlists.sql

test:
	docker compose config --quiet
