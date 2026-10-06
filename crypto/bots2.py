from crypto.functions import getPrice,getPrice_assets
import json
from flask import render_template, request, redirect, url_for, jsonify,Response
import ccxt
from flask_login import login_required,current_user
from crypto import app,db,celery, jwt_required
from crypto.models import User, Exchange, Bot, SafetyOrder, Post
from crypto.notify import send_notification
from crypto.dataStream_indicators import fetch_data,fetch_data2
import talib
from crypto.exchanges import connectExchange
from time import sleep
import time
from datetime import datetime

@app.route('/bots/',methods=['POST','GET'])
@jwt_required
def bots():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))
    
    if request.method == 'POST':
        return jsonify({
            'bots': [bot.serialize() for bot in current_user.bots.all()],
        })
    else:
        return render_template('bots.html',
                                    bots=current_user.bots.all(),
                                    notifications=current_user.notifications.all(),
                                    exchanges = current_user.exchanges.all(),
                                    symbol=request.args.get('symbol'),
                                    exchange=request.args.get('exchange'),
                                    current_user=current_user,
                                    posts = Post.query.all(),
                                    bots_history = json.dumps([hist.serialize() for hist in current_user.bot_history]),
                            )

@app.route('/bot_create/')
@jwt_required
def bot_create():
    if current_user.exchanges.filter(Exchange.isActive==True).first() is None:
        return redirect(url_for('exchanges'))

    exchange = connectExchange()
    
    pairs = []
    for currency in exchange.fetch_markets():
        if currency['active'] and currency['spot']:
            pairs.append(currency['symbol'])

    return render_template('bots_create.html',pairs=pairs,notifications=current_user.notifications.all(),exchanges = current_user.exchanges.all(),symbol=request.args.get('symbol'),exchange=request.args.get('exchange'),current_user=current_user,posts = Post.query.all())

@app.route('/api/v1/toggle_bot',methods=['POST','GET'])
@jwt_required
def toggle_bot():
    bot_id = request.json["bot_id"]
    bot = Bot.query.filter_by(id=bot_id).first()
    if bot.owner_id != current_user.id:
        return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
    bot.isActive = request.json["state"]
    db.session.commit()
    if bot.isActive:
        send_notification(f'{bot.name} bot has been activated***Bot')
    else:
        send_notification(f'{bot.name} bot has been deactivated***Bot')

@app.route('/api/v1/delete_bot',methods=['POST','GET'])
@jwt_required
def delete_bot():
    bot_id = request.json["bot_id"]
    bot = Bot.query.filter_by(id=bot_id).first()
    if bot.owner_id != current_user.id:
        return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
    db.session.delete(bot)
    db.session.commit()
    return jsonify({'message':f"Bot deleted successfully. Bot ID: {bot.id}",'ok':True})

#get_bot_stats
@app.route('/api/v1/get_bot_stats',methods=['POST','GET'])
@jwt_required
def get_bot_stats():
    bot_id = request.args.get("bot_id")
    bot = Bot.query.filter_by(id=bot_id).first()
    if bot:
        if bot.owner_id != current_user.id:
            return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
        if int(bot.timeout_type) == 1:
            timeout = int(bot.timeout)/60/60
        elif int(bot.timeout_type) == 2:
            timeout = int(bot.timeout)/60
        elif int(bot.timeout_type) == 3:
            timeout = int(bot.timeout)/24/60/60
        else:
            timeout = int(bot.timeout)
        return jsonify({
            'name':bot.name,
            'symbol':bot.base_currency+"/"+bot.quote_currency,
            "symbols":str(bot.symbols),
            'isActive':bot.isActive,
            'deal_started':bot.deal_started,
            'take_profit':round(bot.take_profit,2) if bot.take_profit is not None else 0,
            'tp_type':bot.tp_type,
            'tp_percent_type':bot.tp_percent_type,
            'tp_percent':bot.tp_percent,
            'trailing_take_profit':bot.trailing_take_profit,
            'trailing_stop_loss':bot.trailing_stop_loss,
            'units':round(bot.units,2) if bot.units is not None else 0,
            'amount':round(bot.amount,2) if bot.amount is not None else 0,
            'sell_price':round(bot.sell_price,2) if bot.sell_price is not None else 0,
            'stop_loss_price':round(bot.stop_loss_price, 2) if bot.stop_loss_price is not None else 0,
            'buy_price':round(bot.buy_price,2) if bot.buy_price is not None else 0,
            'stop_loss':bot.stop_loss,
            "take_profit":bot.take_profit,
            'Close_deal_after_timeout':bot.Close_deal_after_timeout,
            'timeout':timeout,
            'stop_loss_price_percent':bot.stop_loss_price_percent,
            'stop_loss_time_out':bot.stop_loss_time_out,
            'stop_loss_time_out_time':bot.stop_loss_time_out_time,
            'exchange':bot.exchange,
            'base_currency':bot.base_currency,
            'quote_currency':bot.quote_currency,
            'strategy':bot.strategy,
            'id':bot.id,
            "tp_price":round(bot.tp_price,2) if bot.tp_price is not None else 0,
            'price_now':round(bot.price_now,2) if bot.price_now is not None else 0,
            'total_trades':bot.total_trades,
            'total_profit':bot.total_profit,
            'close_deal_action':bot.close_deal_action,
            'min_volume':bot.min_volume,
            'max_price':bot.max_price,
            'min_price':bot.min_price,
            'min_profit':bot.min_profit,
            'min_profit_type':bot.min_profit_type,
            'min_profit_percent':bot.min_profit_percent,
            'open_deals_and_stop':bot.open_deals_and_stop,
            'trailing_deviation': bot.trailing_deviation,
            'trailing_stop_loss': bot.trailing_stop_loss,
            'cooldown_between_deals': bot.cooldown_between_deals,
            'close_deal_action': bot.close_deal_action,
            'safety_orders_size_type': bot.safety_orders_size_type,
            'amount_type': bot.amount_type,
            'timeout_type': bot.timeout_type,
            'conds':bot.conds,
            'tp_conds':bot.tp_conds,
            'pair_type':bot.pair_type,
            'start_order_type':bot.start_order_type,
    })
    else:
        return jsonify({'message':f"Bot not found",'ok':False})

