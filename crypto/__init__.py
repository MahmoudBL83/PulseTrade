from flask import Flask, redirect, url_for
import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_cors import CORS
import ssl
from celery import Celery
import json
import ccxt
from crypto.dataStream_price import generateSession,sendMessage,send_ping_packet,socketJob
#from websocket import create_connection
from crypto.crypto_indicators import Indicator2,logger
import time
from flask_httpauth import HTTPBasicAuth
from flask_login import login_required,current_user
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from flask_jwt_extended import (
    JWTManager, jwt_required, create_access_token,
    get_jwt_identity, verify_jwt_in_request
)
import crypto
from functools import wraps
from tradingview_ta import TA_Handler, Interval, Exchange, get_multiple_analysis

def get_current_user():
    if current_user.is_authenticated:
        # User is authenticated using Flask-Login
        return current_user
    elif verify_jwt_in_request(optional=True):
        # User is authenticated using JWT
        jwt_identity = get_jwt_identity()
        #if jwt_identity.get('role') == 'user':
        return crypto.models.User.query.filter_by(email=jwt_identity.get('email')).first()
    else:
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
        #task_default_delivery_mode='transient',  # Make the task transient to prevent persistence
        #worker_concurrency=10,  # Limit the worker concurrency to 1
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
if IS_VERCEL_EARLY:
    # Absolute sqlite path under /tmp bypasses instance_path creation.
    # Ephemeral per invocation — set DATABASE_URL (Postgres) for real persistence.
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:////tmp/crypto.db")
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///crypto.db")
app.config["SQLALCHEMY_TRACK_MODIFICATION"] = False
app.config['SESSION_PERMANENT'] = True
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')

from flask import request
import stripe

scheduler = BackgroundScheduler(timezone="utc")

celery = make_celery(app)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-only-change-me')
app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('SECURITY_PASSWORD_SALT', 'dev-only-change-me')
jwt = JWTManager(app)

def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        
        if current_user.is_authenticated or verify_jwt_in_request(optional=True):
            #check invoices
            invoices = stripe.Invoice.list(customer=current_user.stripe_customer_id)
                
            # Extract relevant information from each invoice
            invoice_list = []
            for invoice in invoices.data:
                invoice_data = {
                    'invoice_id': invoice.id,
                    'amount_due': invoice.amount_due,
                    'status': invoice.status,
                    'created': invoice.created,
                    'billing_reason': invoice.billing_reason,
                    'paid': invoice.paid,
                    'currency': invoice.currency,
                    'url': invoice.lines.url,
                    # Add other relevant invoice information here
                }
                invoice_list.append(invoice_data)
            #check if its subscription didn't exceeded one month
            current_time = datetime.utcnow()
            expiration_time = current_user.sub_date + timedelta(days=30)
            if (invoice_list[0]['paid'] if len(invoice_list) else True) or current_user.subType_id == 1 or request.endpoint == 'create_checkout_session':
                #check all the apis of the all the user's exchanges if they are active and if they are not remove them
                for exchange in current_user.exchanges:
                    # try to connect to the exchange to check if the api is valid
                    try:
                        exchange2 = getattr(ccxt, exchange.name)({
                            'apiKey': exchange.api_key,
                            'secret': exchange.api_secret,
                            'password': exchange.password if exchange.password else None
                        })
                        if exchange.demo:
                            exchange2.set_sandbox_mode(True)

                        if exchange2.check_required_credentials():
                            pass
                        else:
                            # if the api is invalid remove it
                            crypto.notify.send_notification(current_user.email, f"Your API for {exchange.name} is invalid, please update it.")
                            current_user.exchanges.remove(exchange)
                            db.session.commit()


                    except Exception as e:
                        print(e)
                        # if the api is invalid remove it
                        crypto.notify.send_notification(current_user.email, f"Your API for {exchange.name} is invalid, please update it.")
                        current_user.exchanges.remove(exchange)
                        db.session.commit()
                if current_user.is_authenticated:
                    # User is authenticated using Flask-Login
                    return fn(*args, **kwargs)
                else:
                    # User is authenticated using JWT
                    jwt_identity = get_jwt_identity()
                    if jwt_identity.get('role') == 'user':
                        return fn(*args, **kwargs)
            else:
                return redirect(url_for('pricing')) # Redirect to pricing if subscription exceeded one month
            
        return redirect(url_for('login'))  # Redirect to login if not authenticated

    return wrapper



# Create an SSL context
#context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
#context.load_cert_chain('cert.pem', 'key.pem')

