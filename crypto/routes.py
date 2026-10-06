import json
from flask import render_template, request, redirect, url_for, jsonify,Response,session
import ccxt
import ccxt.async_support as ccxt2
from flask_login import login_required,current_user
from crypto import app,db,socketio,celery,scheduler,jwt_required
from crypto.auth import admin_required
from crypto.models import User, Exchange, Post, Category,UserCount,BotCount,Pair,Bot,SmartTrade, BalanceHistory24h, Subscription, BotHistory, Transaction,Exchange2, TransactionHistory
from crypto.notify import send_notification
from crypto.dataStream_indicators import update_symbol_data2,calculate_signals2
from search_crypto import search
from crypto.exchanges import connectExchange
from crypto.functions import getPrice_assets
import asyncio
import time
import math
from sqlalchemy import desc
import sys
import requests
import stripe
import os
from datetime import datetime
from datetime import timedelta
from crypto import get_current_user
stripe.api_key = os.environ.get('STRIPE_API_KEY', '')



@app.route("/docs/")
def docs():
    return render_template("docs-page.html")

@app.route("/ai/")
def ai():
    return render_template("index2.html")

@app.route("/")
def index():
    current_user = get_current_user()
    return render_template("index.html", 
                            subscriptions=Subscription.query.all(),
                            is_logged_in=current_user.is_authenticated if current_user else False,
                            exchanges=Exchange2.query.filter(Exchange2.isActive).all(),
                            posts = Post.query.order_by(desc(Post.created_at)).limit(3).all(),
                        )

@app.route("/ai_chat/")
def ai_chat():
    return render_template("ai_chat.html")

@app.route("/ai_social/")
def ai_social():
    return render_template("ai_social.html")

@app.route("/drop_all/")
@admin_required
def drop_all():
    db.drop_all()
    return jsonify("dropped")

@app.route("/create_all/")
@admin_required
def create_all():
    db.create_all()
    '''for x in ['news','updates','announcements','general','trading','technical','fundamental','other']:
        db.session.add(Category(title=x))'''
    if Subscription.query.count() < 3:
        db.session.add(Subscription(type='free',max_bots=5,max_sma=10))
        db.session.add(Subscription(type='advanced',max_bots=25,max_sma=math.inf))
        db.session.add(Subscription(type='pro',max_bots=100,max_sma=math.inf))
    '''for exchange in ccxt.exchanges:
        db.session.add(Exchange2(exchange=exchange))
        db.session.commit()
    db.session.commit()

    pairs = []

    exchange = getattr(ccxt, 'binance')()
    time.sleep(exchange.describe()['rateLimit'] / 1000)
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            pairs.append(currency['symbol'])

    exchange = getattr(ccxt, 'okx')()
    time.sleep(exchange.describe()['rateLimit'] / 1000)
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            if currency['symbol'] not in pairs:
                pairs.append(currency['symbol'])
    
    exchange = getattr(ccxt, 'kucoin')()
    time.sleep(exchange.describe()['rateLimit'] / 1000)
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            if currency['symbol'] not in pairs:
                pairs.append(currency['symbol'])

    exchange = getattr(ccxt, 'gateio')()
    time.sleep(exchange.describe()['rateLimit'] / 1000)
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            if currency['symbol'] not in pairs:
                pairs.append(currency['symbol'])

    exchange = getattr(ccxt, 'bybit')()
    time.sleep(exchange.describe()['rateLimit'] / 1000)
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            if currency['symbol'] not in pairs:
                pairs.append(currency['symbol'])
    

    for pair in pairs:
        db.session.add(Pair(pair=pair))
        db.session.commit()'''
    
    return jsonify("created")

def calculate_stats():
    with app.app_context():
        db.session.add(UserCount(count=User.query.count()))
        db.session.add(BotCount(count=Bot.query.filter(Bot.isActive==True).count()))
        db.session.commit()

def calculate_stats_users():
    with app.app_context():
        for user in User.query.all():
            user.update_balance()
            balance_history = BalanceHistory24h(balance_btc=user.balance_btc,balance_usd=user.balance_usd,owner_id=user.id)
            db.session.add(balance_history)
            user.balance_history24h.append(balance_history)
            db.session.commit()

def calculate_stats_users_bots():
    with app.app_context():
        for user in User.query.all():
            profit = 0
            for bot in user.bots.all():
                #get the last 24 hour only
                #note that the value is "last_total_profit_time = db.Column(db.DateTime,default=datetime.utcnow())"
                if bot.last_total_profit_time > datetime.utcnow() - timedelta(days=1):
                    profit += bot.total_profit
                else:
                    profit += 0
            
            try:
                profit = profit - BotHistory.query.filter(BotHistory.owner_id == user.id).order_by(desc(BotHistory.timestamp)).first().profit 
            except:
                profit= profit
            
            bot_history = BotHistory(profit=profit,owner_id=user.id)
            db.session.add(bot_history)
            user.bot_history.append(bot_history)
            db.session.commit()

def calculate_trans():
    with app.app_context():
        total = 0
        for trans in Transaction.query.all():
            total += trans.value
        trans_history = TransactionHistory(value=total)
        db.session.add(trans_history)
        db.session.commit()



