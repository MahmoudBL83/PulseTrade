import json
from flask import render_template, request, redirect, url_for, jsonify,Response
import ccxt
from crypto import app, db, jwt_required, get_current_user
from crypto.models import Exchange,Post,Transaction
from crypto.notify import send_notification
from crypto.exchanges import connectExchange, nav_context
from crypto.functions import build_exchange, find_exchange_row


def _body():
    return request.get_json(silent=True) or {}


def _has(exchange, feature):
    try:
        return bool(exchange.describe()['has'].get(feature))
    except Exception:
        return False


def _quote(symbol):
    parts = str(symbol or "").split("/")
    return parts[1] if len(parts) > 1 else ""


@app.route('/api/v1/order/', methods=['POST'])
@jwt_required
def place_order():
    '''
    This function is used to place an order on the exchange.
    Params:
        symbol: the symbol of the order
        type: the type of the order (limit, market, cond.limit, cond.market)
        order_price: the price of the order
        trigger_price: the trigger price for conditional orders
        amount: the amount of the order
        side: the side of the order (buy or sell)
        exchange (optional): connected exchange to use, defaults to the active one
    '''
    current_user = get_current_user()
    body = _body()
    row = find_exchange_row(current_user, body.get('exchange'))
    exchange_name = row.name
    exchange = build_exchange(row)

    try:
        # Parse the order parameters from the request body
        symbol = str(body['symbol']).upper()
        order_type = str(body['type']).lower()
        if order_type not in ('limit', 'market', 'cond.limit', 'cond.market'):
            return jsonify({'message': f'Unsupported order type: {order_type}', 'ok': False}), 400
        order_price = float(body['order_price']) if body.get('order_price') else 0
        amount = float(body['amount'])
        side = str(body['side']).lower()
        if side not in ('buy', 'sell'):
            return jsonify({'message': f'Unsupported side: {side}', 'ok': False}), 400
        if not (amount > 0):
            return jsonify({'message': 'Amount must be positive', 'ok': False}), 400
        if order_type in ('limit', 'cond.limit') and not (order_price > 0):
            return jsonify({'message': 'Limit orders require a positive price', 'ok': False}), 400
        if '/' not in symbol:
            return jsonify({'message': f'Invalid symbol: {symbol}', 'ok': False}), 400
        trigger_price = float(body['trigger_price']) if order_type.startswith('cond.') else None
        if order_type.startswith('cond.') and not (trigger_price and trigger_price > 0):
            return jsonify({'message': 'Conditional orders require a positive trigger price', 'ok': False}), 400
        quote = _quote(symbol)

        # Place the order on the exchange and return the order details as a JSON object
        if order_type == 'limit':
            buy_trade = exchange.create_order(symbol, order_type, side, amount, order_price)
            recorded_price = order_price
            send_notification(f'Quick {side} placed on {exchange_name} for {symbol} with {round(order_price * amount, 8)} {quote} ***Limit {side} Order')
            if buy_trade.get('status') == 'open':
                current_user.append_to_open_orders([buy_trade['id'], symbol, f'Limit {side}'])
        elif order_type == 'market':
            buy_trade = exchange.create_order(symbol, order_type, side, amount)
            try:
                fetched = exchange.fetch_order(buy_trade["id"], symbol=symbol)
                recorded_price = fetched.get("average") or fetched.get("price") or 0
            except Exception:
                recorded_price = buy_trade.get("average") or buy_trade.get("price") or 0
            send_notification(f'Quick {side} finished on {exchange_name} for {symbol} with {round((recorded_price or 0) * amount, 8)} {quote} ***Market {side} Order')
        else:
            kind = 'limit' if order_type == 'cond.limit' else 'market'
            buy_trade = exchange.create_order(symbol, kind, side, amount, order_price if kind == 'limit' else None,
                                              params={'triggerPrice': trigger_price})
            recorded_price = order_price or trigger_price
            send_notification(f'Trigger Quick {side} order started on {exchange_name} for {symbol} with {round(trigger_price * amount, 8)} {quote} ***Conditional {kind.capitalize()} {side} Order')
            current_user.append_to_open_orders([buy_trade['id'], symbol, 'Trigger Buy' if side == 'buy' else 'Trigger Sell'])

        db.session.add(Transaction(user_id=current_user.id,exchange=exchange_name,symbol=symbol,type=side,amount=amount,value=recorded_price))
        db.session.commit()
        return jsonify({'message': 'The operation was successful', 'ok': True, 'order': buy_trade})

    except ccxt.InsufficientFunds as e:
        return jsonify({'message': 'Insufficient funds: ' + str(e), 'ok': False})
    except ccxt.InvalidOrder as e:
        return jsonify({'message': str(e), 'ok': False})
    except ccxt.AuthenticationError as e:
        return jsonify({'message': 'Authentication error: ' + str(e), 'ok': False})
    except ccxt.DDoSProtection as e:
        return jsonify({'message': 'DDoS protection error: ' + str(e), 'ok': False})
    except ccxt.ExchangeError as e:
        return jsonify({'message': 'Exchange error: ' + str(e), 'ok': False})
    except ccxt.NetworkError as e:
        return jsonify({'message': 'Network error: ' + str(e), 'ok': False})
    except (KeyError, ValueError, TypeError):
        raise  # handled centrally (400)
    except Exception as e:
        return jsonify({'message': 'An error occurred: ' + str(e), 'ok': False})