@app.route('/api/v1/run_bot',methods=['POST','GET'])
@jwt_required
def run_bot():
    try:
        bot_id = request.args.get("bot_id")
        bot = Bot.query.filter_by(id=bot_id).first()
        if bot.owner_id != current_user.id:
            return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
        bot.isActive = True
        bot.deal_started = False
        bot.units = bot.amount
        db.session.commit()
        return jsonify({'message':f"Bot started successfully. Bot ID: {bot.id}",'ok':True})
    except Exception as e:
        return jsonify({'message':f"Bot not found",'ok':False})
    

@app.route('/api/v1/create_bot/',methods=['POST','GET'])
@jwt_required
def create_bot():
    pair_type = str(request.json["pair_type"]).lower()
    symbols = request.json["symbols"]
    if pair_type == "single":
        if current_user.subType.max_bots <= len(current_user.bots.all()):
            return jsonify({'message':f"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})
    else:
        if current_user.subType.max_bots <= len(symbols):
            return jsonify({'message':f"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})
    exchange_name = request.json["exchange_name"]
    amount = float(request.json["amount"])
    amount_type = int(request.json["amount_type"])
    start_order_type = str(request.json["start_order_type"]).lower()
    symbol = request.json["symbol"]
    
    conds = request.json["conds"]
    tp_type = str(request.json["tp_type"])
    tp_percent = float(request.json["tp_percent"])
    tp_percent_type = str(request.json["tp_percent_type"]).lower()
    profit_currency = str(request.json["profit_currency"]).lower()
    tp_conds = request.json["tp_conds"]
    trailing_take_profit = request.json["trailing_take_profit"]
    trailing_deviation = float(request.json["trailing_deviation"])
    trailing_stop_loss = request.json["trailing_stop_loss"]
    stop_loss = request.json["stop_loss"]
    stop_loss_price_percent = float(request.json["stop_loss_price_percent"])
    stop_loss_time_out = request.json["stop_loss_time_out"]
    stop_loss_time_out_time = int(request.json["stop_loss_time_out_time"])
    Close_deal_after_timeout = request.json["Close_deal_after_timeout"]
    timeout = int(request.json["timeout"])
    timeout_type = int(request.json["timeout_type"]) #hrs mins days
    safety_orders_size = float(request.json["safety_orders_size"])
    safety_orders_size_scale = float(request.json["safety_orders_size_scale"])
    safety_orders_deviation = float(request.json["safety_orders_deviation"])
    safety_orders_deviation_scale = float(request.json["safety_orders_deviation_scale"])
    safety_orders_count = float(request.json["safety_orders_count"])
    safety_orders_count_max_active = float(request.json["safety_orders_count_max_active"])
    safety_orders_size_type = int(request.json["safety_orders_size_type"])
    min_profit = request.json["min_profit"]
    min_profit_type = str(request.json["min_profit_type"])
    min_profit_percent = float(request.json["min_profit_percent"])
    close_deal_action = int(request.json["close_deal_action"])
    if "cooldown_between_deals" in request.json:
        if request.json["cooldown_between_deals"]:
            cooldown_between_deals = int(request.json["cooldown_between_deals"])
        else:
            cooldown_between_deals = None
    else:
        cooldown_between_deals = None
    if "open_deals_and_stop" in request.json:
        if request.json["open_deals_and_stop"]:
            open_deals_and_stop = int(request.json["open_deals_and_stop"])
        else:
            open_deals_and_stop = None
    else:
        open_deals_and_stop = None
    if request.json["min_volume"]:
        min_volume = float(request.json["min_volume"])
    else:
        min_volume = None
    if request.json["max_price"]:
        max_price = float(request.json["max_price"])
    else:
        max_price = None
    if request.json["min_price"]:
        min_price = float(request.json["min_price"])
    else:
        min_price = None

    if timeout_type == 1:
        timeout = timeout*60*60
    elif timeout_type == 2:
        timeout = timeout*60
    elif timeout_type == 3:
        timeout = timeout*24*60*60
    amounts = []
    safety_amounts = []
    exchange = connectExchange(exchange_name)
    if pair_type == "single":
        priceNow2 = getPrice(exchange_name,symbol)
        if amount_type == 1:
            amount = amount/priceNow2
        elif amount_type == 2:
            amount = amount
        # the user will pass the amoutn as percentage of teh usdt balance
        elif amount_type == 3:
            amount = ((amount/100)*exchange.fetch_balance()[symbol.split("/")[1]]['free'])/priceNow2
        
        if safety_orders_size_type == 1:
            safety_orders_size = safety_orders_size/priceNow2
        elif safety_orders_size_type == 2:
            safety_orders_size = safety_orders_size
        # the user will pass the amoutn as percentage of teh usdt balance
        elif safety_orders_size_type == 3:
            safety_orders_size = ((safety_orders_size/100)*exchange.fetch_balance()[symbol.split("/")[1]]['free'])/priceNow2
    else:
        for symbol in symbols:
            priceNow2 = getPrice(exchange_name,symbol)
            if amount_type == 1:
                amount2 = amount/priceNow2
            elif amount_type == 2:
                amount2 = amount
            # the user will pass the amoutn as percentage of teh usdt balance
            elif amount_type == 3:
                amount2 = ((amount/100)*exchange.fetch_balance()[symbol.split("/")[1]]['free'])/priceNow2
            
            if safety_orders_size_type == 1:
                safety_amount2 = safety_orders_size/priceNow2
            elif safety_orders_size_type == 2:
                safety_amount2 = safety_orders_size
            # the user will pass the amoutn as percentage of teh usdt balance
            elif safety_orders_size_type == 3:
                safety_amount2 = ((safety_orders_size/100)*exchange.fetch_balance()[symbol.split("/")[1]]['free'])/priceNow2
            
            amounts.append(amount2)
            safety_amounts.append(safety_amount2)



    if pair_type == "single":
        bot = Bot(
                    name=request.json["name"],
                    base_currency=symbol.split('/')[0],
                    quote_currency=symbol.split('/')[1],
                    exchange=exchange_name,
                    start_order_type=start_order_type,
                    strategy=request.json["strategy"],
                    symbol=symbol,
                    symbols=symbols,
                    pair_type=pair_type,
                    units=amount,
                    amount=amount,
                    total_volume=amount,
                    stop_loss = stop_loss,
                    stop_loss_price_percent = stop_loss_price_percent,
                    trailing_take_profit = trailing_take_profit,
                    trailing_deviation = trailing_deviation,
                    trailing_stop_loss = trailing_stop_loss,
                    stop_loss_time_out = stop_loss_time_out,
                    stop_loss_time_out_time = stop_loss_time_out_time,
                    Close_deal_after_timeout = Close_deal_after_timeout,
                    timeout = timeout,
                    tp_type = tp_type,
                    tp_percent = tp_percent,
                    tp_percent_type = tp_percent_type,
                    safety_orders_size = safety_orders_size,
                    safety_orders_size_scale = safety_orders_size_scale,
                    safety_orders_deviation = safety_orders_deviation,
                    safety_orders_deviation_scale = safety_orders_deviation_scale,
                    safety_orders_count = safety_orders_count,
                    safety_orders_count_active = 0,
                    safety_orders_count_max_active = safety_orders_count_max_active,
                    min_volume = min_volume,
                    max_price = max_price,
                    min_price = min_price,
                    min_profit = min_profit,
                    min_profit_type = min_profit_type,
                    min_profit_percent = min_profit_percent,
                    conds = conds,
                    tp_conds = tp_conds,
                    close_deal_action = close_deal_action,
                    cooldown_between_deals = cooldown_between_deals,
                    open_deals_and_stop = open_deals_and_stop,
                    timeout_type = timeout_type,
                    amount_type = amount_type,
                    safety_orders_size_type = safety_orders_size_type,
                )
        
        current_user.bots.append(bot)
        db.session.add(bot)

        for i in range(int(safety_orders_count)):
            safetyOrder = SafetyOrder()
            bot.safetyOrders.append(safetyOrder)
            db.session.add(safetyOrder)

        db.session.commit()
        send_notification(f'{bot.name} bot has been created for {symbol}***Bot')
    else:
        for i, symbol in enumerate(symbols):
            bot = Bot(
                    name=request.json["name"],
                    base_currency=symbol.split('/')[0],
                    quote_currency=symbol.split('/')[1],
                    exchange=exchange_name,
                    start_order_type=start_order_type,
                    strategy=request.json["strategy"],
                    symbol=symbol,
                    symbols=symbols,
                    pair_type=pair_type,
                    units=amounts[i],
                    amount=amounts[i],
                    total_volume=amounts[i],
                    stop_loss = stop_loss,
                    stop_loss_price_percent = stop_loss_price_percent,
                    trailing_take_profit = trailing_take_profit,
                    trailing_deviation = trailing_deviation,
                    trailing_stop_loss = trailing_stop_loss,
                    stop_loss_time_out = stop_loss_time_out,
                    stop_loss_time_out_time = stop_loss_time_out_time,
                    Close_deal_after_timeout = Close_deal_after_timeout,
                    timeout = timeout,
                    tp_type = tp_type,
                    tp_percent = tp_percent,
                    tp_percent_type = tp_percent_type,
                    safety_orders_size = safety_amounts[i],
                    safety_orders_size_scale = safety_orders_size_scale,
                    safety_orders_deviation = safety_orders_deviation,
                    safety_orders_deviation_scale = safety_orders_deviation_scale,
                    safety_orders_count = safety_orders_count,
                    safety_orders_count_active = 0,
                    safety_orders_count_max_active = safety_orders_count_max_active,
                    min_volume = min_volume,
                    max_price = max_price,
                    min_price = min_price,
                    min_profit = min_profit,
                    min_profit_type = min_profit_type,
                    min_profit_percent = min_profit_percent,
                    conds = conds,
                    tp_conds = tp_conds,
                    close_deal_action = close_deal_action,
                    cooldown_between_deals = cooldown_between_deals,
                    open_deals_and_stop = open_deals_and_stop,
                    timeout_type = timeout_type,
                    amount_type = amount_type,
                    safety_orders_size_type = safety_orders_size_type,
                )
        
            current_user.bots.append(bot)
            db.session.add(bot)

            for i in range(int(safety_orders_count)):
                safetyOrder = SafetyOrder()
                bot.safetyOrders.append(safetyOrder)
                db.session.add(safetyOrder)

            db.session.commit()
            send_notification(f'{bot.name} bot has been created for {symbol}***Bot')
    return jsonify({'message':f"Bot created successfully. Bot ID: {bot.id}",'ok':True})

@app.route('/api/v1/edit_bot/',methods=['POST','GET'])
@jwt_required
def edit_bot():
    conds = request.json["conds"]
    tp_type = str(request.json["tp_type"])
    tp_percent = float(request.json["tp_percent"])
    tp_percent_type = str(request.json["tp_percent_type"]).lower()
    tp_conds = request.json["tp_conds"]
    trailing_take_profit = request.json["trailing_take_profit"]
    trailing_deviation = float(request.json["trailing_deviation"])
    trailing_stop_loss = request.json["trailing_stop_loss"]
    stop_loss = request.json["stop_loss"]
    stop_loss_price_percent = float(request.json["stop_loss_price_percent"])
    stop_loss_time_out = request.json["stop_loss_time_out"]
    stop_loss_time_out_time = int(request.json["stop_loss_time_out_time"])
    Close_deal_after_timeout = request.json["Close_deal_after_timeout"]
    timeout = int(request.json["timeout"])
    timeout_type = int(request.json["timeout_type"]) #hrs mins days
    min_profit = request.json["min_profit"]
    min_profit_type = str(request.json["min_profit_type"])
    min_profit_percent = float(request.json["min_profit_percent"])
    close_deal_action = str(request.json["close_deal_action"])
    if request.json["cooldown_between_deals"]:
        cooldown_between_deals = int(request.json["cooldown_between_deals"])
    else:
        cooldown_between_deals = None
    '''if request.json["open_deals_and_stop"]:
        open_deals_and_stop = int(request.json["open_deals_and_stop"])
    else:
        open_deals_and_stop = None'''
    if request.json["min_volume"]:
        min_volume = float(request.json["min_volume"])
    else:
        min_volume = None
    if request.json["max_price"]:
        max_price = float(request.json["max_price"])
    else:
        max_price = None
    if request.json["min_price"]:
        min_price = float(request.json["min_price"])
    else:
        min_price = None

    if timeout_type == 1:
        timeout = timeout*60*60
    elif timeout_type == 2:
        timeout = timeout*60
    elif timeout_type == 3:
        timeout = timeout*24*60*60
    amounts = []
    bot = Bot.query.filter_by(id=request.json["bot_id"]).first()
    if bot.owner_id != current_user.id:
        return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
    bot.name=request.json["name"]
    #bot.start_order_type=str(request.json["start_order_type"]).lower()
    #bot.strategy=request.json["strategy"]
    bot.stop_loss = stop_loss
    bot.stop_loss_price_percent = stop_loss_price_percent
    bot.trailing_take_profit = trailing_take_profit
    bot.trailing_deviation = trailing_deviation
    bot.trailing_stop_loss = trailing_stop_loss
    bot.stop_loss_time_out = stop_loss_time_out
    bot.stop_loss_time_out_time = stop_loss_time_out_time
    bot.Close_deal_after_timeout = Close_deal_after_timeout
    bot.timeout = timeout
    bot.tp_type = tp_type
    bot.tp_percent = tp_percent
    bot.tp_percent_type = tp_percent_type
    bot.min_volume = min_volume
    bot.max_price = max_price
    bot.min_price = min_price
    bot.min_profit = min_profit
    bot.min_profit_type = min_profit_type
    bot.min_profit_percent = min_profit_percent
    bot.conds = conds
    bot.tp_conds = tp_conds
    bot.close_deal_action = close_deal_action
    bot.cooldown_between_deals = cooldown_between_deals
    if bot.deal_start_price:
        if bot.tp_type == "Percent %":
            tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.tp_percent/100))
            bot.tp_price = tp_price

        elif bot.tp_type == "Conditions":
            tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.min_profit_percent/100))
    #bot.open_deals_and_stop = open_deals_and_stop

    db.session.commit()
    return jsonify({'message':f"Bot created successfully. Bot ID: {bot.id}",'ok':True})