mail = Mail(app)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
db = SQLAlchemy(app)

IS_VERCEL = IS_VERCEL_EARLY
socketio = SocketIO(app, async_mode='threading')
#socketio = SocketIO(app, async_mode='gevent')

socketio.init_app(app, cors_allowed_origins="*")
cors = CORS(app)

# Initialize Flask-Login's LoginManager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

#run routes folder
from crypto import auth
from crypto import routes
from crypto import notify
from crypto import data
from crypto import notify
from crypto import gpt
from crypto import transactions
from crypto import orders
from crypto import bots
from crypto import smartTrade
from crypto import demo

'''@celery.task
def update_symbol_data(symbol,intervals,exchange):
    indicator = Indicator(
        exchange=exchange, 
        pair=symbol,
        intervals=intervals,
        verbose=0
    )
    try:
        indicators = indicator.update_data()
        for interval in intervals:
            with open(f"stochData/stoch_{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json", 'w') as f:
                json.dump(indicators[interval][exchange].to_dict(orient='records'), f)
        
        symbol_name = symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)
        with open(f"24changes/{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{exchange}.json", 'w') as f:
            json.dump(changes.to_dict(orient='records'), f)

        with open(f"24changes/{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{exchange}.json", 'r') as f:
            changes = json.load(f)
            # Calculate the percentage change between the opening and closing prices over the past 24 hours
            last_open = changes[-1]['open']
            last_close = changes[-1]['close']
            price_change = (last_close - last_open) / last_open * 100

            # Calculate the percentage change between the opening and closing prices from 24 hours ago
            last_close = changes[-1]['close']
            first_close = changes[0]['close']                
            percent_change_24h = (last_close - first_close) / first_close * 100

        try:
            with open("pricesData/"+f"{exchange.replace('okex','okx').upper()}{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "r") as f:
                existing_data = json.load(f)
                existing_data[f"{exchange.replace('okex','okx').upper()}:{symbol_name}"][4] = price_change
                existing_data[f"{exchange.replace('okex','okx').upper()}:{symbol_name}"][6] = percent_change_24h

                # write updated data to JSON file
                with open("pricesData/"+f"{exchange.replace('okex','okx').upper()}{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "w") as f:
                    json.dump(existing_data, f)
                    
        except FileNotFoundError:
            existing_data = {}

    except Exception as e:
        logger.exception(e)
    '''
tradingViewSocket = "wss://data.tradingview.com/socket.io/websocket"
headers = json.dumps({"Origin": "https://data.tradingview.com"})
#ws = create_connection(tradingViewSocket, headers=headers)

@celery.task
def update_price_data(symbols,exchange):
    while True: 
        start_time = time.time()
        try:
            print("update_price_data for")
            print(exchange)
            data = getattr(ccxt, exchange)().fetch_tickers()
            for _,symbol in data.items():
                try:
                    price = symbol['last'] if symbol['last'] else 0
                    volume = symbol['baseVolume'] if symbol['baseVolume'] else 0
                    change = symbol['change'] if symbol['change'] else 0
                    change_percentage = symbol['percentage'] if symbol['percentage'] else 0
                    high = symbol['high'] if symbol['high'] else 0
                    low = symbol['low'] if symbol['low'] else 0
                    open_price = symbol['open'] if symbol['open'] else 0

                    # Start job
                    symbol_name = f"{exchange.replace('okex','okx').upper()}"+symbol['symbol'].replace('/', '')
                    if price:
                        try:
                            with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'r') as f:
                                json.load(f)
                        except:
                            data = {}
                            with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'w') as f:
                                json.dump(data, f)

                        data = {symbol['symbol']: [price,volume,change,change_percentage,high,low,open_price]}
                        # check if symbol already exists in the JSON file
                        try:
                            with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "r") as f:
                                existing_data = json.load(f)
                        except FileNotFoundError:
                            existing_data = {}
                        if symbol['symbol'] in existing_data:
                            # update symbol value
                            existing_data[symbol['symbol']][0] = price
                            existing_data[symbol['symbol']][1] = volume
                            existing_data[symbol['symbol']][2] = change
                            existing_data[symbol['symbol']][3] = change_percentage
                            existing_data[symbol['symbol']][4] = high
                            existing_data[symbol['symbol']][5] = low
                            existing_data[symbol['symbol']][6] = open_price
                        else:
                            # add symbol to JSON file
                            existing_data.update(data)

                        # write updated data to JSON file
                        with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "w") as f:
                            json.dump(existing_data, f)
                    #else:
                        #ws = create_connection(tradingViewSocket, headers=headers)
                except Exception as e:
                    continue

        except Exception as e:
            continue
        print(f"Elapsed time (update_price_data): {time.time() - start_time} seconds")

