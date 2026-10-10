from flask import Flask, redirect, url_for, request, jsonify
import os
import logging
from datetime import datetime, timedelta, timezone

try:  # optional .env support for local development (never overrides real env)
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_cors import CORS
from celery import Celery
import json
import ccxt
from crypto.dataStream_price import generateSession,sendMessage,send_ping_packet,socketJob
from crypto.crypto_indicators import Indicator2,logger
import time
from flask_httpauth import HTTPBasicAuth
from apscheduler.schedulers.background import BackgroundScheduler
from flask_jwt_extended import JWTManager, create_access_token, decode_token
import crypto
from functools import wraps
from tradingview_ta import TA_Handler, Interval, Exchange, get_multiple_analysis
import stripe

from crypto.cache import TTLCache
from crypto.errors import register_error_handlers, wants_json

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TESTING = os.environ.get("PULSE_TESTING") == "1"


def get_current_user():
    """The authenticated user from the session cookie *or* a Bearer JWT
    (see ``_load_user_from_bearer``), else None."""
    try:
        if current_user and current_user.is_authenticated:
            return current_user._get_current_object()
    except Exception:
        pass
    return None

auth2 = HTTPBasicAuth()

@auth2.verify_password
def verify_password(username,password):
    expected = os.environ.get('ADMIN_STREAM_PASSWORD', '')
    if expected and password == expected:
        return True
    return False

def make_celery(app):
    redis_url = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379')
    celery = Celery(
        'trading_bots',
        backend=redis_url,
        broker=redis_url,
        task_default_queue='bot_queue',  # Set a specific queue for the task
    )

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

IS_VERCEL_EARLY = bool(os.environ.get("VERCEL"))
_flask_kwargs = {"template_folder": "templates"}
if IS_VERCEL_EARLY:
    # Vercel filesystem is read-only except /tmp; keep Flask instance dir there.
    _flask_kwargs["instance_path"] = "/tmp/instance"
app = Flask(__name__, **_flask_kwargs)
if IS_VERCEL_EARLY or os.environ.get("TRUST_PROXY") == "1":
    # Behind Vercel / a reverse proxy: trust one hop of X-Forwarded-* headers.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def _database_url():
    default = "sqlite:////tmp/crypto.db" if IS_VERCEL_EARLY else "sqlite:///crypto.db"
    url = os.environ.get("DATABASE_URL", default) or default
    if url.startswith("postgres://"):  # Heroku/Render style URLs
        url = "postgresql://" + url[len("postgres://"):]
    return url

app.config["SQLALCHEMY_DATABASE_URI"] = _database_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
    # Survive Neon/Supabase idle disconnects and serverless cold starts.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 280}
app.config['SESSION_PERMANENT'] = True
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or 'noreply@example.com'
app.config['JSON_SORT_KEYS'] = False
# Long-lived caching for static assets (fingerprinted React assets are immutable).
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=7)

# tzinfo object, not a string: zone names are case-sensitive on Linux (no "utc" file in tzdata).
scheduler = BackgroundScheduler(timezone=timezone.utc)

celery = make_celery(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-only-change-me')
app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('SECURITY_PASSWORD_SALT', 'dev-only-change-me')
app.config['JWT_TOKEN_LOCATION'] = ['headers']
# Tokens issued before 2026 carried a dict identity; keep accepting them.
app.config['JWT_VERIFY_SUB'] = False
jwt = JWTManager(app)

mail = Mail(app)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
for _var in ("SECRET_KEY", "JWT_SECRET_KEY", "SECURITY_PASSWORD_SALT", "FERNET_KEY",
             "ADMIN_PASSWORD", "ADMIN_EMAIL"):
    if not os.environ.get(_var) and not TESTING:
        print(f"SECURITY WARNING: {_var} env var not set — using insecure default. Set it before any public deploy.")
db = SQLAlchemy(app)

IS_VERCEL = IS_VERCEL_EARLY
_frontend = os.environ.get('FRONTEND_URL', 'https://pulse-trade-zeta.vercel.app').rstrip('/')
_allowed_origins = [_frontend, "http://localhost:5000", "http://127.0.0.1:5000",
                    "http://localhost:5173", "http://127.0.0.1:5173"]
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=_allowed_origins)
cors = CORS(app, resources={r"/api/*": {"origins": _allowed_origins}})
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_VERCEL_EARLY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

