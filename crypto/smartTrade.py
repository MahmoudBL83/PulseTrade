from flask import render_template, request, redirect, url_for, jsonify,Response,jsonify
import ccxt
from flask_login import login_required,current_user
from crypto import app,db,celery,jwt_required
from crypto.models import User, Exchange, SmartTrade,Post, Transaction, Pair
from crypto.notify import send_notification
from search_crypto import search
from crypto.exchanges import connectExchange
from time import sleep
from crypto.functions import getPrice,getPrice_assets
import time
from datetime import datetime
import json

@app.route('/trade/')
@jwt_required
def trade():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    exchange = connectExchange()
    pairs = []
    try:
        time.sleep(exchange.describe()['rateLimit'] / 1000)
        for currency in exchange.fetch_markets():
            if currency['active'] and currency['spot']:
                pairs.append(currency['symbol'])
    except Exception as e:
        print(e)

    return render_template('trade.html',
                                notifications=current_user.notifications.all(),
                                exchanges = current_user.exchanges.all(),
                                symbol=request.args.get('symbol'),
                                exchange=request.args.get('exchange'),
                                current_user=current_user,
                                pairs=pairs,
                                posts = Post.query.all()
                           )

@app.route('/api/v1/smart_trades/', methods=['GET'])
def get_smart_trades():
    # Retrieve all smart trades for the current user
    smart_trades = SmartTrade.query.filter_by(user_id=current_user.id).all()

    # Serialize the smart trades to JSON format
    serialized_smart_trades = [smart_trade.serialize() for smart_trade in smart_trades]

    # Return the serialized smart trades as a JSON response
    return jsonify(smart_trades=serialized_smart_trades)

@app.route('/api/v1/smart_trades/', methods=['POST'])
def create_smart_trade():
    if current_user.subType.max_sma:
        if int(current_user.subType.max_sma) <= len(SmartTrade.query.filter(SmartTrade.user_id==current_user.id).all()):
            return jsonify({'message':f"You have reached the maximum number of smart trades ({current_user.subType.max_sma}). Please upgrade your subscription to create more smart trades."})
    # Retrieve the trade parameters from the request
    trade_type = str(request.json['trade_type'])
    use_assets = request.json['use_assets']
    symbol = request.json['symbol']
    price = float(request.json['price'])
    triggerPrice = float(request.json['triggerPrice'])
    buy_type = request.json['buy_type']
    total_amount = float(request.json['amount'])
    take_profits = request.json['take_profits']
    tpTriggerType = request.json['tpTriggerType']
    stop_loss = request.json['stop_loss']
    take_profit = request.json['take_profit']
    stop_loss_type = request.json['stop_loss_type']
    if stop_loss:
        stop_loss_price_percent = float(request.json['stop_loss_price_percent'])
        stop_loss_trigger_price = float(request.json['stop_loss_trigger_price'])
    else:
        stop_loss_price_percent = 0
        stop_loss_trigger_price = 0
    trailing_take_profit = request.json['trailing_take_profit']
    trailing_stop_loss = request.json['trailing_stop_loss']
    trailing_deviation = float(request.json['trailing_deviation']) if request.json['trailing_deviation'] else 0
    stop_loss_time_out = request.json['stop_loss_time_out']
    stop_loss_time_out_time = int(request.json['stop_loss_time_out_time'])
    exchange_name = request.json['exchange']
    move_to_break_even = request.json['move_to_break_even']
    deal_started = False

    # Create an instance of the desired exchange
    exchange = connectExchange(exchange_name)

    buy_trade = None
    buy_trade_id = None
    units = None
    isActive = True
    err_msg = ""
    status = True
    try:
        # Place a smart trade (buy and sell with once)
        side = 'buy' if trade_type.lower()=='smart trade' else 'sell'
        if use_assets == False:
            if buy_type == 'limit' or buy_type == 'market':
                try:
                    buy_trade = exchange.create_order(symbol, buy_type, side, total_amount, price if buy_type == 'limit' else None)
                    
                    deal_started = True
                except Exception as e:
                    err_msg = str(e)
                    status = False
                    deal_started = False

                if not take_profit and not stop_loss:
                    units = 0
                    isActive = False

            else:
                buy_trade = None

            if (buy_type == 'limit' or buy_type == 'market') and buy_trade:
                buy_price = exchange.fetch_order(buy_trade['id'],symbol)['price']
                buy_trade_id = buy_trade['id']
                send_notification(f'{trade_type} has completed a Quick {side} on {exchange_name} for {symbol} with {round(total_amount * buy_price,2)} {symbol.split("/")[1]}***{buy_type} {trade_type} {side} Order')
            else:
                buy_price = 0
                send_notification(f'{trade_type} has failed to start a Quick {side} on {exchange_name} for {symbol} with {round(total_amount * price,2)} {symbol.split("/")[1]}***{buy_type} {trade_type} {side} Order')

        else:
            buy_price = price
            deal_started = True
        
        db.session.commit()

        # Create a new smart trade object with the parsed data
        smart_trade = SmartTrade(
            trade_type=trade_type,
            exchange=request.json['exchange'],
            base_currency=request.json['symbol'].split('/')[1],
            quote_currency=request.json['symbol'].split('/')[0],
            units=total_amount if units is None else units,
            amount=total_amount,
            user_id=current_user.id,
            buy_price=buy_price,
            buy_trigger_price=triggerPrice,
            stop_loss=stop_loss,
            take_profit=take_profit,
            take_profit_quantities=take_profits,
            tpTriggerType=tpTriggerType,
            order_type=buy_type,
            buy_order_id=buy_trade_id,
            trailing_order_id=0,
            trailing_take_profit=trailing_take_profit,
            trailing_deviation=trailing_deviation,
            trailing_stop_loss=trailing_stop_loss,
            stop_loss_price_percent=stop_loss_price_percent,
            stop_loss_price=stop_loss_trigger_price,
            stop_loss_type=stop_loss_type,
            stop_loss_time_out=stop_loss_time_out,
            stop_loss_time_out_time=stop_loss_time_out_time,
            deal_started=deal_started,
            move_to_break_even=move_to_break_even,
            isActive=isActive,
            last_price=0,
            bought_price=price,
            use_assets=use_assets,
        )

        if (buy_type == 'limit' or buy_type == 'market') and use_assets == False:
            trans = Transaction(user_id=current_user.id,
                err_msg=err_msg,
                status=status,
                exchange=exchange_name,
                symbol=symbol,
                type=side,
                amount=total_amount,
                value=buy_price
            )
            db.session.add(trans)
            smart_trade.transactions.append(trans)
                

        # Add the new smart trade to the database
        db.session.add(smart_trade)
        db.session.commit()

        return jsonify({'message':f"Smart Trade executed successfully.",'ok':True})
    except Exception as e:
        return jsonify({'message':f"Smart Trade failed {e}",'ok':False})



