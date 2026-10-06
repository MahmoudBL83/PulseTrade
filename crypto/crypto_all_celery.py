import numpy
from pandas import DataFrame as df
from datetime import datetime as dt
import talib
from logzero import logger
from tenacity import retry, wait_fixed
import ccxt
import time
import attr
import json
from search_crypto import search
from pyti.relative_strength_index import relative_strength_index as rsi
import numpy
from pandas import DataFrame as df
from datetime import datetime as dt
from logzero import logger
from tenacity import retry, wait_fixed
import time
import attr
import json
from search_crypto import search
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, timezone
import os
from datetime import datetime as dt, timedelta

@attr.s
class Indicator:
    pair = attr.ib()
    intervals = attr.ib()
    exchange = attr.ib()
    verbose = attr.ib()
    ohlcv = attr.ib(init=False)
    setting = attr.ib(init=False)
    stoch_data = attr.ib(init=False)
    macd_data = attr.ib(init=False)
    wpr_data = attr.ib(init=False)
    cci_data = attr.ib(init=False)
    adx_data = attr.ib(init=False)
    rsi_data = attr.ib(init=False)
    sma10_data = attr.ib(init=False)
    sma20_data = attr.ib(init=False)
    sma30_data = attr.ib(init=False)
    sma50_data = attr.ib(init=False)
    sma100_data = attr.ib(init=False)
    sma200_data = attr.ib(init=False)
    ema10_data = attr.ib(init=False)
    ema20_data = attr.ib(init=False)
    ema30_data = attr.ib(init=False)
    ema50_data = attr.ib(init=False)
    ema100_data = attr.ib(init=False)
    ema200_data = attr.ib(init=False)
    changes = attr.ib(init=False)

    def __attrs_post_init__(self):
        self.stoch_data = {}
        self.macd_data = {}
        self.wpr_data = {}
        self.cci_data = {}
        self.adx_data = {}
        self.rsi_data = {}
        self.sma10_data = {}
        self.sma20_data = {}
        self.sma30_data = {}
        self.sma50_data = {}
        self.sma100_data = {}
        self.sma200_data = {}
        self.ema10_data = {}
        self.ema20_data = {}
        self.ema30_data = {}
        self.ema50_data = {}
        self.ema100_data = {}
        self.ema200_data = {}
        for interval in self.intervals:
            self.stoch_data[interval] = {}
            self.macd_data[interval] = {}
            self.wpr_data[interval] = {}
            self.cci_data[interval] = {}
            self.adx_data[interval] = {}
            self.rsi_data[interval] = {}
            self.sma10_data[interval] = {}
            self.sma20_data[interval] = {}
            self.sma30_data[interval] = {}
            self.sma50_data[interval] = {}
            self.sma100_data[interval] = {}
            self.sma200_data[interval] = {}
            self.ema10_data[interval] = {}
            self.ema20_data[interval] = {}
            self.ema30_data[interval] = {}
            self.ema50_data[interval] = {}
            self.ema100_data[interval] = {}
            self.ema200_data[interval] = {}

    @retry(wait=wait_fixed(9))
    def __fetch_changes(self, exchange):
        logger.info(f"Fetching last changes for pair in {exchange}: {self.pair}")
        try:
            exchange = getattr(ccxt, exchange)()
            trades = exchange.fetch_ohlcv(self.pair, '1h', since=exchange.milliseconds() - 86400000)
            trades_df = pd.DataFrame(trades, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            return trades_df
        except Exception as e:
            logger.exception(e)

    @retry(wait=wait_fixed(9))
    def __fetch_ohlcv(self,interval,exchange,forced=True):
        if forced:
            file_name = f"stochData/stoch_{self.pair.replace('/','')}_{interval}_{exchange}.json"
            data = None
            if os.path.isfile(file_name):
                with open(file_name, "r") as f:
                    try:
                        result = json.load(f)
                        data = [[int(datetime.strptime(d['time'], '%Y-%m-%d %H:%M:%S').timestamp() * 1000), d['open'], d['high'], d['low'], d['close'], d['volume']] for d in result]
                    except Exception as e: 
                        return self.__fetch_ohlcv(interval,exchange,False)
                    
                if (time.time()*1000 - data[-1][0]) < get_timestamps(interval):
                    logger.info(f"Using cached data for interval in {exchange}: {interval}")
                    def totime2(x):
                        result = float(x) / 1000
                        result = int(result)
                        return dt.fromtimestamp(result).strftime('%Y-%m-%d %H:%M:%S')

                    result = df.from_dict({
                        'time':
                        list(map(lambda c: totime2(c[0]), data)),
                        'open':
                        list(map(lambda c: float(c[1]), data)),
                        'high':
                        list(map(lambda c: float(c[2]), data)),
                        'low':
                        list(map(lambda c: float(c[3]), data)),
                        'close':
                        list(map(lambda c: float(c[4]), data)),
                        'volume':
                        list(map(lambda c: float(c[5]), data))
                    })

                    result = result.loc[:, [
                        'time', 'open', 'high', 'low', 'close', 'volume'
                    ]]

                    return result

        logger.info(f"Fetching candlestick data for interval in {exchange}: {interval}")

        try:
            time_ranges = {
                "1m": 7200,
                "3m": 5760,
                "5m": 5472,
                "15m": 4992,
                "30m": 9648,
                "1h": 13680,
                "2h": 6840,
                "4h": 3402,
                "6h": 3402,
                "12h": 3000,
                "1d": 2529,
                "1w": 280,
            }

            result = getattr(ccxt, exchange)().fetch_ohlcv(
                symbol=self.pair, timeframe=interval,limit = time_ranges[interval])
            
            def totime(x):
                result = float(x) / 1000
                result = int(result)
                return dt.fromtimestamp(result).strftime('%Y-%m-%d %H:%M:%S')

            result = df.from_dict({
                'time':
                list(map(lambda c: totime(c[0]), result)),
                'open':
                list(map(lambda c: float(c[1]), result)),
                'high':
                list(map(lambda c: float(c[2]), result)),
                'low':
                list(map(lambda c: float(c[3]), result)),
                'close':
                list(map(lambda c: float(c[4]), result)),
                'volume':
                list(map(lambda c: float(c[5]), result))
            })

            result = result.loc[:, [
                'time', 'open', 'high', 'low', 'close', 'volume'
            ]]
            return result
            
        except Exception as e:
            logger.exception(e)


    def __compute_stoch(self, interval, data):
        try:
            k_period = 14
            d_period = 3
            slowing = 3
            k, d = talib.STOCH(data.high, data.low, data.close, fastk_period=k_period, slowk_matype=0, slowk_period=slowing, slowd_period=d_period, slowd_matype=0)
            data.loc[:, 'slowk'] = k
            data.loc[:, 'slowd'] = d
            data.loc[:, 'j'] = 3 * k - 2 * d
            return data
        except Exception as e:
            logger.exception(e)

    def __compute_macd(self, interval, data):
        try:
            macd, signal, hist = talib.MACD(data.close, fastperiod=12, slowperiod=26, signalperiod=9)
            data.loc[:, 'macd'] = macd
            data.loc[:, 'signal'] = signal
            data.loc[:, 'hist'] = hist
            return data
        except Exception as e:
            logger.exception(e)

    def __compute_wpr(self, interval, data):
        try:
            wpr = talib.WILLR(data.high, data.low, data.close, timeperiod=14)
            data.loc[:, 'wpr'] = wpr

            return data
        except Exception as e:
            logger.exception(e)

    def __compute_adx(self, interval,data):
        try:
            adx = talib.ADX(data.high, data.low, data.close, timeperiod=14)
            data.loc[:, 'adx'] = adx

            return data
        except Exception as e:
            logger.exception(e)

    def __compute_cci(self, interval,data):
        try:
            cci = talib.CCI(data.high, data.low, data.close, timeperiod=20)
            data.loc[:, 'cci'] = cci

            return data
        except Exception as e:
            logger.exception(e)
    
    def __compute_rsi(self, interval,data):
        try:
            indicator = talib.RSI(data.close, 14)
            data.loc[:, 'indicator'] = indicator

            return data
        except Exception as e:
            logger.exception(e)

    def __compute_ema(self, interval, data, timeperiod):
        try:
            ema = talib.EMA(data.close, timeperiod)
            data.loc[:, f'ema{timeperiod}'] = ema

            return data
        except Exception as e:
            logger.exception(e)

    def __compute_sma(self, interval, data, timeperiod):
        try:
            sma = talib.SMA(data.close, timeperiod)
            data.loc[:, f'sma{timeperiod}'] = sma

            return data
        except Exception as e:
            logger.exception(e)

    def update_data(self):
        try:
            for interval in self.intervals:
                self.ohlcv = self.__fetch_ohlcv(interval,self.exchange)
                self.stoch_data[interval][self.exchange] = self.__compute_stoch(interval, self.ohlcv)
                self.macd_data[interval][self.exchange] = self.__compute_macd(interval, self.ohlcv)
                self.wpr_data[interval][self.exchange] = self.__compute_wpr(interval, self.ohlcv)
                self.cci_data[interval][self.exchange] = self.__compute_cci(interval, self.ohlcv)
                self.adx_data[interval][self.exchange] = self.__compute_adx(interval, self.ohlcv)
                self.rsi_data[interval][self.exchange] = self.__compute_rsi(interval, self.ohlcv)
                self.sma10_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 10)
                self.sma20_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 20)
                self.sma30_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 30)
                self.sma50_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 50)
                self.sma100_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 100)
                self.sma200_data[interval][self.exchange] = self.__compute_sma(interval, self.ohlcv, 200)
                self.ema10_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 10)
                self.ema20_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 20)
                self.ema30_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 30)
                self.ema50_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 50)
                self.ema100_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 100)
                self.ema200_data[interval][self.exchange] = self.__compute_ema(interval, self.ohlcv, 200)
            return self.stoch_data
        
        except Exception as e:
            logger.exception(e)

symbols = search()
symbols2 = [symbol['symbol'][:symbol['symbol'].index(symbol['currency_code'])] + '/' + symbol['currency_code'] for symbol in symbols if symbol['currency_code'] == 'USDT' and '.P' not in symbol['symbol']]
symbols2 = symbols2[:1]

from datetime import datetime, timedelta

def get_timestamps(interval):
    end_time = int(datetime.now().timestamp() * 1000)  # End time is the current timestamp in milliseconds
    if interval.endswith('m'):  # Minutes
        start_time = int((datetime.now() - timedelta(minutes=int(interval[:-1]))).timestamp() * 1000)
    elif interval.endswith('h'):  # Hours
        start_time = int((datetime.now() - timedelta(hours=int(interval[:-1]))).timestamp() * 1000)
    elif interval.endswith('d'):  # Days
        start_time = int((datetime.now() - timedelta(days=int(interval[:-1]))).timestamp() * 1000)
    elif interval.endswith('w'):  # Weeks
        start_time = int((datetime.now() - timedelta(weeks=int(interval[:-1]))).timestamp() * 1000)
    else:
        raise ValueError('Invalid interval: ' + interval)
    return end_time - start_time

