from crypto.functions import getPrice,getPrice_assets, build_exchange
import json
from flask import render_template, request, redirect, url_for, jsonify,Response
from sqlalchemy.orm.attributes import flag_modified
from crypto import app,db,celery, jwt_required, get_current_user
from crypto.models import User, Exchange, Bot, SafetyOrder, Post, Pair, Transaction
from crypto.notify import send_notification
from crypto.dataStream_indicators import fetch_data,fetch_data2
from crypto.talib_compat import talib
from crypto.exchanges import connectExchange, nav_context
from crypto import market
from time import sleep
import time
from datetime import datetime


def _body():
    return request.get_json(silent=True) or {}


def _owned_bot(bot_id):
    user = get_current_user()
    bot = db.session.get(Bot, int(bot_id)) if bot_id not in (None, "") and str(bot_id).isdigit() else None
    if bot is None:
        return None, jsonify({'message': "Bot not found", 'ok': False}), 404
    if bot.owner_id != user.id:
        return None, jsonify({'message': "You don't have permission to access this bot", 'ok': False}), 403
    return bot, None, None


@app.route('/bots/',methods=['POST','GET'])
@jwt_required
def bots():
    current_user = get_current_user()
    if request.method == 'POST':
        return jsonify({
            'bots': [bot.serialize() for bot in current_user.bots.filter(Bot.is_hidden == False).all()],
        })
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    return render_template('bots.html',
                                bots=Bot.query.filter(Bot.owner_id==current_user.id,Bot.is_hidden==False).all(),
                                symbol=request.args.get('symbol'),
                                exchange=request.args.get('exchange'),
                                bots_history = json.dumps([hist.serialize() for hist in current_user.bot_history]),
                                **nav_context(current_user),
                        )


def _spot_pairs(exchange):
    try:
        return [m['symbol'] for m in exchange.fetch_markets() if m.get('active', True) and m.get('spot')]
    except Exception as e:
        print(f"market list unavailable ({e}); using public symbols")
        return market.symbols(getattr(exchange, 'id', None))


@app.route('/bot_create/')
@jwt_required
def bot_create():
    current_user = get_current_user()
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    pairs = _spot_pairs(connectExchange())
    pairs_indicators = [pair.pair for pair in Pair.query.filter(Pair.isActive==True).all()]
    return render_template('bots_create.html',
                            pairs_indicators = pairs_indicators,
                            pairs=pairs,
                            symbol=request.args.get('symbol'),
                            exchange=request.args.get('exchange'),
                            **nav_context(current_user),
                        )

