from flask import render_template, request, redirect, url_for, jsonify
from crypto import app,db,celery,jwt_required, get_current_user
from crypto.models import User, Exchange, SmartTrade,Post, Transaction, Pair
from crypto.notify import send_notification
from crypto.exchanges import connectExchange, nav_context
from crypto.functions import getPrice,getPrice_assets, build_exchange
from crypto import market
from time import sleep
import time
from datetime import datetime

LONG_TYPES = ("smart trade",)


def _body():
    return request.get_json(silent=True) or {}


def _kind(st):
    return (st.trade_type or "").strip().lower()


def _entry_side(trade_type):
    return 'buy' if (trade_type or "").strip().lower() in LONG_TYPES else 'sell'


def _open_side(st):
    return _entry_side(st.trade_type)


def _close_side(st):
    return 'sell' if _kind(st) != "smart cover" else 'buy'


def _net_units(order, asset, default):
    """Units actually received: many venues take the buy fee in the bought asset."""
    qty = (order or {}).get('filled') or default
    fee = (order or {}).get('fee') or {}
    if fee.get('cost') and fee.get('currency') == asset:
        qty -= fee['cost']
    return qty


def _sellable(exchange, st, qty):
    """Never try to sell more of the asset than the account holds."""
    if _close_side(st) != 'sell':
        return qty
    try:
        free = (exchange.fetch_balance().get(st.quote_currency) or {}).get('free')
        if free and 0 < free < qty:
            return free
    except Exception:
        pass
    return qty


def _owned(smart_trade_id):
    user = get_current_user()
    st = db.session.get(SmartTrade, smart_trade_id)
    if st is None or st.user_id != user.id:
        return None
    return st


def _num(body, key, default=0.0):
    v = body.get(key)
    if v in (None, ""):
        return default
    return float(v)


@app.route('/trade/')
@jwt_required
def trade():
    current_user = get_current_user()
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    exchange = connectExchange()
    try:
        pairs = [m['symbol'] for m in exchange.fetch_markets() if m.get('active', True) and m.get('spot')]
    except Exception as e:
        print(f"trade page markets unavailable: {e}")
        pairs = market.symbols(getattr(exchange, 'id', None))

    return render_template('trade.html',
                                symbol=request.args.get('symbol'),
                                exchange=request.args.get('exchange'),
                                pairs=pairs,
                                **nav_context(current_user),
                           )

@app.route('/api/v1/smart_trades/', methods=['GET'])
@jwt_required
def get_smart_trades():
    current_user = get_current_user()
    smart_trades = SmartTrade.query.filter_by(user_id=current_user.id).filter(SmartTrade.is_hidden == False).order_by(SmartTrade.id.desc()).all()
    return jsonify(smart_trades=[smart_trade.serialize() for smart_trade in smart_trades])

