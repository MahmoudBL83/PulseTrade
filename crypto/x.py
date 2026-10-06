from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_socketio import SocketIO
from flask_cors import CORS
import ssl
from celery import Celery
import json
import ccxt
from crypto.dataStream_price import generateSession,sendMessage,sendPingPacket,socketJob
from websocket import create_connection
from crypto.crypto_indicators import Indicator2,logger
import time

def update_price_data(symbols,exchange):
    while True:
        for symbol in symbols:
            start_time = time.time()
            exchange = exchange.replace('okex','okx').upper()
            symbol_id = f"{exchange}:{symbol.replace('/', '')}"
            tradingViewSocket = "wss://data.tradingview.com/socket.io/websocket"
            headers = json.dumps({"Origin": "https://data.tradingview.com"})
            print(f"Elapsed time 1 (update_price_data): {time.time() - start_time} seconds")
            ws = create_connection(tradingViewSocket, headers=headers)
            print(f"Elapsed time 2 (update_price_data): {time.time() - start_time} seconds")
            session = generateSession()
            print(f"Elapsed time 3 (update_price_data): {time.time() - start_time} seconds")
            # Send messages
            sendMessage(ws, "quote_create_session", [session])
            sendMessage(ws, "quote_set_fields", [session,"lp","volume","ch","chp"])
            sendMessage(ws, "quote_add_symbols", [session, symbol_id])
            print(f"Elapsed time 4 (update_price_data): {time.time() - start_time} seconds")
            # Start job
            price = socketJob(ws,symbol_id,tradingViewSocket,headers)
            print(f"Elapsed time 5 (update_price_data): {time.time() - start_time} seconds")
            symbol_name = f"{exchange}"+symbol.replace('/', '')
            try:
                with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'r') as f:
                    data2 = json.load(f)
            except FileNotFoundError:
                data = {}
                with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'w') as f:
                    json.dump(data, f)

            data = {symbol: [price,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}
            
            # check if symbol already exists in the JSON file
            try:
                with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "r") as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = {}
            if symbol in existing_data:
                # update symbol value
                existing_data[symbol][0] = price
            else:
                # add symbol to JSON file
                existing_data.update(data)

            # write updated data to JSON file
            with open("pricesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "w") as f:
                json.dump(existing_data, f)
            print(f"Elapsed time 6 (update_price_data): {time.time() - start_time} seconds")

        #print(f"Elapsed time (update_price_data): {time.time() - start_time} seconds")

def update_volume_data(symbols,exchange):
    while True:
        start_time = time.time()
        for symbol in symbols:
            # Start job
            x = getattr(ccxt, exchange)().fetch_ticker(symbol)
            volume = x['baseVolume']
            turnover = x['quoteVolume']
            high = x['high']
            low = x['low']
            percentage = x['percentage']
            change = x['change']
            symbol_name = f"{exchange}"+symbol.replace('/', '')
            try:
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'r') as f:
                    data2 = json.load(f)
            except FileNotFoundError:
                data = {}
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), 'w') as f:
                    json.dump(data, f)

            data = {symbol: [volume,turnover,high,low,percentage,change]}

            # check if symbol already exists in the JSON file
            try:
                with open("volumesData/"+f"{symbol_name}.json".replace("/","").replace(".D","",1).replace(".T","",1), "r") as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = {}
            if symbol in existing_data:
                # update symbol value
                existing_data[symbol][0] = volume
                existing_data[symbol][1] = turnover
                existing_data[symbol][2] = high
                existing_data[symbol][3] = low
                existing_data[symbol][4] = percentage
                existing_data[symbol][5] = change
            else:
                # add symbol to JSON file
                existing_data.update(data)

            # write updated data to JSON file
            with open("volumesData/"+f"{symbol_name.replace('okex','okx').upper()}.json".replace("/","").replace(".D","",1).replace(".T","",1), "w") as f:
                json.dump(existing_data, f)

        time.sleep(1)
        print(f"Elapsed time (update_volume_data): {time.time() - start_time} seconds")

def update_symbol_indicator(symbols,exchange):
    while True:
        start_time = time.time()
        for symbol in symbols:
            for interval in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","12h","1d","1w"]:
                indicator = Indicator2(
                    exchange=exchange, 
                    pair=symbol,
                    interval=interval,
                    verbose=0
                )
                try:
                    indicators_data = indicator.update_data()
                    file_name_stoch = f"stochData/stoch_{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{interval}_{exchange}.json"
                    with open(file_name_stoch, 'w') as f:
                        json.dump(indicators_data[interval].to_dict(orient='records'), f)
                except Exception as e:
                    logger.exception(e)
        time.sleep(1)
        print(f"Elapsed time (update_symbol_indicator): {time.time() - start_time} seconds")

exchanges = ['okex']
for exchange in exchanges:
    pairs = []
    pairs2 = []
    for currency in getattr(ccxt, exchange)().fetch_markets():
        if currency['spot']:
            pairs2.append(currency['symbol'])
        if currency['spot'] and ('USDT' in currency['symbol']):
            pairs.append(currency['symbol'])

    chunk_size = 10
    chunk_size2 = 50

    for i in range(0, int(len(pairs)/chunk_size)):
        #update_volume_data(pairs[i*50:(i+1)*50], exchange)
        update_price_data(pairs[i*chunk_size:(i+1)*chunk_size], exchange)

    for i in range(0, int(len(pairs2)/chunk_size2)):
        #update_symbol_indicator(pairs2[i*chunk_size2:(i+1)*chunk_size2], exchange)
        pass