scheduler.add_job(calculate_stats, 'cron', hour=0, minute=0, second=0)
scheduler.add_job(calculate_trans, 'cron', hour=0, minute=0, second=0)
scheduler.add_job(calculate_stats_users, 'cron', hour=0, minute=0, second=0)
scheduler.add_job(calculate_stats_users_bots, 'cron', hour=0, minute=0, second=0)
#scheduler.add_job(calculate_users, 'interval', seconds = 5)
#scheduler.add_job(calculate_trans, 'interval', seconds = 20)

################################################Dashboard##############################################################

@app.route("/dashboard/")
@jwt_required
def dashboard():
    current_user = get_current_user()
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    #current_user.update_balance()

    '''exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    # Initialize CCXT exchange object
    exchange = connectExchange(exchange_name)
    

    assets_json = []

    for exchange_user in current_user.exchanges.all():
        api_key,api_secret,password = exchange_user.get_creds()
        if password:
            exchangeForUser = getattr(ccxt, exchange_user.name)({
                'apiKey': api_key,
                'secret': api_secret,
                'password':password,
            })
        else:
            exchangeForUser = getattr(ccxt, exchange_user.name)({
                'apiKey': api_key,
                'secret': api_secret,
            })
        if exchange_user.demo:
            exchangeForUser.set_sandbox_mode(True)

        assets = exchangeForUser.fetch_balance()
        for asset, amount in assets["total"].items():
            price = getPrice_assets(exchangeForUser.name,asset+'/USDT')
            if not price:
                price = 0
            if check_assets_json(assets_json, asset):
                for asset_json in assets_json:
                    if asset_json['currency'] == asset:
                        asset_json['free'] += assets["free"][asset]
                        asset_json['used'] += assets["used"][asset]
                        asset_json['total'] += amount
                        asset_json['eqUSD'] += amount*price
            else:
                assets_json.append({"currency":asset,"free":assets["free"][asset],"used":assets["used"][asset],"total":amount,"price":price,'eqUSD':amount*price})'''

    '''open_orders = exchange.fetch_open_orders()
    for exchange_user in current_user.exchanges:
        api_key,api_secret,password = exchange_user.get_creds()
        if password:
                exchangeNow = getattr(ccxt, exchange_user.name)({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'password':password,
                })
        else:
            exchangeNow = getattr(ccxt, exchange_user.name)({
                'apiKey': api_key,
                'secret': api_secret,
            })
        if exchange_user.demo:
            exchangeNow.set_sandbox_mode(True)

        for trans in exchangeNow.fetch_ledger():
            trans['exchange'] = exchange_user.name
            transactions.append(trans)'''
            
    return render_template("dashboard.html",
                                #assets=assets_json,
                                bots=current_user.bots.filter(Bot.isActive,Bot.is_hidden==False).all(),
                                balance_usd = current_user.balance_usd,
                                balance_btc = current_user.balance_btc,
                                balance_history = json.dumps([bal.serialize() for bal in current_user.balance_history]),
                                balance_history24h = json.dumps([bal.serialize() for bal in current_user.balance_history24h]),
                                exchanges=current_user.exchanges.all(),
                                profit_monthly_btc=current_user.profit_monthly_btc,
                                profit_monthly_usd=current_user.profit_monthly_usd,
                                profit_daily_btc = current_user.profit_daily_btc,
                                profit_daily_usd = current_user.profit_daily_usd,
                                profit_monthly_percent_btc = current_user.profit_monthly_percent_btc,
                                profit_monthly_percent_usd = current_user.profit_monthly_percent_usd,
                                profit_daily_percent_btc = current_user.profit_daily_percent_btc,
                                profit_daily_percent_usd = current_user.profit_daily_percent_usd,
                                profit_overall_btc = current_user.profit_overall_btc,
                                profit_overall_usd = current_user.profit_overall_usd,
                                sharpe_ratio=current_user.sharpe_ratio,
                                deviation=current_user.deviation,
                                sortino_ratio=current_user.sortino_ratio,
                                current_user=current_user,
                                notifications=current_user.notifications.all(),
                                posts = Post.query.all(),
                                SMAs = SmartTrade.query.filter(SmartTrade.user_id==current_user.id,SmartTrade.isActive).all(),
                           )

