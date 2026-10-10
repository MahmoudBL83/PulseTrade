from flask import render_template, request, redirect, url_for, jsonify
import ccxt
from crypto import app, db,jwt_required, get_current_user
from crypto.models import Exchange, Post, Transaction
from crypto.notify import send_notification
from crypto.exchanges import connectExchange, nav_context
from crypto.cache import TTLCache
from crypto import market

_meta_cache = TTLCache(ttl=600)


def _body():
    return request.get_json(silent=True) or {}


def _has(exchange, feature):
    try:
        return bool(exchange.describe()['has'].get(feature))
    except Exception:
        return False


def _unsupported(user):
    return render_template('404.html', **nav_context(user)), 404


def _active_name(user):
    row = user.exchanges.filter(Exchange.isActive == True).first() or user.exchanges.first()
    return row.name if row else None


def _cached(key, fn):
    hit = _meta_cache.get(key)
    if hit is None:
        hit = _meta_cache.set(key, fn())
    return hit


@app.route('/api/v1/deposit/', methods=['POST','GET'])
@jwt_required
def crypto_deposit():
    '''
        function for making deposit to exchange
        the parameters are:
        symbol: the symbol of the coin to deposit
        network: the network of the coin to deposit
        the response is:
        {
            "message": "successful deposit",
            "ok": true,
            "deposit": deposit
        }
        deposit is the response from the exchange
    '''
    current_user = get_current_user()
    exchange = connectExchange()
    exchange_name = _active_name(current_user)
    if request.method == 'POST':
        try:
            body = _body()
            symbol = body['symbol']
            network = body.get('network')
            if not _has(exchange, 'fetchDepositAddress'):
                return jsonify({'message': 'Depsoit is not possible', 'ok': False})
            # Initiate deposit with exchange
            deposit = exchange.fetch_deposit_address(symbol, {'network': network} if network else {})
            return jsonify({'message':f"Send only {symbol} to this address {deposit['address']}",
                            'ok':True,
                            'address':deposit['address'],
                            'tag':deposit.get('tag'),
                            'network': deposit.get('network') or network,
                            })
        except ccxt.InsufficientFunds as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Insufficient funds. {str(e)}', 'ok': False})
        except ccxt.InvalidOrder as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Invalid order. {str(e)}', 'ok': False})
        except ccxt.NetworkError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Network error. {str(e)}', 'ok': False})
        except ccxt.ExchangeError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: Exchange error. {str(e)}', 'ok': False})
        except ccxt.BaseError as e:
            return jsonify({'message': f'Error Depositing order on {exchange_name}: {str(e)}', 'ok': False})

    if not _has(exchange, 'fetchDepositAddress'):
        return _unsupported(current_user)
    try:
        deposits = exchange.fetch_deposits() if _has(exchange, 'fetchDeposits') else []
    except Exception as e:
        print(f"fetch_deposits failed: {e}")
        deposits = []
    return render_template('deposit.html', deposits=deposits, **nav_context(current_user))

#get all deposits history
@app.route('/api/v1/deposits/', methods=['POST','GET'])
@jwt_required
def crypto_deposits():
    '''
    the deposits are returned in the following format:
    [
        {
            "info": {
                "currency": "BTC",
                "amount": "0.0001",
                "txid": "5f7a0a9c03aa675e4a06f5b0",
                "address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "addressTo": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "type": "withdrawal",
                "timestamp": "1601817600000",
                "status": "success"
            },
        }
    ]
    '''
    exchange = connectExchange()
    if not _has(exchange, 'fetchDeposits'):
        return jsonify([])
    try:
        return jsonify(exchange.fetch_deposits())
    except ccxt.BaseError as e:
        return jsonify({'message': str(e), 'ok': False}), 502