@app.route('/api/v1/smart_trades/', methods=['POST'])
@jwt_required
def create_smart_trade():
    current_user = get_current_user()
    limit = current_user.subType.max_sma if current_user.subType else None
    if limit and int(limit) <= SmartTrade.query.filter(SmartTrade.user_id==current_user.id, SmartTrade.isActive==True, SmartTrade.is_hidden==False).count():
        return jsonify({'message':f"You have reached the maximum number of smart trades ({limit}). Please upgrade your subscription to create more smart trades.", 'ok': False})
    body = _body()
    trade_type = str(body['trade_type'])
    use_assets = bool(body.get('use_assets'))
    symbol = market.normalize_symbol(body['symbol'])
    price = _num(body, 'price')
    triggerPrice = _num(body, 'triggerPrice')
    buy_type = str(body['buy_type']).lower()
    total_amount = _num(body, 'amount')
    if not total_amount > 0:
        return jsonify({'message': 'Amount must be positive', 'ok': False}), 400
    take_profits = body.get('take_profits') or []
    stop_loss = bool(body.get('stop_loss'))
    take_profit = bool(body.get('take_profit'))
    if stop_loss:
        stop_loss_price_percent = _num(body, 'stop_loss_price_percent')
        stop_loss_trigger_price = _num(body, 'stop_loss_trigger_price')
    else:
        stop_loss_price_percent = 0
        stop_loss_trigger_price = 0
    exchange_name = body['exchange']
    exchange = connectExchange(exchange_name)

    side = _entry_side(trade_type)
    deal_started = False
    isActive = True
    units = None
    buy_trade_id = None
    err_msg = ""
    status = True
    buy_price = price

    if not use_assets:
        if buy_type in ('limit', 'market'):
            try:
                buy_trade = exchange.create_order(symbol, buy_type, side, total_amount, price if buy_type == 'limit' else None)
                buy_trade_id = str(buy_trade['id'])
            except Exception as e:
                err_msg, status = str(e), False
                send_notification(f'{trade_type} has failed to start a Quick {side} on {exchange_name} for {symbol}: {err_msg[:120]}***{buy_type} {trade_type} {side} Order')
                return jsonify({'message': f"Smart Trade failed {err_msg}", 'ok': False})
            try:
                fetched = exchange.fetch_order(buy_trade_id, symbol)
            except Exception:
                fetched = None
            if fetched and str(fetched.get('status') or '').lower() in ('closed', 'filled'):
                buy_price = fetched.get('average') or fetched.get('price') or price or market.price(exchange_name, symbol)
                if side == 'buy':
                    units = _net_units(fetched, symbol.split('/')[0], total_amount)
                deal_started = True
                send_notification(f'{trade_type} has completed a Quick {side} on {exchange_name} for {symbol} with {round(total_amount * buy_price,2)} {symbol.split("/")[1]}***{buy_type} {trade_type} {side} Order')
            else:
                send_notification(f'{trade_type} submitted a Quick {side} on {exchange_name} for {symbol}; waiting for exchange confirmation***{buy_type} {trade_type} {side} Order')
            if deal_started and not take_profit and not stop_loss:
                units = 0
                isActive = False
        elif not buy_type.startswith('cond.'):
            return jsonify({'message': f'Unsupported order type: {buy_type}', 'ok': False}), 400
        # conditional orders wait for the trigger in the engine
    else:
        deal_started = True

    smart_trade = SmartTrade(
        trade_type=trade_type,
        exchange=exchange_name,
        base_currency=symbol.split('/')[1],
        quote_currency=symbol.split('/')[0],
        units=total_amount if units is None else units,
        amount=total_amount,
        user_id=current_user.id,
        buy_price=buy_price,
        buy_trigger_price=triggerPrice,
        stop_loss=stop_loss,
        take_profit=take_profit,
        take_profit_quantities=take_profits,
        tpTriggerType=str(body.get('tpTriggerType') or 'market').lower(),
        order_type=buy_type,
        buy_order_id=buy_trade_id,
        trailing_order_id=None,
        trailing_take_profit=bool(body.get('trailing_take_profit')),
        trailing_deviation=_num(body, 'trailing_deviation'),
        trailing_stop_loss=bool(body.get('trailing_stop_loss')),
        stop_loss_price_percent=stop_loss_price_percent,
        stop_loss_price=stop_loss_trigger_price or (buy_price + buy_price * stop_loss_price_percent / 100 if stop_loss else 0),
        stop_loss_type=body.get('stop_loss_type'),
        stop_loss_time_out=bool(body.get('stop_loss_time_out')),
        stop_loss_time_out_time=int(_num(body, 'stop_loss_time_out_time')),
        deal_started=deal_started,
        move_to_break_even=bool(body.get('move_to_break_even')),
        isActive=isActive,
        last_price=0,
        bought_price=price,
        use_assets=use_assets,
        name=body.get('name'),
    )
    db.session.add(smart_trade)
    db.session.flush()
    if buy_trade_id and deal_started:
        db.session.add(Transaction(user_id=current_user.id, err_msg=err_msg, status=status, exchange=exchange_name,
                                   symbol=symbol, type=side, amount=total_amount, value=buy_price, sma_id=smart_trade.id))
    db.session.commit()
    message = ("Smart Trade executed successfully." if deal_started else
               "Order submitted; waiting for exchange confirmation." if buy_trade_id else
               "Smart Trade armed and waiting for its entry trigger.")
    return jsonify({'message': message, 'ok': True, 'id': smart_trade.id})


