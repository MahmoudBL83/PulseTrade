import asyncio
import os
import sys
from pprint import pprint
import ccxt.async_support as ccxt2  # noqa: E402
import ccxt as ccxt1
import time

start_time = time.time()
pprint(asyncio.get_event_loop().run_until_complete(ccxt2.binance().fetch_ticker('ETH/BTC')))
print("--- %s seconds ---" % (time.time() - start_time))

start_time = time.time()
pprint(ccxt1.binance().fetch_ticker('ETH/BTC'))
print("--- %s seconds ---" % (time.time() - start_time))