@app.route("/api/v1/user_stats/",methods=['GET','POST'])
@jwt_required
def user_info():
    current_user = get_current_user()
    # Initialize CCXT exchange object
    current_user.update_balance()
    if 'exchange_name' in request.json:
        exchange_name = request.json['exchange_name']
    else :
        exchange_name = None

    if 'user_id' in request.json:
        user_id = request.json['user_id']
        current_user2 = User.query.filter(User.id==user_id).first()
    else:
        current_user2 = current_user
    
    if exchange_name:
        exchange = connectExchange(exchange_name)
        # Retrieve historical price data for BTC/USDT and ETH/USDT
        if 'fetchOpenOrders' in exchange.describe()['has']:
            if exchange.describe()['has']['fetchOpenOrders']:
                open_orders = exchange.fetch_open_orders()
            else:
                open_orders = []
        else:
            open_orders = []

        try:
            if 'fetchLedger' in exchange.describe()['has']:
                if exchange.describe()['has']['fetchLedger']:
                    transactions = exchange.fetch_ledger()
                else:
                    transactions = []
            else:
                transactions = []
        except:
            transactions = []
    else:
        open_orders = []
        transactions = []
        not_supported_trans = []
        for exchange_user in current_user2.exchanges:
            api_key,api_secret,password = exchange_user.get_creds()
            if password:
                    exchangeNow = getattr(ccxt, exchange_user.name)({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'password':password,
                    })
            else:
                exchangeNow = getattr(ccxt, exchange_user.name)({
                    'apiKey': api_key,
                    'secret': api_secret,
                })
            if exchange_user.demo:
                exchangeNow.set_sandbox_mode(True)

            try:
                if 'fetchLedger' in exchangeNow.describe()['has']:
                    if exchangeNow.describe()['has']['fetchLedger']:
                        for trans in exchangeNow.fetch_ledger():
                            trans['exchange'] = exchange_user.name
                            transactions.append(trans)
                    else:
                        not_supported_trans.append(exchange_user.name)
                else:
                    not_supported_trans.append(exchange_user.name)
            except:
                not_supported_trans.append(exchange_user.name)

    return jsonify({
                        'exchnages':[exchange.serialize() for exchange in current_user2.exchanges.all()],
                        'open_orders':open_orders,
                        'balance_history':json.dumps([bal.serialize() for bal in current_user.balance_history]),
                        'transactions':transactions,
                        'balance_usd':current_user2.balance_usd,
                        'balance_btc':current_user2.balance_btc,
                        'profit_monthly_btc':current_user2.profit_monthly_btc,
                        'profit_monthly_usd':current_user2.profit_monthly_usd,
                        'profit_daily_btc':current_user2.profit_daily_btc,
                        'profit_daily_usd':current_user2.profit_daily_usd,
                        'profit_monthly_percent_btc':current_user2.profit_monthly_percent_btc,
                        'profit_monthly_percent_usd':current_user2.profit_monthly_percent_usd,
                        'profit_daily_percent_btc':current_user2.profit_daily_percent_btc,
                        'profit_daily_percent_usd':current_user2.profit_daily_percent_usd,
                        'profit_overall_btc':current_user2.profit_overall_btc,
                        'profit_overall_usd':current_user2.profit_overall_usd,
                        'sharpe_ratio':current_user2.sharpe_ratio,
                        'sortino_ratio':current_user2.sortino_ratio,
                        'deviation':current_user2.deviation,
                        'not_supported_trans':not_supported_trans,
                    })

@app.route("/api/v1/edit_user_info/", methods=['POST'])
@jwt_required
def edit_user_info():
    current_user = get_current_user()
    current_user.img = request.data.decode("utf-8")
    db.session.commit()
    

@app.route("/api/v1/reset_stats")
@jwt_required
def reset_stats():
    current_user = get_current_user()
    current_user.reset_stats()
    return jsonify({"message":"your stats have been reset","ok":True})

@app.route("/api/v1/assets")
@jwt_required
def assets():
    current_user = get_current_user()
    exchange_name = request.args.get('exchange')
    
    assets_json = []
    if exchange_name.lower() != "all":
        try:
            exchange = connectExchange(exchange_name)
            assets = exchange.fetch_balance()
            for asset, amount in assets["total"].items():
                price = getPrice_assets(exchange.name,asset+'/USDT')
                if amount > 0:
                    assets_json.append({"currency":asset,"free":assets["free"][asset],"used":assets["used"][asset],"total":amount,"price":price,'eqUSD':amount*price})
        except:
            pass
    else:
        for exchange_user in current_user.exchanges.all():
            try:
                api_key,api_secret,password = exchange_user.get_creds()
                if password:
                    exchangeForUser = getattr(ccxt, exchange_user.name)({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'password':password,
                    })
                else:
                    exchangeForUser = getattr(ccxt, exchange_user.name)({
                        'apiKey': api_key,
                        'secret': api_secret,
                    })
                if exchange_user.demo:
                    exchangeForUser.set_sandbox_mode(True)

                assets = exchangeForUser.fetch_balance()
                for asset, amount in assets["total"].items():
                    if amount > 0:
                        price = getPrice_assets(exchangeForUser.name,asset+'/USDT')
                        if not price:
                            price = 0
                        if check_assets_json(assets_json, asset):
                            for asset_json in assets_json:
                                if asset_json['currency'] == asset:
                                    asset_json['free'] += assets["free"][asset]
                                    asset_json['used'] += assets["used"][asset]
                                    asset_json['total'] += amount
                                    asset_json['eqUSD'] += amount*price
                        else:
                            assets_json.append({"currency":asset,"free":assets["free"][asset],"used":assets["used"][asset],"total":amount,"price":price,'eqUSD':amount*price})
            except:
                pass
    
    return jsonify(assets_json)

########################################################end of dashboard############################################################

@app.route("/subscription")
def pricing():
    current_user = get_current_user()
    return render_template("pricing.html",
                           notifications = current_user.notifications.all(),
                           exchanges=current_user.exchanges.all(),
                           current_user=current_user,
                           posts = Post.query.all(),
                           subscriptions=Subscription.query.all()
                           )

'''#change subscription type
@app.route("/api/v1/subscription",methods=['POST'])
@jwt_required
def change_subscription():
    '''

