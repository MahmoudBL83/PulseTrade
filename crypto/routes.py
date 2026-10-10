import json
from concurrent.futures import ThreadPoolExecutor
from flask import render_template, request, redirect, url_for, jsonify,Response,session, flash
import ccxt
from crypto import app,db,socketio,celery,scheduler,jwt_required, auth_required
from crypto.auth import admin_required
from crypto.models import User, Exchange, Post, Category,UserCount,BotCount,Pair,Bot,SmartTrade, BalanceHistory24h, Subscription, BotHistory, Transaction,Exchange2, TransactionHistory
from crypto.notify import send_notification, emit_to_user
from crypto.dataStream_indicators import update_symbol_data2,calculate_signals2
from search_crypto import search
from crypto.exchanges import connectExchange, nav_context
from crypto.functions import getPrice_assets, build_exchange
from crypto.cache import TTLCache
from crypto import market
import time
import math
from sqlalchemy import desc
import requests
import stripe
import os
from datetime import datetime
from datetime import timedelta
from crypto import get_current_user
stripe.api_key = os.environ.get('STRIPE_API_KEY', '')

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://pulse-trade-zeta.vercel.app').rstrip('/')
TAP_API = "https://api.tap.company/v2"

_signals_cache = TTLCache(ttl=60)


def _body():
    """JSON body or {} (GET requests and empty bodies never raise)."""
    return request.get_json(silent=True) or {}


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
                            is_logged_in=current_user is not None,
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
    # Destroys every table: require an explicit confirmation parameter.
    if request.args.get("confirm") != "DROP":
        return jsonify({"message": "Refusing to drop all tables. Call /drop_all/?confirm=DROP to proceed.", "ok": False}), 400
    db.drop_all()
    return jsonify("dropped")

@app.route("/create_all/")
@admin_required
def create_all():
    from crypto.migrate import init_db
    init_db(db)
    if Subscription.query.count() < 3:
        db.session.add(Subscription(type='free',max_bots=5,max_sma=10))
        db.session.add(Subscription(type='advanced',max_bots=25,max_sma=10**9))
        db.session.add(Subscription(type='pro',max_bots=100,max_sma=10**9))
        db.session.commit()
    return jsonify("created")

def calculate_stats():
    with app.app_context():
        db.session.add(UserCount(count=User.query.count()))
        db.session.add(BotCount(count=Bot.query.filter(Bot.isActive==True).count()))
        db.session.commit()

def calculate_stats_users():
    with app.app_context():
        for user in User.query.all():
            try:
                user.update_balance()
                db.session.add(BalanceHistory24h(balance_btc=user.balance_btc,balance_usd=user.balance_usd,owner_id=user.id))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"daily balance snapshot failed for user {user.id}: {e}")

def calculate_stats_users_bots():
    with app.app_context():
        for user in User.query.all():
            profit = 0
            for bot in user.bots.all():
                # only bots that realised profit during the last 24 hours
                if bot.last_total_profit_time and bot.last_total_profit_time > datetime.utcnow() - timedelta(days=1):
                    profit += bot.total_profit or 0
            last = BotHistory.query.filter(BotHistory.owner_id == user.id).order_by(desc(BotHistory.timestamp)).first()
            if last is not None:
                profit = profit - (last.profit or 0)
            db.session.add(BotHistory(profit=profit,owner_id=user.id))
            db.session.commit()

def calculate_trans():
    with app.app_context():
        total = db.session.query(db.func.coalesce(db.func.sum(Transaction.value), 0)).scalar() or 0
        db.session.add(TransactionHistory(value=total))
        db.session.commit()



scheduler.add_job(calculate_stats, 'cron', hour=0, minute=0, second=0, id="calculate_stats", replace_existing=True)
scheduler.add_job(calculate_trans, 'cron', hour=0, minute=0, second=0, id="calculate_trans", replace_existing=True)
scheduler.add_job(calculate_stats_users, 'cron', hour=0, minute=0, second=0, id="calculate_stats_users", replace_existing=True)
scheduler.add_job(calculate_stats_users_bots, 'cron', hour=0, minute=0, second=0, id="calculate_stats_users_bots", replace_existing=True)