@app.route('/api/v1/order/cancel',methods=['POST'])
@jwt_required
def cancel_order():
    '''
    this function is used to cancel an order on the exchange
    params:
        id: the id of the order
        symbol: the symbol of the order
        exchange (optional): connected exchange, defaults to the active one
    '''
    body = _body()
    id = body['id']
    symbol = body['symbol']
    exchange = connectExchange(body.get('exchange'))
    last_error = None
    # Normal orders first; conditional (stop/trigger) orders need the flag on some venues.
    for params in ({}, {"stop": True}, {"trigger": True}):
        try:
            order = exchange.cancel_order(id, symbol=symbol, params=params)
            user = get_current_user()
            for item in user._open_orders_list():
                if str(item[0]) == str(id):
                    user.remove_from_open_orders(item)
            db.session.commit()
            return jsonify({'message': f'the order with id {id} has been cancelled','ok':True,'order': order})
        except ccxt.BaseError as e:
            last_error = e
            continue
    return jsonify({'message': f'the cancel operation failed: {last_error}','ok':False})

#############################################---------------HISTORY-START-------------#############################################

def _require_exchange(user):
    if user.exchanges.filter(Exchange.isActive==True).first() is None and user.exchanges.first() is None:
        return redirect(url_for('exchanges'))
    return None


def _unique(orders):
    seen = {}
    for o in orders:
        key = (o.get('exchange'), o.get('id'))
        if key not in seen:
            seen[key] = o
    return list(seen.values())


def _trigger_text(order, quote):
    trig = order.get('triggerPrice') or order.get('stopLossPrice') or order.get('takeProfitPrice') or order.get('stopPrice')
    return f"{trig} {quote}" if trig else "--"


@app.route('/api/v1/history/open_orders/', methods=['GET','POST'])
@jwt_required
def history_open_orders():
    current_user = get_current_user()
    missing = _require_exchange(current_user)
    if missing is not None:
        return missing
    open_orders = []
    trigger_orders_all = []
    limit_market_orders_all = []
    not_supported_open_orders = []
    for exchange_user in current_user.exchanges.all():
        try:
            exchangeNow = build_exchange(exchange_user)
            if not _has(exchangeNow, 'fetchOpenOrders'):
                not_supported_open_orders.append(exchange_user.name)
                continue
            limit_market_orders = list(exchangeNow.fetch_open_orders())
            trigger_orders = []
            for params in ({"stop": True, "ordType": "limit"}, {"stop": True, "ordType": "market"}):
                try:
                    limit_market_orders += exchangeNow.fetch_open_orders(params=params)
                except Exception:
                    pass
            try:
                trigger_orders = exchangeNow.fetch_open_orders(params={"stop": True, "ordType": "trigger"})
            except Exception:
                pass
            for x in limit_market_orders + trigger_orders:
                x['exchange'] = exchange_user.name
            limit_market_orders_all += _unique(limit_market_orders)
            trigger_orders_all += _unique(trigger_orders)
            open_orders += _unique(limit_market_orders + trigger_orders)
        except Exception as e:
            print(f"open orders for {exchange_user.name} unavailable: {e}")
            not_supported_open_orders.append(exchange_user.name)

    open_orders = sorted(_unique(open_orders), key = lambda i: i.get('timestamp') or 0,reverse=True)

    formatted_history = []
    for order in open_orders:
        quote = _quote(order.get('symbol'))
        price = order.get('price')
        formatted_history.append({
            'id': order.get('id'),
            'exchange': order.get('exchange'),
            'symbol': order.get('symbol'),
            'filled_amount': order.get('filled') or 0,
            'order_type': order.get('type'),
            'total_amount': order.get('amount'),
            'remaining_amount': order.get('remaining'),
            'cost': order.get('cost'),
            'trigger_price': _trigger_text(order, quote),
            'order_price': f"{price} {quote}" if price and price != -1 else "market",
            'side': order.get('side'),
            'status': order.get('status'),
            'time': order.get('timestamp'),
            'reduceOnly': order.get('reduceOnly'),
        })

    not_supported_open_orders = list(dict.fromkeys(not_supported_open_orders))
    if request.method == 'POST':
        return Response(json.dumps(formatted_history, indent=4, default=str), content_type='application/json')
    return render_template("history_open_orders.html",
                                orders=formatted_history,
                                mormal_count=len(limit_market_orders_all),
                                trigger_count=len(trigger_orders_all),
                                not_supported_open_orders=not_supported_open_orders,
                                **nav_context(current_user),
                            )