'''@celery.task
async def update_price_data(exchanges):
    tasks = []
    start_time = time.time()
    async with aiohttp.ClientSession() as session:
        for exchange in exchanges:
            task = asyncio.create_task(getattr(ccxt2, exchange)().fetch_tickers())
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        

        for exchange, result in zip(exchanges, results):
            print(result)
            if result is not None:
                for _, symbol in result.items():
                    price = symbol['last']
                    volume = symbol['baseVolume']
                    change = symbol['change']
                    change_percentage = symbol['percentage']
                    high = symbol['high']
                    low = symbol['low']
                    open_price = symbol['open']
                    symbol_name = f"{exchange.replace('okex','okx').upper()}{symbol['symbol'].replace('/', '')}"

                    # Load existing data from JSON
                    try:
                        with open(f"pricesData/{symbol_name}.json".replace("/", "").replace(".D", "", 1).replace(".T", "", 1), 'r') as f:
                            existing_data = json.load(f)
                    except FileNotFoundError:
                        existing_data = {}

                    # Update or add symbol data
                    existing_data[symbol['symbol']] = [price, volume, change, change_percentage, high, low, open_price]

                    # Write updated data to JSON file
                    with open(f"pricesData/{symbol_name}.json".replace("/", "").replace(".D", "", 1).replace(".T", "", 1), "w") as f:
                        json.dump(existing_data, f)
    
    print(f"Elapsed time (update_price_data): {time.time() - start_time} seconds")'''

@celery.task
def update_volume_data(symbols,exchange):
    while True:
        time.sleep(0.1)
        start_time = time.time()
        for symbol in symbols:
            # Start job
            x = getattr(ccxt, exchange)().fetch_ticker(symbol)
            volume = x['baseVolume']
            turnover = x['quoteVolume']
            high = x['high']
            low = x['low']
            percentage = x['percentage']
            change = x['change']
            symbol_name = f"{exchange}"+symbol.replace('/', '').replace('okex','okx').upper()
            try:
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'r') as f:
                    data2 = json.load(f)
            except FileNotFoundError:
                data = {}
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'w') as f:
                    json.dump(data, f)

            data = {symbol: [volume,turnover,high,low,percentage,change]}

            # check if symbol already exists in the JSON file
            try:
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "r") as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = {}
            if symbol in existing_data:
                # update symbol value
                existing_data[symbol][0] = volume
                existing_data[symbol][1] = turnover
                existing_data[symbol][2] = high
                existing_data[symbol][3] = low
                existing_data[symbol][4] = percentage
                existing_data[symbol][5] = change
            else:
                # add symbol to JSON file
                existing_data.update(data)

            # write updated data to JSON file
            with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "w") as f:
                json.dump(existing_data, f)

        
        print(f"Elapsed time (update_volume_data): {time.time() - start_time} seconds")

@celery.task
def update_symbol_indicator(symbols,exchange):
    while True:
        start_time = time.time()
        #for symbol in symbols:
        #for interval in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","12h","1d","1w"]:
        symbols_modified = []
        for i,val in enumerate(symbols):
            symbols_modified.append(exchange.replace('okex','okx').upper()+':'+val.replace("/",""))
            #symbols[i] = 'BINANCE:'+symbols[i].replace("/","")
        for interval in ["1m","5m","15m","30m","1h","2h","4h","1d","1W","1M"]:
            '''indicator = Indicator2(
                exchange=exchange, 
                pair=symbol,
                interval=interval,
                verbose=0
            )'''
            try:
                analysis = get_multiple_analysis(
                screener="crypto", 
                interval=interval, 
                symbols=symbols_modified)
                for attr,analysis_obj in analysis.items():
                    try:
                        attr = attr.split(':')[1]
                        #indicators_data = indicator.update_data()
                        obj = {}
                        #file_name_stoch = f"stochData/stoch_{symbol.split(':')[1].replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json"
                        file_name_stoch = f"stochData/stoch_{attr.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json"
                        obj[attr] = {}
                        obj[attr]["indicators"] = analysis_obj.indicators
                        obj[attr]["summary"] = analysis_obj.summary
                        obj[attr]["signals"] = analysis_obj.oscillators["COMPUTE"]
                        obj[attr]["signals2"] = analysis_obj.moving_averages["COMPUTE"]
                        with open(file_name_stoch, 'w') as f:
                            #json.dump(indicators_data[interval].to_dict(orient='records'), f)
                            json.dump(obj, f)
                    except Exception as e:
                        continue
            except Exception as e:
                continue

        print(f"Elapsed time (update_symbol_indicator): {time.time() - start_time} seconds")
        time.sleep(60)