@app.route('/api/v1/transfer/', methods=['POST', 'GET'])
@jwt_required
def crypto_transfer():
    '''
        function for making transfer between spot and funding
        the parameters are:
        amount: the amount to transfer
        side: the side of the transfer (funding or spot)
        symbol: the symbol of the coin to transfer
    '''
    current_user = get_current_user()
    exchange = connectExchange()
    exchange_name = _active_name(current_user)
    if request.method == 'POST':
        body = _body()
        try:
            amount = float(body['amount'])
        except (KeyError, TypeError, ValueError):
            return jsonify({'message': 'Invalid amount', 'ok': False}), 400
        if not (amount > 0):
            return jsonify({'message': 'Amount must be positive', 'ok': False}), 400
        side = body.get('side') or ''
        symbol = body.get('symbol') or ''
        if side not in ('funding', 'spot'):
            return jsonify({'message': f'Invalid side: {side}', 'ok': False}), 400
        if not symbol or '/' in str(symbol):
            return jsonify({'message': f'Invalid symbol: {symbol}', 'ok': False}), 400
        if not _has(exchange, 'transfer'):
            return jsonify({'message': f'{exchange_name} does not support internal transfers', 'ok': False}), 400

        try:
            if side == 'funding':
                result = exchange.transfer(symbol, amount,"spot", "funding")
                send_notification(f'Transfer completed on {exchange_name} for {amount} {symbol} from spot to funding***Transfer')
            else:
                result = exchange.transfer(symbol, amount, "funding","spot")
                send_notification(f'Transfer completed on {exchange_name} for {amount} {symbol} from funding to spot***Transfer')
            if result.get('id'):
                return jsonify({'message': f'Transfer successful. ID: {result["id"]}','ok':True})
            return jsonify({'message': 'Transfer failed', 'ok': False})
        except ccxt.BaseError as e:
            return jsonify({'message': str(e), 'ok': False})

    if not _has(exchange, 'transfer'):
        return _unsupported(current_user)
    formatted_transfers = []
    try:
        for order in (exchange.fetch_transfers() if _has(exchange, 'fetchTransfers') else [])[::-1]:
            formatted_transfers.append({
                'id': order.get('id'),
                'amount': round(float(order.get('amount') or 0),4),
                'currency': order.get('currency'),
                'from': 'spot' if order.get('fromAccount')=='trading' else order.get('fromAccount'),
                'to': 'spot' if order.get('toAccount')=='trading' else order.get('toAccount'),
                'timestamp': order.get('timestamp'),
            })
    except Exception as e:
        print(f"fetch_transfers failed: {e}")
    return render_template('transfer.html', transfers=formatted_transfers, **nav_context(current_user))

