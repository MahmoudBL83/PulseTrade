# Changelog

## 2.0.0 — 2026 modernization

Every legacy page and `/api/v1` endpoint is kept; the classic UI still works at
its old URLs. A new React app is served at `/app`.

### Fixed — crashes
- 104 of 537 route checks used to end in HTTP 500 (missing auth guards,
  `connectExchange()` returning a redirect that callers then used as an exchange,
  missing-field `KeyError`s, views returning `None`, async views needing an extra
  Flask package, models without `serialize()`). A smoke test now hits every route
  as anonymous, user and admin on every CI run.
- Central error handling: JSON errors with proper status codes for API calls,
  friendly pages for browsers, tracebacks in the log, never leaked to clients.
- `send_notification()` silently dropped every message without a `***type`
  suffix, and the invalid-API-key notice passed its arguments in the wrong order.
- `check_assets_json()` returned after the first element, breaking multi-exchange
  asset merging on the dashboard.
- Legacy login with IP check returned a redirect to a `fetch()` call (users never
  reached the code page) and the OTP form rendered raw JSON.
- `/openOrders/` demo fallback returned an object where the trade page expects
  an array.
- `run.py` used Flask's reloader, which runs the app twice.
- Docker image did not include `search_crypto.py`, which `routes.py` imports.

### Fixed — trading engine
- Bots without entry conditions never opened a deal.
- The stop-loss timeout `sleep()`-ed inside the shared loop (freezing every bot)
  and never sold afterwards; it is now non-blocking.
- Filled safety orders were subtracted from the position, so they were never
  sold at take profit; the average entry price is now maintained.
- Safety-order deviation compounded incorrectly; safety orders could be placed
  without an open deal and were left behind when a deal closed.
- Cooldown used `.seconds` (ignoring days) from a timestamp that was never updated.
- "Close deal after timeout" froze the bot instead of closing the deal.
- Deleting an idle bot market-sold coins it never bought.
- Buy fees taken in the base asset made closing sells fail (position tracking is
  now net of fees and capped at the free balance).
- Smart trades: conditional "Smart Trade" entries **sold** instead of bought,
  conditional limit entries were placed at price 0, multi-level take profits
  stopped after the first level.
- Exchange order ids are strings on many venues; Integer columns were widened.

### Security
- Email login codes were derived from a hard-coded public TOTP secret, and stored
  in plaintext in the client-side session. Codes are now random, only an HMAC is
  stored, attempts are limited.
- `/checkout_success_tab` granted paid plans without verifying the payment; the
  Tap charge is now verified server-side. Stripe sessions must belong to the user.
- `/api/v1/user_stats/` let any user read another user's stats.
- Socket.IO broadcast every user's notifications to everyone; events now go to
  per-user rooms.
- Unauthenticated `/api/cron/*`, connect/disconnect exchange, notifications and
  smart-trade endpoints now require auth (cron uses `CRON_SECRET`).
- Users could not see their own support tickets; other users' tickets are now
  private. Admins can reply and close.
- Brute-force lockout, login history, logout revokes JWTs, generic reset-password
  answer (no email probing), avatar URL validation, CSV formula-injection
  neutralised, webhook URLs restricted to Discord/Slack (no SSRF).
- `/drop_all/` requires `?confirm=DROP`.

### Performance
- The trading-area guard no longer re-validates every exchange key on every
  request (cached), Stripe invoice checks are cached for 10 minutes.
- Market data (tickers, candles, order books) is cached and served by a market
  data service with exchange fallbacks; price lookups no longer depend on the
  Celery price workers.
- gzip/brotli compression, long-lived caching of fingerprinted assets,
  O(n) market table sorting, capped notification/post queries, DB indexes.

### Added
- **Paper trading exchange** (ccxt-compatible): every page, order type, DCA bot
  and smart trade works without API keys.
- **Engine** that runs bots, smart trades, alerts and paper order matching from
  an in-process scheduler (`python run.py`), Celery, or `/api/cron/all`
  (serverless).
- **Technical-analysis engine** (26 indicators, TradingView-style summary) used
  by `/getPrice/`, `/api/v1/indicators`, bot conditions and the new UI.
- **Price alerts** (above / below / % move, repeating) with Discord, Slack and
  Telegram delivery.
- **Watchlist**, **trade journal** with stats, **portfolio analytics** (Sharpe,
  Sortino, volatility, max drawdown, CAGR, Calmar), CSV exports.
- **Backtester** for the DCA strategy plus a **grid-search optimizer**.
- **Authenticator-app 2FA**, admin TOTP, security log.
- **Market context beside ccxt**: CoinGecko (market caps, dominance, trending),
  alternative.me Fear & Greed, DefiLlama TVL — cached, with labelled offline
  fallbacks.
- **ccxt.pro live tickers** (optional `MARKET_STREAM=1`).
- Stripe webhook (`/webhooks/stripe`) to keep plans in sync.
- `/api/v2` JSON API for the React app; automatic schema upgrades for existing
  SQLite/Postgres databases.