try:  # gzip/brotli responses (big win for the 5k-line legacy templates)
    from flask_compress import Compress
    app.config.setdefault("COMPRESS_MIMETYPES", [
        "text/html", "text/css", "text/javascript", "application/javascript",
        "application/json", "image/svg+xml"])
    app.config.setdefault("COMPRESS_MIN_SIZE", 1024)
    Compress(app)
except Exception as _e:
    print(f"compression disabled: {_e}")

# Initialize Flask-Login's LoginManager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

register_error_handlers(app)


# --------------------------------------------------------------------------- JWT

def issue_token(user):
    """Access token for ``user``. Identity is the email (a string, as required
    by PyJWT>=2.10); role/uid ride along as claims."""
    return create_access_token(identity=user.email, additional_claims={"role": "user", "email": user.email, "uid": user.id})


def token_revoked(jti):
    if not jti:
        return False
    from crypto.models import TokenBlocklist
    try:
        return db.session.query(TokenBlocklist.id).filter_by(jti=jti).first() is not None
    except Exception:
        return False


@jwt.token_in_blocklist_loader
def _jwt_blocklist(jwt_header, jwt_payload):
    return token_revoked(jwt_payload.get("jti"))


@login_manager.request_loader
def _load_user_from_bearer(req):
    """Authenticate API calls carrying ``Authorization: Bearer <jwt>`` so the
    whole app (including legacy views using flask_login.current_user) works
    for the React client and other API consumers."""
    header = req.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(None, 1)[1].strip() if " " in header else ""
    if not token or token in ("null", "undefined"):
        return None
    try:
        data = decode_token(token)
    except Exception:
        return None
    if data.get("type") != "access" or token_revoked(data.get("jti")):
        return None
    ident = data.get("sub")
    email = ident.get("email") if isinstance(ident, dict) else (data.get("email") or ident)
    from crypto.models import User
    return User.query.filter_by(email=email).first() if email else None


# --------------------------------------------------------------------------- auth decorators

_invoice_cache = TTLCache(ttl=600)
_cred_cache = TTLCache(ttl=900)

# Views a lapsed subscriber must still reach (paying, billing info, logging out).
SUBSCRIPTION_EXEMPT = {
    "create_checkout_session", "create_checkout_session_tap", "get_subscription",
    "get_subscriptions_and_invoices", "logout", "logout2", "pricing",
}


def _unauthorized():
    if wants_json():
        return jsonify({"message": "authentication required", "ok": False}), 401
    return redirect(url_for('login'))


def _latest_invoice(user):
    """(has_invoices, latest_paid) from Stripe, cached for 10 minutes."""
    if not (stripe.api_key and getattr(user, 'stripe_customer_id', None)):
        return False, True
    hit = _invoice_cache.get(user.id)
    if hit is not None:
        return hit
    try:
        invoices = stripe.Invoice.list(customer=user.stripe_customer_id, limit=1).data
        if invoices:
            inv = invoices[0]
            paid = getattr(inv, "paid", None)
            result = (True, bool(paid) if paid is not None else inv.status == "paid")
        else:
            result = (False, True)
    except Exception as e:
        print(f"stripe invoice check skipped: {e}")
        result = (False, True)
    return _invoice_cache.set(user.id, result)


def subscription_ok(user):
    has_invoices, invoice_paid = _latest_invoice(user)
    is_free = (user.subType_id == 1) or (getattr(getattr(user, 'subType', None), 'type', '') == 'free') or user.subType_id is None
    try:
        expired = bool(user.sub_date and datetime.utcnow() > user.sub_date + timedelta(days=30))
    except Exception:
        expired = False
    if not (invoice_paid or is_free):
        return False
    if expired and not is_free and not (has_invoices and invoice_paid):
        return False
    return True


def _validate_exchange_creds(user):
    """Drop exchange connections whose stored credentials are unusable.
    Local checks only (decrypt + required fields), cached per exchange."""
    from cryptography.fernet import InvalidToken
    from crypto.functions import build_exchange
    from crypto.errors import ApiError
    for exchange in user.exchanges.all():
        if exchange.is_paper or _cred_cache.get(exchange.id):
            continue
        try:
            build_exchange(exchange).check_required_credentials()
            _cred_cache.set(exchange.id, True)
        except (InvalidToken, ccxt.AuthenticationError, ApiError) as e:
            print(f"removing invalid exchange connection {exchange.name} for user {user.id}: {e}")
            name = exchange.name
            db.session.delete(exchange)
            db.session.commit()
            crypto.notify.send_notification(f"Your API for {name} is invalid, please update it.***system", user.id)
        except Exception as e:  # e.g. FERNET_KEY missing: server problem, keep the row
            print(f"exchange credential check skipped for {exchange.name}: {e}")