@app.route("/api/v1/subscription",methods=['GET'])
@jwt_required
def get_subscription():
    current_user = get_current_user()
    return jsonify(current_user.subType.type)

@app.route("/api/v1/create_checkout_session", methods=['POST'])
@jwt_required
def create_checkout_session():
    current_user = get_current_user()
    if request.json['price_id'] and request.json['price_id'] != 'None':
        '''current_subscription_id = current_user.subscription_id
        # If the user has a current subscription, cancel it first
        if current_subscription_id:
            try:
                stripe.Subscription.delete(current_subscription_id)
            except:
                pass'''
        '''checkout_session = stripe.checkout.Session.create(
            success_url='http://3.88.63.152:8000/checkout_success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://3.88.63.152:8000/cancel',
            payment_method_types=['card','paypal'],
            mode='subscription',
            line_items=[{
                'price': request.json['price_id'],
                'quantity': 1,
            }],
            customer_email=current_user.email,
        )'''
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                # Add other relevant customer information here
            )

            # Save the generated customer ID in the user's database record
            current_user.stripe_customer_id = customer.id
            db.session.commit()
            # User does not have a Stripe customer ID, create a new customer in Stripe
            

        # Now create the checkout session using the new customer ID
        sub_col = Subscription.query.filter(Subscription.stripe_id==request.json['price_id']).first()
        if sub_col.trial_days > 0:
            checkout_session = stripe.checkout.Session.create(
                success_url='http://3.88.63.152:8000/checkout_success?session_id={CHECKOUT_SESSION_ID}',
                cancel_url='http://3.88.63.152:8000/cancel',
                payment_method_types=['card','paypal'],
                mode='subscription',
                line_items=[{
                    'price': request.json['price_id'],
                    'quantity': 1,
                }],
                subscription_data={
                    "trial_period_days": sub_col.trial_days
                },
                allow_promotion_codes=True,
                customer=current_user.stripe_customer_id,
            )
        else:
            checkout_session = stripe.checkout.Session.create(
                success_url='http://3.88.63.152:8000/checkout_success?session_id={CHECKOUT_SESSION_ID}',
                cancel_url='http://3.88.63.152:8000/cancel',
                payment_method_types=['card','paypal'],
                mode='subscription',
                line_items=[{
                    'price': request.json['price_id'],
                    'quantity': 1,
                }],
                allow_promotion_codes=True,
                customer=current_user.stripe_customer_id,
            )
        current_user.sub_date = datetime.utcnow()
        db.session.commit()
        #session['subscription_type'] = request.json['subscription_type']
        
        return jsonify({'message': 'Subscription changed', 'ok': True, 'url': checkout_session.url})
    else:
        if current_user.subscription_id:
            stripe.Subscription.delete(current_user.subscription_id)
            # Update the user's database record to reflect the cancellation
            current_user.subType = Subscription.query.first()
            db.session.commit()
            # check if user has reduced his plan liek from pro to advanced or advanced to free and reduce his bots and smas
            if current_user.subType.max_bots < current_user.bots.filter(Bot.is_hidden==False, Bot.isActive).count():
                for bot in current_user.bots.filter(Bot.isActive==True).all():
                    bot.isActive = False
                    db.session.commit()
            if current_user.subType.max_sma < SmartTrade.query.filter(SmartTrade.user_id == current_user.id, SmartTrade.isActive).count():
                for sma in SmartTrade.query.filter(SmartTrade.user_id == current_user.id).all():
                    sma.isActive = False
                    db.session.commit()
                    
            current_user.subscription_id = None
            db.session.commit()
            return jsonify({'message': 'Subscription cancelled', 'ok': True})
        else:
            return jsonify({'message': 'You are already on the free plan', 'ok': False}), 403