@celery.task
def update_symbol_indicator2(symbols,exchange):
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

def _init_db():
    """Create tables if missing + widen columns older create_all runs made
    too narrow (SQLite ignores lengths; Postgres enforces them). Idempotent."""
    try:
        db.create_all()
    except Exception as e:
        print(f"db.create_all failed: {e}")
    if db.engine.dialect.name == "postgresql":
        from sqlalchemy import text as _text
        for _ddl in (
            "ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(512)",
        ):
            try:
                with db.engine.begin() as _conn:
                    _conn.execute(_text(_ddl))
            except Exception as e:
                print(f"migrate skipped ({_ddl}): {e}")
                break

# Fresh DBs (first Vercel boot, new Postgres) have no tables yet.
with app.app_context():
    _init_db()

exchanges = []
with app.app_context():
    try:
        for x in Exchange2.query.filter(Exchange2.isActive).all():
            exchanges.append(x.exchange)
    except Exception as e:
        print(e)

print(exchanges)

@app.route('/start_data_stream')
@auth2.login_required
def run_data_stream():
    num_bots = Bot.query.filter(Bot.is_hidden == False).count()
    #every 100 bots will be runned in a seperate thread
    chunk_size = 100
    for i in range(0, int(num_bots/chunk_size) + 1):
        bots.bot_func_all.delay((i+1))
    
    num_smas = SmartTrade2.query.count()
    #every 100 smas will be runned in a seperate thread
    chunk_size = 100
    for i in range(0, int(num_smas/chunk_size)+1):
        smartTrade.smart_trade_bot_all.delay((i+1))
        
    notify.monitor_orders.delay()
    chunk_size2 = 20
    for exchange in exchanges:
        #price
        update_price_data.delay(None, exchange)

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
        update_price_data.delay(None, exchange)

        #tradingview indicators
        try:
            update_symbol_indicator.delay(pairs2, exchange)
        except Exception as e:
            pass
        
        #olhcv
        if int(len(pairs)/chunk_size2) > 1:
            for i in range(0, int(len(pairs)/chunk_size2)):
                update_symbol_indicator2.delay(pairs[i*chunk_size2:(i+1)*chunk_size2], exchange)
        else:
            update_symbol_indicator2.delay(pairs, exchange)
        
    return "runned"

@app.route('/stop_data_stream')
@auth2.login_required
def stop_data_stream():
    task_names = ['update_price_data', 'update_symbol_indicator','smart_trade_bot_all','bot_func_all']

    # Inspect active tasks
    i = celery.control.inspect()
    active_tasks = i.active()

    # Revoke tasks with matching names
    for worker, tasks in active_tasks.items():
        for task in tasks:
            if task['name'] in task_names:
                celery.control.revoke(task['id'])

    return "stopped"


@app.route('/api/health')
def api_health():
    try:
        from sqlalchemy import inspect as _inspect
        tables = sorted(_inspect(db.engine).get_table_names())
    except Exception as e:
        tables = [f"error: {e}"]
    return {
        "status": "ok",
        "vercel": IS_VERCEL,
        "demo": bool(os.environ.get("DEMO")),
        "build": "e1d07ac+tables-guard",
        "db_tables": len(tables),
        "has_subscriptions": "subscriptions" in tables,
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


@app.route('/api/cron/<job>')
def api_cron(job):
    """Vercel Cron entrypoint. Queues heavy work; never runs infinite loops inline."""
    if job not in ('price', 'indicator', 'bots', 'smart'):
        return {"status": "unknown job"}, 404
    if IS_VERCEL:
        # On serverless just acknowledge; full loops stay on Docker/Celery worker.
        return {"status": "queued", "job": job}
    # Local/Docker: dispatch to Celery as before.
    if job == 'bots':
        from crypto import bots as _bots
        from crypto.models import Bot as _Bot
        num = _Bot.query.filter(_Bot.is_hidden == False).count()
        for i in range(0, int(num / 100) + 1):
            _bots.bot_func_all.delay((i + 1))
    return {"status": "dispatched", "job": job}