def auth_required(fn):
    """Logged-in user (session or Bearer JWT); no subscription gating."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if get_current_user() is None:
            return _unauthorized()
        return fn(*args, **kwargs)
    return wrapper


def jwt_required(fn):
    """Legacy guard for the trading area: logged in, subscription in good
    standing, and stored exchange credentials still usable."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return _unauthorized()
        if request.endpoint not in SUBSCRIPTION_EXEMPT and not subscription_ok(user):
            if wants_json():
                return jsonify({"message": "Your subscription has expired. Please renew it.",
                                "ok": False, "redirect": url_for('pricing')}), 402
            return redirect(url_for('pricing'))
        _validate_exchange_creds(user)
        return fn(*args, **kwargs)
    return wrapper


#run routes folder
from crypto import auth
from crypto import routes
from crypto import notify
from crypto import data
from crypto import transactions
from crypto import orders
from crypto import bots
from crypto import smartTrade
from crypto import demo
from crypto import api_v2
from crypto import spa

tradingViewSocket = "wss://data.tradingview.com/socket.io/websocket"
headers = json.dumps({"Origin": "https://data.tradingview.com"})


def _price_file(symbol_name):
    return "pricesData/" + f"{symbol_name}.json".replace("/", "").replace(".D", "", 1).replace(".T", "", 1)


@celery.task
def update_price_data(symbols,exchange):
    os.makedirs("pricesData", exist_ok=True)
    while True:
        start_time = time.time()
        try:
            data = getattr(ccxt, exchange)().fetch_tickers()
            for _,symbol in data.items():
                try:
                    price = symbol['last'] if symbol['last'] else 0
                    if not price:
                        continue
                    volume = symbol['baseVolume'] if symbol['baseVolume'] else 0
                    change = symbol['change'] if symbol['change'] else 0
                    change_percentage = symbol['percentage'] if symbol['percentage'] else 0
                    high = symbol['high'] if symbol['high'] else 0
                    low = symbol['low'] if symbol['low'] else 0
                    open_price = symbol['open'] if symbol['open'] else 0
                    symbol_name = f"{exchange.replace('okex','okx').upper()}"+symbol['symbol'].replace('/', '')
                    path = _price_file(symbol_name)
                    try:
                        with open(path, "r") as f:
                            existing_data = json.load(f)
                    except (FileNotFoundError, ValueError):
                        existing_data = {}
                    existing_data[symbol['symbol']] = [price,volume,change,change_percentage,high,low,open_price]
                    tmp = path + ".tmp"
                    with open(tmp, "w") as f:
                        json.dump(existing_data, f)
                    os.replace(tmp, path)  # atomic: readers never see half-written JSON
                except Exception:
                    continue
        except Exception as e:
            print(f"update_price_data({exchange}) failed: {e}")
            time.sleep(5)
            continue
        print(f"Elapsed time (update_price_data): {time.time() - start_time} seconds")
        time.sleep(1)

@celery.task
def update_volume_data(symbols,exchange):
    os.makedirs("volumesData", exist_ok=True)
    while True:
        time.sleep(0.1)
        start_time = time.time()
        for symbol in symbols:
            try:
                x = getattr(ccxt, exchange)().fetch_ticker(symbol)
            except Exception as e:
                print(f"update_volume_data {symbol}: {e}")
                continue
            symbol_name = f"{exchange}"+symbol.replace('/', '').replace('okex','okx').upper()
            path = "volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1)
            try:
                with open(path, "r") as f:
                    existing_data = json.load(f)
            except (FileNotFoundError, ValueError):
                existing_data = {}
            existing_data[symbol] = [x['baseVolume'], x['quoteVolume'], x['high'], x['low'], x['percentage'], x['change']]
            with open(path, "w") as f:
                json.dump(existing_data, f)
        print(f"Elapsed time (update_volume_data): {time.time() - start_time} seconds")