@app.route('/api/v1/convert/', methods=['POST','GET'])
@jwt_required
def crypto_convert():
    current_user = get_current_user()
    exchange = connectExchange()
    exchange_name = _active_name(current_user)

    if request.method == 'POST':
        body = _body()
        try:
            # Extract the parameters from the JSON request
            amount = float(body['amount'])
            if not (amount > 0):
                return jsonify({'message': 'Amount must be positive', 'ok': False}), 400
            order_type = body['order_type']
            source_asset = str(body['source_asset']).upper()
            target_asset = str(body['target_asset']).upper()
            if not source_asset or not target_asset or source_asset == target_asset:
                return jsonify({'message': 'Invalid asset pair', 'ok': False}), 400
            side = str(body['side'])
            if side not in ('1', '0', 'buy', 'sell'):
                return jsonify({'message': f'Invalid side: {side}', 'ok': False}), 400
            selling = side in ('1', 'sell')
            order_side = 'sell' if selling else 'buy'
            symbol = f"{source_asset}/{target_asset}"

            if not _has(exchange, 'createOrder'):
                return jsonify({'message': f"{exchange_name} does not support the {symbol} trading pair.", 'ok': False})
            if order_type == 'market':
                order = exchange.create_order(symbol, 'market', order_side, amount)
                try:
                    fetched = exchange.fetch_order(order['id'], symbol=symbol)
                    fill = float(fetched.get('average') or fetched.get('price') or 0)
                except Exception:
                    fill = float(order.get('average') or order.get('price') or 0)
                db.session.add(Transaction(user_id=current_user.id,exchange=exchange_name,symbol=symbol,type=order_side,amount=amount,value=fill))
                db.session.commit()
                if selling:
                    send_notification(f'Conversion completed on {exchange_name} to convert {amount} {source_asset} to {fill*amount} {target_asset}***Convert')
                else:
                    send_notification(f'Conversion completed on {exchange_name} to convert {fill*amount} {target_asset} to {amount} {source_asset}***Convert')
            elif order_type == 'limit':
                price = float(body['price'])
                if not (price > 0):
                    return jsonify({'message': 'Limit orders require a positive price', 'ok': False}), 400
                order = exchange.create_order(symbol, 'limit', order_side, amount, price)
                if selling:
                    send_notification(f'Conversion started on {exchange_name} to convert {amount} {source_asset} to {price*amount} {target_asset}***Convert')
                else:
                    send_notification(f'Conversion started on {exchange_name} to convert {price*amount} {target_asset} to {amount} {source_asset}***Convert')
                current_user.append_to_open_orders([order['id'], symbol,'convert'])
                db.session.commit()
            else:
                return jsonify({'message': 'Invalid order type. Supported types: market, limit.', 'ok': False})
            return jsonify({'message': f"Conversion order created on {exchange_name}.",'ok':True, 'order': order})
        except ccxt.InsufficientFunds as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Insufficient funds. {str(e)}', 'ok': False})
        except ccxt.InvalidOrder as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Invalid order. {str(e)}', 'ok': False})
        except ccxt.NetworkError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Network error. {str(e)}', 'ok': False})
        except ccxt.ExchangeError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: Exchange error. {str(e)}', 'ok': False})
        except ccxt.BaseError as e:
            return jsonify({'message': f'Error creating order on {exchange_name}: {str(e)}', 'ok': False})

    try:
        pairs = [m['symbol'] for m in exchange.fetch_markets() if m.get('active', True) and m.get('spot')]
    except Exception as e:
        print(f"convert page markets unavailable: {e}")
        pairs = market.symbols(exchange_name)
    return render_template('convert.html', pairs=pairs, **nav_context(current_user))


@app.route('/api/v1/withdraw/', methods=['POST','GET'])
@jwt_required
def crypto_withdraw():
    current_user = get_current_user()
    exchange = connectExchange()
    exchange_name = _active_name(current_user)
    if request.method == 'POST':
        body = _body()
        try:
            amount = float(body['amount'])
            if not (amount > 0):
                return jsonify({'message': 'Amount must be positive', 'ok': False}), 400
            recipient_address = (body.get('recipient_address') or '').strip()
            if not recipient_address:
                return jsonify({'message': 'Recipient address is required', 'ok': False}), 400
            currency = body['currency']
            network_user = body.get('network')
            if not _has(exchange, 'withdraw'):
                return jsonify({'message': 'Withdraw is not possible', 'ok': False})
            params = {'network': network_user} if network_user else {}
            response = exchange.withdraw(currency, amount, recipient_address, body.get('tag'), params)
            info = response.get('info') if isinstance(response, dict) else None
            if isinstance(info, dict) and info.get('status') == '0':
                return jsonify({"message": "User identity verification is required for this withdrawal", 'ok': False}), 400
            if isinstance(response, dict) and response.get('error'):
                return jsonify({"message": response['error'], 'ok': False}), 400
            send_notification(f'Withdraw completed on {exchange_name} for {amount} {currency}***Withdraw')
            return jsonify({"message": "withdraw done",'ok':True})
        except ccxt.NetworkError as e:
            return jsonify({"message": f"Network error: {str(e)}", 'ok': False}), 502
        except ccxt.BaseError as e:
            return jsonify({"message": f"Exchange error: {str(e)}", 'ok': False}), 400
    if not _has(exchange, 'withdraw'):
        return _unsupported(current_user)
    try:
        withdrawals = exchange.fetch_withdrawals() if _has(exchange, 'fetchWithdrawals') else []
    except Exception as e:
        print(f"fetch_withdrawals failed: {e}")
        withdrawals = []
    return render_template('withdraw.html', withdrawals=withdrawals, **nav_context(current_user))