@app.route('/api/v1/smart_trades/edit/<int:smart_trade_id>', methods=['POST'])
def edit_smart_trade(smart_trade_id):
    # Get the smart trade from the database
    smart_trade = SmartTrade.query.get(smart_trade_id)

    # Retrieve the trade parameters from the request
    trade_type = str(request.json['trade_type'])
    price = float(request.json['price'])
    triggerPrice = float(request.json['triggerPrice'])
    buy_type = request.json['buy_type']
    total_amount = float(request.json['amount'])
    stop_loss = request.json['stop_loss']
    take_profit = request.json['take_profit']
    tpTriggerType = request.json['tpTriggerType']
    stop_loss_type = request.json['stop_loss_type']
    if stop_loss:
        stop_loss_trigger_price = float(request.json['stop_loss_trigger_price'])
        stop_loss_price_percent = float(request.json['stop_loss_price_percent'])
    else:
        stop_loss_trigger_price = 0
        stop_loss_price_percent = 0
    trailing_take_profit = request.json['trailing_take_profit']
    trailing_stop_loss = request.json['trailing_stop_loss']
    trailing_deviation = float(request.json['trailing_deviation'])
    stop_loss_time_out = request.json['stop_loss_time_out']
    stop_loss_time_out_time = int(request.json['stop_loss_time_out_time'])
    exchange_name = request.json['exchange']

    # Check if the smart trade exists
    if not smart_trade or smart_trade.user_id != current_user.id:
        return jsonify({'message': 'Smart trade not found or you do not have permission to edit it','ok':False})

    # Get the exchange from the smart trade
    exchange = connectExchange(exchange_name)

    # Cancel the smart trade on the exchange
    try:
        if smart_trade.buy_order_id:
            if exchange.fetch_order(smart_trade.buy_order_id,symbol=smart_trade.quote_currency+'/'+smart_trade.base_currency)['status'] == 'open':
                exchange.cancel_order(smart_trade.buy_order_id, symbol=smart_trade.quote_currency+'/'+smart_trade.base_currency)
                smart_trade.deal_started=False
                smart_trade.units=total_amount
                smart_trade.amount=total_amount
                smart_trade.buy_price=price
                smart_trade.buy_trigger_price=triggerPrice
                smart_trade.order_type=buy_type
        smart_trade.trade_type=trade_type
        smart_trade.take_profit_quantities=request.json['take_profits']
        smart_trade.tpTriggerType=tpTriggerType
        smart_trade.trailing_take_profit=trailing_take_profit
        smart_trade.stop_loss=request.json['stop_loss']
        smart_trade.trailing_stop_loss=trailing_stop_loss
        smart_trade.stop_loss_price_percent=stop_loss_price_percent
        smart_trade.stop_loss_price=stop_loss_trigger_price
        smart_trade.stop_loss_price = price + price * float(smart_trade.stop_loss_price_percent)/100
        smart_trade.stop_loss_type=stop_loss_type
        smart_trade.stop_loss_time_out=stop_loss_time_out
        smart_trade.stop_loss_time_out_time=stop_loss_time_out_time
        smart_trade.stop_loss=stop_loss
        smart_trade.take_profit=take_profit
        smart_trade.trailing_deviation = trailing_deviation
        smart_trade.use_assets = request.json['use_assets']
        db.session.commit()

        return jsonify({'message': 'Smart trade edited successfully','ok':True})

    except Exception as e:
        return jsonify({'message': f'Error editing smart trade: {e}'})
    