@celery.task
def update_symbol_indicator(symbols,exchange):
    os.makedirs("stochData", exist_ok=True)
    while True:
        start_time = time.time()
        symbols_modified = []
        for i,val in enumerate(symbols):
            symbols_modified.append(exchange.replace('okex','okx').upper()+':'+val.replace("/",""))
        for interval in ["1m","5m","15m","30m","1h","2h","4h","1d","1W","1M"]:
            try:
                analysis = get_multiple_analysis(
                screener="crypto",
                interval=interval,
                symbols=symbols_modified)
                for attr,analysis_obj in analysis.items():
                    try:
                        attr = attr.split(':')[1]
                        obj = {}
                        file_name_stoch = f"stochData/stoch_{attr.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json"
                        obj[attr] = {}
                        obj[attr]["indicators"] = analysis_obj.indicators
                        obj[attr]["summary"] = analysis_obj.summary
                        obj[attr]["signals"] = analysis_obj.oscillators["COMPUTE"]
                        obj[attr]["signals2"] = analysis_obj.moving_averages["COMPUTE"]
                        with open(file_name_stoch, 'w') as f:
                            json.dump(obj, f)
                    except Exception as e:
                        continue
            except Exception as e:
                continue

        print(f"Elapsed time (update_symbol_indicator): {time.time() - start_time} seconds")
        time.sleep(60)

@celery.task
def update_symbol_indicator2(symbols,exchange):
    os.makedirs("stochData2", exist_ok=True)
    while True:
        for symbol in symbols:
            time.sleep(4)
            for interval in ['5m','15m',"30m","1h","4h","1d","1w"]:
                try:
                    indicator = Indicator2(
                        exchange=exchange,
                        pair=symbol,
                        interval=interval,
                        verbose=0
                    )
                    try:
                        indicators_data = indicator.update_data()
                        file_name_stoch = f"stochData2/stoch_{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json"
                        with open(file_name_stoch, 'w') as f:
                            json.dump(indicators_data[interval].to_dict(orient='records'), f)
                    except Exception as e:
                        continue
                except Exception as e:
                    continue

from crypto.models import Exchange2,Pair,Bot, User
from crypto.models import SmartTrade as SmartTrade2
from crypto.migrate import init_db as _init_db_impl


def _init_db():
    """Create tables, add columns introduced by newer releases and widen
    columns older create_all runs made too narrow. Idempotent."""
    _init_db_impl(db)

# Fresh DBs (first Vercel boot, new Postgres) have no tables yet.
with app.app_context():
    try:
        _init_db()
    except Exception as e:
        print(f"db init failed: {e}")

exchanges = []
with app.app_context():
    try:
        for x in Exchange2.query.filter(Exchange2.isActive).all():
            exchanges.append(x.exchange)
    except Exception as e:
        print(e)

def _safe_delay(task, *args):
    """Dispatch a celery task; log and skip when the broker is unreachable
    instead of 500ing the HTTP request."""
    try:
        task.delay(*args)
        return True
    except Exception as e:
        print(f"celery dispatch skipped: {e}")
        return False


def engine_mode():
    """Who runs bots / smart trades / alerts:
    scheduler (in-process APScheduler, default for `python run.py`),
    celery (legacy infinite worker loops started via /start_data_stream),
    cron (only /api/cron/*; default on Vercel) or off."""
    default = "cron" if IS_VERCEL else "scheduler"
    return os.environ.get("ENGINE", default).strip().lower()


@app.route('/start_data_stream')
@auth2.login_required
def run_data_stream():
    if IS_VERCEL:
        # No broker/worker on serverless — .delay() would raise Kombu errors.
        return jsonify({"status": "disabled_on_serverless"}), 202
    dispatched = {"bots": 0, "smart_trades": 0, "data": 0}
    if engine_mode() == "celery":
        try:
            num_bots = Bot.query.filter(Bot.is_hidden == False).count()
            num_smas = SmartTrade2.query.count()
        except Exception as e:
            print(f"celery dispatch skipped: {e}")
            return jsonify({"status": "dispatch_failed"}), 502
        #every 100 bots will be runned in a seperate thread
        chunk_size = 100
        for i in range(0, int(num_bots/chunk_size) + 1):
            dispatched["bots"] += _safe_delay(bots.bot_func_all, (i+1))
        for i in range(0, int(num_smas/chunk_size)+1):
            dispatched["smart_trades"] += _safe_delay(smartTrade.smart_trade_bot_all, (i+1))
        _safe_delay(notify.monitor_orders)
    chunk_size2 = 20
    for exchange in exchanges:
        pairs2 = []
        pairs = []
        try:
            for currency in getattr(ccxt, exchange)().fetch_markets():
                if currency['spot']:
                    pairs2.append(currency['symbol'])
        except Exception as e:
            pass
        for pair in Pair.query.filter(Pair.isActive).all():
            pairs.append(pair.serialize()['pair'])

        #price
        dispatched["data"] += _safe_delay(update_price_data, None, exchange)

        #tradingview indicators
        dispatched["data"] += _safe_delay(update_symbol_indicator, pairs2, exchange)

        #olhcv
        if int(len(pairs)/chunk_size2) > 1:
            for i in range(0, int(len(pairs)/chunk_size2)):
                dispatched["data"] += _safe_delay(update_symbol_indicator2, pairs[i*chunk_size2:(i+1)*chunk_size2], exchange)
        else:
            dispatched["data"] += _safe_delay(update_symbol_indicator2, pairs, exchange)

    return jsonify({"status": "runned", "engine": engine_mode(), "dispatched": dispatched})