################################################Dashboard##############################################################

@app.route("/dashboard/")
@jwt_required
def dashboard():
    current_user = get_current_user()
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    ctx = nav_context(current_user)
    return render_template("dashboard.html",
                                bots=current_user.bots.filter(Bot.isActive,Bot.is_hidden==False).all(),
                                balance_usd = current_user.balance_usd,
                                balance_btc = current_user.balance_btc,
                                balance_history = json.dumps([bal.serialize() for bal in current_user.balance_history]),
                                balance_history24h = json.dumps([bal.serialize() for bal in current_user.balance_history24h]),
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
                                SMAs = SmartTrade.query.filter(SmartTrade.user_id==current_user.id,SmartTrade.isActive).all(),
                                **ctx,
                           )


def _supports(exchange, feature):
    try:
        return bool(exchange.describe()['has'].get(feature))
    except Exception:
        return False


@app.route("/api/v1/user_stats/",methods=['GET','POST'])
@jwt_required
def user_info():
    current_user = get_current_user()
    body = _body()
    exchange_name = body.get('exchange_name')

    # Only admins may inspect another user's stats.
    target = current_user
    if body.get('user_id') and session.get('admin'):
        target = db.session.get(User, int(body['user_id'])) or current_user

    try:
        target.update_balance()
    except Exception as e:
        db.session.rollback()
        print(f"update_balance failed for user {target.id}: {e}")

    open_orders = []
    transactions = []
    not_supported_trans = []
    if exchange_name:
        exchange = connectExchange(exchange_name, target.id)
        try:
            if _supports(exchange, 'fetchOpenOrders'):
                open_orders = exchange.fetch_open_orders()
        except Exception as e:
            print(f"fetch_open_orders failed: {e}")
        try:
            if _supports(exchange, 'fetchLedger'):
                transactions = exchange.fetch_ledger()
            else:
                not_supported_trans.append(exchange_name)
        except Exception:
            not_supported_trans.append(exchange_name)
    else:
        for exchange_user in target.exchanges:
            try:
                exchangeNow = build_exchange(exchange_user)
                if _supports(exchangeNow, 'fetchLedger'):
                    for trans in exchangeNow.fetch_ledger():
                        trans['exchange'] = exchange_user.name
                        transactions.append(trans)
                else:
                    not_supported_trans.append(exchange_user.name)
            except Exception:
                not_supported_trans.append(exchange_user.name)

    exchanges_list = [exchange.serialize() for exchange in target.exchanges.all()]
    return jsonify({
                        'exchnages': exchanges_list,  # legacy (misspelled) key kept for old clients
                        'exchanges': exchanges_list,
                        'open_orders':open_orders,
                        'balance_history':json.dumps([bal.serialize() for bal in target.balance_history]),
                        'transactions':transactions,
                        'balance_usd':target.balance_usd or 0,
                        'balance_btc':target.balance_btc or 0,
                        'profit_monthly_btc':target.profit_monthly_btc,
                        'profit_monthly_usd':target.profit_monthly_usd,
                        'profit_daily_btc':target.profit_daily_btc,
                        'profit_daily_usd':target.profit_daily_usd,
                        'profit_monthly_percent_btc':target.profit_monthly_percent_btc,
                        'profit_monthly_percent_usd':target.profit_monthly_percent_usd,
                        'profit_daily_percent_btc':target.profit_daily_percent_btc,
                        'profit_daily_percent_usd':target.profit_daily_percent_usd,
                        'profit_overall_btc':target.profit_overall_btc,
                        'profit_overall_usd':target.profit_overall_usd,
                        'sharpe_ratio':target.sharpe_ratio,
                        'sortino_ratio':target.sortino_ratio,
                        'deviation':target.deviation,
                        'not_supported_trans':not_supported_trans,
                    })