@app.route('/api/v1/smart_trades/open/<int:smart_trade_id>', methods=['POST'])
def open_smart_trade(smart_trade_id):
    # Get the smart trade from the database
    smart_trade = SmartTrade.query.get(smart_trade_id)

    # Check if the smart trade exists
    if not smart_trade or smart_trade.user_id != current_user.id:
        return jsonify({'message': 'Smart trade not found or you do not have permission to open it','ok':False})


    # Cancel the smart trade on the exchange
    try:
        smart_trade.isActive = True
        db.session.commit()
        return jsonify({'message': 'Smart trade opened successfully','ok':True})

    except Exception as e:
        return jsonify({'message': f'Error opening smart trade: {e}'})
    
@app.route('/api/v1/smart_trades/run/<int:smart_trade_id>', methods=['POST'])
def run_smart_trade(smart_trade_id):
    smart_trade = SmartTrade.query.get(smart_trade_id)

    if not smart_trade or smart_trade.user_id != current_user.id:
        return jsonify({'message': 'Smart trade not found or you do not have permission to run it','ok':False})

    exchange = connectExchange(smart_trade.exchange, current_user.id)

    if current_user.subType.max_sma:
        active_smart_trades_count = len(SmartTrade.query.filter(SmartTrade.isActive == True, SmartTrade.is_hidden == False, SmartTrade.user_id == current_user.id).all())
        if current_user.subType.max_sma <= active_smart_trades_count:
            return jsonify({'message': f"You have reached your maximum number of bots. Upgrade your subscription to create more bots", 'ok': False})

    try:
        deal_started = False
        isActive = True
        symbol = f"{smart_trade.quote_currency}/{smart_trade.base_currency}"
        total_amount = smart_trade.amount
        side = 'buy' if smart_trade.trade_type.lower() == 'smart trade' else 'sell'

        status = True
        if not smart_trade.use_assets:
            buy_type = smart_trade.order_type
            buy_price = 0

            if buy_type == 'limit' or buy_type == 'market':
                try:
                    buy_trade = exchange.create_order(symbol, buy_type, side, total_amount, smart_trade.bought_price if buy_type == 'limit' else None)
                    err_msg = ""
                    deal_started = True
                except Exception as e:
                    buy_trade = None
                    err_msg = str(e)
                    status = False
                    deal_started = False
                    

                try:
                    trans = Transaction(
                        err_msg=err_msg,
                        status=status, 
                        user_id=current_user.id, 
                        exchange=smart_trade.exchange, 
                        symbol=symbol, 
                        type=side, 
                        amount=total_amount, 
                        value=exchange.fetch_order(buy_trade['id'], symbol)['price'] if status else 0
                    )
                    db.session.add(trans)
                    smart_trade.transactions.append(trans)
                except:
                    pass
            else:
                buy_trade = None


            if not smart_trade.take_profit and not smart_trade.stop_loss:
                total_amount = 0
                isActive = False

            if buy_type in ['limit', 'market']:
                buy_price = exchange.fetch_order(buy_trade['id'], symbol)['price'] if buy_trade else smart_trade.bought_price 
                send_notification(f'{smart_trade.trade_type} has completed a Quick {side} on {smart_trade.exchange} for {symbol} with {round(total_amount * buy_price, 2)} {symbol.split("/")[1]}***{buy_type} Smart Trade {side} Order')
            elif not buy_trade:
                send_notification(f'{smart_trade.trade_type} has failed to start a Quick {side} on {smart_trade.exchange} for {symbol} with {round(total_amount * buy_price, 2)} {symbol.split("/")[1]}***{buy_type} Smart Trade {side} Order')
        else:
            deal_started = True
            buy_price = smart_trade.bought_price

        smart_trade.units = total_amount
        smart_trade.deal_started = deal_started
        smart_trade.isActive = isActive
        smart_trade.buy_order_id = None
        smart_trade.trailing_order_id = None
        smart_trade.stop_loss_id = None
        smart_trade.last_take_profit_id = None
        smart_trade.last_take_profit = False
        smart_trade.last_price = 0
        smart_trade.take_profit_index = 0
        smart_trade.stop_loss_time_out_runned = False
        smart_trade.buy_price = buy_price
        smart_trade.stop_loss_price = buy_price + buy_price * float(smart_trade.stop_loss_price_percent) / 100 if smart_trade.stop_loss else 0
        db.session.commit()
        return jsonify({'message': 'Smart trade ran again successfully', 'ok': True})

    except Exception as e:
        return jsonify({'message': f'Error running smart trade: {e}'})



