from logzero import logger
from tenacity import retry, wait_fixed
import ccxt
import time
import attr
import json
from search_crypto import search
from logzero import logger
from tenacity import retry, wait_fixed
import time
import attr
import json
from search_crypto import search
import pandas as pd
import pytz
from datetime import datetime
from crypto import socketio,app
from flask import request


@app.route('/api/v1/order_book_history/')
def order_book_history():
    exchange = request.args.get("exchange")
    symbol = request.args.get("symbol")
    order_book = getattr(ccxt, exchange)().fetch_order_book(symbol=symbol,limit=1)
    if order_book:
        last_order = order_book[0]  # Get the first (last) trade from the list
        trade_data = {
            'side': last_order['side'],
            'price': last_order['price'],
            'amount': last_order['amount']
        }
        with app.app_context():
            socketio.emit('last_order', json.dumps(trade_data))

'''@attr.s
class Indicator:
    pair = attr.ib()
    exchanges = attr.ib()
    verbose = attr.ib()
    order_book = attr.ib(init=False)
    setting = attr.ib(init=False)
    
    def __attrs_post_init__(self):
        pass
            
    @retry(wait=wait_fixed(9))
    def __fetch_order_book(self, exchange):
        logger.info(f"Fetching order book for pair: {self.pair}")
        try:
            
            order_book = getattr(ccxt, exchange)().fetch_order_book(symbol=self.pair,limit=1)
            if order_book:
                last_trade = order_book[0]  # Get the first (last) trade from the list
                trade_data = {
                    'side': last_trade['side'],
                    'price': last_trade['price'],
                    'amount': last_trade['amount']
                }
                with app.app_context():
                    socketio.emit('last_order', json.dumps(trade_data))

        except Exception as e:
            logger.exception(e)

    def update_data(self):
        try:
            for exchange in self.exchanges:
                self.order_book = self.__fetch_order_book(exchange)
            #return self.order_book
        
        except Exception as e:
            logger.exception(e)

symbols = search()
symbols2 = [symbol['symbol'][:symbol['symbol'].index(symbol['currency_code'])] + '/' + symbol['currency_code'] for symbol in symbols if symbol['currency_code'] == 'USDT' and '.P' not in symbol['symbol']]
symbols2 = symbols2[:1]

def update_symbol_data(symbol,exchanges):
    indicator = Indicator(
        exchanges=exchanges, 
        pair=symbol,
        verbose=0
    )
    try:
        indicator.update_data()
        for exchange in exchanges:
            file_name_buy = f"orders/buy_{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{exchange}.json"
            file_name_sell = f"orders/sell_{symbol.replace('/', '').replace('.D', '', 1).replace('.T', '', 1)}_{exchange}.json"
            with open(file_name_buy, 'w') as f:
                json.dump(buy_trades.to_dict(orient='records'), f)
            with open(file_name_sell, 'w') as f:
                json.dump(sell_trades.to_dict(orient='records'), f)
    except Exception as e:
        logger.exception(e)

import concurrent.futures

def update_all_symbols(exchanges):
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = []
        for symbol in symbols2:
            # Submit a new task to the thread pool           
            future = executor.submit(update_symbol_data, symbol,exchanges)
            futures.append(future)

        # Wait for all tasks to complete
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error updating symbol data: {e}")

def fetch_orders():
    while True:
        exchanges = ['okex']
        update_all_symbols(exchanges)'''

