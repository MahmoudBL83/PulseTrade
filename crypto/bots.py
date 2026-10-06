from crypto.functions import getPrice,getPrice_assets
import json
from flask import render_template, request, redirect, url_for, jsonify,Response
import ccxt
from flask_login import login_required,current_user
from crypto import app,db,celery, jwt_required
from crypto.models import User, Exchange, Bot, SafetyOrder, Post, Pair, Transaction
from crypto.notify import send_notification
from crypto.dataStream_indicators import fetch_data,fetch_data2
from crypto.talib_compat import talib
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
                                    bots=Bot.query.filter(Bot.owner_id==current_user.id,Bot.is_hidden==False).all(),
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
    pairs_indicators = []
    for pair in Pair.query.filter(Pair.isActive==True).all():
        pairs_indicators.append(pair.serialize()['pair'])
        
    return render_template('bots_create.html',
                            pairs_indicators = pairs_indicators,
                            pairs=pairs,
                            notifications=current_user.notifications.all(),
                            exchanges = current_user.exchanges.all(),
                            symbol=request.args.get('symbol'),
                            exchange=request.args.get('exchange'),
                            current_user=current_user,
                            posts = Post.query.all()
                        )

@app.route('/api/v1/toggle_bot',methods=['POST','GET'])
@jwt_required
def toggle_bot():
    bot_id = request.json["bot_id"]
    bot = Bot.query.filter_by(id=bot_id).first()
    if bot.owner_id != current_user.id:
        return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
    
    if request.json["state"]:
        if current_user.subType.max_bots:
            if current_user.subType.max_bots <= len(Bot.query.filter(Bot.isActive == True, Bot.is_hidden == False, Bot.owner_id==current_user.id).all()):
                return jsonify({'message':f"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})
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
    
    exchange = connectExchange(bot.exchange,bot.owner_id)

    try:
        if bot.units > 0:
            if bot.strategy.lower() == "long":
                try:
                    exchange.create_order(bot.symbol, 'market', 'sell', bot.units)
                    err_msg = ""
                    status = True
                except Exception as e:
                    err_msg = str(e)
                    status = False
            else:
                try:
                    exchange.create_order(bot.symbol, 'market', 'buy', bot.units)
                    err_msg = ""
                    status = True
                except Exception as e:
                    err_msg = str(e)
                    status = False
            trans = Transaction(
                user_id = bot.owner_id,
                bot_id = bot.id,
                type = "sell" if bot.strategy.lower() == "long" else "buy",
                status = status,
                err_msg = err_msg,
                amount = bot.units,
                symbol = bot.symbol,
                exchange = bot.exchange,
                value=bot.price_now,
            )
            db.session.add(trans)
            bot.transactions.append(trans)
    except Exception as e:
        print(e)
        pass

    bot.is_hidden = True
    #db.session.delete(bot)
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

        safety_orders = []
        for safety_order in SafetyOrder.query.filter_by(owner_id=bot.id).all():
            safety_orders.append({
                "id":safety_order.id,
                "isOpened":safety_order.isOpened,
                "isFilled":safety_order.isFilled,
                "isClosed":safety_order.isClosed,
                "orderId":safety_order.orderId,
                "amount":safety_order.amount,
                "price":safety_order.price,
            })

        return jsonify({
            'name':bot.name,
            'last_price':bot.last_price if bot.last_price is not None else 0,
            'symbol':bot.base_currency+"/"+bot.quote_currency,
            "symbols":str(bot.symbols),
            'isActive':bot.isActive,
            'deal_started':bot.deal_started,
            'take_profit':bot.take_profit if bot.take_profit is not None else 0,
            'tp_type':bot.tp_type,
            'tp_percent_type':bot.tp_percent_type,
            'tp_percent':bot.tp_percent,
            'trailing_take_profit':bot.trailing_take_profit,
            'trailing_stop_loss':bot.trailing_stop_loss,
            'units':bot.units if bot.units is not None else 0,
            'amount':bot.amount if bot.amount is not None else 0,
            'sell_price':bot.sell_price if bot.sell_price is not None else 0,
            'stop_loss_price':bot.stop_loss_price if bot.stop_loss_price is not None else 0,
            'buy_price':bot.buy_price if bot.buy_price is not None else 0,
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
            "tp_price":bot.tp_price if bot.tp_price is not None else 0,
            'price_now':bot.price_now if bot.price_now is not None else 0,
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
            'safety_orders':safety_orders,
            'transactions': [x.serialize() for x in bot.transactions.all()],
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
        bot.deal_started = False
        bot.take_profit = False
        bot.last_price = 0
        bot.sell_price = 0
        bot.stop_loss_time_out_runned = False
        bot.units = bot.amount
        bot.tp_price = 0
        bot.isActive = True
        for safety_order in bot.safetyOrders:
            safety_order.isFilled = False
            safety_order.isOpened = False
            safety_order.isClosed = False   
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
        if current_user.subType.max_bots:
            if current_user.subType.max_bots < len(Bot.query.filter(Bot.is_hidden == False, Bot.owner_id==current_user.id, Bot.isActive).all()) + 1:
                return jsonify({'message':f"You have reached your maximum number of bots. Upgrade your subscription to create more bots",'ok':False})
    else:
        if current_user.subType.max_bots:
            if current_user.subType.max_bots < len(symbols) + len(Bot.query.filter(Bot.is_hidden == False, Bot.owner_id==current_user.id, Bot.isActive).all()):
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
        pair_query = Pair.query.filter(Pair.pair == symbol).first()
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
                    conds = conds if (pair_query and pair_query.isActive) else [],
                    tp_conds = tp_conds if (pair_query and pair_query.isActive) else [],
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
            pair_query = Pair.query.filter(Pair.pair == symbol).first()
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
                    conds = conds if (pair_query and pair_query.isActive) else [],
                    tp_conds = tp_conds if (pair_query and pair_query.isActive) else [],
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
    amount = float(request.json["amount"])
    amount_type = int(request.json["amount_type"])
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
    safety_orders_size = float(request.json["safety_orders_size"]) 
    safety_orders_size_scale = float(request.json["safety_orders_size_scale"])
    safety_orders_deviation = float(request.json["safety_orders_deviation"])
    safety_orders_deviation_scale = float(request.json["safety_orders_deviation_scale"])
    safety_orders_count = float(request.json["safety_orders_count"])
    safety_orders_count_max_active = float(request.json["safety_orders_count_max_active"])
    safety_orders_size_type = int(request.json["safety_orders_size_type"])

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
    bot = Bot.query.filter_by(id=request.json["bot_id"]).first()
    priceNow2 = getPrice(bot.exchange,bot.symbol)
    if amount_type == 1:
        amount = amount/priceNow2
    elif amount_type == 2:
        amount = amount
    # the user will pass the amoutn as percentage of teh usdt balance
    elif amount_type == 3:
        exchange = connectExchange(bot.exchange,bot.owner_id)
        amount = ((amount/100)*exchange.fetch_balance()[bot.symbol.split("/")[1]]['free'])/priceNow2

    amounts = []
    
    if bot.owner_id != current_user.id:
        return jsonify({'message':f"You don't have permission to delete this bot",'ok':False})
    
    if bot.deal_started == False:
        bot.amount = amount
        bot.units = amount
        '''
        bot.total_volume = bot.total_volume + bot.safety_orders_size*(bot.safety_orders_size_scale**index)
        bot.safety_orders_count_active = bot.safety_orders_count_active + 1
        '''
        total_volume = amount
        for i in range(int(bot.safety_orders_count_active)):
            total_volume = total_volume + bot.safety_orders_size*(bot.safety_orders_size_scale*i)
        
        bot.total_volume = total_volume
            

    if safety_orders_size_type == 1:
        safety_orders_size = safety_orders_size/priceNow2
    elif safety_orders_size_type == 2:
        safety_orders_size = safety_orders_size
    else:
        safety_orders_size = ((safety_orders_size/100)*exchange.fetch_balance()[bot.symbol.split("/")[1]]['free'])/priceNow2
        
    bot.safety_orders_size = safety_orders_size
    bot.safety_orders_size_scale = safety_orders_size_scale
    bot.safety_orders_deviation = safety_orders_deviation
    bot.safety_orders_deviation_scale = safety_orders_deviation_scale
    bot.safety_orders_count = safety_orders_count
    bot.safety_orders_count_max_active = safety_orders_count_max_active
    bot.safety_orders_size_type = safety_orders_size_type
    
    bot.name=request.json["name"]
    #bot.start_order_type=str(request.json["start_order_type"]).lower()
    #bot.strategy=request.json["strategy"]
    bot.stop_loss = stop_loss
    bot.stop_loss_price_percent = stop_loss_price_percent
    bot.trailing_take_profit = trailing_take_profit
    if trailing_take_profit == False and bot.sell_price == 0:
        bot.take_profit = False
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


from math import ceil
@celery.task
def bot_func_all(page):
    with app.app_context():
        while True:
            sleep(0.1)
            # Set the number of bots per page
            bots_per_page = 100

            # Calculate the starting index for the slice
            start_index = (page - 1) * bots_per_page

            # Query all bots that are not hidden
            all_bots = Bot.query.filter(Bot.is_hidden == False).all()

            # Calculate the total number of pages
            total_pages = ceil(len(all_bots) / bots_per_page)

            # Get the bots for the current page using slicing
            bots = all_bots[start_index:start_index + bots_per_page]
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
                            db.session.commit()
                            break
                        
                        if bot.Close_deal_after_timeout:
                            elapsed_time = time.time() - start_time
                            if elapsed_time > bot.timeout:
                                db.session.commit()
                                break

                        '''if bot.deal_started and bot.take_profit: 
                            break'''

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
                        bot.price_now = price
                        #db.session.commit()
                        if (check_indicators_condition(bot.conds, symbol, exchange_name,bot.id) or bot.without_conds == True) and bot.deal_started == False and (bot.max_price is None or price <= bot.max_price) and (bot.min_price is None or price >= bot.min_price) and (bot.min_volume is None or volume >= bot.min_volume) and price > 0:
                            if ((bot.cooldown_between_deals > 0 and bot.cooldown_between_deals - (datetime.utcnow() - bot.last_open_trade_time).seconds <= 0) or (bot.cooldown_between_deals == 0)) and (bot.total_trades <= bot.open_deals_and_stop or bot.open_deals_and_stop == 0):
                                
                                if bot.strategy.lower()=='long':
                                    bot.stop_loss_price = price - price * float(bot.stop_loss_price_percent)/100
                                else:
                                    bot.stop_loss_price = price + price * float(bot.stop_loss_price_percent)/100
                                #db.session.commit()
                                if start_order_type == 'limit':
                                    try:
                                        order = exchange.create_order(symbol, 'limit', ('buy' if bot.strategy.lower()=='long' else 'sell') , bot.amount, price)
                                        send_notification(f'{bot.name} bot has started a Quick buy on {exchange_name} for {symbol} with {round(float(price * bot.amount),5)} {bot.quote_currency}***Limit Buy Order',current_user.id,bot.exchange)
                                        err_msg = ""
                                        status = True
                                    except Exception as e: 
                                        err_msg = str(e)
                                        status = False
                                        order = None
                                        send_notification(f'{bot.name} bot has failed to start a Quick buy on {exchange_name} for {symbol} with {round(float(price * bot.amount),5)} {bot.quote_currency}***Limit Buy Order',current_user.id,bot.exchange)
                                    
                                else:
                                    try:
                                        order = exchange.create_order(symbol,'market', ('buy' if bot.strategy.lower()=='long' else 'sell'), bot.amount)
                                        #send_notification(f'{bot.name} bot has completed a Quick buy on {exchange_name} for {symbol} with {round((exchange.fetch_order(order["id"],symbol)["price"] * bot.amount if exchange.fetch_order(order["id"],symbol) else (0)),5)} {bot.quote_currency}***Market Buy Order',current_user.id,bot.exchange)
                                        send_notification(f'{bot.name} bot has started a Quick {("buy" if bot.strategy.lower()=="long" else "sell")} on {exchange_name} for {symbol} with {round(float(price * bot.amount),5)} {bot.quote_currency}***Market {("buy" if bot.strategy.lower()=="long" else "sell")} Order',current_user.id,bot.exchange)
                                        err_msg = ""
                                        status = True
                                    except Exception as e:
                                        err_msg = str(e)
                                        status = False
                                        order = None
                                        send_notification(f'{bot.name} bot has failed to start a Quick {("buy" if bot.strategy.lower()=="long" else "sell")} on {exchange_name} for {symbol} with {round(float(price * bot.amount),5)} {bot.quote_currency}***Market {("buy" if bot.strategy.lower()=="long" else "sell")} Order',current_user.id,bot.exchange)
                                try:
                                    trans = Transaction(
                                        user_id = bot.owner_id,
                                        bot_id = bot.id,
                                        type = "buy" if bot.strategy.lower() == "long" else "sell",
                                        status = status,
                                        err_msg = err_msg,
                                        amount = bot.amount,
                                        symbol = symbol,
                                        exchange = bot.exchange,
                                        value = exchange.fetch_order(order["id"],symbol)["price"] if order else price,
                                    )
                                    db.session.add(trans)
                                    bot.transactions.append(trans)
                                except Exception as e:
                                    print(e)
                                    pass
                                '''order = exchange.fetch_order(order["id"],symbol)
                                bot.deal_start_price = order['price'] if order['price'] else price'''
                                if status:
                                    bot.deal_started = True
                                    bot.deal_start_price = price
                                    deal_order = exchange.fetch_order(order["id"],symbol)
                                    if deal_order["price"]:
                                        bot.buy_price = deal_order["price"]
                                    else:
                                        bot.buy_price = price
                                    bot.total_trades = bot.total_trades + 1
                                '''if deal_order["fee"]:
                                    bot.amount = bot.amount - deal_order["fee"]["cost"]
                                    bot.units = bot.units - deal_order["fee"]["cost"]
                                    bot.total_volume = bot.total_volume - deal_order["fee"]["cost"]'''
                                #db.session.commit()

                        #########################Safety_orders#########################

                        #check if there any open safety order has filled
                        for safetyOrder in bot.safetyOrders.filter(SafetyOrder.isOpened==True).all():
                            safety_ord = exchange.fetch_order(safetyOrder.orderId,symbol)
                            if safety_ord["status"].lower() == "closed" or safety_ord["status"].lower() == "filled":
                                safetyOrder.isOpened = False
                                safetyOrder.isClosed = True
                                bot.safety_orders_count_active = bot.safety_orders_count_active - 1
                                #bot.total_volume = bot.total_volume - safetyOrder.amount - (safety_ord["fee"]["cost"] if safety_ord["fee"] else 0)
                                bot.total_volume = bot.total_volume - safetyOrder.amount
                                #db.session.commit()

                        #put new saftey orders
                        buy_price_deviation_percentage = bot.safety_orders_deviation
                        
                        for index, safetyOrder in enumerate(bot.safetyOrders.all()):
                            buy_price_deviation_percentage = buy_price_deviation_percentage * (bot.safety_orders_deviation_scale ** index)
                            if safetyOrder.isOpened == False and safetyOrder.isClosed == False and bot.safety_orders_count_active < bot.safety_orders_count_max_active and bot.safety_orders_count>0 and price > 0 and ((price <= (bot.buy_price*((100 - buy_price_deviation_percentage)/100))) if bot.strategy.lower()=='long' else (price >= (bot.buy_price*((100 + buy_price_deviation_percentage)/100)))):
                                print("safety Order No."+str(index+1)+" Deviation: "+str(buy_price_deviation_percentage)+"%")
                                print(bot.safety_orders_size*(bot.safety_orders_size_scale**index))
                                if bot.strategy.lower()=='long':
                                    try:
                                        order = exchange.create_order(symbol, 'limit', ('buy' if bot.strategy.lower()=='long' else 'sell'), bot.safety_orders_size*(bot.safety_orders_size_scale**index), bot.buy_price*((100 - buy_price_deviation_percentage)/100))
                                        send_notification(f'{bot.name} bot has started a {("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order on {exchange_name} for {symbol} with {round(float(bot.buy_price*((100 - buy_price_deviation_percentage)/100)),5)} {bot.quote_currency}***{("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order',current_user.id,bot.exchange)
                                        err_msg = ""
                                        status = True
                                    except Exception as e:
                                        err_msg = str(e)
                                        status = False
                                        send_notification(f'{bot.name} bot has failed to start a {("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order on {exchange_name} for {symbol} with {round(float(bot.buy_price*((100 - buy_price_deviation_percentage)/100)),5)} {bot.quote_currency}***{("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order',current_user.id,bot.exchange)
                                        
                                else:
                                    try:
                                        order = exchange.create_order(symbol, 'limit', ('buy' if bot.strategy.lower()=='long' else 'sell'), bot.safety_orders_size*(bot.safety_orders_size_scale**index), bot.buy_price*((100 + buy_price_deviation_percentage)/100))
                                        send_notification(f'{bot.name} bot has started a {("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order on {exchange_name} for {symbol} with {round(float(bot.buy_price*((100 + buy_price_deviation_percentage)/100)),5)} {bot.quote_currency}***{("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order',current_user.id,bot.exchange)
                                        err_msg = ""
                                        status = True
                                    except Exception as e:
                                        err_msg = str(e)
                                        status = False
                                        send_notification(f'{bot.name} bot has failed to start a {("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order on {exchange_name} for {symbol} with {round(float(bot.buy_price*((100 + buy_price_deviation_percentage)/100)),5)} {bot.quote_currency}***{("buy" if bot.strategy.lower()=="long" else "sell")} Safety Order',current_user.id,bot.exchange)
                                try:
                                    trans = Transaction(    
                                        user_id = bot.owner_id,
                                        bot_id = bot.id,
                                        type = "buy" if bot.strategy.lower() == "long" else "sell",
                                        status = status,
                                        err_msg = err_msg,
                                        amount = bot.safety_orders_size*(bot.safety_orders_size_scale**index),
                                        symbol = symbol,
                                        exchange = bot.exchange,
                                        value = bot.buy_price*((100 - buy_price_deviation_percentage)/100) if bot.strategy.lower() == "long" else bot.buy_price*((100 + buy_price_deviation_percentage)/100)
                                    )
                                    db.session.add(trans)
                                    bot.transactions.append(trans)
                                except Exception as e:
                                    print(e)
                                    pass
                                if status:
                                    safetyOrder.isOpened = True
                                    safetyOrder.orderId = order["id"]
                                    if bot.strategy.lower()=='long':
                                        safetyOrder.price = bot.buy_price*((100 - buy_price_deviation_percentage)/100)
                                    else:
                                        safetyOrder.price = bot.buy_price*((100 + buy_price_deviation_percentage)/100)
                                    bot.total_volume = bot.total_volume + bot.safety_orders_size*(bot.safety_orders_size_scale**index)
                                    bot.safety_orders_count_active = bot.safety_orders_count_active + 1
                                    safetyOrder.amount = bot.safety_orders_size*(bot.safety_orders_size_scale**index)
                                #db.session.commit()

                        #######################take-profit-conditions########################
                        if bot.deal_started and bot.take_profit == False and price > 0:
                            #take profit without conditions based on a percent
                            #symbol_order = symbol if profit_currency == "quote" else symbol.split('/')[1] + '/' + symbol.split('/')[0]
                            symbol_order = symbol
                            #price = getPrice(exchange_name,symbol)
                            if bot.tp_type == "Percent %":
                                if bot.strategy.lower()=='long':
                                    tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.tp_percent/100))
                                else:
                                    tp_price = float(bot.deal_start_price) - (float(bot.deal_start_price) * (bot.tp_percent/100))
                                bot.tp_price = tp_price
                                if (bot.strategy.lower()=='long' and price >= tp_price) or (bot.strategy.lower()=='short' and price <= tp_price):
                                    if not bot.trailing_take_profit:
                                        try:
                                            order = exchange.create_order(symbol_order, "market", ('sell' if bot.strategy.lower()=='long' else 'buy'),(bot.amount if tp_percent_type == "base" else bot.total_volume))
                                            
                                            sell_price_ord = price
                                            #sell_price_ord = order["price"] if order else price
                                            sell_price_ord = exchange.fetch_order(order["id"],symbol_order)["price"] if order else price
                                            bot.sell_price = sell_price_ord
                                            bot.deal_started = False
                                            bot.total_profit = bot.total_profit + float((1 if bot.strategy.lower()=='long' else -1)*(sell_price_ord - bot.buy_price)*(1 if bot.quote_currency == "USDT" else getPrice_assets(exchange_name,symbol_order.split('/')[1] + '/USDT')))*float(bot.amount)
                                            bot.last_total_profit_time = datetime.utcnow()
                                            bot.units = 0
                                            #db.session.commit()
                                            #send_notification(f'{bot.name} bot has completed a Take Profit for {bot.base_currency} on {exchange_name} with {round(price * (bot.amount if tp_percent_type == "base" else bot.total_volume),4)} {bot.quote_currency}***Market { ("sell" if bot.strategy.lower()=="long" else "buy")} Order',current_user.id,bot.exchange)
                                            #send notification if teh bot gain profit or get loss
                                            if (1 if bot.strategy.lower()=='long' else -1) * (sell_price_ord - bot.buy_price) * (1 if bot.quote_currency == "USDT" else getPrice_assets(exchange_name, symbol_order.split('/')[1] + '/USDT')) > 0:
                                                send_notification(f"{bot.name} bot has gained profit for {bot.base_currency} on {exchange_name} with {float(bot.amount)*(round((1 if bot.strategy.lower()=='long' else -1)*(sell_price_ord - bot.buy_price)*(1 if bot.quote_currency == 'USDT' else getPrice_assets(exchange_name, symbol_order.split('/')[1] + '/USDT')), 4))} USDT", current_user.id, bot.exchange)
                                            else:
                                                send_notification(f"{bot.name} bot has lost profit for {bot.base_currency} on {exchange_name} with {float(bot.amount)*(round((1 if bot.strategy.lower()=='long' else -1)*(sell_price_ord - bot.buy_price)*(1 if bot.quote_currency == 'USDT' else getPrice_assets(exchange_name, symbol_order.split('/')[1] + '/USDT')), 4))} USDT", current_user.id, bot.exchange)

                                            err_msg = ""
                                            status = True
                                            bot.isActive = False
                                            bot.take_profit = True
                                            bot.last_price = bot.sell_price
                                        except Exception as e:
                                            err_msg = str(e)
                                            status = False
                                            send_notification(f'{bot.name} bot has failed to complete a Take Profit for {bot.base_currency} on {exchange_name} with {round(price * (bot.amount if tp_percent_type == "base" else bot.total_volume),4)} {bot.quote_currency}***Market { ("sell" if bot.strategy.lower()=="long" else "buy")} Order',current_user.id,bot.exchange)
                                        try:
                                            trans = Transaction(
                                                user_id = bot.owner_id,
                                                bot_id = bot.id,
                                                type = "sell" if bot.strategy.lower() == "long" else "buy",
                                                status = status,
                                                err_msg = err_msg,
                                                amount = bot.amount,
                                                symbol = symbol,
                                                exchange = bot.exchange,
                                                value = sell_price_ord if status else price,
                                            )
                                            db.session.add(trans)
                                            bot.transactions.append(trans)
                                        except Exception as e:
                                            print(e)
                                    else:
                                        bot.take_profit = True
                                        bot.last_price = price
                                    #bot.take_profit_details = f"Take Profit Percent {bot.tp_percent} {profit_currency}"
                                #db.session.commit()
                                
                            elif bot.tp_type == "Conditions":
                                tpGateIsOpened = False
                                if bot.min_profit:
                                    if bot.strategy.lower()=='long':
                                        tp_price = float(bot.deal_start_price) + (float(bot.deal_start_price) * (bot.min_profit_percent/100))
                                    else:
                                        tp_price = float(bot.deal_start_price) - (float(bot.deal_start_price) * (bot.min_profit_percent/100))
                                    bot.tp_price = tp_price
                                    if (bot.strategy.lower()=='long' and price >= tp_price) or (bot.strategy.lower()=='short' and price <= tp_price):
                                        tpGateIsOpened = True
                                        #db.session.commit()

                                if check_indicators_condition(bot.tp_conds,symbol,exchange_name,bot.id) and (tpGateIsOpened or bot.min_profit == False):
                                    try:
                                        order = exchange.create_order(symbol,'market', ('sell' if bot.strategy.lower()=='long' else 'buy'), (bot.amount if tp_percent_type == "base" else bot.total_volume))
                                        #send_notification(f'{bot.name} bot has completed a Take Profit for {bot.base_currency} on {exchange_name} with {round(exchange.fetch_order(order["id"],symbol)["price"] * (bot.amount if tp_percent_type == "base" else bot.total_volume),4)} {bot.quote_currency} ***Market Sell Order',current_user.id,bot.exchange)
                                        send_notification(f'{bot.name} bot has completed a Take Profit for {bot.base_currency} on {exchange_name} with {round(price * (bot.amount if tp_percent_type == "base" else bot.total_volume),4)} {bot.quote_currency} ***Market { ("sell" if bot.strategy.lower()=="long" else "buy")} Order',current_user.id,bot.exchange)
                                        err_msg = ""
                                        status = True
                                    except Exception as e:
                                        err_msg = str(e)
                                        status = False
                                        order = None
                                        send_notification(f'{bot.name} bot has failed to complete a Take Profit for {bot.base_currency} on {exchange_name} with {round(price * (bot.amount if tp_percent_type == "base" else bot.total_volume),4)} {bot.quote_currency} ***Market { ("sell" if bot.strategy.lower()=="long" else "buy")} Order',current_user.id,bot.exchange)
                                    try:
                                        trans = Transaction(
                                            user_id = bot.owner_id,
                                            bot_id = bot.id,
                                            type = "sell" if bot.strategy.lower() == "long" else "buy",
                                            status = status,
                                            err_msg = err_msg,
                                            amount = bot.amount,
                                            symbol = symbol,
                                            exchange = bot.exchange,
                                            value=exchange.fetch_order(order["id"],symbol)["price"] if order else price,
                                        )
                                        db.session.add(trans)
                                        bot.transactions.append(trans)
                                    except Exception as e:
                                        print(e)
                                    if status:
                                        bot.take_profit = True
                                        bot.units = 0
                                        bot.sell_price = exchange.fetch_order(order["id"],symbol)["price"]
                                        #bot.sell_price = price
                                        bot.deal_started = False
                                        bot.isActive = False
                                    #db.session.commit()
                        
                        #######################-----Trailing-----########################
                        #price = getPrice(exchange_name,symbol,bot.owner_id)
                        if bot.deal_started and (bot.trailing_stop_loss or (bot.trailing_take_profit and bot.tp_type == "Percent %" and bot.take_profit)) and price > 0:
                            if (price > bot.last_price and bot.strategy.lower()=='long') or (price < bot.last_price and bot.strategy.lower()=='short'):
                                # Update stop loss price
                                bot.last_price = price
                                if bot.trailing_stop_loss:
                                    if bot.strategy.lower()=='long':
                                        bot.stop_loss_price = price - price * float(bot.stop_loss_price_percent)/100
                                    else:
                                        bot.stop_loss_price = price + price * float(bot.stop_loss_price_percent)/100
                                if bot.trailing_take_profit and bot.tp_type == "Percent %" and bot.take_profit:
                                    '''if bot.strategy.lower()=='long':
                                        bot.tp_price = price + price * float(bot.tp_percent)/100
                                    else:
                                        bot.tp_price = price - price * float(bot.tp_percent)/100'''
                                    if bot.strategy.lower()=='long':
                                        bot.stop_loss_price = price - price * float(bot.trailing_deviation)/100
                                    else:
                                        bot.stop_loss_price = price + price * float(bot.trailing_deviation)/100

                            #db.session.commit()

                        #######################stop-loss-sell########################
                        if bot.deal_started and (( bot.strategy.lower()=='long' and  price <= bot.stop_loss_price) or (bot.strategy.lower()=='short' and  price >= bot.stop_loss_price)) and bot.units > 0 and (bot.stop_loss or bot.trailing_take_profit) and (price > 0):
                            # Making the stop loss sell order
                            if bot.stop_loss_time_out and bot.stop_loss:
                                sleep(bot.stop_loss_time_out_time)
                                bot.stop_loss_time_out_runned = True
                                db.session.commit()
                                continue
                            try:
                                trailing_order = exchange.create_order(symbol, 'market', ('sell' if bot.strategy.lower()=='long' else 'buy'), bot.total_volume)
                                err_msg = ""
                                status = True
                                message = f"{bot.name} bot has completed a Stop loss {('sell' if bot.strategy.lower()=='long' else 'buy')} order for {symbol} on {bot.exchange} by {round(price * bot.units,5)} {bot.quote_currency}***Bot"
                            except Exception as e:
                                trailing_order = None
                                err_msg = str(e)
                                status = False
                                message = f"{bot.name} bot has failed to complete a Stop loss {('sell' if bot.strategy.lower()=='long' else 'buy')} order for {symbol} on {bot.exchange} by {round(price * bot.units,5)} {bot.quote_currency}***Bot"
                            bot.deal_started = False
                            #db.session.commit()
                            # Send notification
                            send_notification(message, current_user.id,bot.exchange)
                            try:
                                trans = Transaction(
                                    user_id = bot.owner_id,
                                    bot_id = bot.id,
                                    type = "sell" if bot.strategy.lower() == "long" else "buy",
                                    status = status,
                                    err_msg = err_msg,
                                    amount = bot.amount,
                                    symbol = symbol,
                                    exchange = bot.exchange,
                                    value = exchange.fetch_order(trailing_order["id"],symbol)['price'] if trailing_order else price,
                                )
                                db.session.add(trans)
                                bot.transactions.append(trans)
                            except Exception as e:
                                print(e)

                            if status:
                                

                                #sell_price_ord_sl = exchange.fetch_order(trailing_order["id"],symbol)["price"]
                                sell_price_ord_sl = exchange.fetch_order(trailing_order["id"],symbol)['price'] if trailing_order else price
                                bot.sell_price = sell_price_ord_sl
                                bot.total_profit = bot.total_profit + float((1 if bot.strategy.lower()=='long' else -1)*((sell_price_ord_sl - bot.buy_price) if bot.quote_currency == "USDT" else (sell_price_ord_sl - bot.buy_price) * getPrice_assets(exchange_name,symbol.split('/')[1] + '/USDT')))*float(bot.amount)
                                bot.last_total_profit_time = datetime.utcnow()
                                if int(bot.close_deal_action) == 1 and bot.stop_loss:
                                    bot.take_profit = False
                                    bot.units = bot.amount
                                    bot.isActive = True
                                    bot.deal_start_price = None
                                elif int(bot.close_deal_action) == 2 or bot.stop_loss==False:
                                    bot.units = 0
                                    bot.isActive = False
                                    bot.take_profit = False
                                if (1 if bot.strategy.lower()=='long' else -1)*((sell_price_ord_sl - bot.buy_price) if bot.quote_currency == "USDT" else (sell_price_ord_sl - bot.buy_price) * getPrice_assets(exchange_name,symbol.split('/')[1] + '/USDT')) > 0:
                                    send_notification(f'{bot.name} bot has gained profit for {symbol} on {bot.exchange} by {float(bot.amount)*(round((sell_price_ord_sl - bot.buy_price) * bot.units,5))} {bot.quote_currency}***Bot', current_user.id,bot.exchange)
                                else:
                                    send_notification(f'{bot.name} bot has got loss for {symbol} on {bot.exchange} by {float(bot.amount)*(round((sell_price_ord_sl - bot.buy_price) * bot.units,5))} {bot.quote_currency}***Bot', current_user.id,bot.exchange)
                            else:
                                send_notification(f'{bot.name} bot has failed to complete a Stop loss {("sell" if bot.strategy.lower()=="long" else "buy")} order for {symbol} on {bot.exchange} by {round(price * bot.units,5)} {bot.quote_currency}***Bot', current_user.id,bot.exchange)
                            
                    #db.session.commit()
                    print(f"Elapsed time: {time.time() - start_time} seconds")
                    db.session.commit()
                except Exception as e:
                    print(e)
                    db.session.commit()
                    continue

def check_indicators_condition(conds,symbol,exchange,bot_id):
    MACDisTrue1 = True
    MACDisTrue2 = True
    RSIisTrue = True
    CCIisTrue = True
    BollingerisTrue = True
    UltoscisTrue = True
    ADXisTrue = True
    MFIisTrue = True
    SARisTrue = True
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
                cci = talib.CCI(data.high, data.low, data.close, timeperiod=int(cond_data['Length']))
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

            if cond['indicator'] == 'Money Flow Index':
                MFIisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                mfi = talib.MFI(data.high, data.low, data.close, data.volume, timeperiod=int(cond_data["MFI Length"]))
                data.loc[:, 'mfi'] = mfi
                fullMfi = data.to_dict(orient='records')[-2:]
                cond['value'] = fullMfi[-1]['mfi']
                if cond_data['Condition'] == 'Crossing Up':
                    if fullMfi[-1]['mfi'] > float(cond_data['Signal Value']) and fullMfi[-2]['mfi'] < float(cond_data['Signal Value']):
                        MFIisTrue = True
                    else:
                        MFIisTrue = False
                elif cond_data['Condition'] == 'Crossing Down':
                    if fullMfi[-1]['mfi'] < float(cond_data['Signal Value']) and fullMfi[-2]['mfi'] > float(cond_data['Signal Value']):
                        MFIisTrue = True
                    else:
                        MFIisTrue = False

            if cond['indicator'] == 'Parabolic SAR':
                SARisTrue = False
                cond_data = cond['conds']
                data = fetch_data(symbol,exchange,cond_data['Timeframe'])
                sar = talib.SAR(data.high, data.low, acceleration=float(cond_data["Start"]), maximum=float(cond_data["Maximum"]))
                data.loc[:, 'sar'] = sar
                fullSar = data.to_dict(orient='records')[-2:]
                cond['value'] = fullSar[-1]['sar']
                if cond_data['Condition'] == 'Crossing Up (Long)':
                    if fullSar[-1]['sar'] > fullSar[-1]['close'] and fullSar[-2]['sar'] < fullSar[-2]['close']:
                        SARisTrue = True
                    else:
                        SARisTrue = False
                elif cond_data['Condition'] == 'Crossing Down (Short)':
                    if fullSar[-1]['sar'] < fullSar[-1]['close'] and fullSar[-2]['sar'] > fullSar[-2]['close']:
                        SARisTrue = True
                    else:
                        SARisTrue = False

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

    return MACDisTrue1 and MACDisTrue2 and CCIisTrue and RSIisTrue and BollingerisTrue and UltoscisTrue and ADXisTrue and MFIisTrue and SARisTrue and TradingViewisTrue

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