def _valid_avatar(value):
    v = (value or "").strip()
    if not v or len(v) > 512:
        return False
    return v.startswith(("https://", "http://", "/static/"))


@app.route("/api/v1/edit_user_info/", methods=['POST'])
@jwt_required
def edit_user_info():
    current_user = get_current_user()
    raw = request.get_data(as_text=True) or ""
    body = request.get_json(silent=True)
    img = body.get("img") if isinstance(body, dict) else raw.strip().strip('"')
    if not _valid_avatar(img):
        return jsonify({"message": "Avatar must be an http(s) URL or a /static path", "ok": False}), 400
    current_user.img = img
    db.session.commit()
    return jsonify({"message": "profile updated", "ok": True, "img": img})


@app.route("/api/v1/reset_stats")
@jwt_required
def reset_stats():
    current_user = get_current_user()
    current_user.reset_stats()
    return jsonify({"message":"your stats have been reset","ok":True})


def _collect_assets(exchange, assets_json, only_positive=True):
    assets = exchange.fetch_balance()
    free_map = assets.get("free") or {}
    used_map = assets.get("used") or {}
    for asset, amount in (assets.get("total") or {}).items():
        if only_positive and not (amount and amount > 0):
            continue
        price = getPrice_assets(exchange.name, asset + '/USDT') or 0
        free, used = free_map.get(asset) or 0, used_map.get(asset) or 0
        if check_assets_json(assets_json, asset):
            for asset_json in assets_json:
                if asset_json['currency'] == asset:
                    asset_json['free'] += free
                    asset_json['used'] += used
                    asset_json['total'] += amount
                    asset_json['eqUSD'] += amount * price
        else:
            assets_json.append({"currency": asset, "free": free, "used": used, "total": amount,
                                "price": price, 'eqUSD': amount * price})


@app.route("/api/v1/assets")
@jwt_required
def assets():
    current_user = get_current_user()
    exchange_name = request.args.get('exchange') or 'all'

    assets_json = []
    if exchange_name.lower() != "all":
        try:
            _collect_assets(connectExchange(exchange_name), assets_json)
        except Exception as e:
            print(f"assets({exchange_name}) failed: {e}")
    else:
        for exchange_user in current_user.exchanges.all():
            try:
                _collect_assets(build_exchange(exchange_user), assets_json)
            except Exception as e:
                print(f"assets({exchange_user.name}) failed: {e}")

    return jsonify(assets_json)

########################################################end of dashboard############################################################

@app.route("/subscription")
def pricing():
    current_user = get_current_user()
    if current_user is None:
        return redirect(url_for('login'))
    return render_template("pricing.html",
                           subscriptions=Subscription.query.all(),
                           **nav_context(current_user),
                           )

@app.route("/api/v1/subscription",methods=['GET'])
@jwt_required
def get_subscription():
    current_user = get_current_user()
    sub = getattr(current_user, 'subType', None) if current_user else None
    return jsonify(sub.type if sub else 'free')


def _apply_plan_downgrade(current_user, hide=False):
    """Deactivate bots/smart trades exceeding the (new) plan limits."""
    plan = current_user.subType
    if plan is None:
        return
    active_bots = current_user.bots.filter(Bot.is_hidden==False, Bot.isActive==True)
    if (plan.max_bots or 0) < active_bots.count():
        for bot in active_bots.all():
            if hide:
                bot.is_hidden = True
            bot.isActive = False
    active_smas = SmartTrade.query.filter(SmartTrade.user_id == current_user.id, SmartTrade.isActive==True)
    if (plan.max_sma or 0) < active_smas.count():
        for sma in active_smas.all():
            sma.isActive = False
    db.session.commit()