###############################################################################################################

@celery.task
def bot_func_all():
    with app.app_context():
        while True:
            sleep(2)
            bots = Bot.query.all()
            for bot in bots:
                try:
                    print(f"{bot.name} bot is running")
                    current_user = User.query.filter_by(id=bot.owner_id).first()
                    bot = current_user.bots.filter(Bot.id==bot.id).first()
                    exchange_name = bot.exchange
                    symbol = bot.base_currency+"/"+bot.quote_currency
                    tp_percent_type = bot.tp_percent_type
                    start_order_type = bot.start_order_type
                    start_time = time.time()
                
                    if bot.isActive:
                        bot = current_user.bots.filter(Bot.id==bot.id).first()
                        if bot.units == 0:
                            break
                        
                        if bot.Close_deal_after_timeout:
                            elapsed_time = time.time() - start_time
                            if elapsed_time > bot.timeout:
                                break

                        if bot.deal_started and bot.take_profit: 
                            break

                        api_key,api_secret,password = current_user.exchanges.filter(Exchange.name==exchange_name).first().get_creds()
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

                        if current_user.exchanges.filter(Exchange.name==exchange_name).first().demo:
                                exchange.set_sandbox_mode(True)


                        #######################deal-start-conditions########################
                        price,volume = getPrice_assets(exchange_name,symbol,bot.owner_id,True)
                        print("Price: "+str(price))
                        print(symbol)
                        print("Volume (24h): "+str(volume))
                        bot.price_now = price
                        db.session.commit()
                        if (check_indicators_condition(bot.conds, symbol, exchange_name,bot.id) or bot.without_conds == True) and bot.deal_started == False and (bot.max_price is None or price <= bot.max_price) and (bot.min_price is None or price >= bot.min_price) and (bot.min_volume is None or volume >= bot.min_volume):
                            if ((bot.cooldown_between_deals > 0 and bot.cooldown_between_deals - (datetime.utcnow() - bot.last_open_trade_time).seconds <= 0) or (bot.cooldown_between_deals == 0)) and (bot.total_trades <= bot.open_deals_and_stop or bot.open_deals_and_stop == 0):
                                bot.deal_started = True
                                bot.stop_loss_price = price - price * float(bot.stop_loss_price_percent)/100
                                db.session.commit()
                                if start_order_type == 'limit':
                                    order = exchange.create_order(symbol, 'limit', ('buy' if bot.strategy.lower()=='long' else 'sell') , bot.amount, price)
                                    send_notification(f'{bot.name} bot has started a Quick buy on {exchange_name} for {symbol} with {round(float(price * bot.amount),5)} {bot.base_currency}***Limit Buy Order',current_user.id,bot.exchange)
                                else:
                                    order = exchange.create_order(symbol,'market', ('buy' if bot.strategy.lower()=='long' else 'sell'), bot.amount)
                                    send_notification(f'{bot.name} bot has completed a Quick buy on {exchange_name} for {symbol} with {(round(exchange.fetch_order(order["id"],symbol)["price"],5) if exchange.fetch_order(order["id"],symbol) else 0) * bot.amount} {bot.quote_currency}***Market Buy Order',current_user.id,bot.exchange)
                                
                                order = exchange.fetch_order(order["id"],symbol)
                                bot.deal_start_price = order['price'] if order['price'] else price
                                deal_order = exchange.fetch_order(order["id"],symbol)
                                if deal_order["price"]:
                                    bot.buy_price = deal_order["price"]
                                else:
                                    bot.buy_price = price
                                bot.total_trades = bot.total_trades + 1
                                if deal_order["fee"]:
                                    bot.amount = bot.amount - deal_order["fee"]["cost"]
                                    bot.units = bot.units - deal_order["fee"]["cost"]
                                    bot.total_volume = bot.total_volume - deal_order["fee"]["cost"]
                                db.session.commit()

                            #########################Safety_orders#########################

                            #check if there any open safety order has filled
                            for safetyOrder in bot.safetyOrders.filter(SafetyOrder.isOpened==True).all():
                                safety_ord = exchange.fetch_order(safetyOrder.orderId,symbol)
                                if safety_ord["status"] == "closed":
                                    safetyOrder.isOpened = False
                                    safetyOrder.isClosed = True
                                    bot.safety_orders_count_active = bot.safety_orders_count_active - 1
                                    bot.total_volume = bot.total_volume - safetyOrder.amount - (safety_ord["fee"]["cost"] if safety_ord["fee"] else 0)
                                    db.session.commit()

                            #put new saftey orders
                            buy_price_deviation_percentage = 0
                            for index, safetyOrder in enumerate(bot.safetyOrders.all()):
                                buy_price_deviation_percentage = buy_price_deviation_percentage + (bot.safety_orders_deviation_scale ** index)
                                if safetyOrder.isOpened == False and safetyOrder.isClosed == False and bot.safety_orders_count_active < bot.safety_orders_count_max_active and bot.safety_orders_count_active>0:
                                    print("safety Order No."+str(index+1)+" Deviation: "+str(buy_price_deviation_percentage)+"%")
                                    print(bot.safety_orders_size*(bot.safety_orders_size_scale**index))
                                    order = exchange.create_order(symbol, 'limit', ('buy' if bot.strategy.lower()=='long' else 'sell'), bot.safety_orders_size*(bot.safety_orders_size_scale**index), bot.buy_price*((100 - buy_price_deviation_percentage)/100))
                                    safetyOrder.isOpened = True
                                    safetyOrder.orderId = order["id"]
                                    bot.total_volume = bot.total_volume + bot.safety_orders_size*(bot.safety_orders_size_scale**index)
                                    bot.safety_orders_count_active = bot.safety_orders_count_active + 1
                                    safetyOrder.amount = bot.safety_orders_size*(bot.safety_orders_size_scale**index)
                                    db.session.commit()

                        #######################take-profit-conditions########################
                        if bot.deal_started and bot.take_profit == False:
                            #take profit without conditions based on a percent
                            #symbol_order = symbol if profit_currency == "quote" else symbol.split('/')[1] + '/' + symbol.split('/')[0]
                            symbol_order = symbol
                            #price = getPrice(exchange_name,symbol)
                            if bot.tp_type == "Percent %":
                                tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.tp_percent/100))
                                bot.tp_price = tp_price
                                if price >= tp_price:
                                    if not bot.trailing_take_profit:
                                        order = exchange.create_order(symbol_order, "market", ('sell' if bot.strategy.lower()=='long' else 'buy'),(bot.amount if tp_percent_type == "base" else bot.total_volume))
                                        bot.units = 0
                                        sell_price_ord = exchange.fetch_order(order["id"],symbol)["price"]
                                        bot.sell_price = sell_price_ord
                                        bot.deal_started = False
                                        bot.total_profit = bot.total_profit + ((sell_price_ord - bot.buy_price) if bot.quote_currency == "USDT" else (sell_price_ord - bot.buy_price) * getPrice_assets(exchange_name,symbol_order.split('/')[1] + '/USDT'))
                                        db.session.commit()
                                        send_notification(f'{bot.name} bot has completed a Take Profit for {bot.base_currency} on {exchange_name} with {round(price,4) * (bot.amount if tp_percent_type == "base" else bot.total_volume)} {bot.quote_currency}***Market Sell Order',current_user.id,bot.exchange)
                                        bot.isActive = False
                                    bot.take_profit = True
                                    bot.last_price = bot.sell_price
                                    
                                    #bot.take_profit_details = f"Take Profit Percent {bot.tp_percent} {profit_currency}"
                                db.session.commit()
                                
                            elif bot.tp_type == "Conditions":
                                tpGateIsOpened = False
                                if bot.min_profit:
                                    tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.min_profit_percent/100))
                                    bot.tp_price = tp_price
                                    if price >= tp_price:
                                        tpGateIsOpened = True
                                        db.session.commit()

                                if check_indicators_condition(bot.tp_conds,symbol,exchange_name,bot.id) and (tpGateIsOpened or bot.min_profit == False):
                                    order = exchange.create_order(symbol,'market', ('sell' if bot.strategy.lower()=='long' else 'buy'), (bot.amount if tp_percent_type == "base" else bot.total_volume))
                                    send_notification(f'{bot.name} bot has completed a Take Profit for {bot.base_currency} on {exchange_name} with {round(exchange.fetch_order(order["id"],symbol)["price"],4) * (bot.amount if tp_percent_type == "base" else bot.total_volume)} {bot.quote_currency} ***Market Sell Order',current_user.id,bot.exchange)
                                    bot.take_profit = True
                                    bot.units = 0
                                    bot.sell_price = exchange.fetch_order(order["id"],symbol)["price"]
                                    bot.deal_started = False
                                    bot.isActive = False
                                    db.session.commit()
                        
                        #######################-----Trailing-----########################
                        #price = getPrice(exchange_name,symbol,bot.owner_id)
                        if bot.deal_started and (bot.trailing_stop_loss or (bot.trailing_take_profit and bot.tp_type == "Percent %" and bot.take_profit)):
                            if price > bot.last_price:
                                # Update stop loss price
                                bot.last_price = price
                                if bot.trailing_stop_loss:
                                    bot.stop_loss_price = price - price * float(bot.stop_loss_price_percent)/100
                                if bot.trailing_take_profit  and bot.tp_type == "Percent %" and bot.take_profit:
                                    bot.stop_loss_price = price - price * float(bot.trailing_deviation)/100
                            db.session.commit()

                        #######################stop-loss-sell########################
                        print("Remaining units:", bot.units)
                        if bot.deal_started and price <= bot.stop_loss_price and bot.units > 0 and (bot.stop_loss or bot.trailing_take_profit):
                            # Making the stop loss sell order
                            if bot.stop_loss_time_out:
                                sleep(bot.stop_loss_time_out_time)

                            trailing_order = exchange.create_order(symbol, 'market', ('sell' if bot.strategy.lower()=='long' else 'buy'), bot.units)
                            bot.deal_started = False
                            if int(bot.close_deal_action) == 1:
                                bot.take_profit = False
                                bot.units = bot.amount
                                bot.isActive = True
                                bot.deal_start_price = None
                            elif int(bot.close_deal_action) == 2:
                                bot.units = 0
                                bot.isActive = False
                                bot.take_profit = False

                            sell_price_ord_sl = exchange.fetch_order(trailing_order["id"],symbol)["price"]
                            bot.sell_price = sell_price_ord_sl
                            bot.total_profit = bot.total_profit + ((sell_price_ord_sl - bot.buy_price) if bot.quote_currency == "USDT" else (sell_price_ord_sl - bot.buy_price) * getPrice_assets(exchange_name,symbol.split('/')[1] + '/USDT'))
                            db.session.commit()
                            # Send notification
                            message = f"{bot.name} bot has completed a Stop loss sell order for {symbol} on {bot.exchange} by {price * bot.units} {bot.quote_currency}***Bot"
                            send_notification(message, current_user.id,bot.exchange)
                    db.session.commit()
                except Exception as e:
                    print(e)
                    continue
                print(f"Elapsed time: {time.time() - start_time} seconds")