@app.route('/api/v1/smart_trades/edit/<int:smart_trade_id>', methods=['POST'])
@jwt_required
def edit_smart_trade(smart_trade_id):
    smart_trade = _owned(smart_trade_id)
    if smart_trade is None:
        return jsonify({'message': 'Smart trade not found or you do not have permission to edit it','ok':False}), 404
    pending = _reconcile_pending_take_profit(smart_trade)
    if pending is not None:
        return pending
    body = _body()
    price = _num(body, 'price', smart_trade.bought_price or 0)
    total_amount = _num(body, 'amount', smart_trade.amount or 0)
    stop_loss = bool(body.get('stop_loss'))
    if stop_loss:
        stop_loss_trigger_price = _num(body, 'stop_loss_trigger_price')
        stop_loss_price_percent = _num(body, 'stop_loss_price_percent')
    else:
        stop_loss_trigger_price = 0
        stop_loss_price_percent = 0
    exchange = connectExchange(body.get('exchange') or smart_trade.exchange)
    symbol = smart_trade.symbol

    # A still-open entry order can be replaced with the new parameters.
    try:
        if smart_trade.buy_order_id:
            entry = exchange.fetch_order(smart_trade.buy_order_id, symbol=symbol)
            state = str(entry.get('status') or '').lower()
            if state == 'open':
                exchange.cancel_order(smart_trade.buy_order_id, symbol=symbol)
                entry = exchange.fetch_order(smart_trade.buy_order_id, symbol=symbol)
                state = str(entry.get('status') or '').lower()
            if state in ('canceled', 'cancelled', 'expired', 'rejected') and not float(entry.get('filled') or 0):
                smart_trade.deal_started = False
                smart_trade.units = total_amount
                smart_trade.amount = total_amount
                smart_trade.buy_price = price
                smart_trade.bought_price = price
                smart_trade.buy_trigger_price = _num(body, 'triggerPrice', smart_trade.buy_trigger_price or 0)
                smart_trade.order_type = 'cond.limit' if body.get('buy_type') in ('limit', 'cond.limit') else 'cond.market'
                smart_trade.buy_order_id = None
            elif state in ('closed', 'filled', 'canceled', 'cancelled', 'expired', 'rejected'):
                if not smart_trade.deal_started:
                    if _reconcile_entry(smart_trade, exchange, smart_trade.buy_price or price) != 'opened':
                        return jsonify({'message': 'Entry fill could not be reconciled before editing.', 'ok': False}), 502
            else:
                return jsonify({'message': 'Entry status is not confirmed. Smart trade was kept for review.', 'ok': False}), 502
    except Exception as e:
        return jsonify({'message': f'Error verifying entry before editing: {e}', 'ok': False}), 502
    if not smart_trade.deal_started and body.get('buy_type'):
        smart_trade.order_type = str(body.get('buy_type')).lower()
        smart_trade.buy_trigger_price = _num(body, 'triggerPrice', smart_trade.buy_trigger_price or 0)
        smart_trade.amount = total_amount
        smart_trade.units = total_amount
        smart_trade.bought_price = price
        smart_trade.buy_price = price
    smart_trade.trade_type = str(body.get('trade_type') or smart_trade.trade_type)
    smart_trade.take_profit_quantities = body.get('take_profits') or smart_trade.take_profit_quantities or []
    smart_trade.tpTriggerType = str(body.get('tpTriggerType') or smart_trade.tpTriggerType or 'market').lower()
    smart_trade.trailing_take_profit = bool(body.get('trailing_take_profit'))
    smart_trade.trailing_stop_loss = bool(body.get('trailing_stop_loss'))
    smart_trade.stop_loss_price_percent = stop_loss_price_percent
    ref = smart_trade.buy_price or price
    smart_trade.stop_loss_price = stop_loss_trigger_price or (ref + ref * stop_loss_price_percent / 100 if stop_loss else 0)
    smart_trade.stop_loss_type = body.get('stop_loss_type')
    smart_trade.stop_loss_time_out = bool(body.get('stop_loss_time_out'))
    smart_trade.stop_loss_time_out_time = int(_num(body, 'stop_loss_time_out_time'))
    smart_trade.stop_loss = stop_loss
    smart_trade.take_profit = bool(body.get('take_profit'))
    smart_trade.trailing_deviation = _num(body, 'trailing_deviation')
    smart_trade.use_assets = bool(body.get('use_assets', smart_trade.use_assets))
    if 'move_to_break_even' in body:
        smart_trade.move_to_break_even = bool(body.get('move_to_break_even'))
    db.session.commit()
    return jsonify({'message': 'Smart trade edited successfully','ok':True})


@app.route('/api/v1/smart_trades/open/<int:smart_trade_id>', methods=['POST'])
@jwt_required
def open_smart_trade(smart_trade_id):
    smart_trade = _owned(smart_trade_id)
    if smart_trade is None:
        return jsonify({'message': 'Smart trade not found or you do not have permission to open it','ok':False}), 404
    smart_trade.isActive = True
    db.session.commit()
    return jsonify({'message': 'Smart trade opened successfully','ok':True})