#get all withdrawals history
@app.route('/api/v1/withdrawals/', methods=['POST','GET'])
@jwt_required
def crypto_withdrawals():
    '''
    the withdrawals are returned in the following format:
    [
        {
            "info": {
                "currency": "BTC",
                "amount": "0.0001",
                "txid": "5f7a0a9c03aa675e4a06f5b0",
                "address": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "addressTo": "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
                "type": "withdrawal",
                "timestamp": "1601817600000",
                "status": "success"
            },
        }
    ]
    '''
    exchange = connectExchange()
    if not _has(exchange, 'fetchWithdrawals'):
        return jsonify([])
    try:
        return jsonify(exchange.fetch_withdrawals())
    except ccxt.BaseError as e:
        return jsonify({'message': str(e), 'ok': False}), 502

@app.route('/api/v1/precision/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_precision(exchange_name):
    symbol = _body().get('symbol') or request.args.get('symbol')
    if not symbol:
        return jsonify({'message': 'Missing field: symbol', 'ok': False}), 400
    exchange = connectExchange(exchange_name)
    try:
        exchange.load_markets()
        precision = exchange.market(symbol).get('precision') or {}
    except Exception as e:
        return jsonify({'message': f'Unknown market {symbol}: {e}', 'ok': False}), 400
    return jsonify({'amount':precision.get('amount'),'price':precision.get('price')})


@app.route('/api/v1/currencies/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_currencies(exchange_name):
    '''
    the currencies are returned as a list of ccxt currency structures:
    {"code": "ETHW", "name": "ETHW", "deposit": true, "withdraw": true, "fee": 0.01,
     "networks": {...}, "limits": {...}, "precision": 1e-8, ...}
    '''
    exchange = connectExchange(exchange_name)
    try:
        currencies = _cached(("currencies", exchange_name, getattr(exchange, 'user_id', None) or 0), exchange.fetch_currencies)
    except Exception as e:
        print(f"fetch_currencies failed: {e}")
        currencies = None
    if not currencies:
        return jsonify([])
    return jsonify(list(currencies.values()))

@app.route('/api/v1/fees', methods=['POST','GET'])
@jwt_required
def get_fees():
    code = request.args.get('code') or _body().get('code')
    if not code:
        return jsonify({'message': 'Missing field: code', 'ok': False}), 400
    exchange = connectExchange()
    try:
        return jsonify(exchange.fetch_deposit_withdraw_fees([code]))
    except Exception as e:
        return jsonify({'message': f'Fees unavailable: {e}', 'ok': False}), 502


def _markets(exchange_name):
    exchange = connectExchange(exchange_name)
    try:
        return exchange.fetch_markets() or []
    except Exception as e:
        print(f"fetch_markets failed: {e}")
        return [{"symbol": s, "base": s.split("/")[0], "quote": s.split("/")[1], "spot": True, "active": True}
                for s in market.symbols(exchange_name)]


@app.route('/api/v1/markets/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_markets(exchange_name):
    '''
    the markets are returned in the following format:
    {
        "base": {"1INCH": "1INCH", "1SOL": "1SOL", ...},
        "quote": {"BRZ": "BRZ", "BTC": "BTC", ...}
    }
    '''
    currencies = _markets(exchange_name)
    return jsonify({"base": {c["base"]: c["base"] for c in currencies if c.get("base")},
                    "quote": {c["quote"]: c["quote"] for c in currencies if c.get("quote")}})

@app.route('/api/v1/all_markets/<exchange_name>', methods=['POST','GET'])
@jwt_required
def get_all_markets(exchange_name):
    return jsonify([c['symbol'] for c in _markets(exchange_name) if c.get('active', True) and c.get('spot')])