@app.route('/api/v1/history/orders/', methods=['GET','POST'])
@jwt_required
def history_orders():
    current_user = get_current_user()
    missing = _require_exchange(current_user)
    if missing is not None:
        return missing
    history_orders = []
    not_supported_closed_orders = []
    closed_count = 0
    cancelled_count = 0
    for exchange_user in current_user.exchanges.all():
        try:
            exchangeNow = build_exchange(exchange_user)
        except Exception as e:
            not_supported_closed_orders.append(exchange_user.name)
            continue
        closed, cancelled = [], []
        if _has(exchangeNow, 'fetchClosedOrders'):
            try:
                closed = list(exchangeNow.fetch_closed_orders())
            except Exception:
                not_supported_closed_orders.append(exchange_user.name)
        else:
            not_supported_closed_orders.append(exchange_user.name)
        if _has(exchangeNow, 'fetchCanceledOrders'):
            for kind in ("limit", "market", "trigger"):
                try:
                    cancelled += exchangeNow.fetch_canceled_orders(params={"stop": True, "ordType": kind})
                except Exception:
                    continue
        else:
            not_supported_closed_orders.append(exchange_user.name)
        for x in closed + cancelled:
            x['exchange'] = exchange_user.name
        closed, cancelled = _unique(closed), _unique(cancelled)
        closed_count += len(closed)
        cancelled_count += len(cancelled)
        history_orders += cancelled + closed

    history_orders = sorted(_unique(history_orders), key = lambda i: i.get('timestamp') or 0,reverse=True)

    formatted_history = []
    for order in history_orders:
        quote = _quote(order.get('symbol'))
        base = str(order.get('symbol') or "").split("/")[0]
        price = order.get('price')
        fee = order.get('fee') or {}
        formatted_history.append({
            'id': order.get('id'),
            'exchange': order.get('exchange'),
            'timestamp': order.get('timestamp'),
            'datetime': order.get('datetime'),
            'side': order.get('side'),
            'order_type': order.get('type'),
            'reduceOnly': order.get('reduceOnly'),
            'stopLossPrice': order.get('stopLossPrice'),
            'stopPrice': order.get('stopPrice'),
            'takeProfitPrice': order.get('takeProfitPrice'),
            'trigger_price': _trigger_text(order, quote),
            'order_price': f"{price if price >= 0 else 'market'} {quote}" if price else "market",
            'average': order.get('average'),
            'status': order.get('status'),
            'symbol': order.get('symbol'),
            'amount': f"{abs(order.get('amount') or 0)} {base}",
            'fee': f"{fee.get('cost')} {fee.get('currency')}" if fee.get('cost') is not None else 0,
        })

    if request.method == 'POST':
        return Response(json.dumps(formatted_history, indent=4, default=str), content_type='application/json')
    return render_template("history_orders.html",
                                orders=formatted_history,
                                closed_count=closed_count,
                                cancelled_count=cancelled_count,
                                not_supported_closed_orders=list(dict.fromkeys(not_supported_closed_orders)),
                                **nav_context(current_user),
                             )

