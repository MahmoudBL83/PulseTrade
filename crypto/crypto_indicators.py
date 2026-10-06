from logzero import logger
from tenacity import retry, wait_fixed
import ccxt
from pandas import DataFrame as df
import time
import attr
import json
import os
from datetime import datetime as dt, timedelta
from datetime import datetime, timedelta

@attr.s
class Indicator2:
    pair = attr.ib()
    interval = attr.ib()
    exchange = attr.ib()
    verbose = attr.ib()
    ohlcv = attr.ib(init=False)
    setting = attr.ib(init=False)
    
    def __attrs_post_init__(self):
        self.ohlcv = {}
            
    @retry(wait=wait_fixed(9))
    def __fetch_ohlcv(self,interval,exchange,forced=True):
        if forced:
            file_name = f"stochData2/stoch_{self.pair.replace('/','')}_{interval}_{exchange}.json"
            data = None
            if os.path.isfile(file_name):
                with open(file_name, "r") as f:
                    try:
                        result = json.load(f)
                        data = [[int(datetime.strptime(d['time'], '%Y-%m-%d %H:%M:%S').timestamp() * 1000), d['open'], d['high'], d['low'], d['close'], d['volume']] for d in result]
                    except Exception as e: 
                        return self.__fetch_ohlcv(interval,exchange,False)
                    
                if (time.time()*1000 - data[-1][0]) < get_timestamps(interval):
                    logger.info(f"Using cached data for interval: {interval} for {self.pair} on {exchange}")
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

        logger.info(f"Fetching candlestick data for interval: {interval} for {self.pair} on {exchange}")

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

    def update_data(self):
        try:
            self.ohlcv[self.interval] = self.__fetch_ohlcv(self.interval,self.exchange)
            return self.ohlcv
        
        except Exception as e:
            logger.exception(e)

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