def _cancel_paid_plan(current_user):
    if not current_user.subscription_id:
        return jsonify({'message': 'You are already on the free plan', 'ok': False}), 403
    if stripe.api_key:
        try:
            stripe.Subscription.delete(current_user.subscription_id)
        except Exception as e:
            print(f"stripe cancel failed: {e}")
    current_user.subType = Subscription.query.filter_by(type='free').first() or Subscription.query.first()
    current_user.subscription_id = None
    db.session.commit()
    _apply_plan_downgrade(current_user)
    return jsonify({'message': 'Subscription cancelled', 'ok': True})


@app.route("/api/v1/create_checkout_session", methods=['POST'])
@jwt_required
def create_checkout_session():
    current_user = get_current_user()
    price_id = _body().get('price_id')
    if not price_id or price_id == 'None':
        return _cancel_paid_plan(current_user)
    if not stripe.api_key:
        return jsonify({'message': 'Card payments are not configured on this server', 'ok': False}), 503
    sub_col = Subscription.query.filter(Subscription.stripe_id==price_id).first()
    if sub_col is None:
        return jsonify({'message': 'Unknown plan', 'ok': False}), 400
    try:
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        params = dict(
            success_url=f'{FRONTEND_URL}/checkout_success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{FRONTEND_URL}/cancel',
            payment_method_types=['card','paypal'],
            mode='subscription',
            line_items=[{'price': price_id, 'quantity': 1}],
            customer=current_user.stripe_customer_id,
        )
        if (sub_col.trial_days or 0) > 0:
            params["subscription_data"] = {"trial_period_days": sub_col.trial_days}
            params["allow_promotion_codes"] = True
        checkout_session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as e:
        return jsonify({'message': f'Payment provider error: {e.user_message or str(e)}', 'ok': False}), 502
    return jsonify({'message': 'Subscription changed', 'ok': True, 'url': checkout_session.url})

@app.route("/api/v1/create_checkout_session_tap", methods=['POST'])
@jwt_required
def create_checkout_session_tap():
    current_user = get_current_user()
    price_id = _body().get('price_id')
    if not price_id or price_id == 'None':
        return _cancel_paid_plan(current_user)
    tap_key = os.environ.get('TAP_API_KEY', '')
    if not tap_key:
        return jsonify({'message': 'Tap payments are not configured on this server', 'ok': False}), 503
    sub_col = Subscription.query.filter(Subscription.stripe_id==price_id).first()
    if sub_col is None:
        return jsonify({'message': 'Unknown plan', 'ok': False}), 400
    headers = {"accept": "application/json", "content-type": "application/json", "Authorization": "Bearer " + tap_key}
    try:
        payload = {
            "amount": sub_col.price if sub_col.price and sub_col.price > 0 else 1,
            "currency": os.environ.get("TAP_CURRENCY", "KWD"),
            "customer_initiated": True,
            "threeDSecure": True,
            "save_card": False,
            "description": f"PulseTrade {sub_col.type} plan",
            "metadata": {"user_id": str(current_user.id), "plan": price_id},
            "receipt": {"email": True, "sms": False},
            "customer": {"first_name": current_user.firstName or "", "last_name": current_user.lastName or "",
                         "email": current_user.email},
            "reference": {"order": price_id, "transaction": f"u{current_user.id}-{int(time.time())}"},
            "source": {"id": "src_all"},
            "redirect": {"url": f"{FRONTEND_URL}/checkout_success_tab?session_id={price_id}"},
        }
        res = requests.post(f"{TAP_API}/charges/", json=payload, headers=headers, timeout=(5, 15))
        url = res.json()['transaction']['url'] if 'transaction' in res.json() else res.json()['redirect']['url']
        return jsonify({'message': 'Subscription changed', 'ok': True, 'url': url})
    except Exception as e:
        return jsonify({'message': f'Payment provider error: {e}', 'ok': False}), 502