@app.route("/api/v1/create_checkout_session_tap", methods=['POST'])
@jwt_required
def create_checkout_session_tap():
    current_user = get_current_user()
    if request.json['price_id'] and request.json['price_id'] != 'None':
        try:
            url = "https://api.tap.company/v2/charges/"

            

            if not current_user.stripe_customer_id:
                payload = {
                    "first_name": current_user.firstName,
                    "last_name": current_user.lastName,
                    "email": current_user.email,
                }
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Authorization": "Bearer " + os.environ.get('TAP_API_KEY', '')
                }

                current_user.stripe_customer_id = requests.post("https://api.tap.company/v2/customers", json=payload, headers=headers).json()["id"]
                db.session.commit()
                
            # Now create the checkout session using the new customer ID
            sub_col = Subscription.query.filter(Subscription.stripe_id==request.json['price_id']).first()
            if sub_col is None:
                sub_col = Subscription.query.first()
            if sub_col.trial_days > 0:
                payload = {
                    "amount": 1,
                    "currency": "KWD",
                    "customer_initiated": True,
                    "threeDSecure": True,
                    "save_card": True,
                    "order": { "id": request.json['price_id'] },
                    "receipt": {
                        "email": True,
                        "sms": True
                    },
                    "customer": {
                        "id": "1"
                    },
                    "reference": {
                        "order": request.json['price_id'],
                    },
                    "source": { "id": "src_all" },
                    "redirect": { "url": f"http://3.88.63.152:8000/checkout_success_tab?session_id={request.json['price_id']}" }
                }
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Authorization": "Bearer " + os.environ.get('TAP_API_KEY', '')
                }

                res = requests.post(url, json=payload, headers=headers)
            else:
                payload = {
                    "amount": 1,
                    "currency": "KWD",
                    "customer_initiated": True,
                    "threeDSecure": True,
                    "save_card": True,
                    "order": { "id": request.json['price_id'] },
                    "receipt": {
                        "email": True,
                        "sms": True
                    },
                    "customer": {
                        "id": "1"
                    },
                    "reference": {
                        "order": request.json['price_id'],
                    },
                    "source": { "id": "src_all" },
                    "redirect": { "url": f"http://3.88.63.152:8000/checkout_success_tab?session_id={request.json['price_id']}" }
                }
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Authorization": "Bearer " + os.environ.get('TAP_API_KEY', '')
                }

                res = requests.post(url, json=payload, headers=headers)

            #session['subscription_type'] = request.json['subscription_type']
            
            return jsonify({'message': 'Subscription changed', 'ok': True, 'url': res.json()['redirect']['url']})
        except Exception as e:
            return jsonify({'message': str(e), 'ok': False}), 403
    else:
        if current_user.subscription_id:
            stripe.Subscription.delete(current_user.subscription_id)
            # Update the user's database record to reflect the cancellation
            current_user.subType = Subscription.query.first()
            db.session.commit()
            # check if user has reduced his plan liek from pro to advanced or advanced to free and reduce his bots and smas
            if current_user.subType.max_bots < current_user.bots.filter(Bot.is_hidden==False).count():
                for bot in current_user.bots.filter(Bot.isActive==True).all():
                    bot.is_hidden = True
                    db.session.commit()
            if current_user.subType.max_sma < SmartTrade.query.filter(SmartTrade.user_id == current_user.id).count():
                for sma in SmartTrade.query.filter(SmartTrade.user_id == current_user.id).all():
                    db.session.delete(sma)
                    db.session.commit()
                    
            current_user.subscription_id = None
            db.session.commit()
            return jsonify({'message': 'Subscription cancelled', 'ok': True})
        else:
            return jsonify({'message': 'You are already on the free plan', 'ok': False}), 403




@app.route("/checkout_success", methods=['GET','POST'])
def checkout_success():
    current_user = get_current_user()
    session_id = request.args.get('session_id')
    # Retrieve the subscription details using the session ID
    checkout_session = stripe.checkout.Session.retrieve(session_id)
    subscription_id = checkout_session.subscription
    if current_user.subscription_id:
        stripe.Subscription.delete(current_user.subscription_id)
    current_user.subscription_id = subscription_id
    # Save the subscription ID in the user's database record
    try:
        plan_id = stripe.Subscription.retrieve(subscription_id)['items'].data[0].price.id
        current_user.subType = Subscription.query.filter(Subscription.stripe_id==plan_id).first()
        db.session.commit()
    except:
        pass
    return redirect(url_for('pricing'))

@app.route("/cancel", methods=['GET','POST'])
def cancel():
    return redirect(url_for('pricing'))

@app.route("/checkout_success_tab", methods=['GET','POST'])
def checkout_success_tab():
    current_user = get_current_user()
    session_id = request.args.get('session_id')
    # Save the subscription ID in the user's database record
    try:
        plan_id = session_id
        current_user.subType = Subscription.query.filter(Subscription.stripe_id==plan_id).first()
        db.session.commit()
    except:
        pass
    return redirect(url_for('pricing'))


from flask import jsonify

@app.route("/api/v1/get_subscriptions_and_invoices", methods=['POST'])
@jwt_required
def get_subscriptions_and_invoices():
    user = get_current_user()
    try:
        if user.stripe_customer_id:
            # Retrieve all subscriptions (including canceled ones) associated with the customer ID
            subscriptions = stripe.Subscription.list(customer=user.stripe_customer_id, status='all')

            # Extract relevant information from each subscription
            subscription_list = []
            for subscription in subscriptions.data:
                subscription_data = {
                    'subscription_id': subscription.id,
                    'status': subscription.status,
                    'current_period_start': subscription.current_period_start,
                    'current_period_end': subscription.current_period_end,
                    # Add other relevant subscription information here
                }
                subscription_list.append(subscription_data)

            # Retrieve the invoices associated with the customer ID
            invoices = stripe.Invoice.list(customer=user.stripe_customer_id)
            
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

            return jsonify({'subscriptions': subscription_list, 'invoices': invoice_list, 'ok': True})
        else:
            return jsonify({'message': 'User does not have a Stripe customer ID', 'ok': False}), 403
    except Exception as e:
        return jsonify({'message': str(e), 'ok': False}), 500



'''@app.route('/webhooks/stripe', methods=['POST'])
def handle_stripe_webhook():
    payload = request.get_json()
    event = None

    try:
        event = stripe.Event.construct_from(
            payload, stripe.api_key
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({'error': str(e)}), 400

    # Handle different event types
    if event.type == 'invoice.paid':
        # Subscription invoice is paid
        handle_invoice_paid(event.data.object)
    # Handle other event types as needed

    return jsonify({'success': True})

def handle_invoice_paid(invoice):
    # Retrieve relevant information from the invoice object
    subscription_id = invoice.subscription
    amount_paid = invoice.amount_paid
    stripe_id = invoice.lines.data[0].price.id
    current_user.subType = Subscription.query.filter(Subscription.stripe_id==stripe_id).first()
    current_user.sub_date = datetime.utcnow()
    db.session.commit()
    
    # Update your database or perform necessary actions
    # For example, mark the subscription as paid or upgrade the user's account'''