@app.route('/api/v1/toggle_bot',methods=['POST','GET'])
@jwt_required
def toggle_bot():
    current_user = get_current_user()
    body = _body()
    bot, err, code = _owned_bot(body.get("bot_id"))
    if err is not None:
        return err, code
    state = bool(body.get("state"))
    if state and not bot.isActive:
        limit = current_user.subType.max_bots if current_user.subType else None
        active = Bot.query.filter(Bot.isActive == True, Bot.is_hidden == False, Bot.owner_id==current_user.id).count()
        if limit and limit <= active:
            return jsonify({'message':"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})
        if not bot.deal_started and not bot.units:
            bot.units = bot.amount  # re-arm a bot that finished its last deal
    bot.isActive = state
    db.session.commit()
    send_notification(f'{bot.name} bot has been {"activated" if bot.isActive else "deactivated"}***Bot')
    return jsonify({'message': f'{bot.name} bot has been {"activated" if bot.isActive else "deactivated"}', 'ok': True, 'isActive': bot.isActive})

@app.route('/api/v1/delete_bot',methods=['POST','GET'])
@jwt_required
def delete_bot():
    bot, err, code = _owned_bot(_body().get("bot_id"))
    if err is not None:
        return err, code
    symbol = bot.symbol or f"{bot.base_currency}/{bot.quote_currency}"
    try:
        exchange = connectExchange(bot.exchange, bot.owner_id)
    except Exception as e:
        exchange = None
        print(f"delete_bot: exchange unavailable: {e}")

    if exchange is not None:
        # Cancel leftover open safety orders so no ghost orders stay on the exchange.
        _cancel_safety_orders(exchange, bot, symbol)
        # Close the position only when the bot actually holds one.
        position = bot.total_volume or bot.units or 0
        if bot.deal_started and position > 0:
            side = _close_side(bot)
            try:
                exchange.create_order(symbol, 'market', side, position)
                err_msg, status = "", True
            except Exception as e:
                err_msg, status = str(e), False
            db.session.add(Transaction(user_id=bot.owner_id, bot_id=bot.id, type=side, status=status,
                                       err_msg=err_msg, amount=position, symbol=symbol, exchange=bot.exchange,
                                       value=bot.price_now))

    bot.is_hidden = True
    bot.isActive = False
    bot.deal_started = False
    db.session.commit()
    return jsonify({'message':f"Bot deleted successfully. Bot ID: {bot.id}",'ok':True})


def _timeout_display(bot):
    t = bot.timeout or 0
    kind = int(bot.timeout_type) if str(bot.timeout_type or "").isdigit() else 0
    if kind == 1:
        return t / 60 / 60
    if kind == 2:
        return t / 60
    if kind == 3:
        return t / 24 / 60 / 60
    return t


#get_bot_stats
@app.route('/api/v1/get_bot_stats',methods=['POST','GET'])
@jwt_required
def get_bot_stats():
    bot, err, code = _owned_bot(request.args.get("bot_id") or _body().get("bot_id"))
    if err is not None:
        return err, code
    safety_orders = [{
        "id":so.id, "isOpened":so.isOpened, "isFilled":so.isFilled, "isClosed":so.isClosed,
        "orderId":so.orderId, "amount":so.amount, "price":so.price,
    } for so in SafetyOrder.query.filter_by(owner_id=bot.id).order_by(SafetyOrder.id.asc()).all()]

    return jsonify({
        'name':bot.name,
        'last_price':bot.last_price if bot.last_price is not None else 0,
        'symbol':f"{bot.base_currency}/{bot.quote_currency}",
        "symbols":str(bot.symbols),
        'isActive':bot.isActive,
        'deal_started':bot.deal_started,
        'tp_type':bot.tp_type,
        'tp_percent_type':bot.tp_percent_type,
        'tp_percent':bot.tp_percent,
        'trailing_take_profit':bot.trailing_take_profit,
        'trailing_stop_loss':bot.trailing_stop_loss,
        'units':bot.units if bot.units is not None else 0,
        'amount':bot.amount if bot.amount is not None else 0,
        'total_volume': bot.total_volume or 0,
        'sell_price':bot.sell_price if bot.sell_price is not None else 0,
        'stop_loss_price':bot.stop_loss_price if bot.stop_loss_price is not None else 0,
        'buy_price':bot.buy_price if bot.buy_price is not None else 0,
        'deal_start_price': bot.deal_start_price or 0,
        'stop_loss':bot.stop_loss,
        "take_profit":bot.take_profit if bot.take_profit is not None else False,
        'Close_deal_after_timeout':bot.Close_deal_after_timeout,
        'timeout':_timeout_display(bot),
        'stop_loss_price_percent':bot.stop_loss_price_percent,
        'stop_loss_time_out':bot.stop_loss_time_out,
        'stop_loss_time_out_time':bot.stop_loss_time_out_time,
        'exchange':bot.exchange,
        'base_currency':bot.base_currency,
        'quote_currency':bot.quote_currency,
        'strategy':bot.strategy,
        'id':bot.id,
        "tp_price":bot.tp_price if bot.tp_price is not None else 0,
        'price_now':bot.price_now if bot.price_now is not None else 0,
        'total_trades':bot.total_trades or 0,
        'total_profit':bot.total_profit or 0,
        'min_volume':bot.min_volume,
        'max_price':bot.max_price,
        'min_price':bot.min_price,
        'min_profit':bot.min_profit,
        'min_profit_type':bot.min_profit_type,
        'min_profit_percent':bot.min_profit_percent,
        'open_deals_and_stop':bot.open_deals_and_stop,
        'trailing_deviation': bot.trailing_deviation,
        'cooldown_between_deals': bot.cooldown_between_deals,
        'close_deal_action': bot.close_deal_action,
        'safety_orders_size_type': bot.safety_orders_size_type,
        'safety_orders_size': bot.safety_orders_size,
        'safety_orders_size_scale': bot.safety_orders_size_scale,
        'safety_orders_deviation': bot.safety_orders_deviation,
        'safety_orders_deviation_scale': bot.safety_orders_deviation_scale,
        'safety_orders_count': bot.safety_orders_count,
        'safety_orders_count_active': bot.safety_orders_count_active,
        'safety_orders_count_max_active': bot.safety_orders_count_max_active,
        'amount_type': bot.amount_type,
        'timeout_type': bot.timeout_type,
        'conds':bot.conds,
        'tp_conds':bot.tp_conds,
        'pair_type':bot.pair_type,
        'start_order_type':bot.start_order_type,
        'auto_restart': bool(bot.auto_restart),
        'last_error': bot.last_error,
        'safety_orders':safety_orders,
        'transactions': [x.serialize() for x in bot.transactions.order_by(Transaction.id.desc()).limit(500).all()],
    })


def reset_bot_for_new_deal(bot):
    bot.deal_started = False
    bot.take_profit = False
    bot.last_price = 0
    bot.sell_price = 0
    bot.stop_loss_time_out_runned = False
    bot.stop_loss_triggered_at = None
    bot.units = bot.amount
    bot.total_volume = bot.amount
    bot.tp_price = 0
    bot.deal_start_price = None
    bot.safety_orders_count_active = 0
    for safety_order in bot.safetyOrders:
        safety_order.isFilled = False
        safety_order.isOpened = False
        safety_order.isClosed = False
        safety_order.orderId = None


@app.route('/api/v1/run_bot',methods=['POST','GET'])
@jwt_required
def run_bot():
    bot, err, code = _owned_bot(request.args.get("bot_id") or _body().get("bot_id"))
    if err is not None:
        return err, code
    if bot.deal_started and bot.isActive:
        return jsonify({'message': "This bot already has an open deal", 'ok': False})
    reset_bot_for_new_deal(bot)
    bot.isActive = True
    db.session.commit()
    return jsonify({'message':f"Bot started successfully. Bot ID: {bot.id}",'ok':True})


def _f(body, key, default=0.0):
    v = body.get(key)
    if v in (None, ""):
        return default
    return float(v)


def _i(body, key, default=0):
    v = body.get(key)
    if v in (None, ""):
        return default
    return int(float(v))


def _opt(body, key, cast=float):
    v = body.get(key)
    return cast(v) if v not in (None, "", 0, "0") else None


def _to_seconds(value, kind):
    if kind == 1:
        return value*60*60
    if kind == 2:
        return value*60
    if kind == 3:
        return value*24*60*60
    return value


def _size_in_base(size, size_type, symbol, price, exchange):
    """Order size in base units from the form's size type:
    1 = quote amount, 2 = base amount, 3 = % of free quote balance."""
    if size_type == 1:
        return size/price
    if size_type == 3:
        free = exchange.fetch_balance().get(symbol.split("/")[1], {}).get('free') or 0
        return ((size/100)*free)/price
    return size


@app.route('/api/v1/create_bot/',methods=['POST','GET'])
@jwt_required
def create_bot():
    current_user = get_current_user()
    body = _body()
    pair_type = str(body["pair_type"]).lower()
    symbols = body.get("symbols") or []
    symbol = body.get("symbol")
    if pair_type == "single":
        symbols_to_create = [symbol]
    else:
        symbols_to_create = list(symbols)
    if not symbols_to_create or not all(s and "/" in str(s) for s in symbols_to_create):
        return jsonify({'message': 'Choose at least one valid pair', 'ok': False}), 400
    limit = current_user.subType.max_bots if current_user.subType else None
    active = Bot.query.filter(Bot.is_hidden == False, Bot.owner_id==current_user.id, Bot.isActive).count()
    if limit and limit < active + len(symbols_to_create):
        return jsonify({'message':"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})

    exchange_name = body["exchange_name"]
    amount = _f(body, "amount")
    if not amount > 0:
        return jsonify({'message': 'Base order size must be positive', 'ok': False}), 400
    amount_type = _i(body, "amount_type", 2)
    safety_orders_size_type = _i(body, "safety_orders_size_type", 2)
    timeout_type = _i(body, "timeout_type", 1) #hrs mins days
    safety_orders_count = max(0, min(_i(body, "safety_orders_count"), 50))
    exchange = connectExchange(exchange_name)

    created = []
    for sym in symbols_to_create:
        price = getPrice(exchange_name, sym)
        if not price:
            return jsonify({'message': f'No price available for {sym}', 'ok': False}), 400
        base_amount = _size_in_base(amount, amount_type, sym, price, exchange)
        so_size = _size_in_base(_f(body, "safety_orders_size"), safety_orders_size_type, sym, price, exchange)
        bot = Bot(
                name=str(body.get("name") or f"{sym} bot")[:120],
                base_currency=sym.split('/')[0],
                quote_currency=sym.split('/')[1],
                exchange=exchange_name,
                start_order_type=str(body.get("start_order_type") or "market").lower(),
                strategy=body.get("strategy") or "Long",
                symbol=sym,
                symbols=symbols,
                pair_type=pair_type,
                units=base_amount,
                amount=base_amount,
                total_volume=base_amount,
                stop_loss = bool(body.get("stop_loss")),
                stop_loss_price_percent = _f(body, "stop_loss_price_percent"),
                trailing_take_profit = bool(body.get("trailing_take_profit")),
                trailing_deviation = _f(body, "trailing_deviation"),
                trailing_stop_loss = bool(body.get("trailing_stop_loss")),
                stop_loss_time_out = bool(body.get("stop_loss_time_out")),
                stop_loss_time_out_time = _i(body, "stop_loss_time_out_time"),
                Close_deal_after_timeout = bool(body.get("Close_deal_after_timeout")),
                timeout = _to_seconds(_i(body, "timeout"), timeout_type),
                tp_type = str(body.get("tp_type") or "Percent %"),
                tp_percent = _f(body, "tp_percent"),
                tp_percent_type = str(body.get("tp_percent_type") or "volume").lower(),
                safety_orders_size = so_size,
                safety_orders_size_scale = _f(body, "safety_orders_size_scale", 1.0),
                safety_orders_deviation = _f(body, "safety_orders_deviation"),
                safety_orders_deviation_scale = _f(body, "safety_orders_deviation_scale", 1.0),
                safety_orders_count = safety_orders_count,
                safety_orders_count_active = 0,
                safety_orders_count_max_active = _i(body, "safety_orders_count_max_active"),
                min_volume = _opt(body, "min_volume"),
                max_price = _opt(body, "max_price"),
                min_price = _opt(body, "min_price"),
                min_profit = bool(body.get("min_profit")),
                min_profit_type = str(body.get("min_profit_type") or "volume"),
                min_profit_percent = _f(body, "min_profit_percent"),
                conds = body.get("conds") or [],
                tp_conds = (body.get("tp_conds") or []),
                close_deal_action = _i(body, "close_deal_action", 1),
                cooldown_between_deals = _opt(body, "cooldown_between_deals", int),
                open_deals_and_stop = _opt(body, "open_deals_and_stop", int),
                timeout_type = timeout_type,
                amount_type = amount_type,
                safety_orders_size_type = safety_orders_size_type,
                auto_restart = bool(body.get("auto_restart")),
                last_open_trade_time = None,
            )
        current_user.bots.append(bot)
        db.session.add(bot)
        for _ in range(safety_orders_count):
            bot.safetyOrders.append(SafetyOrder())
        db.session.commit()
        created.append(bot)
        send_notification(f'{bot.name} bot has been created for {sym}***Bot')
    return jsonify({'message':f"Bot created successfully. Bot ID: {created[-1].id}",'ok':True,
                    'bot_id': created[-1].id, 'bot_ids': [b.id for b in created]})

@app.route('/api/v1/edit_bot/',methods=['POST','GET'])
@jwt_required
def edit_bot():
    body = _body()
    bot, err, code = _owned_bot(body["bot_id"])
    if err is not None:
        return err, code
    amount = _f(body, "amount", bot.amount or 0)
    amount_type = _i(body, "amount_type", 2)
    safety_orders_size_type = _i(body, "safety_orders_size_type", 2)
    timeout_type = _i(body, "timeout_type", 1) #hrs mins days
    symbol = bot.symbol or f"{bot.base_currency}/{bot.quote_currency}"
    price = getPrice(bot.exchange, symbol)
    if not price:
        return jsonify({'message': f'No price available for {symbol}', 'ok': False}), 400
    exchange = connectExchange(bot.exchange, bot.owner_id) if 3 in (amount_type, safety_orders_size_type) else None
    base_amount = _size_in_base(amount, amount_type, symbol, price, exchange)

    if not bot.deal_started:
        bot.amount = base_amount
        bot.units = base_amount
        bot.total_volume = base_amount

    bot.safety_orders_size = _size_in_base(_f(body, "safety_orders_size"), safety_orders_size_type, symbol, price, exchange)
    bot.safety_orders_size_scale = _f(body, "safety_orders_size_scale", 1.0)
    bot.safety_orders_deviation = _f(body, "safety_orders_deviation")
    bot.safety_orders_deviation_scale = _f(body, "safety_orders_deviation_scale", 1.0)
    new_count = max(0, min(_i(body, "safety_orders_count"), 50))
    existing = bot.safetyOrders.count()
    for _ in range(max(0, new_count - existing)):
        bot.safetyOrders.append(SafetyOrder())
    bot.safety_orders_count = new_count
    bot.safety_orders_count_max_active = _i(body, "safety_orders_count_max_active")
    bot.safety_orders_size_type = safety_orders_size_type
    bot.amount_type = amount_type

    bot.name = str(body.get("name") or bot.name)[:120]
    bot.stop_loss = bool(body.get("stop_loss"))
    bot.stop_loss_price_percent = _f(body, "stop_loss_price_percent")
    bot.trailing_take_profit = bool(body.get("trailing_take_profit"))
    if bot.trailing_take_profit == False and not bot.sell_price:
        bot.take_profit = False
    bot.trailing_deviation = _f(body, "trailing_deviation")
    bot.trailing_stop_loss = bool(body.get("trailing_stop_loss"))
    bot.stop_loss_time_out = bool(body.get("stop_loss_time_out"))
    bot.stop_loss_time_out_time = _i(body, "stop_loss_time_out_time")
    bot.Close_deal_after_timeout = bool(body.get("Close_deal_after_timeout"))
    bot.timeout = _to_seconds(_i(body, "timeout"), timeout_type)
    bot.timeout_type = timeout_type
    bot.tp_type = str(body.get("tp_type") or bot.tp_type)
    bot.tp_percent = _f(body, "tp_percent")
    bot.tp_percent_type = str(body.get("tp_percent_type") or "volume").lower()
    bot.min_volume = _opt(body, "min_volume")
    bot.max_price = _opt(body, "max_price")
    bot.min_price = _opt(body, "min_price")
    bot.min_profit = bool(body.get("min_profit"))
    bot.min_profit_type = str(body.get("min_profit_type") or "volume")
    bot.min_profit_percent = _f(body, "min_profit_percent")
    if "conds" in body:
        bot.conds = body.get("conds") or []
    if "tp_conds" in body:
        bot.tp_conds = body.get("tp_conds") or []
    bot.close_deal_action = _i(body, "close_deal_action", 1)
    bot.cooldown_between_deals = _opt(body, "cooldown_between_deals", int)
    if "open_deals_and_stop" in body:
        bot.open_deals_and_stop = _opt(body, "open_deals_and_stop", int)
    if "auto_restart" in body:
        bot.auto_restart = bool(body.get("auto_restart"))
    if bot.deal_started and bot.deal_start_price:
        bot.tp_price = _tp_price(bot)
        if bot.stop_loss and not bot.take_profit:
            bot.stop_loss_price = _initial_stop(bot, bot.deal_start_price)

    db.session.commit()
    return jsonify({'message':f"Bot updated successfully. Bot ID: {bot.id}",'ok':True})


###############################################################################################################
# Engine: one evaluation of one bot. Called by the Celery loop (bot_func_all),
# the in-process scheduler and /api/cron/bots (see crypto/engine.py).
###############################################################################################################

def _is_long(bot):
    return (bot.strategy or "long").lower() != "short"


def _open_side(bot):
    return 'buy' if _is_long(bot) else 'sell'


def _close_side(bot):
    return 'sell' if _is_long(bot) else 'buy'


def _quote_usd(exchange_name, quote):
    return 1 if quote in market.STABLES else (getPrice_assets(exchange_name, quote + '/USDT') or 0)


def _fetch(exchange, order, symbol):
    try:
        return exchange.fetch_order(order["id"], symbol) or {}
    except Exception:
        return {}


def _fill_price(exchange, order, symbol, fallback):
    o = _fetch(exchange, order, symbol)
    return o.get("average") or o.get("price") or fallback


def _net_quantity(order, base, default):
    """Filled quantity actually received: venues often take the buy fee in
    the base asset, so the sellable position is filled - fee."""
    qty = order.get("filled") or default
    fee = order.get("fee") or {}
    if fee.get("cost") and fee.get("currency") == base:
        qty -= fee["cost"]
    return qty


def _record(bot, side, status, err_msg, amount, value, symbol):
    trans = Transaction(user_id=bot.owner_id, bot_id=bot.id, type=side, status=status, err_msg=err_msg,
                        amount=amount, symbol=symbol, exchange=bot.exchange, value=value)
    db.session.add(trans)
    return trans


def _entry_price(bot, basis):
    """TP / min-profit basis: 'base' = first fill, otherwise average entry."""
    if str(basis or "").lower() == "base":
        return bot.deal_start_price or bot.buy_price
    return bot.buy_price or bot.deal_start_price


def _tp_price(bot):
    entry = float(_entry_price(bot, bot.tp_percent_type) or 0)
    pct = float(bot.tp_percent or 0) / 100
    return entry * (1 + pct) if _is_long(bot) else entry * (1 - pct)


def _initial_stop(bot, price):
    pct = float(bot.stop_loss_price_percent or 0) / 100
    return price * (1 - pct) if _is_long(bot) else price * (1 + pct)


def _cancel_safety_orders(exchange, bot, symbol):
    for so in bot.safetyOrders.all():
        if so.isOpened and not so.isClosed and so.orderId:
            try:
                exchange.cancel_order(str(so.orderId), symbol)
            except Exception as e:
                print(f"safety cancel skipped {so.orderId}: {e}")
        so.isOpened = False


def _finish_deal(bot, exchange, symbol, exit_price, reason, now):
    """Bookkeeping after a deal is closed at ``exit_price``."""
    position = bot.total_volume or bot.units or 0
    sign = 1 if _is_long(bot) else -1
    entry = bot.buy_price or bot.deal_start_price or exit_price
    profit = sign * (exit_price - entry) * position * _quote_usd(bot.exchange, bot.quote_currency)
    bot.total_profit = (bot.total_profit or 0) + float(profit)
    bot.last_total_profit_time = now
    bot.sell_price = exit_price
    bot.last_price = exit_price
    bot.deal_started = False
    bot.stop_loss_triggered_at = None
    _cancel_safety_orders(exchange, bot, symbol)
    word = "gained profit" if profit > 0 else "got loss"
    send_notification(f"{bot.name} bot has {word} for {symbol} on {bot.exchange} by {round(profit, 4)} USDT ({reason})***Bot",
                      bot.owner_id, bot.exchange)
    return profit


def _rearm(bot):
    reset_bot_for_new_deal(bot)
    bot.isActive = True


def _stop(bot):
    bot.units = 0
    bot.isActive = False


def _close_position(bot, exchange, symbol, price, reason, now):
    position = bot.total_volume or bot.units or 0
    side = _close_side(bot)
    if side == 'sell':
        # never try to sell more than the account holds (fees, manual trades)
        try:
            free = (exchange.fetch_balance().get(bot.base_currency) or {}).get('free')
            if free and 0 < free < position:
                position = free
        except Exception:
            pass
    try:
        order = exchange.create_order(symbol, 'market', side, position)
        exit_price = _fill_price(exchange, order, symbol, price)
        err_msg, status = "", True
    except Exception as e:
        order, exit_price, err_msg, status = None, price, str(e), False
    _record(bot, side, status, err_msg, position, exit_price, symbol)
    if not status:
        bot.last_error = err_msg[:255]
        send_notification(f"{bot.name} bot has failed to close the deal for {symbol} on {bot.exchange} ({reason}): {err_msg[:120]}***Bot",
                          bot.owner_id, bot.exchange)
        return False, None
    profit = _finish_deal(bot, exchange, symbol, exit_price, reason, now)
    return True, profit


def _conditions_met(conds, symbol, exchange_name, bot):
    return check_indicators_condition(conds, symbol, exchange_name, bot.id, bot=bot)


def _deal_allowed(bot, price, volume, now):
    if bot.max_price is not None and price > bot.max_price:
        return False
    if bot.min_price is not None and price < bot.min_price:
        return False
    if bot.min_volume is not None and volume < bot.min_volume:
        return False
    # Cooldown counts from the close of the previous deal (none before the first).
    cooldown = bot.cooldown_between_deals or 0
    last_close = bot.last_total_profit_time if (bot.total_trades or 0) > 0 else None
    if cooldown > 0 and last_close and (now - last_close).total_seconds() < cooldown:
        return False
    max_deals = bot.open_deals_and_stop or 0
    if max_deals and (bot.total_trades or 0) >= max_deals:
        return False
    return True


def run_bot_once(bot, now=None):
    """Evaluate one bot once. Returns a short status string."""
    now = now or datetime.utcnow()
    if not bot.isActive or bot.is_hidden:
        return "inactive"
    if (bot.units or 0) == 0 and not bot.deal_started:
        return "idle"
    owner = db.session.get(User, bot.owner_id)
    row = owner.exchanges.filter(Exchange.name == bot.exchange).first() if owner else None
    if row is None:
        bot.last_error = f"{bot.exchange} is not connected"
        db.session.commit()
        return "no-exchange"
    exchange = build_exchange(row)
    symbol = f"{bot.base_currency}/{bot.quote_currency}"
    exchange_name = bot.exchange
    long = _is_long(bot)

    price, volume = getPrice_assets(exchange_name, symbol, bot.owner_id, True)
    if not price or price <= 0:
        return "no-price"
    bot.price_now = price

    #######################deal-timeout########################
    if bot.deal_started and bot.Close_deal_after_timeout and bot.timeout and bot.last_open_trade_time:
        if (now - bot.last_open_trade_time).total_seconds() > bot.timeout:
            ok, _ = _close_position(bot, exchange, symbol, price, "deal timeout", now)
            if ok:
                if int(bot.close_deal_action or 1) == 1:
                    _rearm(bot)
                else:
                    _stop(bot)
            db.session.commit()
            return "timeout"

    #######################deal-start-conditions########################
    if not bot.deal_started:
        if not _deal_allowed(bot, price, volume or 0, now):
            db.session.commit()
            return "waiting"
        if bot.conds and not bot.without_conds and not _conditions_met(bot.conds, symbol, exchange_name, bot):
            db.session.commit()
            return "waiting"
        side = _open_side(bot)
        order_type = 'limit' if (bot.start_order_type or '').lower() == 'limit' else 'market'
        try:
            order = exchange.create_order(symbol, order_type, side, bot.amount, price if order_type == 'limit' else None)
            fetched = _fetch(exchange, order, symbol)
            fill = fetched.get("average") or fetched.get("price") or price
            position = _net_quantity(fetched, bot.base_currency, bot.amount) if long else bot.amount
            err_msg, status = "", True
            send_notification(f'{bot.name} bot has started a Quick {side} on {exchange_name} for {symbol} with {round(float(fill * bot.amount),5)} {bot.quote_currency}***{order_type.capitalize()} {side} Order',
                              bot.owner_id, bot.exchange)
        except Exception as e:
            order, fill, err_msg, status, position = None, price, str(e), False, 0
            bot.last_error = err_msg[:255]
            send_notification(f'{bot.name} bot has failed to start a Quick {side} on {exchange_name} for {symbol}: {err_msg[:120]}***{order_type.capitalize()} {side} Order',
                              bot.owner_id, bot.exchange)
        _record(bot, side, status, err_msg, bot.amount, fill, symbol)
        if status:
            bot.deal_started = True
            bot.take_profit = False
            bot.deal_start_price = fill
            bot.buy_price = fill
            bot.total_volume = position
            bot.units = position
            bot.last_price = fill
            bot.stop_loss_price = _initial_stop(bot, fill)
            bot.tp_price = _tp_price(bot)
            bot.last_open_trade_time = now
            bot.total_trades = (bot.total_trades or 0) + 1
            bot.stop_loss_triggered_at = None
            bot.last_error = None
        db.session.commit()
        return "opened" if status else "open-failed"

    #########################Safety_orders#########################
    # 1) fills of previously placed safety orders update the position/average
    for so in bot.safetyOrders.filter(SafetyOrder.isOpened == True).all():
        try:
            o = exchange.fetch_order(so.orderId, symbol)
        except Exception:
            continue
        st = str(o.get("status") or "").lower()
        if st in ("closed", "filled"):
            qty = _net_quantity(o, bot.base_currency, so.amount or 0) if long else (o.get("filled") or so.amount or 0)
            fill = o.get("average") or o.get("price") or so.price or price
            pos = bot.total_volume or 0
            bot.buy_price = ((bot.buy_price or fill) * pos + fill * qty) / (pos + qty) if (pos + qty) else fill
            bot.total_volume = pos + qty
            bot.units = bot.total_volume
            so.isOpened, so.isClosed, so.isFilled = False, True, True
            bot.safety_orders_count_active = max(0, (bot.safety_orders_count_active or 0) - 1)
            bot.tp_price = _tp_price(bot)
        elif st in ("canceled", "cancelled", "expired", "rejected"):
            so.isOpened, so.isClosed = False, True
            bot.safety_orders_count_active = max(0, (bot.safety_orders_count_active or 0) - 1)

    # 2) place the next safety order once price reaches its level
    #    level k = deal_start * (1 -/+ sum_{i<k} deviation * scale^i)
    base = bot.deal_start_price or bot.buy_price
    max_active = int(bot.safety_orders_count_max_active or 0)
    cumulative = 0.0
    for index, so in enumerate(bot.safetyOrders.order_by(SafetyOrder.id.asc()).all()):
        if index >= int(bot.safety_orders_count or 0):
            break
        cumulative += float(bot.safety_orders_deviation or 0) * (float(bot.safety_orders_deviation_scale or 1) ** index)
        if so.isOpened or so.isClosed:
            continue
        if (bot.safety_orders_count_active or 0) >= max_active or not base or not bot.safety_orders_deviation:
            break
        level = base * (1 - cumulative / 100) if long else base * (1 + cumulative / 100)
        reached = price <= level if long else price >= level
        if not reached:
            break
        size = float(bot.safety_orders_size or 0) * (float(bot.safety_orders_size_scale or 1) ** index)
        side = _open_side(bot)
        try:
            order = exchange.create_order(symbol, 'limit', side, size, level)
            err_msg, status = "", True
            send_notification(f'{bot.name} bot has started a {side} Safety Order No.{index + 1} on {exchange_name} for {symbol} at {round(level, 8)} {bot.quote_currency}***{side} Safety Order',
                              bot.owner_id, bot.exchange)
        except Exception as e:
            order, err_msg, status = None, str(e), False
            bot.last_error = err_msg[:255]
            send_notification(f'{bot.name} bot has failed to start a {side} Safety Order on {exchange_name} for {symbol}: {err_msg[:120]}***{side} Safety Order',
                              bot.owner_id, bot.exchange)
        _record(bot, side, status, err_msg, size, level, symbol)
        if not status:
            break
        so.isOpened = True
        so.orderId = str(order["id"])
        so.price = level
        so.amount = size
        bot.safety_orders_count_active = (bot.safety_orders_count_active or 0) + 1
        break  # at most one new safety order per evaluation

    #######################take-profit-conditions########################
    if not bot.take_profit:
        if bot.tp_type == "Percent %":
            tp_price = _tp_price(bot)
            bot.tp_price = tp_price
            if (long and price >= tp_price) or (not long and price <= tp_price):
                if bot.trailing_take_profit:
                    # arm trailing TP: from now on the stop follows the price
                    bot.take_profit = True
                    bot.last_price = price
                    dev = float(bot.trailing_deviation or 0) / 100
                    bot.stop_loss_price = price * (1 - dev) if long else price * (1 + dev)
                else:
                    ok, _ = _close_position(bot, exchange, symbol, price, "take profit", now)
                    if ok:
                        bot.take_profit = True
                        _after_take_profit(bot)
                    db.session.commit()
                    return "take-profit" if ok else "close-failed"
        elif bot.tp_type == "Conditions":
            gate_open = True
            if bot.min_profit:
                entry = float(_entry_price(bot, bot.min_profit_type) or 0)
                pct = float(bot.min_profit_percent or 0) / 100
                bot.tp_price = entry * (1 + pct) if long else entry * (1 - pct)
                gate_open = (long and price >= bot.tp_price) or (not long and price <= bot.tp_price)
            if bot.tp_conds:
                signal = gate_open and _conditions_met(bot.tp_conds, symbol, exchange_name, bot)
            else:
                signal = gate_open and bool(bot.min_profit)
            if signal:
                ok, _ = _close_position(bot, exchange, symbol, price, "take profit", now)
                if ok:
                    bot.take_profit = True
                    _after_take_profit(bot)
                db.session.commit()
                return "take-profit" if ok else "close-failed"

    #######################-----Trailing-----########################
    trailing_tp = bool(bot.trailing_take_profit and bot.tp_type == "Percent %" and bot.take_profit)
    if bot.trailing_stop_loss or trailing_tp:
        improved = (price > (bot.last_price or 0)) if long else (price < (bot.last_price or float("inf")))
        if improved:
            bot.last_price = price
            if trailing_tp:
                dev = float(bot.trailing_deviation or 0) / 100
            else:
                dev = float(bot.stop_loss_price_percent or 0) / 100
            candidate = price * (1 - dev) if long else price * (1 + dev)
            # a trailing stop only ever moves in the favourable direction
            if not bot.stop_loss_price or (long and candidate > bot.stop_loss_price) or (not long and candidate < bot.stop_loss_price):
                bot.stop_loss_price = candidate

    #######################stop-loss-sell########################
    stop = bot.stop_loss_price or 0
    hit = stop > 0 and ((long and price <= stop) or (not long and price >= stop))
    if hit and (bot.stop_loss or trailing_tp):
        if bot.stop_loss_time_out and bot.stop_loss and not trailing_tp:
            # Only stop out if price stays beyond the stop for the timeout.
            if bot.stop_loss_triggered_at is None:
                bot.stop_loss_triggered_at = now
                bot.stop_loss_time_out_runned = True
                db.session.commit()
                return "stop-loss-pending"
            if (now - bot.stop_loss_triggered_at).total_seconds() < (bot.stop_loss_time_out_time or 0):
                db.session.commit()
                return "stop-loss-pending"
        reason = "trailing take profit" if trailing_tp else "stop loss"
        ok, _ = _close_position(bot, exchange, symbol, price, reason, now)
        if ok:
            if trailing_tp:
                _after_take_profit(bot)
            elif int(bot.close_deal_action or 1) == 1 and bot.stop_loss:
                _rearm(bot)
            else:
                _stop(bot)
                bot.take_profit = False
        db.session.commit()
        return "stop-loss" if ok else "close-failed"
    elif not hit and bot.stop_loss_triggered_at is not None:
        bot.stop_loss_triggered_at = None  # price recovered before the timeout

    db.session.commit()
    return "holding"


def _after_take_profit(bot):
    """Legacy behaviour stops the bot after a take profit; bots created with
    auto_restart re-arm for the next deal (respecting cooldown / max deals)."""
    max_deals = bot.open_deals_and_stop or 0
    if bot.auto_restart and not (max_deals and (bot.total_trades or 0) >= max_deals):
        _rearm(bot)
    else:
        _stop(bot)


from math import ceil


def run_bots_page(page, per_page=100):
    ids = [r[0] for r in db.session.query(Bot.id).filter(Bot.is_hidden == False, Bot.isActive == True)
           .order_by(Bot.id.asc()).offset((page - 1) * per_page).limit(per_page).all()]
    stats = {}
    for bot_id in ids:
        bot = db.session.get(Bot, bot_id)
        if bot is None:
            continue
        try:
            status = run_bot_once(bot)
        except Exception as e:
            db.session.rollback()
            print(f"bot {bot_id} failed: {e}")
            status = "error"
        stats[status] = stats.get(status, 0) + 1
    return stats


@celery.task
def bot_func_all(page):
    with app.app_context():
        while True:
            sleep(0.5)
            run_bots_page(page)
            db.session.remove()


def _compare(cond, cur, prev, level):
    cond = (cond or "").replace("Greather", "Greater").lower()
    if cond == 'greater than':
        return cur > level
    if cond == 'less than':
        return cur < level
    if cond == 'crossing up':
        return cur > level and prev < level
    if cond == 'crossing down':
        return cur < level and prev > level
    return False


def _last_two(data, column):
    rows = data[column].tolist()
    if len(rows) < 2:
        return float("nan"), float("nan")
    return float(rows[-1]), float(rows[-2])


def check_indicators_condition(conds,symbol,exchange,bot_id,bot=None):
    """True when every configured indicator condition currently holds.
    Each condition's latest value is stored back on the bot for the UI."""
    if not conds:
        return False
    results = []
    symbol = symbol.replace("/","")
    for cond in conds:
        try:
            name = cond.get('indicator')
            cd = cond.get('conds') or {}
            if name == "TradingView Crypto Screener":
                rec = fetch_data2(symbol, exchange, cd['Timeframe'])['summary']['RECOMMENDATION']
                cond['value'] = rec
                results.append(str(rec).upper() == str(cd.get('Signal Value', '')).upper().replace(" ", "_"))
                continue
            data = fetch_data(symbol, exchange, cd['Timeframe'])
            level = float(cd.get('Signal Value') or 0)
            if name == "RSI":
                data.loc[:, 'v'] = talib.RSI(data.close.to_numpy(), int(cd['RSI Length']))
                cur, prev = _last_two(data, 'v')
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == "MACD":
                macd, signal, hist = talib.MACD(data.close.to_numpy(), int(cd['Fast Length']), int(cd['Slow Length']), int(cd['Signal Length']))
                hist_v, sig_v = float(hist[-1]), float(signal[-1])
                cur = hist_v
                ok1 = hist_v > 0 if cd.get('MACD Trigger') == 'Crossing Up' else (hist_v < 0 if cd.get('MACD Trigger') == 'Crossing Down' else True)
                ok2 = sig_v > 0 if cd.get('Line Trigger') == 'Greater Than 0' else (sig_v < 0 if cd.get('Line Trigger') == 'Less Than 0' else True)
                ok = ok1 and ok2
            elif name == "Commodity Channel Index":
                data.loc[:, 'v'] = talib.CCI(data.high.to_numpy(), data.low.to_numpy(), data.close.to_numpy(), timeperiod=int(cd['Length']))
                cur, prev = _last_two(data, 'v')
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == "Bollinger Bands":
                up, mid, low = talib.BBANDS(data.close.to_numpy(), timeperiod=int(cd["BB% Period"]), nbdevup=int(cd["Deviation"]), nbdevdn=int(cd["Deviation"]))
                close = data.close.to_numpy()
                width = up - low
                pct = [(c - lo) / w if w else 0 for c, lo, w in zip(close[-2:], low[-2:], width[-2:])]
                cur, prev = pct[-1], pct[0]
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == 'Ultimate Oscillator':
                data.loc[:, 'v'] = talib.ULTOSC(data.high.to_numpy(), data.low.to_numpy(), data.close.to_numpy(), timeperiod1=int(cd["Fast Length"]), timeperiod2=int(cd["Middle Length"]), timeperiod3=int(cd["Slow Length"]))
                cur, prev = _last_two(data, 'v')
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == 'Average Directional Index':
                data.loc[:, 'v'] = talib.ADX(data.high.to_numpy(), data.low.to_numpy(), data.close.to_numpy(), timeperiod=int(cd["ADX and DI Length"]))
                cur, prev = _last_two(data, 'v')
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == 'Money Flow Index':
                data.loc[:, 'v'] = talib.MFI(data.high.to_numpy(), data.low.to_numpy(), data.close.to_numpy(), data.volume.to_numpy(), timeperiod=int(cd["MFI Length"]))
                cur, prev = _last_two(data, 'v')
                ok = _compare(cd.get('Condition'), cur, prev, level)
            elif name == 'Parabolic SAR':
                data.loc[:, 'v'] = talib.SAR(data.high.to_numpy(), data.low.to_numpy(), acceleration=float(cd["Start"]), maximum=float(cd["Maximum"]))
                sar_cur, sar_prev = _last_two(data, 'v')
                c_cur, c_prev = _last_two(data, 'close')
                cur = sar_cur
                if cd.get('Condition') == 'Crossing Up (Long)':
                    ok = sar_cur > c_cur and sar_prev < c_prev
                elif cd.get('Condition') == 'Crossing Down (Short)':
                    ok = sar_cur < c_cur and sar_prev > c_prev
                else:
                    ok = False
            else:
                continue  # unknown indicator: ignored, like before
            cond['value'] = None if cur != cur else cur  # NaN -> None (JSON safe)
            results.append(bool(ok))
        except Exception as e:
            print(f"indicator condition {cond.get('indicator')} failed for {symbol}: {e}")
            results.append(False)

    # The latest values were written into the dicts in place; tell SQLAlchemy.
    target = bot if bot is not None else db.session.get(Bot, bot_id)
    if target is not None:
        for attr in ("conds", "tp_conds"):
            if getattr(target, attr) is conds:
                flag_modified(target, attr)
    return all(results) if results else False