@app.route("/checkout_success", methods=['GET','POST'])
@auth_required
def checkout_success():
    current_user = get_current_user()
    session_id = request.args.get('session_id')
    if not (session_id and stripe.api_key):
        return redirect(url_for('pricing'))
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        # The session must belong to this user's Stripe customer.
        if checkout_session.customer != current_user.stripe_customer_id:
            return redirect(url_for('pricing'))
        subscription_id = checkout_session.subscription
        if current_user.subscription_id and current_user.subscription_id != subscription_id:
            try:
                stripe.Subscription.delete(current_user.subscription_id)
            except Exception as e:
                print(f"old subscription cancel failed: {e}")
        current_user.subscription_id = subscription_id
        plan_id = stripe.Subscription.retrieve(subscription_id)['items'].data[0].price.id
        plan = Subscription.query.filter(Subscription.stripe_id==plan_id).first()
        if plan is not None:
            current_user.subType = plan
            current_user.sub_date = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"checkout_success failed: {e}")
    return redirect(url_for('pricing'))

@app.route("/cancel", methods=['GET','POST'])
def cancel():
    return redirect(url_for('pricing'))

@app.route("/checkout_success_tab", methods=['GET','POST'])
@auth_required
def checkout_success_tab():
    """Tap redirects here with ?session_id=<plan>&tap_id=<charge>. The plan is
    only granted after the charge is confirmed CAPTURED with Tap's API."""
    current_user = get_current_user()
    plan_id = request.args.get('session_id')
    tap_id = request.args.get('tap_id')
    tap_key = os.environ.get('TAP_API_KEY', '')
    if not (plan_id and tap_id and tap_key):
        return redirect(url_for('pricing'))
    try:
        charge = requests.get(f"{TAP_API}/charges/{tap_id}", headers={"Authorization": "Bearer " + tap_key},
                              timeout=(5, 15)).json()
        captured = str(charge.get("status", "")).upper() == "CAPTURED"
        same_plan = (charge.get("reference") or {}).get("order") == plan_id
        same_user = str((charge.get("metadata") or {}).get("user_id", current_user.id)) == str(current_user.id)
        plan = Subscription.query.filter(Subscription.stripe_id==plan_id).first()
        if captured and same_plan and same_user and plan is not None:
            current_user.subType = plan
            current_user.sub_date = datetime.utcnow()
            db.session.commit()
            send_notification(f"Your {plan.type} plan is active***system", current_user.id)
    except Exception as e:
        db.session.rollback()
        print(f"tap verification failed: {e}")
    return redirect(url_for('pricing'))


@app.route("/api/v1/get_subscriptions_and_invoices", methods=['POST'])
@jwt_required
def get_subscriptions_and_invoices():
    user = get_current_user()
    if not user.stripe_customer_id or not stripe.api_key:
        return jsonify({'message': 'User does not have a Stripe customer ID', 'ok': False, 'subscriptions': [], 'invoices': []}), 403
    try:
        subscription_list = [{
            'subscription_id': s.id, 'status': s.status,
            'current_period_start': getattr(s, 'current_period_start', None),
            'current_period_end': getattr(s, 'current_period_end', None),
        } for s in stripe.Subscription.list(customer=user.stripe_customer_id, status='all').data]
        invoice_list = [{
            'invoice_id': inv.id, 'amount_due': inv.amount_due, 'status': inv.status, 'created': inv.created,
            'billing_reason': inv.billing_reason, 'paid': getattr(inv, 'paid', inv.status == 'paid'),
            'currency': inv.currency, 'url': getattr(inv, 'hosted_invoice_url', None) or inv.lines.url,
        } for inv in stripe.Invoice.list(customer=user.stripe_customer_id).data]
        return jsonify({'subscriptions': subscription_list, 'invoices': invoice_list, 'ok': True})
    except Exception as e:
        return jsonify({'message': str(e), 'ok': False}), 502