@app.route('/api/v1/smart_trades/close/<int:smart_trade_id>', methods=['POST'])
def close_smart_trade(smart_trade_id):
    smart_trade = SmartTrade.query.get(smart_trade_id)

    if not smart_trade or smart_trade.user_id != current_user.id:
        return jsonify({'message': 'Smart trade not found or you do not have permission to close it','ok':False})

    exchange = connectExchange(smart_trade.exchange, current_user.id)

    try:
        smart_trade.isActive = False
        order_type = 'market'
        side = 'sell' if smart_trade.trade_type.lower() == 'smart trade' else 'buy'

        try:
            order = exchange.create_order(f"{smart_trade.quote_currency}/{smart_trade.base_currency}", order_type, side, smart_trade.units)
            close_price = exchange.fetch_order(order["id"], f"{smart_trade.quote_currency}/{smart_trade.base_currency}")['price']
            err_msg = ""
            status = True
        except Exception as e:
            order = None
            close_price = smart_trade.price_now
            err_msg = str(e)
            status = False
            

        unit_price_factor = 1 if smart_trade.base_currency == "USDT" else getPrice_assets(smart_trade.exchange, smart_trade.base_currency + '/USDT')
        profit = ((close_price if order else smart_trade.price_now) - smart_trade.bought_price) * unit_price_factor * smart_trade.units

        gain_loss = "gained" if profit > 0 else "lost"
        message = f"{smart_trade.trade_type} has {gain_loss} {round(abs(profit), 2)} {smart_trade.base_currency}***Smart Trade {gain_loss.capitalize()}"
        smart_trade.total_profit += profit
        send_notification(message, current_user.id, smart_trade.exchange)

        if status:
            trans = Transaction(
                status=status,
                err_msg=err_msg,
                user_id=current_user.id,
                exchange=smart_trade.exchange,
                symbol=f"{smart_trade.quote_currency}/{smart_trade.base_currency}",
                type=side,
                amount=smart_trade.units,
                value=close_price if status else 0
            )
            db.session.add(trans)
            smart_trade.transactions.append(trans)

        db.session.commit()
        return jsonify({'message': 'Smart trade closed successfully','ok':True})

    except Exception as e:
        return jsonify({'message': f'Error closing smart trade: {e}'})