#########################################################################

#knowledge base
'''@app.route("/knowledge_base",methods=['GET','POST'])
def kb():
    #current_user = get_current_user()
    if request.method == 'POST':
        return jsonify({'posts':Post.query.all(),'categories':Category.query.all()})
    else:
        return render_template("knowledge_base.html",
                                cats=Category.query.all(),
                                posts = Post.query.all(),
                                is_logged_in=current_user.is_authenticated if current_user else False,
                                #notifications=current_user.notifications.all(),
                                #exchanges = current_user.exchanges.all(),
                            )'''

@app.route("/knowledge_base_cat",methods=['GET','POST'])
def kb_cat_all():
    #current_user = get_current_user()
    if request.method == 'POST':
        return jsonify({'posts':Post.query.all(),'category':Category.query.first(),'articles':Post.query.all(),'ok':True,'message':'success'})
    else:
        return render_template("knowledge_base_cat.html",
                                articles=Post.query.all(),
                                category=Category.query.first(),
                                posts = Post.query.all(),
                                cats=Category.query.all(),
                                cat_now=None,
                                is_logged_in=current_user.is_authenticated if current_user else False,
                                #notifications=current_user.notifications.all(),
                                #exchanges = current_user.exchanges.all(),
                            )

@app.route("/knowledge_base_cat/<category_id>",methods=['GET','POST'])
def kb_cat(category_id):
    #current_user = get_current_user()
    if request.method == 'POST':
        return jsonify({'posts':Post.query.filter(Post.category_id==category_id).all(),'category':Category.query.filter(Category.id==category_id).first(),'articles':Post.query.filter(Post.category_id==category_id).all(),'ok':True,'message':'success'})
    else:
        return render_template("knowledge_base_cat.html",
                                articles=Post.query.filter(Post.category_id==category_id).all(),
                                category=Category.query.filter(Category.id==category_id).first(),
                                posts = Post.query.all(),
                                cats=Category.query.all(),
                                cat_now=Category.query.filter(Category.id==category_id).first(),
                                is_logged_in=current_user.is_authenticated if current_user else False,
                                #notifications=current_user.notifications.all(),
                                #exchanges = current_user.exchanges.all(),
                            )

@app.route("/knowledge_base_post/<int:post_id>",methods=['GET','POST'])
def kb_post(post_id):
    #current_user = get_current_user()
    if request.method == 'POST':
        return jsonify({'post':Post.query.filter(Post.id==post_id).first(),'posts':Post.query.all(),'ok':True,'message':'success'})
    else:
        return render_template("knowledge_base_post.html",
                                post=Post.query.filter(Post.id==post_id).first(),
                                posts = Post.query.all(),
                                cats=Category.query.all(),
                                cat_now=Post.query.filter(Post.id==post_id).first().category,
                                is_logged_in=current_user.is_authenticated if current_user else False,
                                #notifications=current_user.notifications.all(),
                                #exchanges = current_user.exchanges.all(),
                            )


@app.route('/user/profile')
@jwt_required
def user_profile():
    current_user = get_current_user()
    return render_template('user-profile.html',exchanges=current_user.exchanges.all(),current_user=current_user,notifications=current_user.notifications.all(),posts = Post.query.all())

@app.route('/user/setting')
@jwt_required
def user_privacy_setting():
    current_user = get_current_user()
    return render_template('user-privacy-setting.html',exchanges=current_user.exchanges.all(),current_user=current_user,notifications=current_user.notifications.all(),posts = Post.query.all())


@app.route("/getData/")
def search2():
    current_user = get_current_user()
    symbols = search()
    #symbols2 = [symbol['symbol'][:symbol['symbol'].index(symbol['currency_code'])] + '/' + symbol['currency_code'] for symbol in symbols if symbol['currency_code'] == 'USDT' and '.P' not in symbol['symbol']]
    return jsonify(symbols)

@app.route('/api/v1/order_book_history')
def order_book_history():
    exchange = request.args.get("exchange")
    market = request.args.get("market")
    pair = request.args.get("pair")
    exchangeNow = getattr(ccxt, exchange)()
    time.sleep(exchangeNow.describe()['rateLimit']/1000)
    order_book = exchangeNow.fetch_order_book(symbol=pair+"/"+market,limit=1)

    if order_book:
        socketio.emit('last_order', json.dumps(order_book))
    return "true"

@app.route('/api/v1/last_trades_history')
def last_trades_history():
    exchange = request.args.get("exchange")
    market = request.args.get("market")
    pair = request.args.get("pair")
    exchangeNow = getattr(ccxt, exchange)()
    time.sleep(exchangeNow.describe()['rateLimit']/1000)
    last_trades = exchangeNow.fetch_trades(symbol=pair+"/"+market,limit=1)[0]
    if last_trades:
        socketio.emit('last_trade', json.dumps(last_trades))
    return "true"