@app.route('/webhooks/stripe', methods=['POST'])
def handle_stripe_webhook():
    """Keeps plans in sync with Stripe (renewals, cancellations). Requires
    STRIPE_WEBHOOK_SECRET; events are signature-verified."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return jsonify({'error': 'webhook not configured'}), 503
    try:
        event = stripe.Webhook.construct_event(request.get_data(), request.headers.get("Stripe-Signature", ""), secret)
    except Exception as e:
        return jsonify({'error': 'invalid signature'}), 400
    obj = event["data"]["object"]
    user = User.query.filter_by(stripe_customer_id=obj.get("customer")).first() if obj.get("customer") else None
    if user is None:
        return jsonify({'success': True, 'ignored': True})
    if event["type"] == "invoice.paid":
        try:
            price_id = obj["lines"]["data"][0]["price"]["id"]
            plan = Subscription.query.filter(Subscription.stripe_id == price_id).first()
            if plan is not None:
                user.subType = plan
            user.sub_date = datetime.utcnow()
            if obj.get("subscription"):
                user.subscription_id = obj["subscription"]
            db.session.commit()
        except (KeyError, IndexError, TypeError):
            pass
    elif event["type"] == "customer.subscription.deleted" and obj.get("id") == user.subscription_id:
        user.subType = Subscription.query.filter_by(type='free').first()
        user.subscription_id = None
        db.session.commit()
        _apply_plan_downgrade(user)
        send_notification("Your subscription has ended; you are now on the free plan***system", user.id)
    return jsonify({'success': True})
#########################################################################

def _kb_context():
    u = get_current_user()
    return {"posts": Post.query.all(), "cats": Category.query.all(), "is_logged_in": u is not None}


@app.route("/knowledge_base_cat",methods=['GET','POST'])
def kb_cat_all():
    posts = Post.query.all()
    category = Category.query.first()
    if request.method == 'POST':
        return jsonify({'posts':[p.serialize() for p in posts],'category':category.serialize(False) if category else None,
                        'articles':[p.serialize() for p in posts],'ok':True,'message':'success'})
    return render_template("knowledge_base_cat.html", articles=posts, category=category, cat_now=None, **_kb_context())

@app.route("/knowledge_base_cat/<category_id>",methods=['GET','POST'])
def kb_cat(category_id):
    category = Category.query.filter(Category.id==category_id).first()
    articles = Post.query.filter(Post.category_id==category_id).all()
    if request.method == 'POST':
        return jsonify({'posts':[p.serialize() for p in articles],'category':category.serialize(False) if category else None,
                        'articles':[p.serialize() for p in articles],'ok':True,'message':'success'})
    if category is None:
        return redirect(url_for('kb_cat_all'))
    return render_template("knowledge_base_cat.html", articles=articles, category=category, cat_now=category, **_kb_context())

@app.route("/knowledge_base_post/<int:post_id>",methods=['GET','POST'])
def kb_post(post_id):
    post = db.session.get(Post, post_id)
    if request.method == 'POST':
        if post is None:
            return jsonify({'message': 'post not found', 'ok': False}), 404
        return jsonify({'post':post.serialize(),'posts':[p.serialize() for p in Post.query.all()],'ok':True,'message':'success'})
    if post is None:
        return redirect(url_for('kb_cat_all'))
    post.views = (post.views or 0) + 1
    db.session.commit()
    return render_template("knowledge_base_post.html", post=post, cat_now=post.category, **_kb_context())


@app.route('/user/profile')
@jwt_required
def user_profile():
    return render_template('user-profile.html', **nav_context(get_current_user()))

@app.route('/user/setting')
@jwt_required
def user_privacy_setting():
    return render_template('user-privacy-setting.html', **nav_context(get_current_user()))


@app.route("/getData/")
def search2():
    return jsonify(search())


def _pair_args():
    exchange = request.args.get("exchange") or market.default_exchange()
    market_q = (request.args.get("market") or "USDT").upper()
    pair = (request.args.get("pair") or "").upper()
    if not pair:
        from crypto.errors import ApiError
        raise ApiError("pair parameter is required", 400)
    return exchange, f"{pair}/{market_q}"


@app.route('/api/v1/order_book_history')
def order_book_history():
    exchange, symbol = _pair_args()
    if exchange not in ccxt.exchanges and market.normalize_exchange(exchange) not in ccxt.exchanges:
        return jsonify({"error": f"unsupported exchange: {exchange}"}), 400
    order_book = market.order_book(exchange, symbol, 5)
    if order_book:
        emit_to_user('last_order', json.dumps(order_book))
    return "true"

@app.route('/api/v1/last_trades_history')
def last_trades_history():
    exchange, symbol = _pair_args()
    if exchange not in ccxt.exchanges and market.normalize_exchange(exchange) not in ccxt.exchanges:
        return jsonify({"error": f"unsupported exchange: {exchange}"}), 400
    trades = market.trades(exchange, symbol, 1)
    if trades:
        emit_to_user('last_trade', json.dumps(trades[0]))
    return "true"

@app.route('/api/v1/live_balance')
@auth_required
def live_balance():
    current_user = get_current_user()
    symbol = request.args.get("symbol") or "USDT"
    exchange = connectExchange(request.args.get("exchange"), current_user.id)
    try:
        balance = exchange.fetch_balance().get(symbol, {}).get('free') or 0
    except Exception:
        balance = 0
    return jsonify(balance)

@app.route('/api/v1/live_balance_json')
@auth_required
def live_balance_json():
    current_user = get_current_user()
    exchange = connectExchange(request.args.get("exchange"), current_user.id)
    try:
        balance = exchange.fetch_balance()['free']
    except Exception:
        balance = {}
    return jsonify(balance)

@app.route('/api/v1/live_price')
def live_price():
    current_user = get_current_user()
    exchange = (request.args.get("exchange") or market.default_exchange()).upper().replace("OKEX",'OKX')
    pair = request.args.get("pair") or "BTC"
    market_q = request.args.get("market") or "USDT"
    stream = request.args.get("stream") or "true"
    price = getPrice_assets(exchange,pair+"/"+market_q)
    if price and stream == "true":
        emit_to_user('live_price', json.dumps([current_user.id if current_user else None, price]),
                     current_user.id if current_user else None)
    return jsonify(price)


def fetch_price(current_user2,exchange_name,symbol):
    """Ticker for ``symbol`` on the user's (active) exchange."""
    return connectExchange(exchange_name, current_user2.id).fetch_ticker(symbol)


