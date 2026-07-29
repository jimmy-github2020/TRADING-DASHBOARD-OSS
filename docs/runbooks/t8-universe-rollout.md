# T8 Instrument Universe Rollout

T8 adds canonical instruments, provider-symbol mappings, synchronization runs,
watchlists, and tracking tiers. Existing `symbols`, `portfolio_holdings`, and
`market_ohlcv` data must be preserved.

## Safety Rules

- Take and verify a database backup before migration.
- Apply migrations `013`, `014`, and `015` separately and in order.
- Stop on the first error.
- Do not restore or roll back a successful migration automatically.
- Do not run metadata sync until all migration checks pass.
- Metadata sync must not enable OHLCV tracking for the full catalog.

## Source Checkpoint

Create a bundle outside tracked source before deployment:

```powershell
New-Item -ItemType Directory -Force .\backups
git bundle create .\backups\pre-t8-source.bundle --all
git bundle verify .\backups\pre-t8-source.bundle
```

`backups/` must remain ignored and must never be committed.

## Database Backup

Use `pg_dump` in custom format and record its SHA256:

```powershell
docker compose exec -T postgres pg_dump `
  -U trading -d trading_dashboard -Fc `
  > .\backups\pre-t8-trading-dashboard.dump

Get-FileHash -Algorithm SHA256 .\backups\pre-t8-trading-dashboard.dump
docker compose exec -T postgres pg_restore --list `
  /path/to/mounted/backup.dump
```

Adapt the verification command to the backup location available to PostgreSQL.
Never commit the dump.

## Apply Migrations

Review each SQL file before execution. Apply and verify one migration at a time:

```powershell
Get-Content .\db\migrations\013_instrument_catalog.sql |
  docker compose exec -T postgres psql `
    -U trading -d trading_dashboard -v ON_ERROR_STOP=1

Get-Content .\db\migrations\014_instrument_sync_runs.sql |
  docker compose exec -T postgres psql `
    -U trading -d trading_dashboard -v ON_ERROR_STOP=1

Get-Content .\db\migrations\015_watchlists.sql |
  docker compose exec -T postgres psql `
    -U trading -d trading_dashboard -v ON_ERROR_STOP=1
```

After each migration, use read-only queries to confirm:

- existing table counts did not decrease;
- every holding resolves to an instrument;
- sync-run tables are initially empty;
- the default watchlist contains only migrated existing holdings;
- no OHLCV rows were created by the schema migration.

## Metadata Sync

Always run dry-run first:

```powershell
docker compose run --rm --no-deps worker `
  python main.py sync-instruments --market tw --source twse --dry-run

docker compose run --rm --no-deps worker `
  python main.py sync-instruments --market tw --source tpex --dry-run
```

Only proceed after reviewing scope, provider terms, row counts, and errors.
Nasdaq and market-data providers have separate terms and are not implied by the
TWSE/TPEx OGDL metadata license. See
[`docs/provider-policy.md`](../provider-policy.md).

## Rollback

Prefer an application rollback to the source checkpoint while leaving additive
tables unused. Restore the database only through a separately reviewed recovery
procedure, from a verified backup, and with an explicit maintenance window.