def check_indicators_condition(conds,symbol,exchange,bot_id):
    MACDisTrue1 = True
    MACDisTrue2 = True
    RSIisTrue = True
    CCIisTrue = True
    BollingerisTrue = True
    UltoscisTrue = True
    ADXisTrue = True
    TradingViewisTrue = True

    with app.app_context():
        bot = Bot.query.filter_by(id=bot_id).first()
        symbol = symbol.replace("/","")
        for cond in conds:
            if cond['indicator']=="RSI":
                RSIisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                rsi = talib.RSI(data.close, int(cond_data['RSI Length']))
                data.loc[:, 'rsi'] = rsi
                rsi = data.to_dict(orient='records')[-2:]
                cond['value'] = rsi[-1]['rsi']
                print(cond_data['Signal Value'])
                if cond_data['Condition'] == 'Greater than':
                    if rsi[-1]['rsi'] > float(cond_data['Signal Value']):
                        RSIisTrue = True
                    else:
                        RSIisTrue = False
                elif cond_data['Condition'] == 'Less than':
                    if rsi[-1]['rsi'] < float(cond_data['Signal Value']):
                        RSIisTrue = True
                    else:
                        RSIisTrue = False
                elif cond_data['Condition'] == 'Crossing Up':
                    if rsi[-1]['rsi'] > float(cond_data['Signal Value']) and rsi[-2]['rsi'] < float(cond_data['Signal Value']):
                        RSIisTrue = True
                    else:
                        RSIisTrue = False
                elif cond_data['Condition'] == 'Crossing Down':
                    if rsi[-1]['rsi'] < float(cond_data['Signal Value']) and rsi[-2]['rsi'] > float(cond_data['Signal Value']):
                        RSIisTrue = True
                    else:
                        RSIisTrue = False

            if cond['indicator']=="MACD":
                MACDisTrue1 = False
                MACDisTrue2 = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                macd, signal, hist = talib.MACD(data.close, int(cond_data['Fast Length']), int(cond_data['Slow Length']), int(cond_data['Signal Length']))
                data.loc[:, 'macd'] = macd
                data.loc[:, 'signal'] = signal
                data.loc[:, 'hist'] = hist
                macd = data.to_dict(orient='records')[-1]['macd']
                signal = data.to_dict(orient='records')[-1]['signal']
                hist = data.to_dict(orient='records')[-1]['hist']
                cond['value'] = hist
                if cond_data['MACD Trigger'] == 'Crossing Up':
                    if hist > 0:
                        MACDisTrue1 = True
                    else:
                        MACDisTrue1 = False
                elif cond_data['MACD Trigger'] == 'Crossing Down':
                    if hist < 0:
                        MACDisTrue1 = True
                    else:
                        MACDisTrue1 = False

                if cond_data['Line Trigger'] == 'Greater Than 0':
                    if signal > 0:
                        MACDisTrue2 = True
                    else:
                        MACDisTrue2 = False
                elif cond_data['Line Trigger'] == 'Less Than 0':
                    if signal < 0:
                        MACDisTrue2 = True
                    else:
                        MACDisTrue2 = False

            if cond['indicator']=="Commodity Channel Index":
                CCIisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                cci = talib.CCI(data.high, data.low, data.close, timeperiod=20)
                data.loc[:, 'cci'] = cci
                fullCCI = data.to_dict(orient='records')[-2:]
                cond['value'] = fullCCI[-1]['cci']
                if cond_data['Condition'] == 'Greater Than':
                    if fullCCI[-1]['cci'] > float(cond_data['Signal Value']):
                        CCIisTrue = True
                    else:
                        CCIisTrue = False
                elif cond_data['Condition'] == 'Less Than':
                    if fullCCI[-1]['cci'] < float(cond_data['Signal Value']):
                        CCIisTrue = True
                    else:
                        CCIisTrue = False
                elif cond_data['Condition'] == 'Crossing Up':
                    if fullCCI[-1]['cci'] > float(cond_data['Signal Value']) and fullCCI[-2]['cci'] < float(cond_data['Signal Value']):
                        CCIisTrue = True
                    else:
                        CCIisTrue = False
                elif cond_data['Condition'] == 'Crossing Down':
                    if fullCCI[-1]['cci'] < float(cond_data['Signal Value']) and fullCCI[-2]['cci'] > float(cond_data['Signal Value']):
                        CCIisTrue = True
                    else:
                        CCIisTrue = False
                        
            if cond['indicator']=="Bollinger Bands":
                BollingerisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                upper_band, middle_band, lower_band = talib.BBANDS(data.close, timeperiod=int(cond_data["BB% Period"]), nbdevup=int(cond_data["Deviation"]), nbdevdn=int(cond_data["Deviation"]))
                data.loc[:, 'upper_band'] = upper_band
                data.loc[:, 'middle_band'] = middle_band
                data.loc[:, 'lower_band'] = lower_band
                upper_band = data.to_dict(orient='records')[-1]['upper_band']
                middle_band = data.to_dict(orient='records')[-1]['middle_band']
                lower_band = data.to_dict(orient='records')[-1]['lower_band']
                close = data.to_dict(orient='records')[-1]['close']
                bb_percentage = (close - lower_band) / (upper_band - lower_band)
                crossing_up = (bb_percentage < float(cond_data["Signal Value"])) & (bb_percentage >= float(cond_data["Signal Value"]))
                crossing_down = (bb_percentage > float(cond_data["Signal Value"])) & (bb_percentage <= float(cond_data["Signal Value"]))
                greater_than = bb_percentage > float(cond_data["Signal Value"])
                less_than = bb_percentage < float(cond_data["Signal Value"])
                cond['value'] = bb_percentage
                if cond_data["Condition"] == "Greather Than":
                    if greater_than:
                        BollingerisTrue = True
                    else:
                        BollingerisTrue = False
                elif cond_data["Condition"] == "Less Than":
                    if less_than:
                        BollingerisTrue = True
                    else:
                        BollingerisTrue = False
                elif cond_data["Condition"] == "Crossing Up":
                    if crossing_up:
                        BollingerisTrue = True
                    else:
                        BollingerisTrue = False
                elif cond_data["Condition"] == "Crossing Down":
                    if crossing_down:
                        BollingerisTrue = True
                    else:
                        BollingerisTrue = False
            if cond['indicator'] == 'Ultimate Oscillator':
                UltoscisTrue = False    
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                ultosc = talib.ULTOSC(data.high, data.low, data.close, timeperiod1=int(cond_data["Fast Length"]), timeperiod2=int(cond_data["Middle Length"]), timeperiod3=int(cond_data["Slow Length"]))
                data.loc[:, 'ultosc'] = ultosc
                fullUltosc = data.to_dict(orient='records')[-2:]
                cond['value'] = fullUltosc[-1]['ultosc']
                if cond_data['Condition'] == 'Greater Than':
                    if fullUltosc[-1]['ultosc'] > float(cond_data['Signal Value']):
                        UltoscisTrue = True
                    else:
                        UltoscisTrue = False
                elif cond_data['Condition'] == 'Less Than':
                    if fullUltosc[-1]['ultosc'] < float(cond_data['Signal Value']):
                        UltoscisTrue = True
                    else:
                        UltoscisTrue = False
                elif cond_data['Condition'] == 'Crossing Up':
                    if fullUltosc[-1]['ultosc'] > float(cond_data['Signal Value']) and fullUltosc[-2]['ultosc'] < float(cond_data['Signal Value']):
                        UltoscisTrue = True
                    else:
                        UltoscisTrue = False
                elif cond_data['Condition'] == 'Crossing Down':
                    if fullUltosc[-1]['ultosc'] < float(cond_data['Signal Value']) and fullUltosc[-2]['ultosc'] > float(cond_data['Signal Value']):
                        UltoscisTrue = True
                    else:
                        UltoscisTrue = False

            if cond['indicator'] == 'Average Directional Index':
                ADXisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                adx = talib.ADX(data.high, data.low, data.close, timeperiod=int(cond_data["ADX and DI Length"]))
                data.loc[:, 'adx'] = adx
                fullAdx = data.to_dict(orient='records')[-2:]
                cond['value'] = fullAdx[-1]['adx']
                if cond_data['Condition'] == 'Greater Than':
                    if fullAdx[-1]['adx'] > float(cond_data['Signal Value']):
                        ADXisTrue = True
                    else:
                        ADXisTrue = False
                elif cond_data['Condition'] == 'Less Than':
                    if fullAdx[-1]['adx'] < float(cond_data['Signal Value']):
                        ADXisTrue = True
                    else:
                        ADXisTrue = False
                elif cond_data['Condition'] == 'Crossing Up':
                    if fullAdx[-1]['adx'] > float(cond_data['Signal Value']) and fullAdx[-2]['adx'] < float(cond_data['Signal Value']):
                        ADXisTrue = True
                    else:
                        ADXisTrue = False
                elif cond_data['Condition'] == 'Crossing Down':
                    if fullAdx[-1]['adx'] < float(cond_data['Signal Value']) and fullAdx[-2]['adx'] > float(cond_data['Signal Value']):
                        ADXisTrue = True
                    else:
                        ADXisTrue = False

            if cond['indicator']=="TradingView Crypto Screener":
                TradingViewisTrue = False
                cond_data = cond['conds']
                data = fetch_data2(symbol,exchange,cond_data['Timeframe'])['summary']['RECOMMENDATION']
                cond['value'] = data
                if data == cond_data['Signal Value'].upper():
                    TradingViewisTrue = True
                else:
                    TradingViewisTrue = False
            
        bot.conds = conds
        db.session.commit()

    return MACDisTrue1 and MACDisTrue2 and CCIisTrue and RSIisTrue and BollingerisTrue and UltoscisTrue and ADXisTrue and TradingViewisTrue