@app.route('/api/v1/smart_trades/run/<int:smart_trade_id>', methods=['POST'])
@jwt_required
def run_smart_trade(smart_trade_id):
    current_user = get_current_user()
    smart_trade = _owned(smart_trade_id)
    if smart_trade is None:
        return jsonify({'message': 'Smart trade not found or you do not have permission to run it','ok':False}), 404
    if smart_trade.buy_order_id and not smart_trade.deal_started:
        return jsonify({'message': 'An entry order is pending. Reconcile or cancel it before restarting.', 'ok': False}), 409
    pending = _reconcile_pending_take_profit(smart_trade)
    if pending is not None:
        return pending
    if smart_trade.deal_started and (smart_trade.units or 0) > 0:
        return jsonify({'message': 'Close the current position before restarting this smart trade.', 'ok': False}), 409
    limit = current_user.subType.max_sma if current_user.subType else None
    if limit and not smart_trade.isActive:
        active = SmartTrade.query.filter(SmartTrade.isActive == True, SmartTrade.is_hidden == False, SmartTrade.user_id == current_user.id).count()
        if limit <= active:
            return jsonify({'message': "You have reached your maximum number of smart trades. Upgrade your subscription to create more", 'ok': False})

    exchange = connectExchange(smart_trade.exchange, current_user.id)
    symbol = smart_trade.symbol
    total_amount = smart_trade.amount or 0
    side = _open_side(smart_trade)
    deal_started = False
    isActive = True
    buy_price = smart_trade.bought_price or 0
    buy_type = (smart_trade.order_type or 'market').lower()
    buy_trade_id = None

    if not smart_trade.use_assets:
        if buy_type in ('limit', 'market'):
            try:
                buy_trade = exchange.create_order(symbol, buy_type, side, total_amount, smart_trade.bought_price if buy_type == 'limit' else None)
                buy_trade_id = str(buy_trade['id'])
            except Exception as e:
                err_msg = str(e)
                send_notification(f'{smart_trade.trade_type} has failed to start a Quick {side} on {smart_trade.exchange} for {symbol}: {err_msg[:120]}***{buy_type} Smart Trade {side} Order')
                return jsonify({'message': f'Error running smart trade: {err_msg}', 'ok': False}), 502
            try:
                fetched = exchange.fetch_order(buy_trade_id, symbol)
            except Exception:
                fetched = None
            if fetched and str(fetched.get('status') or '').lower() in ('closed', 'filled'):
                buy_price = fetched.get('average') or fetched.get('price') or buy_price
                if side == 'buy':
                    total_amount = _net_units(fetched, smart_trade.quote_currency, total_amount)
                deal_started = True
                send_notification(f'{smart_trade.trade_type} has completed a Quick {side} on {smart_trade.exchange} for {symbol} with {round(total_amount * buy_price, 2)} {symbol.split("/")[1]}***{buy_type} Smart Trade {side} Order')
                db.session.add(Transaction(err_msg="", status=True, user_id=current_user.id, exchange=smart_trade.exchange,
                                           symbol=symbol, type=side, amount=total_amount, value=buy_price,
                                           sma_id=smart_trade.id))
            else:
                send_notification(f'{smart_trade.trade_type} submitted a Quick {side} on {smart_trade.exchange} for {symbol}; waiting for exchange confirmation***{buy_type} Smart Trade {side} Order')
        if deal_started and not smart_trade.take_profit and not smart_trade.stop_loss:
            total_amount = 0
            isActive = False
    else:
        deal_started = True

    smart_trade.units = total_amount
    smart_trade.deal_started = deal_started
    smart_trade.isActive = isActive
    smart_trade.buy_order_id = buy_trade_id
    smart_trade.trailing_order_id = None
    smart_trade.stop_loss_id = None
    smart_trade.last_take_profit_id = None
    smart_trade.last_take_profit = False
    smart_trade.last_price = 0
    smart_trade.take_profit_index = 0
    smart_trade.stop_loss_time_out_runned = False
    smart_trade.stop_loss_triggered_at = None
    smart_trade.buy_price = buy_price
    smart_trade.stop_loss_price = buy_price + buy_price * float(smart_trade.stop_loss_price_percent or 0) / 100 if smart_trade.stop_loss else 0
    db.session.commit()
    message = ('Smart trade ran again successfully' if deal_started else
               'Order submitted; waiting for exchange confirmation' if buy_trade_id else
               'Smart trade armed and waiting for its entry trigger')
    return jsonify({'message': message, 'ok': True})


def _profit_usd(st, exit_price, qty):
    entry = st.buy_price or exit_price
    sign = 1 if _kind(st) in LONG_TYPES else -1
    quote = st.base_currency  # legacy naming: base_currency holds the quote asset
    factor = 1 if quote in market.STABLES else (getPrice_assets(st.exchange, quote + '/USDT') or 0)
    return sign * (exit_price - entry) * factor * qty


@app.route('/api/v1/smart_trades/close/<int:smart_trade_id>', methods=['POST'])
@jwt_required
def close_smart_trade(smart_trade_id):
    current_user = get_current_user()
    smart_trade = _owned(smart_trade_id)
    if smart_trade is None:
        return jsonify({'message': 'Smart trade not found or you do not have permission to close it','ok':False}), 404
    entry = _prepare_pending_entry_for_exit(smart_trade)
    if entry is not None:
        return entry
    pending = _reconcile_pending_take_profit(smart_trade, cancel_open=True)
    if pending is not None:
        return pending
    exchange = connectExchange(smart_trade.exchange, current_user.id)
    symbol = smart_trade.symbol
    side = _close_side(smart_trade)
    qty = smart_trade.units or 0
    if qty <= 0 or not smart_trade.deal_started:
        smart_trade.isActive = False
        db.session.commit()
        return jsonify({'message': 'Smart trade closed (no open position)', 'ok': True})
    qty = _sellable(exchange, smart_trade, qty)
    submitted = False
    try:
        order = exchange.create_order(symbol, 'market', side, qty)
        submitted = True
        fetched = exchange.fetch_order(order["id"], symbol)
        close_price = fetched.get('average') or fetched.get('price') or smart_trade.price_now
        err_msg, status = "", True
    except Exception as e:
        close_price, err_msg, status = smart_trade.price_now, str(e), False
        if submitted:
            # A close may have executed even when its follow-up lookup failed.
            # Pause automation until the exchange order is reconciled.
            smart_trade.isActive = False
    db.session.add(Transaction(status=status, err_msg=err_msg, user_id=current_user.id, exchange=smart_trade.exchange,
                               symbol=symbol, type=side, amount=qty, value=close_price if status else 0, sma_id=smart_trade.id))
    if status:
        smart_trade.isActive = False
        profit = _profit_usd(smart_trade, close_price or 0, qty)
        smart_trade.total_profit = (smart_trade.total_profit or 0) + profit
        smart_trade.last_total_profit_time = datetime.utcnow()
        smart_trade.units = 0
        smart_trade.deal_started = False
        gain_loss = "gained" if profit > 0 else "lost"
        send_notification(f"{smart_trade.trade_type} has {gain_loss} {round(abs(profit), 2)} USDT***Smart Trade {gain_loss.capitalize()}",
                          current_user.id, smart_trade.exchange)
        db.session.commit()
        return jsonify({'message': 'Smart trade closed successfully','ok':True})
    db.session.commit()
    if submitted:
        return jsonify({'message': 'Close order submitted but its status could not be confirmed. Check the exchange order before retrying.',
                        'code': 'close_unconfirmed', 'ok': False}), 502
    return jsonify({'message': f'Error closing smart trade: {err_msg}',
                    'code': 'close_failed', 'ok': False}), 502


