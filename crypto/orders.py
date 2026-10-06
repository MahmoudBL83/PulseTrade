import json
from flask import render_template, request, redirect, url_for, jsonify,Response
import ccxt
from flask_login import login_required,current_user
from crypto import app, db, jwt_required
from crypto.models import Exchange,Post,Transaction
from crypto.notify import send_notification
from crypto.exchanges import connectExchange

@app.route('/api/v1/order/', methods=['POST'])
@jwt_required
def place_order():
    '''
    This function is used to place an order on the exchange.
    Params:
        symbol: the symbol of the order
        type: the type of the order (limit or market)
        order_price: the price of the order
        trigger_price: the trigger price for conditional orders
        amount: the amount of the order
        side: the side of the order (buy or sell)
    '''
    exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    
    # Instantiate the exchange API client using the provided API credentials
    exchange = connectExchange(exchange_name)
    
    try:
        # Parse the order parameters from the request body
        symbol = str(request.json['symbol']).upper()
        order_type = str(request.json['type']).lower()
        if request.json['order_price']:
            order_price = float(request.json['order_price'])
        else:
            order_price = 0
        amount = float(request.json['amount'])
        side = str(request.json['side']).lower()

        # Place the order on the exchange and return the order details as a JSON object
        if order_type == 'limit':
            buy_trade = exchange.create_order(symbol, order_type, side, amount, order_price)
            send_notification(f'Quick buy Finished on {exchange_name} for {symbol} with {order_price * amount} {symbol.split("/")[1]} ***Limit Buy Order')
        elif order_type == 'market':
            buy_trade = exchange.create_order(symbol, order_type, side, amount)
            buy_trade_price = exchange.fetch_order(buy_trade["id"], symbol=symbol)["price"]
            send_notification(f'Quick {side} finished on {exchange_name} for {symbol} with {buy_trade_price * amount} {symbol.split("/")[1]} ***Market {side} Order')
        elif order_type == 'cond.limit':
            buy_trade = exchange.create_order(symbol, 'limit', side, amount, order_price, params={
                'triggerPrice': float(request.json['trigger_price']),
            })
            send_notification(f'Trigger Quick {side} order started on {exchange_name} for {symbol} with {float(request.json["trigger_price"]) * amount} {symbol.split("/")[1]} ***Conditional Limit {side} Order')
            current_user.append_to_open_orders([buy_trade['id'], symbol,'Trigger Buy'])
        elif order_type == 'cond.market':
            buy_trade = exchange.create_order(symbol, 'market', side, amount, params={
                'triggerPrice': float(request.json['trigger_price']),
            })
            send_notification(f'Trigger Quick {side} order started on {exchange_name} for {symbol} with {float(request.json["trigger_price"]) * amount} {symbol.split("/")[1]} ***Conditional Market {side} Order')
            current_user.append_to_open_orders([buy_trade['id'], symbol,'Trigger Sell'])

        db.session.add(Transaction(user_id=current_user.id,exchange=exchange_name,symbol=symbol,type=side,amount=amount,value=order_price))
        db.session.commit()
        return jsonify({'message': 'The operation was successful', 'ok': True, 'order': buy_trade})
    
    except ccxt.InvalidOrder as e:
        return jsonify({'message': str(e), 'ok': False})
    
    except ccxt.DDoSProtection as e:
        return jsonify({'message': 'DDoS protection error: ' + str(e), 'ok': False})
    
    except ccxt.ExchangeError as e:
        return jsonify({'message': 'Exchange error: ' + str(e), 'ok': False})
    
    except ccxt.AuthenticationError as e:
        return jsonify({'message': 'Authentication error: ' + str(e), 'ok': False})
    
    except ccxt.NetworkError as e:
        return jsonify({'message': 'Network error: ' + str(e), 'ok': False})
    
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
    '''
    id = request.json['id']
    exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    symbol = request.json['symbol']
    exchange = connectExchange(exchange_name)
    try:
        order = exchange.cancel_order(id,symbol=symbol, params = {"stop":True})
        return jsonify({'message': f'the order with id {id} has been cancelled','ok':True,'order': order})
    except ccxt.InvalidOrder:
        return jsonify({'message': 'the canel operation failed','ok':False})

#############################################---------------HISTORY-START-------------#############################################

@app.route('/api/v1/history/open_orders/', methods=['GET','POST'])
@jwt_required
def history_open_orders():
    # Instantiate the exchange API client using the provided API credentials
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        #return jsonify('message','No active exchange found')
        return redirect(url_for('exchanges'))
    formatted_history = []
    open_orders = []
    limit_market_orders = []
    trigger_orders_all = []
    limit_market_orders_all = []
    not_supported_open_orders = []
    for exchange_user in current_user.exchanges:
        open_ords = []
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
        #exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
        #exchange = connectExchange(exchange_name)
        
        #open_orders = exchange.fetch_open_orders(params = {"stop":True,"ordType":"conditional"})
        try:
            if 'fetchOpenOrders' in exchangeNow.describe()['has']:
                if exchangeNow.describe()['has']['fetchOpenOrders']:
                    limit_market_orders = exchangeNow.fetch_open_orders()
                    limit_market_orders += exchangeNow.fetch_open_orders(params = {"stop":True,"ordType":"limit"})
                    limit_market_orders += exchangeNow.fetch_open_orders(params = {"stop":True,"ordType":"market"})
                    trigger_orders = exchangeNow.fetch_open_orders(params = {"stop":True,"ordType":"trigger"})
                    trigger_orders_all += trigger_orders
                    limit_market_orders_all += limit_market_orders
                    #conditional_orders = exchange.fetch_open_orders(params = {"stop":True,"ordType":"conditional"})
                    
                    open_ords += limit_market_orders
                    open_ords += trigger_orders
                    #open_orders += conditional_orders
                    
                    x_ords = []
                    for x in open_ords:
                        if x['id'] in x_ords:
                            open_ords.remove(x)
                        else:
                            x_ords.append(x['id'])

                    for x in open_ords:
                        x['exchange'] = exchange_user.name
                    
                    open_orders += open_ords
                else:
                    not_supported_open_orders.append(exchange_user.name)
            else:
                not_supported_open_orders.append(exchange_user.name)
        except:
            not_supported_open_orders.append(exchange_user.name)

    open_orders = sorted(open_orders, key = lambda i: i['timestamp'],reverse=True)
    mormal_count = len(limit_market_orders_all)
    trigger_count = len(trigger_orders_all)
    #conditional_count = len(conditional_orders)

    '''page = int(request.args.get('page', 1))  # Get the current page number from the request query parameters
    items_per_page = 20  # Number of items to display per page
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page'''
    
    for order in open_orders:
        formatted_open_order = {
            'id': order['id'],
            'exchange': order['exchange'],
            'symbol': order['symbol'],
            'filled_amount': order['filled'] if order['filled'] else 0,
            'order_type': order['type'],
            'total_amount': order['amount'],
            'remaining_amount': order['remaining'],
            'cost': order['cost'],
            'trigger_price': str(order['triggerPrice'] if order['triggerPrice'] else (order['stopLossPrice'] if order['stopLossPrice'] else order['takeProfitPrice'])) + " " + order['symbol'].split("/")[1] if order['triggerPrice'] or order['stopLossPrice'] or order['takeProfitPrice']  else "--",
            'order_price': str(order['price']) + " " + order['symbol'].split("/")[1] if order['price'] and order['price'] != -1 else "market",
            'side': order['side'],
            #'tp': order['takeProfitPrice'],
            #'sl': order['stopLossPrice'],
            'status': order['status'],
            'time': order['timestamp'],
            'reduceOnly': order['reduceOnly'],
            #'instrument': order['info']['instId'],
            #'instType': order['info']['instType'],
        }
        formatted_history.append(formatted_open_order)
    #paginated_history = formatted_history[start_index:end_index]

    x_ords = []
    for x in not_supported_open_orders:
        if x in x_ords:
            not_supported_open_orders.remove(x)
        else:
            x_ords.append(x)

    if request.method == 'POST':
        formatted_history_json = json.dumps(formatted_history, indent=4)
        return Response(formatted_history_json, content_type='application/json')
    else:
        #total_pages = (len(open_orders) + items_per_page - 1) // items_per_page
        return render_template("history_open_orders.html",
                                    notifications=current_user.notifications.all(),
                                    exchanges=current_user.exchanges.all(),
                                    orders=formatted_history,
                                    #total_pages=total_pages,
                                    #current_page=page,
                                    current_user=current_user,
                                    posts = Post.query.all(),
                                    mormal_count=mormal_count,
                                    trigger_count=trigger_count,
                                    #conditional_count=conditional_count,
                                    not_supported_open_orders=not_supported_open_orders,
                                ) 

@app.route('/api/v1/history/orders/', methods=['GET','POST'])
@jwt_required
def history_orders():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    '''exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    exchange = connectExchange(exchange_name)'''
    history_orders = []
    not_supported_closed_orders = []
    history_cancelled_orders = []
    history_closed_orders = []
    for exchange_user in current_user.exchanges.all():
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

        history_orders2 = []
        history_closed_orders2 = []
        history_cancelled_orders2 = []
        

        if 'fetchClosedOrders' in exchangeNow.describe()['has']:
            try:
                if exchangeNow.describe()['has']['fetchClosedOrders']:
                    history_closed_orders2 = []
                    history_closed_orders += exchangeNow.fetch_closed_orders()
                    history_closed_orders2 += exchangeNow.fetch_closed_orders()
                else:
                    not_supported_closed_orders.append(exchange_user.name)
            except:
                not_supported_closed_orders.append(exchange_user.name)
        else:
            not_supported_closed_orders.append(exchange_user.name)

        if 'fetchCanceledOrders' in exchangeNow.describe()['has']:
            try:
                if exchangeNow.describe()['has']['fetchCanceledOrders']:
                    history_cancelled_orders2 = []
                    history_cancelled_orders += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"limit"})
                    history_cancelled_orders += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"market"})
                    history_cancelled_orders += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"trigger"})
                    history_cancelled_orders2 += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"limit"})
                    history_cancelled_orders2 += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"market"})
                    history_cancelled_orders2 += exchangeNow.fetch_canceled_orders(params = {"stop":True,"ordType":"trigger"})
                else:
                    not_supported_closed_orders.append(exchange_user.name)
            except:
                not_supported_closed_orders.append(exchange_user.name)
        else:
            not_supported_closed_orders.append(exchange_user.name)
        history_orders2 = history_cancelled_orders2 + history_closed_orders2

        for x in history_orders2:
            x['exchange'] = exchange_user.name

        x_ords = []
        for x in not_supported_closed_orders:
            if x in x_ords:
                not_supported_closed_orders.remove(x)
            else:
                x_ords.append(x)

        history_orders += history_orders2

    history_orders = sorted(history_orders, key = lambda i: i['timestamp'],reverse=True)

    closed_count = len(history_closed_orders)
    cancelled_count = len(history_cancelled_orders)


    # Pagination parameters
    '''page = int(request.args.get('page', 1))  # Get the current page number from the request query parameters
    items_per_page = 20  # Number of items to display per page
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page'''
    formatted_history = []
    for order in history_orders:
        formatted_order = {
            'id': order['id'],
            'exchange': order['exchange'],
            'timestamp': order['timestamp'],
            'datetime': order['datetime'],
            'side': order['side'],
            'order_type': order['type'],
            #'fillPx': order['info']['fillPx'],
            #'px': order['info']['px'] if order['info']['px'] else "market",
            #'fillSz': order['info']['fillSz'],
            #'sz': order['info']['sz'],
            'reduceOnly': order['reduceOnly'],
            #'remaining': order['remaining'],
            'stopLossPrice': order['stopLossPrice'],
            'stopPrice': order['stopPrice'],
            'takeProfitPrice': order['takeProfitPrice'],
            'trigger_price': (str(order['triggerPrice'] if order['triggerPrice'] else (order['stopLossPrice'] if order['stopLossPrice'] else order['takeProfitPrice']))+ " " + order['symbol'].split("/")[1]) if order['triggerPrice'] or order['stopLossPrice'] or order['takeProfitPrice'] else "--",
            'order_price': str(order['price'] if order['price']>=0 else "market")+ " " + order['symbol'].split("/")[1] if order['price'] else "market",
            'status': order['status'],
            'symbol': order['symbol'],
            'amount': str(abs(order['amount'] or 0))+ " " + (order['symbol'].split("/")[0] if order['side'].lower() == "sell" else order['symbol'].split("/")[0]),
            #'average': order['average'],
            #'cost': order['cost'],
            'fee': str(order['fee']['cost']) + " " + order["fee"]["currency"] if order['fee'] else 0,
            #'currency1': order['symbol'].split('/')[0],
            #'currency2':order['symbol'].split('/')[1],
            #'filled':order['filled'],
            #'filled_cost':order['cost'],
        }
        formatted_history.append(formatted_order)


    
    #paginated_history = formatted_history[start_index:end_index]
    if request.method == 'POST':
        formatted_history_json = json.dumps(formatted_history, indent=4)
        return Response(formatted_history_json, content_type='application/json')
    else:
        #total_pages = (len(history_orders) + items_per_page - 1) // items_per_page
        return render_template("history_orders.html",
                                    exchanges=current_user.exchanges.all(),
                                    notifications=current_user.notifications.all(), 
                                    orders=formatted_history,
                                    #total_pages=total_pages,
                                    #current_page=page,
                                    current_user=current_user,
                                    posts = Post.query.all(),
                                    closed_count=closed_count,
                                    cancelled_count=cancelled_count,
                                    not_supported_closed_orders=not_supported_closed_orders,
                                 )  

@app.route('/api/v1/history/trades/', methods=['GET', 'POST'])
@jwt_required
def history_trades_history():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    '''exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    exchange = connectExchange(exchange_name)

    if exchange.describe()['has']['fetchLedger']:
        trading_history = exchange.fetch_ledger()[::-1]
    else:
        trading_history = []'''
    open_orders = []
    not_supported_trading_history = []
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
        ledgers = []
        if exchange_user.demo:
            exchangeNow.set_sandbox_mode(True)
        if 'fetchLedger' in exchangeNow.describe()['has']:
            try:
                if exchangeNow.describe()['has']['fetchLedger']:
                    ledgers = exchangeNow.fetch_ledger(params = {"stop":True,"ordType":"trigger"})
                else:
                    not_supported_trading_history.append(exchange_user.name)
            except:
                not_supported_trading_history.append(exchange_user.name)
        else:
            not_supported_trading_history.append(exchange_user.name)
        
        for x in ledgers:
            x['exchange'] = exchange_user.name

        open_orders += ledgers

    trading_history = sorted(open_orders, key = lambda i: i['timestamp'],reverse=True)

    formatted_history = []
    for order in trading_history:
        formatted_order = {
            'id': order['id'],
            'exchange': order['exchange'],
            'timestamp': order['timestamp'],
            'order_type': order['type'],
            'side': 'Buy' if order['amount'] >= 0 else 'Sell',
            'currency': order['currency'],
            'symbol': order['symbol'],
            'amount': abs(order['amount']),
            'fee': order['fee']['cost'] if order['fee'] else "-",
            'feeCcy':order['fee']['currency'] if order['fee'] else "-",
        }
        formatted_history.append(formatted_order)

    x_ords = []
    for x in not_supported_trading_history:
        if x in x_ords:
            not_supported_trading_history.remove(x)
        else:
            x_ords.append(x)

    if request.method == 'POST':
        formatted_history_json = json.dumps(formatted_history, indent=4)
        return Response(formatted_history_json, content_type='application/json')
    else:
        return render_template("history_trading.html",
                                    exchanges=current_user.exchanges.all(),
                                    trading_history=formatted_history,
                                    current_user=current_user,
                                    posts = Post.query.all(),
                                    notifications=current_user.notifications.all(),
                                    not_supported_trading_history=not_supported_trading_history,
                                )  

@app.route('/api/v1/history/positions_history/', methods=['GET', 'POST'])
@jwt_required
def history_positions_history():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    exchange = connectExchange(exchange_name)

    if exchange.describe()['has']['fetchPositions']:
        positions_history = exchange.fetch_positions()[::-1]
        ()[::-1]
    else:
        positions_history = []

    # Pagination parameters
    page = int(request.args.get('page', 1))  # Get the current page number from the request query parameters
    items_per_page = 20  # Number of items to display per page
    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page
    paginated_history = positions_history[start_index:end_index]
    if request.method == 'POST':
        formatted_history_json = json.dumps(positions_history, indent=4)
        return Response(formatted_history_json, content_type='application/json')
    else:
        total_pages = (len(positions_history) + items_per_page - 1) // items_per_page
        return render_template("history_positions.html",exchanges=current_user.exchanges.all(), positions_history=paginated_history, total_pages=total_pages, current_page=page,current_user=current_user,posts = Post.query.all())  

@app.route('/api/v1/history/funding_history/', methods=['GET','POST'])
@jwt_required
def history_funding_history():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    exchange_name = current_user.exchanges.filter(Exchange.isActive==True).first().name
    exchange = connectExchange(exchange_name)

    transfers = exchange.fetch_transfers()[::-1]

    formatted_transfers = []
    for order in transfers:
        formatted_transfer = {
            'id': order['id'],
            'amount': round(float(order['amount']),4),
            'currency': order['currency'],
            'from': 'spot' if order['fromAccount']=='trading' else order['fromAccount'],
            'to': 'spot' if order['toAccount']=='trading' else order['toAccount'],
            'timestamp': order['timestamp'],
            'status': order['status'],
            #'type': 'Transfer out' if order['fromAccount']=='funding' else 'Transfer in',
        }
        if order['toAccount'] == 'funding' or order['fromAccount'] == 'funding' or True:
            formatted_transfers.append(formatted_transfer)

    if request.method == 'POST':
        return jsonify(transfers)
    else:
        return render_template("history_funding.html",
                                    exchanges=current_user.exchanges.all(),
                                    transfers=formatted_transfers,
                                    current_user=current_user,
                                    posts = Post.query.all(),
                                    notifications=current_user.notifications.all(),
                               )