@app.route('/api/v1/live_balance')
def live_balance():
    current_user = get_current_user()
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    exchange = connectExchange(exchange,current_user.id)
    try:
        balance = exchange.fetch_balance()[symbol]['free']
        #socketio.emit('live_balance', json.dumps(balance))
    except:
        balance = 0
        #socketio.emit('live_balance',json.dumps([current_user.id,balance]))
    return jsonify(balance)

@app.route('/api/v1/live_balance_json')
def live_balance_json():
    current_user = get_current_user()
    exchange = request.args.get("exchange")
    exchange = connectExchange(exchange,current_user.id)
    try:
        balance = exchange.fetch_balance()['free']
        #socketio.emit('live_balance', json.dumps(balance))
    except:
        balance = {}
        #socketio.emit('live_balance',json.dumps([current_user.id,balance]))
    return jsonify(balance)

@app.route('/api/v1/live_price')
def live_price():
    current_user = get_current_user()
    exchange = request.args.get("exchange").upper().replace("OKEX",'OKX')
    market = request.args.get("market")
    pair = request.args.get("pair")
    stream = request.args.get("stream")

    if stream is None:
        stream = "true"
    exchange = exchange
    #exchange = connectExchange()
    #price = exchange.fetch_ticker(pair+"/"+market)['last']
    price = getPrice_assets(exchange,pair+"/"+market)
    '''try:
        if pair+"/"+market == 'USDT/USDT':
            return jsonify(1)
  
        if market == 'USDT':
            symbol_id = f"{str(exchange).upper().replace('OKEX','OKX')}{pair+market}"
            with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                price = json.load(f)[pair+'/'+market][0]
        else:
            price1 = 0
            price2 = 0
            symbol_id1 = f"{str(exchange).upper().replace('OKEX','OKX')}{pair+'USDT'}"
            with open("pricesData/"+f"{symbol_id1}.json", "r") as f:
                price1 = json.load(f)[pair+"/"+'USDT'][0]
            symbol_id2 = f"{str(exchange).upper().replace('OKEX','OKX')}{market+'USDT'}"
            with open("pricesData/"+f"{symbol_id2}.json", "r") as f:
                price2 = json.load(f)[market+"/"+'USDT'][0]
            if  price1 == 0:
                price = 0
            else:
                price = price2/price1
    except FileNotFoundError:
        price = 0'''

    if price and stream == "true":
        socketio.emit('live_price', json.dumps([current_user.id,price]))
    return jsonify(price)

async def fetch_price(current_user2,exchange_name,symbol):
    if exchange_name is None:
        if current_user2.exchanges.filter(Exchange.isActive==True).first():
            exchange_name = current_user2.exchanges.filter(Exchange.isActive==True).first().name
        else:
            return redirect(url_for('exchanges'))
        api_key,api_secret,password = current_user2.exchanges.filter(Exchange.name==exchange_name).first().get_creds()
        if current_user2.exchanges.filter(Exchange.name==exchange_name).first().password:
            exchange = getattr(ccxt2, exchange_name)({
                'apiKey': api_key,
                'secret': api_secret,
                'password': password,
            })
        else:
            exchange = getattr(ccxt2, exchange_name)({
                'apiKey': api_key,
                'secret': api_secret,
            })

        if current_user2.exchanges.filter(Exchange.name==exchange_name).first().demo:
                exchange.set_sandbox_mode(True)
        ticker = await exchange.fetch_ticker(symbol)
        return ticker

@app.route('/api/v1/market_table')
async def market_table():
    current_user = get_current_user()
    exchange_name = request.args.get("exchange")
    current_user2 = current_user
    api_key,api_secret,password = current_user2.exchanges.filter(Exchange.name==exchange_name).first().get_creds()
    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().password:
        exchange = getattr(ccxt2, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
            'password': password,
        })
    else:
        exchange = getattr(ccxt2, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
        })

    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().demo:
        exchange.set_sandbox_mode(True)
    
    data_array = await exchange.fetch_tickers()
    arrange_array = []
    try:
        market_data = await exchange.fetch_markets()
        for currency in market_data:
            if currency['spot'] and currency['symbol'].upper().split('/')[1] == 'USDT':
                arrange_array.append(currency['symbol'].upper())
    except:
        pass
    # Extract the symbol from the first array
    symbols = list(data_array.keys())
    # Sort the symbols based on the order in the arrange_array
    sorted_symbols = sorted(symbols, key=lambda x: arrange_array.index(x) if x in arrange_array else float('inf'))
    # Create a new array with sorted items
    sorted_array = [{symbol: list(data_array.values())[symbols.index(symbol)]} for symbol in sorted_symbols]
    return jsonify(sorted_array)