@app.route('/stop_data_stream')
@auth2.login_required
def stop_data_stream():
    task_names = ['update_price_data', 'update_symbol_indicator','smart_trade_bot_all','bot_func_all']
    try:
        active_tasks = celery.control.inspect(timeout=2).active() or {}
    except Exception as e:
        return jsonify({"status": "broker_unreachable", "error": str(e)}), 503

    # Revoke tasks with matching names
    revoked = 0
    for worker, tasks in active_tasks.items():
        for task in tasks:
            if task['name'].split('.')[-1] in task_names:
                celery.control.revoke(task['id'], terminate=True)
                revoked += 1

    return jsonify({"status": "stopped", "revoked": revoked})


BUILD_ID = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7] or "local"


@app.route('/api/health')
def api_health():
    try:
        from sqlalchemy import inspect as _inspect
        tables = sorted(_inspect(db.engine).get_table_names())
        db_ok = True
    except Exception as e:
        tables = []
        db_ok = False
    from crypto import market as _market
    return {
        "status": "ok" if db_ok else "degraded",
        "vercel": IS_VERCEL,
        "demo": os.environ.get("DEMO", "0") == "1",
        "build": BUILD_ID,
        "db": db_ok,
        "db_tables": len(tables),
        "has_subscriptions": "subscriptions" in tables,
        "engine": engine_mode(),
        "market_data": _market.mode(),
        "react_app": spa.has_build(),
        "time": datetime.utcnow().isoformat() + "Z",
    }


_tables_ready = False

@app.before_request
def _ensure_tables():
    """Serverless instances each have their own ephemeral /tmp; make sure
    tables exist in this instance before serving. No-op when already ready."""
    global _tables_ready
    if _tables_ready:
        return
    try:
        _init_db()
        _tables_ready = True
    except Exception as e:
        print(f"ensure_tables failed: {e}")


def _cron_authorized():
    secret = os.environ.get("CRON_SECRET", "")
    if not secret:
        return TESTING or not IS_VERCEL  # local/dev convenience; set CRON_SECRET in prod
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {secret}" or request.args.get("secret") == secret


@app.route('/api/cron/<job>')
def api_cron(job):
    """Vercel Cron / external scheduler entrypoint. Runs one bounded engine
    pass (never an infinite loop) so bots, smart trades, alerts and paper
    orders progress on serverless deploys. Protected by CRON_SECRET."""
    jobs = {'price': (), 'indicator': (), 'bots': ('bots',), 'smart': ('smart',),
            'alerts': ('alerts',), 'paper': ('paper',), 'all': ('paper', 'alerts', 'bots', 'smart')}
    if job not in jobs:
        return {"status": "unknown job"}, 404
    if not _cron_authorized():
        return {"status": "unauthorized"}, 401
    if not jobs[job]:
        # Market data is fetched on demand (cached) by crypto.market now.
        return {"status": "ok", "job": job, "note": "market data is served on demand"}
    from crypto import engine as _engine
    budget = float(os.environ.get("CRON_BUDGET_SECONDS", "8"))
    stats = _engine.tick(jobs[job], budget=budget)
    return {"status": "dispatched", "job": job, "stats": stats}


def start_background_engine():
    """Start the in-process scheduler (daily stats + engine ticks). Call once
    per process (run.py / a single-process gunicorn)."""
    from crypto import engine as _engine
    if engine_mode() == "scheduler":
        interval = max(5, int(os.environ.get("ENGINE_INTERVAL", "15")))
        scheduler.add_job(_engine.tick_in_app, 'interval', seconds=interval, id="engine_tick",
                          replace_existing=True, max_instances=1, coalesce=True)
    if not scheduler.running:
        scheduler.start()
    from crypto import stream as _stream
    _stream.start(app)  # ccxt.pro live tickers when MARKET_STREAM=1
