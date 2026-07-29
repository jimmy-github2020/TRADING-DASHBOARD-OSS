# TRADING-DASHBOARD

Self-hosted market research dashboard focused on transparent data ingestion,
canonical instrument identity, watchlists, technical analysis, backtesting, and
AI-assisted market briefs.

The project is designed for research and education. It does not execute live
trades, and live-trading behavior is disabled by default.

## Highlights

- FastAPI, Next.js, PostgreSQL/TimescaleDB, Redis, and a Python worker
- Taiwan and U.S. instrument catalog with provider-symbol mappings
- Custom watchlists separated from portfolio holdings
- Catalog, quote, daily, and intraday tracking tiers
- OHLCV ingestion through provider adapters
- Technical indicators, ranking, correlation, and backtesting APIs
- Dry-run-first Telegram and LINE notification infrastructure
- AI market briefs with user-supplied provider credentials
- Additive migrations and documented recovery procedures

## Safety Defaults

- `ENABLE_LIVE_TRADING=false`
- `NOTIFICATION_DRY_RUN=true`
- `WORKER_AUTOMATION_ENABLED=false`
- News providers are disabled until explicitly enabled
- Instrument catalog sync does not automatically enable OHLCV tracking
- No credentials, portfolio data, downloaded market data, or database dumps are
  included in the repository

This software is not financial advice. Market data may be delayed, incomplete,
or inaccurate. Review provider terms before enabling any external integration.

## Quick Start

Requirements:

- Docker Desktop or Docker Engine with Docker Compose v2
- Git

```bash
git clone https://github.com/jimmy-github2020/TRADING-DASHBOARD-OSS.git
cd TRADING-DASHBOARD-OSS
cp .env.example .env
docker compose config --quiet
docker compose up -d
```

PowerShell:

```powershell
git clone https://github.com/jimmy-github2020/TRADING-DASHBOARD-OSS.git
Set-Location TRADING-DASHBOARD-OSS
Copy-Item .env.example .env
docker compose config --quiet
docker compose up -d
```

Open:

- Web: http://localhost:3100
- API health: http://localhost:8011/health
- OpenAPI: http://localhost:8011/docs

Database migrations are intentionally not applied by the Quick Start command.
Read [Setup](docs/setup.md) and create a backup before applying migrations.

## Verification

The CI-equivalent checks do not start the production Compose stack:

```bash
docker compose config --quiet
docker compose build api worker web
docker compose run --rm --no-deps api \
  python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm --no-deps worker \
  python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm --no-deps web npm run check:encoding
docker compose run --rm --no-deps web npm run build
```

## Data Providers

Provider adapter code and provider-returned data have different licenses.
External integrations are opt-in, require user-supplied credentials where
applicable, and must not be assumed to grant redistribution rights.

Read [Provider Policy](docs/provider-policy.md) before enabling sync or news
features.

## Documentation

- [Setup](docs/setup.md)
- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Provider Policy](docs/provider-policy.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)
- [T8 Universe Rollout](docs/runbooks/t8-universe-rollout.md)

## License

Source code is licensed under [Apache License 2.0](LICENSE). Third-party
services, market data, news content, and dependency licenses remain subject to
their respective terms. See [NOTICE](NOTICE).