'''def check_indicators_condition(conds,symbol,exchange):
    MACDisTrue1 = True
    MACDisTrue2 = True
    RSIisTrue = True
    CCIisTrue = True
    BollingerisTrue = True
    UltoscisTrue = True
    ADXisTrue = True
    symbol = symbol.replace("/","")
    for cond in conds:
        if cond['indicator']=="RSI":
            RSIisTrue = False
            cond_data = cond['conds']
            rsi = fetch_data2(symbol,exchange,cond_data['Timeframe'])["indicators"]
            print(cond_data['Signal Value'])
            if cond_data['Condition'] == 'Greater than':
                if rsi["RSI"] > float(cond_data['Signal Value']):
                    RSIisTrue = True
                else:
                    RSIisTrue = False
            elif cond_data['Condition'] == 'Less than':
                if rsi["RSI"] < float(cond_data['Signal Value']):
                    RSIisTrue = True
                else:
                    RSIisTrue = False
            elif cond_data['Condition'] == 'Crossing Up':
                if rsi["RSI"] > float(cond_data['Signal Value']) and rsi["RSI[1]"] < float(cond_data['Signal Value']):
                    RSIisTrue = True
                else:
                    RSIisTrue = False
            elif cond_data['Condition'] == 'Crossing Down':
                if rsi["RSI"] < float(cond_data['Signal Value']) and rsi["RSI[1]"] > float(cond_data['Signal Value']):
                    RSIisTrue = True
                else:
                    RSIisTrue = False

        if cond['indicator']=="MACD":
            MACDisTrue1 = False
            MACDisTrue2 = False
            cond_data = cond['macd']
            macd = fetch_data2(symbol,exchange,cond_data['Timeframe'])["indicators"]
            macd = macd["MACD.macd"]
            signal = macd["MACD.signal"]
            hist = signal - macd

            if cond_data['MACD Trigger'] == 'Crossing Up':
                if hist > 0:
                    MACDisTrue1 = True
                else:
                    MACDisTrue1 = False
            elif cond_data['MACD Trigger'] == 'Crossing Down':
                if hist < 0:
                    MACDisTrue1 = True
                else:
                    MACDisTrue1 = False

            if cond_data['Line Trigger'] == 'Greater Than 0':
                if signal > 0:
                    MACDisTrue2 = True
                else:
                    MACDisTrue2 = False
            elif cond_data['Line Trigger'] == 'Less Than 0':
                if signal < 0:
                    MACDisTrue2 = True
                else:
                    MACDisTrue2 = False

        if cond['indicator']=="Commodity Channel Index":
            CCIisTrue = False
            cond_data = cond['conds']
            cci = fetch_data2(symbol,exchange,cond_data['Timeframe'])
            if cond_data['Condition'] == 'Greater Than':
                if cci['CCI20'] > float(cond_data['Signal Value']):
                    CCIisTrue = True
                else:
                    CCIisTrue = False
            elif cond_data['Condition'] == 'Less Than':
                if cci['CCI20'] < float(cond_data['Signal Value']):
                    CCIisTrue = True
                else:
                    CCIisTrue = False
            elif cond_data['Condition'] == 'Crossing Up':
                if cci['CCI20'] > float(cond_data['Signal Value']) and cci['CCI20[1]'] < float(cond_data['Signal Value']):
                    CCIisTrue = True
                else:
                    CCIisTrue = False
            elif cond_data['Condition'] == 'Crossing Down':
                if cci['CCI20'] < float(cond_data['Signal Value']) and cci['CCI20[1]'] > float(cond_data['Signal Value']):
                    CCIisTrue = True
                else:
                    CCIisTrue = False
                    
        if cond['indicator']=="Bollinger Bands":
            BollingerisTrue = False
            cond_data = cond['conds']
            data = fetch_data2(symbol,exchange,cond_data['Timeframe'])
            upper_band, middle_band, lower_band = talib.BBANDS(data.close, timeperiod=int(cond_data["BB% Period"]), nbdevup=int(cond_data["Deviation"]), nbdevdn=int(cond_data["Deviation"]))
            data.loc[:, 'upper_band'] = upper_band
            data.loc[:, 'middle_band'] = middle_band
            data.loc[:, 'lower_band'] = lower_band
            upper_band = data.to_dict(orient='records')[-1]['upper_band']
            middle_band = data.to_dict(orient='records')[-1]['middle_band']
            lower_band = data.to_dict(orient='records')[-1]['lower_band']
            close = data.to_dict(orient='records')[-1]['close']
            bb_percentage = (close - lower_band) / (upper_band - lower_band)
            print(bb_percentage)
            print(BollingerisTrue)
            crossing_up = (bb_percentage < float(cond_data["Signal Value"])) & (bb_percentage >= float(cond_data["Signal Value"]))
            crossing_down = (bb_percentage > float(cond_data["Signal Value"])) & (bb_percentage <= float(cond_data["Signal Value"]))
            greater_than = bb_percentage > float(cond_data["Signal Value"])
            less_than = bb_percentage < float(cond_data["Signal Value"])
            if cond_data["Condition"] == "Greather Than":
                if greater_than:
                    BollingerisTrue = True
                else:
                    BollingerisTrue = False
            elif cond_data["Condition"] == "Less Than":
                if less_than:
                    BollingerisTrue = True
                else:
                    BollingerisTrue = False
            elif cond_data["Condition"] == "Crossing Up":
                if crossing_up:
                    BollingerisTrue = True
                else:
                    BollingerisTrue = False
            elif cond_data["Condition"] == "Crossing Down":
                if crossing_down:
                    BollingerisTrue = True
                else:
                    BollingerisTrue = False
        if cond['indicator'] == 'Ultimate Oscillator':
            UltoscisTrue = False    
            cond_data = cond['conds']
            data = fetch_data2(symbol,exchange,cond_data['Timeframe'])
            ultosc = talib.ULTOSC(data.high, data.low, data.close, timeperiod1=int(cond_data["Fast Length"]), timeperiod2=int(cond_data["Middle Length"]), timeperiod3=int(cond_data["Slow Length"]))
            data.loc[:, 'ultosc'] = ultosc
            fullUltosc = data.to_dict(orient='records')[-2:]['ultosc']
            if cond_data['Condition'] == 'Greater Than':
                if fullUltosc[-1]['ultosc'] > float(cond_data['Signal Value']):
                    UltoscisTrue = True
                else:
                    UltoscisTrue = False
            elif cond_data['Condition'] == 'Less Than':
                if fullUltosc[-1]['ultosc'] < float(cond_data['Signal Value']):
                    UltoscisTrue = True
                else:
                    UltoscisTrue = False
            elif cond_data['Condition'] == 'Crossing Up':
                if fullUltosc[-1]['ultosc'] > float(cond_data['Signal Value']) and fullUltosc[-2]['ultosc'] < float(cond_data['Signal Value']):
                    UltoscisTrue = True
                else:
                    UltoscisTrue = False
            elif cond_data['Condition'] == 'Crossing Down':
                if fullUltosc[-1]['ultosc'] < float(cond_data['Signal Value']) and fullUltosc[-2]['ultosc'] > float(cond_data['Signal Value']):
                    UltoscisTrue = True
                else:
                    UltoscisTrue = False
        if cond['indicator'] == 'Average Directional Index':
            ADXisTrue = False
            cond_data = cond['conds']
            data = fetch_data2(symbol,exchange,cond_data['Timeframe'])
            adx = talib.ADX(data.high, data.low, data.close, timeperiod=int(cond_data["ADX and DI Length"]))
            data.loc[:, 'adx'] = adx
            fullAdx = data.to_dict(orient='records')[-2:]['adx']
            if cond_data['Condition'] == 'Greater Than':
                if fullAdx[-1]['adx'] > float(cond_data['Signal Value']):
                    ADXisTrue = True
                else:
                    ADXisTrue = False
            elif cond_data['Condition'] == 'Less Than':
                if fullAdx[-1]['adx'] < float(cond_data['Signal Value']):
                    ADXisTrue = True
                else:
                    ADXisTrue = False
            elif cond_data['Condition'] == 'Crossing Up':
                if fullAdx[-1]['adx'] > float(cond_data['Signal Value']) and fullAdx[-2]['adx'] < float(cond_data['Signal Value']):
                    ADXisTrue = True
                else:
                    ADXisTrue = False
            elif cond_data['Condition'] == 'Crossing Down':
                if fullAdx[-1]['adx'] < float(cond_data['Signal Value']) and fullAdx[-2]['adx'] > float(cond_data['Signal Value']):
                    ADXisTrue = True
                else:
                    ADXisTrue = False
            
    return MACDisTrue1 and MACDisTrue2 and CCIisTrue and RSIisTrue and BollingerisTrue and UltoscisTrue and ADXisTrue'''