@app.route('/api/v1/smart_trades/cancel/<int:smart_trade_id>', methods=['POST'])
@jwt_required
def cancel_smart_trade(smart_trade_id):
    current_user = get_current_user()
    smart_trade = _owned(smart_trade_id)
    if smart_trade is None:
        return jsonify({'error': 'Smart trade not found or you do not have permission to cancel it', 'ok': False}), 404
    entry = _prepare_pending_entry_for_exit(smart_trade)
    if entry is not None:
        return entry
    pending = _reconcile_pending_take_profit(smart_trade, cancel_open=True)
    if pending is not None:
        return pending
    symbol = smart_trade.symbol
    if smart_trade.buy_order_id:
        try:
            exchange = connectExchange(smart_trade.exchange, current_user.id)
            entry = exchange.fetch_order(smart_trade.buy_order_id, symbol=symbol)
            state = entry.get('status')
            filled = float(entry.get('filled') or 0)
            if state == 'open':
                exchange.cancel_order(smart_trade.buy_order_id, symbol=symbol)
            if state == 'closed':
                qty = (smart_trade.units or 0) if smart_trade.deal_started else 0
            elif filled > 0:
                qty = _net_units(entry, smart_trade.quote_currency, filled)
            else:
                qty = 0
            if state not in ('open', 'closed', 'canceled') and qty <= 0:
                return jsonify({'message': 'Entry order status is unknown. Smart trade was kept for review.',
                                'ok': False}), 502
            if qty > 0:
                side = _close_side(smart_trade)
                qty = _sellable(exchange, smart_trade, qty)
                try:
                    close = exchange.create_order(symbol, 'market', side, qty)
                except Exception:
                    return jsonify({'message': 'Could not close the open position. Smart trade was kept for retry.',
                                    'ok': False}), 502
                try:
                    confirmation = exchange.fetch_order(close['id'], symbol)
                except Exception:
                    smart_trade.isActive = False
                    db.session.commit()
                    return jsonify({'message': 'Close order submitted but its status could not be confirmed. Check the exchange before retrying.',
                                    'code': 'close_unconfirmed', 'ok': False}), 502
                if confirmation.get('status') != 'closed':
                    smart_trade.isActive = False
                    db.session.commit()
                    return jsonify({'message': 'Close order is not confirmed filled. Check the exchange before retrying.',
                                    'code': 'close_unconfirmed', 'ok': False}), 502
                value = confirmation.get('average') or confirmation.get('price') or smart_trade.price_now or 0
                db.session.add(Transaction(status=True, err_msg="", user_id=current_user.id,
                                           exchange=smart_trade.exchange, symbol=symbol, type=side,
                                           amount=qty, value=value, sma_id=smart_trade.id))
        except Exception:
            db.session.rollback()
            return jsonify({'message': 'Could not verify or cancel the exchange order. Smart trade was kept for retry.',
                            'ok': False}), 502

    # Transactions keep their history: detach them before deleting the trade.
    Transaction.query.filter(Transaction.sma_id == smart_trade.id).update({Transaction.sma_id: None})
    db.session.delete(smart_trade)
    db.session.commit()
    return jsonify({'message': 'Smart trade cancelled successfully','ok':True})

# GET /api/v1/smart_trades/:id
@app.route('/api/v1/smart_trades/<int:id>', methods=['GET'])
@jwt_required
def get_smart_trade(id):
    smart_trade = _owned(id)
    if not smart_trade:
        return jsonify({'error': f'Smart trade with ID {id} does not exist or does not belong to this user'}), 404
    return jsonify(smart_trade=smart_trade.serialize())


###############################################################################################################
# Engine: one evaluation of one smart trade (Celery loop, scheduler, cron).
###############################################################################################################