@app.route('/api/v1/market_table')
@auth_required
def market_table():
    current_user = get_current_user()
    exchange_name = request.args.get("exchange")
    try:
        exchange = connectExchange(exchange_name, current_user.id)
        data_array = exchange.fetch_tickers()
        try:
            order = [m['symbol'].upper() for m in exchange.fetch_markets()
                     if m.get('spot') and m['symbol'].upper().split('/')[-1] == 'USDT']
        except Exception:
            order = []
    except Exception as e:
        # Fall back to public market data instead of failing the dashboard table.
        print(f"market_table via user exchange failed: {e}")
        data_array = {t['symbol']: t for t in market.tickers(exchange_name or None, 'USDT')}
        order = list(data_array.keys())
    rank = {sym: i for i, sym in enumerate(order)}
    sorted_symbols = sorted(data_array.keys(), key=lambda s: rank.get(s, float('inf')))
    return jsonify([{symbol: data_array[symbol]} for symbol in sorted_symbols])

@app.route('/api/v1/live_crypto_data')
def live_crypto_data():
    current_user = get_current_user()
    exchange_name = request.args.get("exchange")
    if not exchange_name and current_user is not None:
        row = current_user.exchanges.filter(Exchange.isActive==True).first()
        exchange_name = row.name if row else None
    exchange_name = (exchange_name or market.default_exchange()).lower().replace('okx','okex')
    pair = request.args.get("pair") or "BTC"
    market_q = request.args.get("market") or "USDT"
    price,volume,change,percentage,high,low,open_ = getPrice_assets(exchange_name,pair+"/"+market_q,None,False,True)
    if price and open_ and price < open_:
        signal = 'danger'
    elif price and open_ and price > open_:
        signal = 'success'
    else:
        signal = "nn"
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
    exchange = request.args.get("exchange") or market.default_exchange()
    pair = request.args.get("pair") or "BTC"
    market_q = request.args.get("market") or "USDT"
    interval = request.args.get("interval") or "1h"
    indicators = update_symbol_data2(pair+'/'+market_q,interval,exchange)
    emit_to_user('indicators', indicators)
    return "true"


