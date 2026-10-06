# PulseTrade (refreshed)

Crypto trading dashboard: DCA bots, SmartTrade TP/SL, multi-exchange via ccxt,
TradingView signals. Flask 3 + Python 3.12. Original 2023 monolith, refreshed
for public release: secrets to env, pinned deps, Vercel + Docker support.
No behavior changes to trading logic — additive only.

## Quick start (local)
```bash
cp .env.example .env  # fill FERNET_KEY etc.
pip install -r requirements.txt
python run.py  # full mode: web + celery + scheduler
```

## Deploy to Vercel
1. Push this repo to GitHub.
2. Vercel -> New Project -> import. Framework: Other, entry `api/index.py`.
3. Set env vars from `.env.example`:
   `SECRET_KEY JWT_SECRET_KEY SECURITY_PASSWORD_SALT FERNET_KEY`
   `DATABASE_URL` (Neon/Supabase Postgres), `REDIS_URL` (Upstash, optional),
   `MAIL_* STRIPE_API_KEY GOOGLE_API_KEY HF_TOKEN TAP_API_KEY`.
4. Generate Fernet key: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`.

### Vercel limits (by design)
- No Celery worker, APScheduler, raw threads, or SocketIO streaming.
  `run.py` and `crypto/__init__.py` skip them when `VERCEL=1`.
- Background loops (`update_price_data`, indicators, bots) stay on Docker worker.
  Vercel Cron can hit `/api/cron/price|indicator|bots|smart` (ack/queue only).
- SQLite default is local-only. Use Postgres `DATABASE_URL` in prod.
- Health: `/api/health`.

## Docker (full bots, local parity)
```bash
docker compose up --build
# web :8000, worker runs celery, postgres + redis included
```

## Demo mode (no API keys)```bash
DEMO=1 python run.py
# then visit /api/demo/seed once to create catalog rows
```
- `/getPrice/?symbol=BTCUSDT` returns synthetic snapshot (`"demo": true`).
- `/openOrders/`, `/lastTrades/` return synthetic book/trades.
- `/api/demo/status` reports mode. Real exchange paths untouched.
- Full endpoint list: `openapi.yaml`.

## Email verification (off by default)
- `REQUIRE_EMAIL_VERIFICATION=0` (default): register auto-verifies, login never
  blocks on mail. Use this until real SMTP creds exist.
- Set `REQUIRE_EMAIL_VERIFICATION=1` + `MAIL_USERNAME`/`MAIL_PASSWORD` to enforce
  verification emails again. No code change needed.

## Repo hygiene
- Secrets: none committed. All via env (`crypto/__init__.py`, `models.py`,
  `auth.py`, `routes.py`, `bard.py`, `gpt.py`, `gpt_ace.py` patched).
- Excluded: venv, `__pycache__`, `*.db`, `*.pem`, `pricesData/ volumesData/`
  `orders/ trades/ stochData*/ rsiData/ 24changes/`, certs, logs.
- Old duplicate `coinex/` package and stale outer `flask/` copy not included.
- `requirements2.txt` (scraping/g4f extras) kept for reference, not installed.

## Structure
- `crypto/` Flask package (factory in `__init__.py`, models/routes/auth/bots/...)
- `templates/` + `static/` Jinja + theme assets
- `wsgi.py` gunicorn/Docker entry, `api/index.py` Vercel entry
- `vercel.json`, `Dockerfile`, `docker-compose.yml`

## Security
Old keys found in legacy code were removed. Rotate all before prod.
See `SECURITY.md`.
