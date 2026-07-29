# Contributing

Thank you for helping improve TRADING-DASHBOARD.

## Before You Start

- Search existing issues before opening a new one.
- Use synthetic fixtures; never submit credentials, portfolio data, downloaded
  market data, or copyrighted news content.
- Keep external providers opt-in and document their terms and attribution.
- Do not introduce live-trading behavior without a separate security design and
  explicit maintainer review.

## Development

Create a branch, keep changes focused, and run:

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

## Developer Certificate of Origin

Contributions use the Developer Certificate of Origin 1.1. Sign each commit:

```text
Signed-off-by: Your Name <your-email@example.com>
```

By signing off, you certify that you have the right to submit the contribution
under this project's license. See https://developercertificate.org/.

## Pull Requests

Explain the behavior change, data/provider implications, tests performed, and
rollback path. Maintainers may request changes when a contribution expands
network access, data retention, credential scope, or migration risk.