@app.route('/api/v1/live_crypto_data')
async def live_crypto_data():
    current_user = get_current_user()
    symbol = request.args.get("symbol")
    exchange_name = request.args.get("exchange").lower().replace('okx','okex')
    current_user2 = current_user
    if exchange_name is None:
        if current_user2.exchanges.filter(Exchange.isActive==True).first():
            exchange_name = current_user2.exchanges.filter(Exchange.isActive==True).first().name
        else:
            return redirect(url_for('exchanges'))
    '''api_key,api_secret,password = current_user2.exchanges.filter(Exchange.name==exchange_name).first().get_creds()
    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().password:
        exchange = getattr(ccxt2, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
            'password': password,
        })
    else:
        exchange = getattr(ccxt2, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
        })

    if current_user2.exchanges.filter(Exchange.name==exchange_name).first().demo:
        exchange.set_sandbox_mode(True)'''
    #exchange = connectExchange(exchange_name,id)
    

    #data = exchange.fetch_ticker(symbol)
    
    market = request.args.get("market")
    pair = request.args.get("pair")
    #data = exchange.fetch_ticker(pair+"/"+market)
    price,volume,change,percentage,high,low,open = getPrice_assets(exchange_name,pair+"/"+market,None,False,True)
    '''try:
        loop = asyncio.get_running_loop()
        pass
    except:  # no event loop running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pass

    data = await loop.run_in_executor(None, exchange.fetch_ticker, pair+"/"+market)
    data = await data
    
    #data = asyncio.get_event_loop().run_until_complete(exchange.fetch_ticker(pair+"/"+market))
    price = data['last']
    percentage = data['percentage']
    low = data['low']
    high = data['high']
    volume = data['baseVolume']
    change = data['change']
    '''
    if price < open:
        signal = 'danger'
    elif price > open:
        signal = 'success'
    else:
        signal = "nn"

    '''try:
        if pair+"/"+market == 'USDT/USDT':
            return jsonify(1)
  
        if market == 'USDT':
            symbol_id = f"{str(exchange).upper().replace('OKEX','OKX')}{pair+market}"
            with open("pricesData/"+f"{symbol_id}.json", "r") as f:
                data = json.load(f)[pair+'/'+market]
        else:
            symbol_id1 = f"{str(exchange).upper().replace('OKEX','OKX')}{pair+'USDT'}"
            with open("pricesData/"+f"{symbol_id1}.json", "r") as f:
                data1 = json.load(f)[pair+"/"+'USDT']
            symbol_id2 = f"{str(exchange).upper().replace('OKEX','OKX')}{market+'USDT'}"
            with open("pricesData/"+f"{symbol_id2}.json", "r") as f:
                data2 = json.load(f)[market+"/"+'USDT']

            data = [data1[0]/data[1] for data in zip(data1,data2)]
    except FileNotFoundError:
        data = {}'''
        
    return jsonify({
        'price':price,
        'percentage':percentage,
        'low':low,
        'high':high,
        'volume':volume,
        "change":change,
        'signal':signal,
    })

@app.route('/api/v1/indicators')
def indicators():
    exchange = request.args.get("exchange")
    market = request.args.get("market")
    pair = request.args.get("pair")
    interval = request.args.get("interval")
    #indicators = update_symbol_data(pair+'/'+market,interval,exchange,connectExchange(exchange),current_user.id)
    indicators = update_symbol_data2(pair+'/'+market,interval,exchange)
    socketio.emit('indicators', json.dumps(indicators))
    return "true"

                 
###############################################################################################################
      

@app.route('/api/v1/indicators_signals', methods=['GET'])
@jwt_required
def indicators_signals():
    interval = request.args.get("interval")
    exchange_name = request.args.get("exchange")

    exchange = connectExchange(exchange_name)

    pairs = []
    try:
        for currency in exchange.fetch_markets():
            if currency['active'] and currency['spot']:
                pairs.append(currency['symbol'])
    except:
        pass   
        
    return calculate_signals2(pairs,interval,exchange_name)
    #return calculate_signals(pairs,interval,exchange_name,exchange,current_user.id)

##########################################################################################

def check_assets_json(assets_json, currency):
    """
    Check if the array of assets_json contains json fiel which currency has teh assets value.

    Args:
    assets_json: The array of assets_json.
    currency: The currency to check.

    Returns:
    True if the array of assets_json contains json fiel which currency has teh assets value, False otherwise.
    """

    for asset in assets_json:
        if asset["currency"] == currency:
            return True
        return False

#####################################User_settings###################################

@app.route('/api/v1/user_settings/ip_check', methods=['POST'])
@jwt_required
def user_settings_ip_check():
    current_user = get_current_user()
    isActive = request.json['isActive']
    current_user.ip_check = isActive
    db.session.commit()

#####################################admin###################################

@app.route('/api/admin/v1/send_custom_notification', methods=['POST'])
@admin_required
def send_custom_notification():
    message = request.json['message']
    user_id = request.json['user_id']
    send_notification(message+"***system",user_id)
    return jsonify({"message": "the message has been sent successfully",'ok':True})

@app.route('/api/admin/v1/send_custom_notification_all', methods=['POST'])
@admin_required
def send_custom_notification_all():
    message = request.json['message']
    for user in User.query.all():
        send_notification(message+"***system",user.id)
    return jsonify({"message": "the messages have been sent successfully",'ok':True})

@app.route('/privacy-policy', methods=['GET'])
def privacy_policy():
    current_user = get_current_user()
    return render_template('privacy-policy.html',is_logged_in=current_user.is_authenticated if current_user else False,)

@app.route('/terms-of-service', methods=['GET'])
def terms_of_service():
    current_user = get_current_user()
    return render_template('terms-of-service.html',is_logged_in=current_user.is_authenticated if current_user else False,)