###############################################################################################################


@app.route('/api/v1/indicators_signals', methods=['GET'])
@jwt_required
def indicators_signals():
    interval = request.args.get("interval") or "1h"
    exchange_name = request.args.get("exchange")
    key = (exchange_name, interval)
    hit = _signals_cache.get(key)
    if hit is not None:
        return hit
    try:
        exchange = connectExchange(exchange_name)
        pairs = [m['symbol'] for m in exchange.fetch_markets() if m.get('active', True) and m.get('spot')]
    except Exception:
        pairs = []
    result = calculate_signals2(pairs, interval, exchange_name)
    if result == json.dumps([[], []]):
        result = _computed_signals(exchange_name, interval)
    return _signals_cache.set(key, result)


def _computed_signals(exchange_name, interval, top=24):
    """Same shape as calculate_signals2, computed live from OHLCV for the most
    liquid USDT pairs when no screener files are available."""
    from crypto import ta
    symbols = [t['symbol'] for t in market.tickers(exchange_name, 'USDT', top)]

    def one(sym):
        try:
            s = ta.analysis(exchange_name, sym, interval)['summary']
            b, se = s['BUY'], s['SELL']
            tot = (b + se) or 1
            return {"symbol": sym, "buy_count": b, "buy_percentage": b / tot * 100, "sell_count": se,
                    "sell_percentage": se / tot * 100, "percentage": b / tot * 100}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        signals = [s for s in pool.map(one, symbols) if s]
    return json.dumps([sorted(signals, key=lambda x: x["buy_percentage"], reverse=True),
                       sorted(signals, key=lambda x: x["sell_percentage"], reverse=True)])

##########################################################################################

def check_assets_json(assets_json, currency):
    """True if ``assets_json`` already holds an entry for ``currency``."""
    for asset in assets_json:
        if asset["currency"] == currency:
            return True
    return False

#####################################User_settings###################################

@app.route('/api/v1/user_settings/ip_check', methods=['POST'])
@jwt_required
def user_settings_ip_check():
    current_user = get_current_user()
    is_active = _body().get('isActive')
    if isinstance(is_active, str):
        is_active = is_active.lower() in ("1", "true", "yes", "on")
    current_user.ip_check = bool(is_active)
    db.session.commit()
    return jsonify({"message": "IP check enabled" if current_user.ip_check else "IP check disabled",
                    "ok": True, "ip_check": current_user.ip_check})

#####################################admin###################################

@app.route('/api/admin/v1/send_custom_notification', methods=['POST'])
@admin_required
def send_custom_notification():
    body = _body()
    message = str(body['message'])
    user_id = body['user_id']
    if send_notification(message+"***system",user_id) is None:
        return jsonify({"message": "user not found", "ok": False}), 404
    return jsonify({"message": "the message has been sent successfully",'ok':True})

@app.route('/api/admin/v1/send_custom_notification_all', methods=['POST'])
@admin_required
def send_custom_notification_all():
    message = str(_body()['message'])
    for user in User.query.all():
        send_notification(message+"***system",user.id)
    return jsonify({"message": "the messages have been sent successfully",'ok':True})

@app.route('/privacy-policy', methods=['GET'])
def privacy_policy():
    return render_template('privacy-policy.html',is_logged_in=get_current_user() is not None)

@app.route('/terms-of-service', methods=['GET'])
def terms_of_service():
    return render_template('terms-of-service.html',is_logged_in=get_current_user() is not None)