@app.route('/api/v1/smart_trades/cancel/<int:smart_trade_id>', methods=['POST'])
def cancel_smart_trade(smart_trade_id):
    # Get the smart trade from the database
    smart_trade = SmartTrade.query.get(smart_trade_id)

    # Check if the smart trade exists and belongs to the current user
    if not smart_trade or smart_trade.user_id != current_user.id:
        return jsonify({'error': 'Smart trade not found or you do not have permission to cancel it'}), 404

    # Get the exchange from the smart trade
    exchange = connectExchange(smart_trade.exchange, current_user.id)

    # Cancel the smart trade on the exchange
    try:
        if smart_trade.buy_order_id:

            # Check if the buy order is still open
            if exchange.fetch_order(smart_trade.buy_order_id,symbol=smart_trade.quote_currency+'/'+smart_trade.base_currency)['status'] == 'open':
                try:
                    exchange.cancel_order(smart_trade.buy_order_id, symbol=smart_trade.quote_currency+'/'+smart_trade.base_currency)
                except:
                    pass
            else:
                buy_or_sell = 'sell' if smart_trade.trade_type.lower() == 'smart trade' else 'buy'
                try:
                    order = exchange.create_order(smart_trade.quote_currency+'/'+smart_trade.base_currency, 'market', buy_or_sell, smart_trade.units)
                    err_msg = ""
                    status = True
                except Exception as e:
                    err_msg = str(e)
                    order = None
                    status = False
                try:
                    trans = Transaction(status=status,
                                        err_msg=err_msg,
                                        user_id=current_user.id,
                                        exchange=smart_trade.exchange,
                                        symbol=smart_trade.quote_currency+'/'+smart_trade.base_currency,
                                        type=buy_or_sell,
                                        amount=smart_trade.units,
                                        value=exchange.fetch_order(order['id'],smart_trade.quote_currency+'/'+smart_trade.base_currency)['price'] if status else 0
                                    )
                    db.session.add(trans)
                    smart_trade.transactions.append(trans)
                except:
                    pass
    except Exception as e:
        pass

    db.session.delete(smart_trade)
    db.session.commit()
    return jsonify({'message': 'Smart trade cancelled successfully','ok':True})

# GET /api/v1/smart_trades/:id
@app.route('/api/v1/smart_trades/<int:id>', methods=['GET'])
def get_smart_trade(id):
    # Retrieve the smart trade with the specified ID and user ID
    smart_trade = SmartTrade.query.filter_by(id=id, user_id=current_user.id).first()

    # If the smart trade does not exist, return a 404 error response
    if not smart_trade:
        return jsonify({'error': f'Smart trade with ID {id} does not exist or does not belong to this user'}), 404

    # Serialize the smart trade to JSON format
    serialized_smart_trade = smart_trade.serialize()

    # Return the serialized smart trade as a JSON response
    return jsonify(smart_trade=serialized_smart_trade)

