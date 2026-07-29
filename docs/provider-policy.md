# Provider and Data Policy

Provider adapter source code and provider-returned data are separate works. The
Apache-2.0 license for this repository does not grant rights to market data,
news, trademarks, or third-party API content.

## Default Behavior

- External news integrations are disabled.
- Worker background automation is disabled.
- Notification delivery is dry-run-first.
- Live trading is disabled.
- Catalog sync is an explicit command.
- Catalog entries do not automatically enter quote, daily, or intraday tracking.
- No fetched data is included in source releases.

## Provider Matrix

| Provider | Default | Intended use |
|---|---|---|
| TWSE company metadata | Explicit sync | OGDL-licensed listed-company metadata with attribution |
| TPEx company metadata | Explicit sync | OGDL-licensed OTC-company metadata with attribution |
| Yahoo Finance / yfinance | Explicit adapter use | User-directed research; no bundled or redistributed data |
| Binance | Explicit adapter use | Public market-data API subject to rate limits and provider terms |
| Nasdaq Trader directory | Explicit sync | Adapter only; do not redistribute downloaded snapshots |
| NewsAPI | Disabled | Requires `NEWS_API_ENABLED=true`, a user key, and an eligible plan |
| UDN Money RSS | Disabled | Requires `UDN_RSS_ENABLED=true` and authorization for the intended use |
| Alternative.me | Explicit use | Attribution must be displayed with Fear & Greed data |
| OpenAI / Gemini / Perplexity | User credentials | Optional AI analysis under each provider's terms |
| Telegram / LINE | Dry-run-first | User-owned notification credentials and recipients |

## Attribution

Taiwan company metadata sources and OGDL attribution are recorded in
[`NOTICE`](../NOTICE). Alternative.me data must retain prominent attribution in
the same user-facing context where it is displayed.

## Adding a Provider

A provider contribution must document:

1. endpoint and authentication;
2. terms and redistribution posture;
3. rate limits and retry behavior;
4. data retention and deletion behavior;
5. opt-in configuration;
6. synthetic tests that make no external request;
7. failure behavior when credentials or permission are absent.

When rights are unclear, publish the adapter disabled by default and do not ship
provider-returned data.