def _tp_levels(st):
    out = []
    for tp in st.take_profit_quantities or []:
        try:
            out.append((float(tp[0]), float(tp[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _record_take_profit_fill(st, order, now, levels):
    """Advance a target only after the exchange confirms an actual fill."""
    idx = min(st.take_profit_index or 0, len(levels) - 1)
    fallback = (st.units or 0) if idx == len(levels) - 1 else levels[idx][1] * (st.amount or 0) / 100
    qty = min(float(order.get('filled') or order.get('amount') or fallback), st.units or 0)
    if qty <= 0:
        return False
    fill = order.get('average') or order.get('price') or st.price_now or st.buy_price
    side = _close_side(st)
    db.session.add(Transaction(status=True, err_msg="", user_id=st.user_id, exchange=st.exchange,
                               symbol=st.symbol, type=side, amount=qty, value=fill, sma_id=st.id))
    profit = _profit_usd(st, fill, qty)
    st.total_profit = (st.total_profit or 0) + profit
    st.last_total_profit_time = now
    st.units = max(0.0, (st.units or 0) - qty)
    st.last_price = st.price_now
    st.take_profit_index = min(idx + 1, len(levels) - 1)
    st.last_take_profit_id = None
    if st.move_to_break_even and len(levels) > 1 and idx == 0:
        st.stop_loss_price = st.buy_price
    gain_loss = "gained" if profit > 0 else "lost"
    send_notification(f"{st.trade_type} has {gain_loss} {round(profit, 2)} USDT (take profit {idx + 1}/{len(levels)})***Smart Trade {gain_loss.capitalize()}", st.user_id, st.exchange)
    if st.units <= 1e-12:
        st.units = 0
        st.isActive = False
        st.deal_started = False
    return True


def _reconcile_pending_take_profit(st, cancel_open=False):
    """Let manual actions settle a completed TP even when no engine worker runs."""
    if not st.last_take_profit_id:
        return None
    try:
        exchange = connectExchange(st.exchange, st.user_id)
        order = exchange.fetch_order(st.last_take_profit_id, st.symbol)
    except Exception:
        return jsonify({'message': 'Could not verify the pending take-profit order. Smart trade was kept for review.', 'ok': False}), 502
    state = str(order.get('status') or '').lower()
    if state == 'open' and cancel_open:
        try:
            exchange.cancel_order(st.last_take_profit_id, st.symbol)
            order = exchange.fetch_order(st.last_take_profit_id, st.symbol)
            state = str(order.get('status') or '').lower()
        except Exception:
            return jsonify({'message': 'Could not cancel or verify the pending take-profit order. Smart trade was kept for review.', 'ok': False}), 502
    levels = _tp_levels(st)
    if state in ('closed', 'filled'):
        if not levels or not _record_take_profit_fill(st, order, datetime.utcnow(), levels):
            return jsonify({'message': 'Could not reconcile the take-profit fill. Smart trade was kept for review.', 'ok': False}), 502
        db.session.commit()
        return None
    if state in ('canceled', 'cancelled', 'expired', 'rejected'):
        st.last_take_profit_id = None
        if float(order.get('filled') or 0) > 0:
            if not levels or not _record_take_profit_fill(st, order, datetime.utcnow(), levels):
                return jsonify({'message': 'Could not reconcile the partial take-profit fill. Smart trade was kept for review.', 'ok': False}), 502
        db.session.commit()
        return None
    return jsonify({'message': 'A take-profit order is still pending. Cancel it on the exchange before changing this trade.', 'ok': False}), 409


def _reconcile_entry(st, exchange, fallback_price):
    """Resolve one submitted entry without ever submitting it a second time."""
    try:
        order = exchange.fetch_order(st.buy_order_id, st.symbol)
    except Exception:
        return "entry-unconfirmed"
    state = str(order.get('status') or '').lower()
    filled = float(order.get('filled') or 0)
    if state in ('open', 'pending'):
        return "entry-pending"
    if state in ('canceled', 'cancelled', 'expired', 'rejected') and filled <= 0:
        st.buy_order_id = None
        if not (st.order_type or '').startswith('cond.'):
            st.isActive = False
        db.session.commit()
        return "entry-cancelled"
    if state not in ('closed', 'filled', 'canceled', 'cancelled', 'expired', 'rejected'):
        return "entry-unconfirmed"
    side = _open_side(st)
    qty = filled or (st.amount or 0)
    if side == 'buy':
        qty = _net_units(order, st.quote_currency, qty)
    fill = order.get('average') or order.get('price') or fallback_price
    st.units = qty
    st.buy_price = fill
    st.deal_started = True
    st.stop_loss_price = fill + fill * float(st.stop_loss_price_percent or 0) / 100 if st.stop_loss else 0
    db.session.add(Transaction(status=True, err_msg="", user_id=st.user_id, exchange=st.exchange,
                               symbol=st.symbol, type=side, value=fill, amount=qty, sma_id=st.id))
    send_notification(f'{st.trade_type} confirmed a {side} entry on {st.exchange} for {st.symbol}***Smart Trade Entry', st.user_id, st.exchange)
    if not st.take_profit and not st.stop_loss:
        st.units = 0
        st.isActive = False
    db.session.commit()
    return "opened"


def _prepare_pending_entry_for_exit(st):
    """Cancel an open entry and account for any fill before an exit or delete."""
    if not st.buy_order_id or st.deal_started:
        return None
    try:
        exchange = connectExchange(st.exchange, st.user_id)
        status = _reconcile_entry(st, exchange, st.buy_price or st.price_now or 0)
        if status == "entry-pending":
            try:
                exchange.cancel_order(st.buy_order_id, st.symbol)
            except Exception:
                pass  # it may have filled between fetch and cancel
            status = _reconcile_entry(st, exchange, st.buy_price or st.price_now or 0)
    except Exception:
        return jsonify({'message': 'Could not reconcile the pending entry. Smart trade was kept for review.', 'ok': False}), 502
    if status not in ('opened', 'entry-cancelled'):
        return jsonify({'message': 'Entry status is not confirmed. Smart trade was kept for review.', 'ok': False}), 502
    return None


def _market_close(st, exchange, symbol, qty, price, label):
    side = _close_side(st)
    qty = _sellable(exchange, st, qty)
    try:
        order = exchange.create_order(symbol, 'market', side, qty)
        fetched = exchange.fetch_order(order['id'], symbol)
        fill = fetched.get('average') or fetched.get('price') or price
        err_msg, status = "", True
    except Exception as e:
        fill, err_msg, status = price, str(e), False
    db.session.add(Transaction(status=status, err_msg=err_msg, user_id=st.user_id, exchange=st.exchange, symbol=symbol,
                               type=side, amount=qty, value=fill if status else 0, sma_id=st.id))
    if status:
        profit = _profit_usd(st, fill, qty)
        st.total_profit = (st.total_profit or 0) + profit
        st.last_total_profit_time = datetime.utcnow()
        st.units = 0
        st.isActive = False
        st.deal_started = False
        st.stop_loss_triggered_at = None
        gain_loss = "gained" if profit > 0 else "lost"
        send_notification(f"{st.trade_type} has completed a {label} {side} order for {symbol} on {st.exchange}***{st.trade_type}", st.user_id, st.exchange)
        send_notification(f"{st.trade_type} has {gain_loss} {round(abs(profit), 2)} USDT***Smart Trade {gain_loss.capitalize()}", st.user_id, st.exchange)
    else:
        send_notification(f"{st.trade_type} has failed to complete a {label} {side} order for {symbol} on {st.exchange}: {err_msg[:120]}***{st.trade_type} Stop Loss Error", st.user_id, st.exchange)
    return status


def run_smart_trade_once(st, now=None):
    now = now or datetime.utcnow()
    if not st.isActive or st.is_hidden or (st.units or 0) <= 0:
        return "inactive"
    owner = db.session.get(User, st.user_id)
    row = owner.exchanges.filter(Exchange.name == st.exchange).first() if owner else None
    if row is None:
        return "no-exchange"
    exchange = build_exchange(row)
    symbol = st.symbol
    kind = _kind(st)
    cover = kind == "smart cover"
    price = getPrice_assets(st.exchange, symbol, st.user_id)
    if not price or price <= 0:
        return "no-price"
    st.price_now = price

    # --- conditional entry (cond.limit / cond.market) once the trigger is hit
    if not st.use_assets and not st.deal_started:
        if st.buy_order_id:
            return _reconcile_entry(st, exchange, price)
        if (st.order_type or "").startswith("cond.") and st.buy_trigger_price and price >= st.buy_trigger_price:
            side = _open_side(st)
            order_type = 'limit' if st.order_type == 'cond.limit' else 'market'
            limit_price = (st.bought_price or st.buy_price or price) if order_type == 'limit' else None
            try:
                order = exchange.create_order(symbol, order_type, side, st.amount, limit_price)
                st.buy_order_id = str(order['id'])
            except Exception as e:
                send_notification(f'{st.trade_type} has failed to start a Conditional {side} on {st.exchange} for {symbol}: {str(e)[:120]}***{st.order_type} {st.trade_type} {side} Order', st.user_id, st.exchange)
                return "entry-failed"
            db.session.commit()
            return _reconcile_entry(st, exchange, limit_price or price)
        db.session.commit()
        return "waiting"

    if not st.deal_started:
        return "waiting"

    # --- take profit levels: [percent from entry, % of amount]
    levels = _tp_levels(st)
    if st.last_take_profit_id:
        try:
            pending = exchange.fetch_order(st.last_take_profit_id, symbol)
        except Exception:
            return "take-profit-unconfirmed"
        state = str(pending.get('status') or '').lower()
        if state in ('closed', 'filled'):
            if levels and _record_take_profit_fill(st, pending, now, levels):
                db.session.commit()
                return "take-profit"
            return "take-profit-unconfirmed"
        if state in ('canceled', 'cancelled', 'expired', 'rejected'):
            st.last_take_profit_id = None
            if levels and float(pending.get('filled') or 0) > 0:
                _record_take_profit_fill(st, pending, now, levels)
                db.session.commit()
                return "take-profit"
            db.session.commit()
            return "take-profit-cancelled"
        stop = st.stop_loss_price or 0
        stop_hit = stop > 0 and ((price >= stop) if cover else (price <= stop))
        trailing_exit = bool(st.trailing_take_profit and st.last_take_profit)
        if not stop_hit and st.stop_loss_triggered_at is not None:
            st.stop_loss_triggered_at = None
            db.session.commit()
        if state == 'open' and stop_hit and (st.stop_loss or trailing_exit):
            if st.stop_loss_time_out and st.stop_loss and not trailing_exit:
                if st.stop_loss_triggered_at is None:
                    st.stop_loss_triggered_at = now
                    db.session.commit()
                    return "stop-loss-pending"
                if (now - st.stop_loss_triggered_at).total_seconds() < (st.stop_loss_time_out_time or 0):
                    return "stop-loss-pending"
            try:
                exchange.cancel_order(st.last_take_profit_id, symbol)
                return "take-profit-cancelling"
            except Exception:
                return "take-profit-pending"
        return "take-profit-pending"
    if st.take_profit and levels and kind != "smart buy":
        idx = min(st.take_profit_index or 0, len(levels) - 1)
        pct, qty_pct = levels[idx]
        target = st.buy_price + st.buy_price * pct / 100
        reached = price <= target if cover else price >= target
        is_last = idx == len(levels) - 1
        if reached:
            if is_last and st.trailing_take_profit:
                st.last_take_profit = True
            if not (is_last and st.trailing_take_profit):
                qty = min(st.units or 0, qty_pct * (st.amount or 0) / 100) if not is_last else (st.units or 0)
                qty = _sellable(exchange, st, qty)
                order_type = 'limit' if (st.tpTriggerType or '').lower() == 'limit' else 'market'
                side = _close_side(st)
                try:
                    order = exchange.create_order(symbol, order_type, side, qty, target if order_type == 'limit' else None)
                    st.last_take_profit_id = str(order['id'])
                except Exception as e:
                    send_notification(f"{st.trade_type} has failed to submit a Take profit {side} order for {symbol} on {st.exchange}: {str(e)[:120]}***Smart Trade Take Profit", st.user_id, st.exchange)
                    db.session.commit()
                    return "take-profit-failed"
                try:
                    fetched = exchange.fetch_order(st.last_take_profit_id, symbol)
                except Exception:
                    db.session.commit()
                    return "take-profit-unconfirmed"
                state = str(fetched.get('status') or '').lower()
                if state in ('closed', 'filled'):
                    result = "take-profit" if _record_take_profit_fill(st, fetched, now, levels) else "take-profit-unconfirmed"
                else:
                    result = "take-profit-pending"
                db.session.commit()
                return result

    # --- trailing stop / trailing take profit
    improved = (price < (st.last_price or float("inf"))) if cover else (price > (st.last_price or 0))
    if improved:
        st.last_price = price
        candidate = None
        if st.trailing_take_profit and st.last_take_profit:
            candidate = price + price * float(st.trailing_deviation or 0) / 100
        elif st.trailing_stop_loss and st.stop_loss:
            candidate = price + price * float(st.stop_loss_price_percent or 0) / 100
        if candidate:
            better = (candidate < (st.stop_loss_price or float("inf"))) if cover else (candidate > (st.stop_loss_price or 0))
            if better or not st.stop_loss_price:
                st.stop_loss_price = candidate

    # --- stop loss (or trailing take-profit exit)
    stop = st.stop_loss_price or 0
    hit = stop > 0 and ((price >= stop) if cover else (price <= stop))
    trailing_exit = bool(st.trailing_take_profit and st.last_take_profit)
    if hit and (st.units or 0) > 0 and (st.stop_loss or trailing_exit):
        if st.stop_loss_time_out and st.stop_loss and not trailing_exit:
            if st.stop_loss_triggered_at is None:
                st.stop_loss_triggered_at = now
                st.stop_loss_time_out_runned = True
                db.session.commit()
                return "stop-loss-pending"
            if (now - st.stop_loss_triggered_at).total_seconds() < (st.stop_loss_time_out_time or 0):
                db.session.commit()
                return "stop-loss-pending"
        _market_close(st, exchange, symbol, st.units, price, "Trailing take profit" if trailing_exit else "Stop loss")
        db.session.commit()
        return "stop-loss"
    if not hit and st.stop_loss_triggered_at is not None:
        st.stop_loss_triggered_at = None

    db.session.commit()
    return "holding"


def _run_smart_trade_ids(ids):
    stats = {}
    for st_id in ids:
        st = db.session.get(SmartTrade, st_id)
        if st is None:
            continue
        try:
            status = run_smart_trade_once(st)
        except Exception as e:
            db.session.rollback()
            print(f"smart trade {st_id} failed: {e}")
            status = "error"
        stats[status] = stats.get(status, 0) + 1
    return stats


def run_smart_trades_page(page, per_page=100):
    """Legacy fixed page for the Celery worker."""
    ids = [r[0] for r in db.session.query(SmartTrade.id).filter(SmartTrade.isActive == True, SmartTrade.is_hidden == False)
           .order_by(SmartTrade.id.asc()).offset((page - 1) * per_page).limit(per_page).all()]
    return _run_smart_trade_ids(ids)


def run_smart_trades_after(after_id, per_page=100):
    """Stable engine batch even when earlier trades complete during this tick."""
    ids = [r[0] for r in db.session.query(SmartTrade.id).filter(
        SmartTrade.isActive == True, SmartTrade.is_hidden == False, SmartTrade.id > after_id
    ).order_by(SmartTrade.id.asc()).limit(per_page).all()]
    return _run_smart_trade_ids(ids), (ids[-1] if ids else after_id), len(ids)


@celery.task
def smart_trade_bot_all(page):
    with app.app_context():
        while True:
            sleep(0.5)
            run_smart_trades_page(page)
            db.session.remove()