@celery.task
def smart_trade_bot_all(page):
    with app.app_context(): 
        while True:
            sleep(0.5)
            # Set the number of bots per page
            bots_per_page = 100

            # Calculate the starting index for the slice
            start_index = (page - 1) * bots_per_page

            # Get the bots for the current page using slicing
            smart_trade_bots = SmartTrade.query.all()[start_index:start_index + bots_per_page]
            for smart_trade_bot in smart_trade_bots:
                try:
                    print(f"{smart_trade_bot.trade_type} bot {smart_trade_bot.id} is running")
                    start_time_print = time.time()
                    # Get the current user and smart trade bot
                    current_user = User.query.filter_by(id=smart_trade_bot.user_id).first()
                    smart_trade_bot = SmartTrade.query.filter_by(id=smart_trade_bot.id).first()

                    if smart_trade_bot.isActive and smart_trade_bot and smart_trade_bot.units > 0:
                        symbol = smart_trade_bot.quote_currency+'/'+smart_trade_bot.base_currency
                        exchange_name = smart_trade_bot.exchange

                        # Check if the smart trade bot is using assets
                        if smart_trade_bot.units == 0:
                            smart_trade_bot.isActive = False
                        
                        # Get the current price of the asset
                        price = getPrice_assets(exchange_name, symbol,smart_trade_bot.user_id)
                        # Update the last price of the smart trade bot
                        smart_trade_bot.price_now = price

                        ########################### Get the exchange from the current user  ###########################

                        api_key,api_secret,password = current_user.exchanges.filter(Exchange.name == exchange_name).first().get_creds()
                        if password:
                            exchange = getattr(ccxt, exchange_name)({
                                'apiKey': api_key,
                                'secret': api_secret,
                                'password': password,
                            })
                        else:
                            exchange = getattr(ccxt, exchange_name)({
                                'apiKey': api_key,
                                'secret': api_secret,
                            })

                        if current_user.exchanges.filter(Exchange.name == exchange_name).first().demo:
                            exchange.set_sandbox_mode(True)

                        ########################### End of Getting the exchange from the current user  ###########################

                        #conditional buy orders
                        if smart_trade_bot.use_assets == False and price >= smart_trade_bot.buy_trigger_price and smart_trade_bot.deal_started == False and price > 0:
                            try:
                                if smart_trade_bot.order_type in ['cond.limit', 'cond.market']:
                                    buy_or_sell = 'buy' if smart_trade_bot.trade_type == 'smart trade' else 'sell'
                                    order_type = 'limit' if smart_trade_bot.order_type == 'cond.limit' else 'market'
                                    buy_trade = exchange.create_order(symbol, order_type, buy_or_sell, smart_trade_bot.amount, smart_trade_bot.buy_price if order_type == 'limit' else None)
                                    buy_trade_ord = exchange.fetch_order(buy_trade['id'], symbol) if buy_trade else None
                                    status = True
                                    err_msg = ""
                                    trans = Transaction(
                                        status=status,
                                        err_msg=err_msg,
                                        user_id=current_user.id,
                                        exchange=exchange_name, 
                                        symbol=symbol, 
                                        type=buy_or_sell, 
                                        value=smart_trade_bot.buy_price if not buy_trade else (exchange.fetch_order(buy_trade['id'], symbol)['price']), 
                                        amount=smart_trade_bot.amount
                                    )
                                    db.session.add(trans)
                                    smart_trade_bot.transactions.append(trans)
                                    if buy_trade_ord and buy_trade_ord['fee']:
                                        smart_trade_bot.units -= buy_trade_ord["fee"]["cost"]
                                        smart_trade_bot.amount -= buy_trade_ord["fee"]["cost"]
                                    smart_trade_bot.buy_price = buy_trade_ord['price'] if buy_trade_ord else None
                            except Exception as e:
                                err_msg = str(e)
                                status = False
                                buy_trade = None
                                buy_trade_ord = None

                            if status:
                                smart_trade_bot.deal_started = True
                                try:
                                    smart_trade_bot.buy_order_id = buy_trade['id']
                                except:
                                    pass    
                                send_notification(f'{smart_trade_bot.trade_type} has started a Condtional {buy_or_sell} on {exchange_name} for {symbol} with {round(exchange.fetch_order(buy_trade["id"],symbol=symbol)["price"] * smart_trade_bot.amount, 2)} {smart_trade_bot.base_currency}***{smart_trade_bot.order_type} {smart_trade_bot.trade_type} {buy_or_sell} Order', current_user.id,smart_trade_bot.exchange)
                                
                                # Check if the smart trade bot will use assets again after the buy order
                                if not smart_trade_bot.take_profit and not smart_trade_bot.stop_loss:
                                    smart_trade_bot.units = 0
                                    smart_trade_bot.isActive = False
                            else:
                                send_notification(f'{smart_trade_bot.trade_type} has failed to start a Condtional {buy_or_sell} on {exchange_name} for {symbol} with {round(smart_trade_bot.amount * smart_trade_bot.buy_price, 2)} {smart_trade_bot.base_currency}***{smart_trade_bot.order_type} {smart_trade_bot.trade_type} {buy_or_sell} Order', current_user.id,smart_trade_bot.exchange)
                            

                        #take-profit-orders
                        if smart_trade_bot.take_profit and smart_trade_bot.deal_started and price > 0:
                            for ind ,take_profit in enumerate(smart_trade_bot.take_profit_quantities):
                                sell_price = take_profit[0]*smart_trade_bot.buy_price/100 + (smart_trade_bot.buy_price) # Calculate sell price based on take profit
                                sell_amount = take_profit[1]*smart_trade_bot.amount/100
                                if (price >= sell_price and smart_trade_bot.trade_type.lower() != "smart cover" and smart_trade_bot.trade_type.lower() != "smart buy") or (price <= sell_price and smart_trade_bot.trade_type.lower() == "smart cover" and smart_trade_bot.trade_type.lower() != "smart buy"):
                                    
                                    # check if the last take profit is reached
                                    if take_profit == smart_trade_bot.take_profit_quantities[-1]:
                                        smart_trade_bot.last_take_profit = True
                                    if ind == smart_trade_bot.take_profit_index and (take_profit != smart_trade_bot.take_profit_quantities[-1] or smart_trade_bot.trailing_take_profit == False):
                                        
                                        try:
                                            sell_trade = exchange.create_order(
                                                symbol, 
                                                smart_trade_bot.tpTriggerType,'sell' if smart_trade_bot.trade_type.lower() != "smart cover" else 'buy', 
                                                sell_amount, 
                                                sell_price if smart_trade_bot.tpTriggerType == 'limit' else None
                                            )
                                            status = True
                                            err_msg = ""
                                        except Exception as e:
                                            sell_trade = None
                                            err_msg = str(e)
                                            status = False
                                        try:
                                            trans = Transaction(
                                                status = status,
                                                err_msg = err_msg,
                                                user_id=current_user.id,
                                                exchange=exchange_name,
                                                symbol=symbol,
                                                type='sell' if smart_trade_bot.trade_type.lower() != "smart cover" else 'buy',
                                                amount=sell_amount,
                                                value=exchange.fetch_order(sell_trade['id'],symbol=symbol)['price'] if sell_trade else 0
                                            )
                                            db.session.add(trans)
                                            smart_trade_bot.transactions.append(trans)
                                        except Exception as e:
                                            print(e)

                                        
                                            

                                        if status:

                                            

                                            

                                            # go to the next take profit
                                            if smart_trade_bot.take_profit_index < len(smart_trade_bot.take_profit_quantities) - 1:
                                                smart_trade_bot.take_profit_index += 1

                                            # fetch the take profit order
                                            sell_trade_ord = exchange.fetch_order(sell_trade['id'],symbol)['price'] if exchange.fetch_order(sell_trade['id'],symbol) else price
                                            
                                            # update the units remaining
                                            smart_trade_bot.units = smart_trade_bot.units - sell_amount

                                            trade_type = smart_trade_bot.trade_type.lower()

                                            gain_loss_factor = 1 if symbol.split("/")[1] == "USDT" else getPrice_assets(exchange_name, symbol.split('/')[1] + '/USDT')
                                            profit = (sell_trade_ord - smart_trade_bot.buy_price) * gain_loss_factor * sell_amount
                                            profit = profit if trade_type == "smart trade" else -1 * profit

                                            gain_loss = "gained" if profit > 0 else "lost"
                                            message = f"{trade_type} has {gain_loss} {round(profit, 2)} {symbol.split('/')[1]}***Smart Trade  {gain_loss.capitalize()}"
                                            send_notification(message, current_user.id, exchange_name)

                                            smart_trade_bot.total_profit += profit
                                            smart_trade_bot.last_total_profit_time = datetime.utcnow()
                                            smart_trade_bot.last_price = price

                                            if not smart_trade_bot.trailing_take_profit:
                                                smart_trade_bot.units = 0
                                                smart_trade_bot.isActive = False
                                        else:
                                            send_notification(f"{trade_type} has failed to complete a Take profit {'sell' if smart_trade_bot.trade_type.lower() != 'smart cover' else 'buy'} order for {symbol} on {exchange_name} with {round(sell_amount * sell_price, 2)} {smart_trade_bot.base_currency}***Smart Trade Take Profit", current_user.id, exchange_name)

                        # Update the Stop Loss price
                        if (smart_trade_bot.trade_type.lower() == "smart trade" and price > smart_trade_bot.last_price) or (smart_trade_bot.trade_type.lower() == "smart cover" and price < smart_trade_bot.last_price) and price > 0:
                            smart_trade_bot.last_price = price
                            # Update stop loss price
                            if smart_trade_bot.move_to_break_even and ((smart_trade_bot.trade_type.lower() == "smart trade" and smart_trade_bot.take_profit_quantities[0][0] < price) or (smart_trade_bot.trade_type.lower() == "smart cover" and smart_trade_bot.take_profit_quantities[0][0] > price) ) and len(smart_trade_bot.take_profit_quantities) > 1 and smart_trade_bot.last_price > 0:
                                smart_trade_bot.stop_loss_price = smart_trade_bot.buy_price
                            if smart_trade_bot.trailing_stop_loss and smart_trade_bot.stop_loss:
                                smart_trade_bot.stop_loss_price = price + price * float(smart_trade_bot.stop_loss_price_percent)/100
                            if smart_trade_bot.trailing_take_profit and smart_trade_bot.last_take_profit and smart_trade_bot.last_price > 0:
                                smart_trade_bot.stop_loss_price = price + price * float(smart_trade_bot.trailing_deviation)/100

                        if (price <= smart_trade_bot.stop_loss_price if (smart_trade_bot.trade_type.lower() != "smart cover") else price >= smart_trade_bot.stop_loss_price) and smart_trade_bot.units > 0 and smart_trade_bot.deal_started and (smart_trade_bot.stop_loss or (smart_trade_bot.trailing_take_profit and smart_trade_bot.last_take_profit)) and price > 0:
                            # Making the stop loss sell order
                            if smart_trade_bot.stop_loss_time_out and smart_trade_bot.stop_loss:
                                if smart_trade_bot.stop_loss_time_out_runned == False:
                                    sleep(smart_trade_bot.stop_loss_time_out_time)
                                    smart_trade_bot.stop_loss_time_out_runned = True
                                    db.session.commit()
                                    continue
                            
                            buy_or_sell = 'sell' if smart_trade_bot.trade_type.lower() != "smart cover" else 'buy'
                            
                            try:
                                trailing_order = exchange.create_order(symbol, 'market', buy_or_sell, smart_trade_bot.units)
                                status = True
                                err_msg = ""
                            except Exception as e:
                                trailing_order = None
                                status = False
                                err_msg = str(e)
                                
                            try: 
                                trans = Transaction(status = status, 
                                                    err_msg = err_msg,
                                                    user_id=current_user.id,
                                                    exchange=exchange_name,
                                                    symbol=symbol,
                                                    type=buy_or_sell,
                                                    amount=smart_trade_bot.units,
                                                    value = exchange.fetch_order(trailing_order['id'],symbol)['price'] if trailing_order else 0
                                                )
                                db.session.add(trans)
                                smart_trade_bot.transactions.append(trans)
                            except:
                                pass
                            
                            if status:
                                trailing_order_price = exchange.fetch_order(trailing_order['id'],symbol)['price'] if exchange.fetch_order(trailing_order['id'],symbol) else price
                            
                                # Send notification
                                message = f"{smart_trade_bot.trade_type} has completed a Stop loss {buy_or_sell} order for {symbol} on {smart_trade_bot.exchange} with {round(smart_trade_bot.units * price, 2)} {smart_trade_bot.base_currency}***{smart_trade_bot.trade_type}"
                                send_notification(message, current_user.id,smart_trade_bot.exchange)

                                
                                trade_type = smart_trade_bot.trade_type.lower()
                                unit_price_factor = 1 if symbol.split("/")[1] == "USDT" else getPrice_assets(exchange_name, symbol.split('/')[1] + '/USDT')
                                profit_calculation = (trailing_order_price - smart_trade_bot.buy_price) if trade_type == "smart trade" else (smart_trade_bot.buy_price - trailing_order_price)
                                profit = profit_calculation * unit_price_factor * smart_trade_bot.units
                                smart_trade_bot.units = 0
                                smart_trade_bot.isActive = False

                                gain_loss = "gained" if profit > 0 else "lost"
                                message = f"{trade_type} has {gain_loss} {round(abs(profit), 2)} {symbol.split('/')[1]}***Smart Trade {gain_loss.capitalize()}"
                                send_notification(message, current_user.id, exchange_name)

                                smart_trade_bot.total_profit += profit
                                smart_trade_bot.last_total_profit_time = datetime.utcnow()

                            else:
                                send_notification(f"{smart_trade_bot.trade_type} has failed to complete a Stop loss {buy_or_sell} order for {symbol} on {smart_trade_bot.exchange} with {round(smart_trade_bot.units * price, 2)} {smart_trade_bot.base_currency}***{smart_trade_bot.trade_type} Stop Loss Error", current_user.id,smart_trade_bot.exchange)
                    else:
                        continue
                    print("--- %s seconds ---" % (time.time() - start_time_print))
                    db.session.commit()
                except Exception as e:
                    print(e)
