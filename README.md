# PulseTrade

PulseTrade is a crypto trading dashboard with DCA bots, smart trades, alerts,
portfolio analytics, paper trading, backtesting, and multi-exchange access
through ccxt. The original Flask/Jinja interface and API remain available.
The React interface is served at `/app/`.

## Run locally

Use Python 3.12 or 3.13 and Node.js 22 or newer. Copy `.env.example` to
`.env`, then replace the development secrets. Generate a persistent Fernet
key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```bash
pip install -r requirements.txt
python run.py
```

The Flask server listens on `http://127.0.0.1:5000` by default. The classic
interface is at `/` and the React interface is at `/app/`. The compiled
React assets are included in the repository. For frontend development:

```bash
cd frontend
npm ci
npm run dev
```

`npm run build` checks TypeScript and writes production assets to
`crypto/static/app`. To use synthetic market data while offline, set
`MARKET_DATA=synthetic`. Paper trading does not require exchange keys.

## Deploy

`docker compose up --build` starts the web process, Postgres, Redis, and a
legacy Celery worker. The web process runs the trading engine in scheduler
mode. Set the secrets in `.env` before starting it.

Vercel uses `api/index.py` and `vercel.json`. Configure `DATABASE_URL`
with persistent Postgres and set `SECRET_KEY`, `JWT_SECRET_KEY`,
`SECURITY_PASSWORD_SALT`, `FERNET_KEY`, and any provider credentials in
the Vercel project. SQLite on serverless storage is ephemeral. Keep the
Fernet key stable so saved exchange credentials remain decryptable.

Serverless instances do not run the in-process scheduler, Celery worker, or
ccxt.pro streaming service. Set `CRON_SECRET` and schedule authenticated
`GET /api/cron/all` calls with `Authorization: Bearer <CRON_SECRET>` to
advance paper orders, alerts, bots, and smart trades. The `price` and
`indicator` cron routes are compatibility routes; market data is fetched
on demand. `/api/health` reports build, database, and engine status.
No cron schedule is registered in `vercel.json` yet. Vercel Hobby cron
jobs can run only once per day, which is too infrequent for live trading
decisions. Run the scheduler on an always running Docker server for active
bots, smart trades, and alerts; use the Vercel app for the dashboard. Both
deployments must share the same persistent `DATABASE_URL` and `FERNET_KEY`.

## Binance connections

The server calls Binance through ccxt to load markets and validate the API
key. A restricted server IP can cause an HTTP 451 response; an invalid key,
missing permission, testnet/live mismatch, or IP allowlist can cause an
authentication error. The connection API reports these cases separately.

The Vercel function region is set to Frankfurt (`fra1`) in `vercel.json`.
This changes the server's location, which is the location Binance sees for
the API request. It cannot guarantee that Binance will accept every account
or IP. Vercel outbound IPs can change unless static egress is configured;
consider a fixed-egress backend if the exchange key requires an IP
allowlist. Never put exchange credentials in the browser or repository.

## Verify

```bash
pip install -r requirements-dev.txt
python -m pytest -q
cd frontend
npm ci
npm run build
```

GitHub Actions runs the backend suite and the frontend build on pushes and
pull requests. `openapi.yaml` documents the legacy API; `CHANGELOG.md`
records the modernization changes. See `SECURITY.md` before production use.