@app.route('/api/v1/history/trades/', methods=['GET', 'POST'])
@jwt_required
def history_trades_history():
    current_user = get_current_user()
    missing = _require_exchange(current_user)
    if missing is not None:
        return missing
    ledgers_all = []
    not_supported_trading_history = []
    for exchange_user in current_user.exchanges.all():
        try:
            exchangeNow = build_exchange(exchange_user)
            if not _has(exchangeNow, 'fetchLedger'):
                not_supported_trading_history.append(exchange_user.name)
                continue
            ledgers = exchangeNow.fetch_ledger(params = {"stop":True,"ordType":"trigger"})
        except Exception:
            not_supported_trading_history.append(exchange_user.name)
            continue
        for x in ledgers:
            x['exchange'] = exchange_user.name
        ledgers_all += ledgers

    trading_history = sorted(ledgers_all, key = lambda i: i.get('timestamp') or 0,reverse=True)

    formatted_history = []
    for order in trading_history:
        fee = order.get('fee') or {}
        amount = order.get('amount') or 0
        formatted_history.append({
            'id': order.get('id'),
            'exchange': order.get('exchange'),
            'timestamp': order.get('timestamp'),
            'order_type': order.get('type'),
            'side': 'Buy' if amount >= 0 else 'Sell',
            'currency': order.get('currency'),
            'symbol': order.get('symbol'),
            'amount': abs(amount),
            'fee': fee.get('cost') if fee.get('cost') is not None else "-",
            'feeCcy': fee.get('currency') or "-",
        })

    if request.method == 'POST':
        return Response(json.dumps(formatted_history, indent=4, default=str), content_type='application/json')
    return render_template("history_trading.html",
                                trading_history=formatted_history,
                                not_supported_trading_history=list(dict.fromkeys(not_supported_trading_history)),
                                **nav_context(current_user),
                            )

@app.route('/api/v1/history/positions_history/', methods=['GET', 'POST'])
@jwt_required
def history_positions_history():
    current_user = get_current_user()
    missing = _require_exchange(current_user)
    if missing is not None:
        return missing
    exchange = connectExchange()
    positions_history = []
    if _has(exchange, 'fetchPositions'):
        try:
            positions_history = list(exchange.fetch_positions())[::-1]
        except Exception as e:
            print(f"fetch_positions failed: {e}")

    # Pagination parameters
    page = max(1, int(request.args.get('page', 1)))
    items_per_page = 20  # Number of items to display per page
    start_index = (page - 1) * items_per_page
    paginated_history = positions_history[start_index:start_index + items_per_page]
    if request.method == 'POST':
        return Response(json.dumps(positions_history, indent=4, default=str), content_type='application/json')
    total_pages = (len(positions_history) + items_per_page - 1) // items_per_page
    return render_template("history_positions.html", positions_history=paginated_history, total_pages=total_pages,
                           current_page=page, **nav_context(current_user))

@app.route('/api/v1/history/funding_history/', methods=['GET','POST'])
@jwt_required
def history_funding_history():
    current_user = get_current_user()
    missing = _require_exchange(current_user)
    if missing is not None:
        return missing
    exchange = connectExchange()
    transfers = []
    if _has(exchange, 'fetchTransfers'):
        try:
            transfers = list(exchange.fetch_transfers())[::-1]
        except Exception as e:
            print(f"fetch_transfers failed: {e}")

    formatted_transfers = []
    for order in transfers:
        try:
            amount = round(float(order.get('amount') or 0),4)
        except (TypeError, ValueError):
            amount = 0
        formatted_transfers.append({
            'id': order.get('id'),
            'amount': amount,
            'currency': order.get('currency'),
            'from': 'spot' if order.get('fromAccount')=='trading' else order.get('fromAccount'),
            'to': 'spot' if order.get('toAccount')=='trading' else order.get('toAccount'),
            'timestamp': order.get('timestamp'),
            'status': order.get('status'),
        })

    if request.method == 'POST':
        return Response(json.dumps(transfers, default=str), content_type='application/json')
    return render_template("history_funding.html", transfers=formatted_transfers, **nav_context(current_user))
