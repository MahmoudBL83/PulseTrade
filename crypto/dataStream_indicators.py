from pandas import DataFrame as df
import talib
from tenacity import retry, wait_fixed
import ccxt
import attr
from logzero import logger
import math
import json
import os
from datetime import datetime as dt,timedelta
from datetime import datetime
from crypto.functions import getPrice,getPrice_assets

@attr.s
class Indicator:
    pair = attr.ib()
    interval = attr.ib()
    exchange = attr.ib()
    verbose = attr.ib()
    ohlcv = attr.ib(init=False)
    setting = attr.ib(init=False)
    '''stoch_data = attr.ib(init=False)
    macd_data = attr.ib(init=False)
    wpr_data = attr.ib(init=False)
    cci_data = attr.ib(init=False)
    adx_data = attr.ib(init=False)
    rsi_data = attr.ib(init=False)
    stochRSI_data = attr.ib(init=False)
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
    bbp_data = attr.ib(init=False)
    ao_data = attr.ib(init=False)
    uo_data = attr.ib(init=False)
    momentum_data = attr.ib(init=False)
    bb_bands_data = attr.ib(init=False)
    sar_data = attr.ib(init=False)
    hma_data = attr.ib(init=False)
    mfi_data = attr.ib(init=False)'''
    
    def __attrs_post_init__(self):
        '''self.stoch_data = {}
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
        self.bbp_data = {}
        self.ao_data = {}
        self.uo_data = {}
        self.momentum_data = {}
        self.bb_bands_data = {}
        self.sar_data = {}
        self.hma_data = {}
        self.mfi_data = {}'''
    
    def __fetch_data(self,exchange,interval):
        file_name = f"stochData/stoch_{self.pair.replace('/','')}_{interval}_{exchange}.json"
        data = None
        if os.path.isfile(file_name):
            with open(file_name, "r") as f:
                result = json.load(f)
                data = [[int(datetime.strptime(d['time'], '%Y-%m-%d %H:%M:%S').timestamp() * 1000), d['open'], d['high'], d['low'], d['close'], d['volume']] for d in result]

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

            return result.loc[:, [
                'time', 'open', 'high', 'low', 'close', 'volume'
            ]]
        
    @retry(wait=wait_fixed(9))
    def __fetch_ohlcv(self,exchange,interval):
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


    '''def compute_stoch(self, data):
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

    def compute_macd(self, data):
        try:
            macd, signal, hist = talib.MACD(data.close, fastperiod=12, slowperiod=26, signalperiod=9)
            data.loc[:, 'macd'] = macd
            data.loc[:, 'signal'] = signal
            data.loc[:, 'hist'] = hist
            return data
        except Exception as e:
            logger.exception(e)

    def compute_wpr(self, data):
        try:
            wpr = talib.WILLR(data.high, data.low, data.close, timeperiod=14)
            data.loc[:, 'wpr'] = wpr

            return data
        except Exception as e:
            logger.exception(e)

    def compute_adx(self,data):
        try:
            adx = talib.ADX(data.high, data.low, data.close, timeperiod=14)
            data.loc[:, 'adx'] = adx

            return data
        except Exception as e:
            logger.exception(e)

    def compute_ao(self,data):
        try:
            ao = talib.MA(data.close, timeperiod=5, matype=talib.MA_Type.SMA) - talib.MA(data.close, timeperiod=34, matype=talib.MA_Type.SMA)
            data.loc[:, 'ao'] = ao

            return data
        except Exception as e:
            logger.exception(e)
    
    def compute_cci(self,data):
        try:
            cci = talib.CCI(data.high, data.low, data.close, timeperiod=20)
            data.loc[:, 'cci'] = cci

            return data
        except Exception as e:
            logger.exception(e)

    def calc_uo(self, data):
        try:
            high = data.high
            low = data.low
            close = data.close

            uo = talib.ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28)
            data['uo'] = uo

            return data
        except Exception as e:
            logger.exception(e)

    def calc_bbp(self, data):
        try:
            high = data.high
            low = data.low
            close = data.close

            bull_power = high - talib.EMA(close, timeperiod=13)
            bear_power = low - talib.EMA(close, timeperiod=13)

            data['bull_power'] = bull_power
            data['bear_power'] = bear_power

            return data
        except Exception as e:
            logger.exception(e)

    def calc_momentum(self, data):
        try:
            momentum = talib.MOM(data.close, timeperiod=10)
            data['momentum'] = momentum
            return data
        except Exception as e:
            logger.exception(e)

    def compute_rsi(self,data):
        try:
            indicator = talib.RSI(data.close, 14)
            data.loc[:, 'indicator'] = indicator

            return data
        except Exception as e:
            logger.exception(e)

    def compute_stoch_rsi(self, data):
        try:
            # Calculate Stochastic RSI
            stoch_rsi = talib.STOCHRSI(data.indicator, 14, 3, 3, 0, 0)

            # Assign Stochastic RSI values to DataFrame
            data['Stoch_RSI_%K'] = stoch_rsi[0]
            data['Stoch_RSI_%D'] = stoch_rsi[1]

            return data
        except Exception as e:
            logger.exception(e)

    def compute_ema(self, data, timeperiod):
        try:
            ema = talib.EMA(data.close, timeperiod)
            data.loc[:, f'ema{timeperiod}'] = ema
            return data
        except Exception as e:
            logger.exception(e)

    def compute_sma(self, data, timeperiod):
        try:
            sma = talib.SMA(data.close, timeperiod)
            data.loc[:, f'sma{timeperiod}'] = sma

            return data
        except Exception as e:
            logger.exception(e)

    def compute_mfi(self,data):
        try:
            # Calculate Money Flow Index
            mfi = talib.MFI(data.high, data.low, data.close, data.volume, timeperiod=14)
            data.loc[:, 'mfi'] = mfi
            return data
        except Exception as e:
            logger.exception(e)

    def compute_bb_bands(self,data):
        try:
            # Calculate Bollinger Bands
            upper_band, middle_band, lower_band = talib.BBANDS(data.close, timeperiod=20)
            data.loc[:, 'upper_band'] = upper_band
            data.loc[:, 'middle_band'] = middle_band
            data.loc[:, 'lower_band'] = lower_band
            return data
        except Exception as e:
            logger.exception(e)

    def compute_sar(self,data):
        try:
            # Calculate Parabolic SAR
            sar = talib.SAR(data.high, data.low, acceleration=0.02, maximum=0.2)
            data.loc[:, 'sar'] = sar
            return data
        except Exception as e:
            logger.exception(e)

    def compute_hma(self,data):
        try:
            # Calculate Hull Moving Average (9)
            hma = talib.HMA(data.close, timeperiod=9)
            data.loc[:, 'hma'] = hma
            return data
        except Exception as e:
            logger.exception(e)'''

    def update_data(self,symbol,exchange,interval,realExchange):
        try:
            #self.ohlcv = self.__fetch_data(exchange,interval)
            self.ohlcv = fetch_ohlcv2(symbol,exchange,interval,realExchange)
            '''self.stoch_data = self.compute_stoch(self.ohlcv)
            self.macd_data = self.compute_macd(self.ohlcv)
            self.wpr_data = self.compute_wpr(self.ohlcv)
            self.cci_data = self.compute_cci(self.ohlcv)
            self.adx_data = self.compute_adx(self.ohlcv)
            self.rsi_data = self.compute_rsi(self.ohlcv)
            self.stochRSI_data = self.compute_stoch_rsi(self.ohlcv)
            self.sma10_data = self.compute_sma(self.ohlcv, 10)
            self.sma20_data = self.compute_sma(self.ohlcv, 20)
            self.sma30_data = self.compute_sma(self.ohlcv, 30)
            self.sma50_data = self.compute_sma(self.ohlcv, 50)
            self.sma100_data = self.compute_sma(self.ohlcv, 100)
            self.sma200_data = self.compute_sma(self.ohlcv, 200)
            self.ema10_data = self.compute_ema(self.ohlcv, 10)
            self.ema20_data = self.compute_ema(self.ohlcv, 20)
            self.ema30_data = self.compute_ema(self.ohlcv, 30)
            self.ema50_data = self.compute_ema(self.ohlcv, 50)
            self.ema100_data = self.compute_ema(self.ohlcv, 100)
            self.ema200_data = self.compute_ema(self.ohlcv, 200)
            self.ao_data = self.compute_ao(self.ohlcv)
            self.uo_data = self.calc_uo(self.ohlcv)
            self.bbp_data = self.calc_bbp(self.ohlcv)
            self.momentum_data = self.calc_momentum(self.ohlcv)
            self.bb_bands_data = self.compute_bb_bands(self.ohlcv)
            self.sar_data = self.compute_sar(self.ohlcv)
            self.mfi_data = self.compute_mfi(self.ohlcv)'''
            compute_stoch(self.ohlcv)
            compute_ichimoku_base_line(self.ohlcv)
            compute_macd(self.ohlcv)
            compute_wpr(self.ohlcv)
            compute_cci(self.ohlcv)
            compute_adx(self.ohlcv)
            compute_rsi(self.ohlcv)
            compute_stoch_rsi(self.ohlcv)
            compute_vwma(self.ohlcv)
            compute_sma(self.ohlcv, 10)
            compute_sma(self.ohlcv, 20)
            compute_sma(self.ohlcv, 30)
            compute_sma(self.ohlcv, 50)
            compute_sma(self.ohlcv, 100)
            compute_sma(self.ohlcv, 200)
            compute_ema(self.ohlcv, 10)
            compute_ema(self.ohlcv, 20)
            compute_ema(self.ohlcv, 30)
            compute_ema(self.ohlcv, 50)
            compute_ema(self.ohlcv, 100)
            compute_ema(self.ohlcv, 200)
            compute_ao(self.ohlcv)
            calc_uo(self.ohlcv)
            calc_bbp(self.ohlcv)
            calc_momentum(self.ohlcv)
            compute_bb_bands(self.ohlcv)
            compute_sar(self.ohlcv)
            compute_mfi(self.ohlcv)
            compute_hull_moving_average(self.ohlcv)
        
            return self.ohlcv
        except Exception as e:
            logger.exception(e)

import json
def update_symbol_data(symbol, interval,exchange,realExchange,id):
    fullRes = Indicator(
        exchange=exchange, 
        pair=symbol,
        interval=interval,
        verbose=0
    ).update_data(symbol,exchange,interval,realExchange).to_dict(orient='records')
    res = fullRes[-1]
    price = getPrice(exchange,symbol,id)
    dataToReturn = {
                    "ema200": replace_nan(res["ema200"]),
                    "ema100": replace_nan(res["ema100"]),
                    "ema50": replace_nan(res["ema50"]),
                    "ema30": replace_nan(res["ema30"]),
                    "ema20": replace_nan(res["ema20"]),
                    "ema10": replace_nan(res["ema10"]),
                    "sma200": replace_nan(res["sma200"]),
                    "sma100": replace_nan(res["sma100"]),
                    "sma50": replace_nan(res["sma50"]),
                    "sma30": replace_nan(res["sma30"]),
                    "sma20": replace_nan(res["sma20"]),
                    "sma10": replace_nan(res["sma10"]),
                    "adx": replace_nan(res["adx"]),
                    "cci": replace_nan(res["cci"]),
                    "wpr": replace_nan(res["wpr"]),
                    "ichimoku_base_line": replace_nan(res["ichimoku_base_line"]),
                    "stoch": res["slowk"],
                    "macd": res["macd"],
                    "rsi": res["indicator"],
                    "stoch_rsi": res["Stoch_RSI_%K"],
                    "vwma": res["vwma"],
                    "ao": res["ao"],
                    "uo": res["uo"],
                    "bbp_bull": res["bull_power"],
                    "bbp_bear": res["bear_power"],
                    "momentum": res["momentum"],
                    "hma": res["hma"],
                    "rsi_signal": rsi_signal(res["indicator"]),
                    "stoch_rsi_signal": stoch_rsi_signal(res["Stoch_RSI_%K"],res["Stoch_RSI_%D"]),
                    "ichimoku_base_line_signal": ichimoku_base_line_signal(res["ichimoku_base_line"],exchange,symbol,price),
                    "vwma_signal": vwma_signal(res["vwma"],exchange,symbol,price),
                    "macd_signal": macd_signal(res["macd"],res["signal"]),
                    "wpr_signal": wpr_signal(res["wpr"]),
                    "cci_signal": cci_signal(res["cci"]),
                    "adx_signal": adx_signal(res["adx"]),
                    "stoch_signal": stoch_signal(res["slowk"],res["slowd"]),
                    "sma10_signal": ma_signal(res["sma10"],exchange,symbol,price),
                    "sma20_signal": ma_signal(res["sma20"],exchange,symbol,price),
                    "sma30_signal": ma_signal(res["sma30"],exchange,symbol,price),
                    "sma50_signal": ma_signal(res["sma50"],exchange,symbol,price),
                    "sma100_signal": ma_signal(res["sma100"],exchange,symbol,price),
                    "sma200_signal": ma_signal(res["sma200"],exchange,symbol,price),
                    "ema10_signal": ma_signal(res["ema10"],exchange,symbol,price),
                    "ema20_signal": ma_signal(res["ema20"],exchange,symbol,price),
                    "ema30_signal": ma_signal(res["ema30"],exchange,symbol,price),
                    "ema50_signal": ma_signal(res["ema50"],exchange,symbol,price),
                    "ema100_signal": ma_signal(res["ema100"],exchange,symbol,price),
                    "ema200_signal": ma_signal(res["ema200"],exchange,symbol,price),
                    "bbp_signal": bbp_signal(res["bull_power"],res["bear_power"]),
                    "ao_signal": ao_signal(res["ao"]),
                    "uo_signal": uo_signal(res["uo"]),
                    "momentum_signal": momentum_signal(res["close"],res["momentum"]),
                    "hma_signal": hma_signal(fullRes),
                }
    return json.dumps(dataToReturn)

{'RECOMMENDATION': 'BUY', 'BUY': 12, 'SELL': 7, 'NEUTRAL': 9}

def calculate_signals2(symbols, interval, exchange):
    try:
        signals = []
        for symbol in symbols:
            file_name = f"stochData/stoch_{symbol.replace('/','')}_{interval}_{exchange}.json"
            if os.path.isfile(file_name):
                res = None
                with open(file_name, "r") as f:
                    res = json.load(f)[symbol.replace('/','')]['summary']
                buy_count = res["BUY"]
                sell_count = res["SELL"]
                dataToReturn = {
                        "symbol": symbol,
                        "buy_count": buy_count,
                        "buy_percentage": (buy_count/(buy_count+sell_count if buy_count+sell_count !=0 else 1))*100,
                        "sell_count":sell_count,
                        "sell_percentage": (sell_count/(buy_count+sell_count if  buy_count+sell_count !=0 else 1))*100,
                        "percentage": (buy_count/(buy_count+sell_count if  buy_count+sell_count !=0 else 1))*100,
                    }     
                signals.append(dataToReturn)

        sorted_signals_buy = sorted(signals, key=lambda x: x["buy_percentage"], reverse=True)
        sorted_signals_sell = sorted(signals, key=lambda x: x["sell_percentage"], reverse=True)
        return json.dumps([sorted_signals_buy,sorted_signals_sell])
    except:
        return json.dumps([[],[]])

def calculate_signals(symbols, interval, exchange, realExchange, id):
        signals = []
        for symbol in symbols:
            try:
                #fullRes = fetch_ohlcv2(symbol,exchange,interval,realExchange)

                file_name = f"stochData/stoch_{symbol.replace('/','')}_{interval}_{exchange}.json"
                data = None
                if os.path.isfile(file_name):
                    with open(file_name, "r") as f:
                        result = json.load(f)
                        data = [[int(datetime.strptime(d['time'], '%Y-%m-%d %H:%M:%S').timestamp() * 1000), d['open'], d['high'], d['low'], d['close'], d['volume']] for d in result]

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

                    fullRes = (result.loc[:, [
                        'time', 'open', 'high', 'low', 'close', 'volume'
                    ]])
                    
                
                    stoch_data = compute_stoch(fullRes)
                    compute_macd(fullRes)
                    compute_wpr(fullRes)
                    compute_cci(fullRes)
                    compute_adx(fullRes)
                    compute_rsi(fullRes)
                    compute_stoch_rsi(fullRes)
                    compute_vwma(fullRes)
                    compute_ichimoku_base_line(fullRes)
                    compute_sma(fullRes, 10)
                    compute_sma(fullRes, 20)
                    compute_sma(fullRes, 30)
                    compute_sma(fullRes, 50)
                    compute_sma(fullRes, 100)
                    compute_sma(fullRes, 200)
                    compute_ema(fullRes, 10)
                    compute_ema(fullRes, 20)
                    compute_ema(fullRes, 30)
                    compute_ema(fullRes, 50)
                    compute_ema(fullRes, 100)
                    compute_ema(fullRes, 200)
                    compute_ao(fullRes)
                    calc_uo(fullRes)
                    calc_bbp(fullRes)
                    calc_momentum(fullRes)
                    compute_bb_bands(fullRes)
                    compute_sar(fullRes)
                    compute_mfi(fullRes)

                    res = stoch_data.to_dict(orient='records')[-1]
                    price = getPrice_assets(exchange,symbol,id)
                    signals_data = [
                        rsi_signal(res["indicator"]),
                        stoch_rsi_signal(res["Stoch_RSI_%K"], res["Stoch_RSI_%D"]),
                        ichimoku_base_line_signal(res["ichimoku_base_line"],exchange,symbol,price),
                        vwma_signal(res["vwma"],exchange,symbol,price),
                        macd_signal(res["macd"], res["signal"]),
                        wpr_signal(res["wpr"]),
                        cci_signal(res["cci"]),
                        adx_signal(res["adx"]),
                        stoch_signal(res["slowk"], res["slowd"]),
                        ma_signal(res["sma10"],exchange,symbol,price),
                        ma_signal(res["sma20"],exchange,symbol,price),
                        ma_signal(res["sma30"],exchange,symbol,price),
                        ma_signal(res["sma50"],exchange,symbol,price),
                        ma_signal(res["sma100"],exchange,symbol,price),
                        ma_signal(res["sma200"],exchange,symbol,price),
                        ma_signal(res["ema10"],exchange,symbol,price),
                        ma_signal(res["ema20"],exchange,symbol,price),
                        ma_signal(res["ema30"],exchange,symbol,price),
                        ma_signal(res["ema50"],exchange,symbol,price),
                        ma_signal(res["ema100"],exchange,symbol,price),
                        ma_signal(res["ema200"],exchange,symbol,price),
                        bbp_signal(res["bull_power"], res["bear_power"]),
                        ao_signal(res["ao"]),
                        uo_signal(res["uo"]),
                        momentum_signal(res["close"], res["momentum"]),
                    ]
                    buy_count = signals_data.count("buy")
                    sell_count = signals_data.count("sell")
                    dataToReturn = {
                        "symbol": symbol,
                        "buy_count": buy_count,
                        "buy_percentage": (buy_count/(buy_count+sell_count))*100,
                        "sell_count":sell_count,
                        "sell_percentage": (sell_count/(buy_count+sell_count))*100,
                        "percentage": (buy_count/(buy_count+sell_count))*100,
                    }     
                    signals.append(dataToReturn)
            except Exception as e:
                logger.exception(e)

        sorted_signals_buy = sorted(signals, key=lambda x: x["buy_percentage"], reverse=True)
        sorted_signals_sell = sorted(signals, key=lambda x: x["sell_percentage"], reverse=True)
        return json.dumps([sorted_signals_buy,sorted_signals_sell])


def replace_nan(value):
    if math.isnan(value):
        return 0
    else:
        return value

def rsi_signal(rsi_value):
    if rsi_value < 30:
        return 'buy'
    elif rsi_value > 70:
        return 'sell'
    else:
        return 'neutral'

def stoch_rsi_signal(k_value, d_value):
    oversold_threshold = 20
    overbought_threshold = 80

    if k_value > d_value and k_value < oversold_threshold:
        return 'buy'
    elif k_value < d_value and k_value > overbought_threshold:
        return 'sell'
    else:
        return 'neutral'

def ichimoku_base_line_signal(ichimoku_base_line,exchange,symbol,price):
    if ichimoku_base_line < price:
        return 'buy'
    elif ichimoku_base_line > price:
        return 'sell'
    else:
        return 'neutral'

def vwma_signal(vwma_line,exchange,symbol,price):
    if vwma_line > price:
        return 'buy'
    elif vwma_line < price:
        return 'sell'
    else:
        return 'neutral'

def hma_signal(hma_value):
    if hma_value[-2]['hma'] < hma_value[-1]['hma']:
        return 'buy'
    elif hma_value[-2]['hma'] > hma_value[-1]['hma']:
        return 'sell'
    else:
        return 'neutral'

def momentum_signal(price, momentum):
    if price > momentum:
        return 'buy'
    elif price < momentum:
        return 'sell'
    else:
        return 'neutral'

def bbp_signal(bbp_bull,bbp_bear):
    if bbp_bull > 0 and bbp_bear < 0:
        return 'buy'
    elif bbp_bull < 0 and bbp_bear > 0:
        return 'sell'
    else:
        return 'neutral'
    
def ao_signal(ao_value):
    if ao_value > 0:
        return 'buy'
    elif ao_value < 0:
        return 'sell'
    else:
        return 'neutral'
    
def uo_signal(uo_value):
    if uo_value < 30:
        return 'buy'
    elif uo_value > 70:
        return 'sell'
    else:
        return 'neutral'

def macd_signal(macd, signal):
    if macd > signal:
        return 'buy'
    elif macd < signal:
        return 'sell'
    else:
        return 'neutral'

def stoch_signal(stoch_k, stoch_d):
    if stoch_k < 20 and stoch_d < 20:
        return 'buy'
    elif stoch_k > 80 and stoch_d > 80:
        return 'sell'
    else:
        return 'neutral'

def wpr_signal(wpr_value):
    if wpr_value < -80:
        return 'buy'
    elif wpr_value > -20:
        return 'sell'
    else:
        return 'neutral'

def cci_signal(cci_value):
    if cci_value < -100:
        return 'buy'
    elif cci_value > 100:
        return 'sell'
    else:
        return 'neutral'

def adx_signal(adx_value):
    if adx_value > 25:
        return 'buy'
    elif adx_value < 20:
        return 'sell'
    else:
        return 'neutral'

def ma_signal(ma,exchange,symbol,price):
    if price > ma:
        return 'buy'
    elif price < ma:
        return 'sell'
    else:
        return 'neutral'

def fetch_ohlcv2(symbol,exchange,interval,realExchange):
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

            result = realExchange.fetch_ohlcv(
                symbol=symbol, timeframe=interval,limit = time_ranges[interval])
            
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

def fetch_data(symbol,exchange,interval):
        exchange = exchange.replace('okx','okex')
        file_name = f"stochData2/stoch_{symbol.replace('/','')}_{interval}_{exchange}.json"
        data = None
        if os.path.isfile(file_name):
            with open(file_name, "r") as f:
                result = json.load(f)
                data = [[int(datetime.strptime(d['time'], '%Y-%m-%d %H:%M:%S').timestamp() * 1000), d['open'], d['high'], d['low'], d['close'], d['volume']] for d in result]

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

            return result.loc[:, [
                'time', 'open', 'high', 'low', 'close', 'volume'
            ]]

def fetch_data2(symbol,exchange,interval):
        file_name = f"stochData/stoch_{symbol.replace('/','')}_{interval}_{exchange}.json"
        if os.path.isfile(file_name):
            with open(file_name, "r") as f:
                return json.load(f)[symbol.replace('/','')]

def update_symbol_data2(symbol,interval,exchange):
        file_name = f"stochData/stoch_{symbol.replace('/','')}_{interval}_{exchange}.json"
        if os.path.isfile(file_name):
            with open(file_name, "r") as f:
                try:
                    res = json.load(f)[symbol.replace('/','')]
                    
                    return json.dumps({
                        "ema200": res['indicators']["EMA200"] if res['indicators']["EMA200"] else 0,
                        "ema100": res['indicators']["EMA100"] if res['indicators']["EMA100"] else 0,
                        "ema50": res['indicators']["EMA50"] if res['indicators']["EMA50"] else 0,
                        "ema30": res['indicators']["EMA30"] if res['indicators']["EMA30"] else 0,
                        "ema20": res['indicators']["EMA20"] if res['indicators']["EMA20"] else 0,
                        "ema10": res['indicators']["EMA10"] if res['indicators']["EMA10"] else 0,
                        "sma200": res['indicators']["SMA200"] if res['indicators']["SMA200"] else 0,
                        "sma100": res['indicators']["SMA100"] if res['indicators']["SMA100"] else 0,
                        "sma50": res['indicators']["SMA50"] if res['indicators']["SMA50"] else 0,
                        "sma30": res['indicators']["SMA30"] if res['indicators']["SMA30"] else 0,
                        "sma20": res['indicators']["SMA20"] if res['indicators']["SMA20"] else 0,
                        "sma10": res['indicators']["SMA10"] if res['indicators']["SMA10"] else 0,
                        "adx": res['indicators']["ADX"] if res['indicators']["ADX"] else 0,
                        "cci": res['indicators']["CCI20"] if res['indicators']["CCI20"] else 0,
                        "wpr": res['indicators']["W.R"] if res['indicators']["W.R"] else 0,
                        "ichimoku_base_line": res['indicators']["Ichimoku.BLine"] if res['indicators']["Ichimoku.BLine"] else 0,
                        "stoch": res['indicators']["Stoch.K"] if res['indicators']["Stoch.K"] else 0,
                        "macd": res['indicators']["MACD.macd"] if res['indicators']["MACD.macd"] else 0,
                        "rsi": res['indicators']["RSI"] if res['indicators']["RSI"] else 0,
                        "stoch_rsi": res['indicators']["Stoch.RSI.K"] if res['indicators']["Stoch.RSI.K"] else 0,
                        "vwma": res['indicators']["VWMA"] if res['indicators']["VWMA"] else 0,
                        "ao": res['indicators']["AO"] if res['indicators']["AO"] else 0,
                        "uo": res['indicators']["UO"] if res['indicators']["UO"] else 0,
                        "bbp_bull": res['indicators']["BBPower"] if res['indicators']["BBPower"] else 0,
                        "bbp_bear": res['indicators']["BBPower"] if res['indicators']["BBPower"] else 0,
                        "momentum": res['indicators']["Mom"] if res['indicators']["Mom"] else 0,
                        "hma": res['indicators']["HullMA9"] if res['indicators']["HullMA9"] else 0,
                        "rsi_signal": res["signals"]["RSI"] if 'RSI' in res["signals"] else '',
                        "stoch_rsi_signal": res["signals"]["Stoch.RSI"] if 'Stoch.RSI' in res["signals"] else "",
                        "ichimoku_base_line_signal": res["signals2"]["Ichimoku"] if 'Ichimoku' in res["signals2"] else "",
                        "vwma_signal": res["signals2"]["VWMA"] if 'VWMA' in res["signals2"] else "",
                        "macd_signal": res["signals"]["MACD"] if 'MACD' in res["signals"] else "",
                        "wpr_signal": res["signals"]["W%R"] if 'W%R' in res["signals"] else "",
                        "cci_signal": res["signals"]["CCI"] if 'CCI' in res["signals"] else "",
                        "adx_signal": res["signals"]["ADX"] if 'ADX' in res["signals"] else "",
                        "stoch_signal": res["signals"]["STOCH.K"] if 'STOCH.K' in res["signals"] else "",
                        "sma10_signal": res["signals2"]["SMA10"] if 'SMA10' in res["signals2"] else "",
                        "sma20_signal": res["signals2"]["SMA20"] if 'SMA20' in res["signals2"] else "",
                        "sma30_signal": res["signals2"]["SMA30"] if 'SMA30' in res["signals2"] else "",
                        "sma50_signal": res["signals2"]["SMA50"] if 'SMA50' in res["signals2"] else "",
                        "sma100_signal": res["signals2"]["SMA100"] if 'SMA100' in res["signals2"] else "",
                        "sma200_signal": res["signals2"]["SMA200"] if 'SMA200' in res["signals2"] else "",
                        "ema10_signal": res["signals2"]["EMA10"] if 'EMA10' in res["signals2"] else "",
                        "ema20_signal": res["signals2"]["EMA20"] if 'EMA20' in res["signals2"] else "",
                        "ema30_signal": res["signals2"]["EMA30"] if 'EMA30' in res["signals2"] else "",
                        "ema50_signal": res["signals2"]["EMA50"] if 'EMA50' in res["signals2"] else "",
                        "ema100_signal": res["signals2"]["EMA100"] if 'EMA100' in res["signals2"] else "",
                        "ema200_signal": res["signals2"]["EMA200"] if 'EMA200' in res["signals2"] else "",
                        "bbp_signal": res["signals"]["BBP"] if 'BBP' in res["signals"] else "",
                        "ao_signal": res["signals"]["AO"] if 'AO' in res["signals"] else "",
                        "uo_signal": res["signals"]["UO"] if 'UO' in res["signals"] else "",
                        "momentum_signal": res["signals"]["Mom"] if 'Mom' in res["signals"] else "",
                        "hma_signal": res["signals2"]["HullMA"] if 'HullMA' in res["signals2"] else "",
                    })
                except Exception as e:
                    logger.exception(e)
                    return json.dumps({})


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

########################################

def compute_stoch( data):
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

def compute_macd( data):
    try:
        macd, signal, hist = talib.MACD(data.close, fastperiod=12, slowperiod=26, signalperiod=9)
        data.loc[:, 'macd'] = macd
        data.loc[:, 'signal'] = signal
        data.loc[:, 'hist'] = hist
        return data
    except Exception as e:
        logger.exception(e)

def compute_wpr( data):
    try:
        wpr = talib.WILLR(data.high, data.low, data.close, timeperiod=14)
        data.loc[:, 'wpr'] = wpr

        return data
    except Exception as e:
        logger.exception(e)

def compute_adx(data):
    try:
        adx = talib.ADX(data.high, data.low, data.close, timeperiod=14)
        data.loc[:, 'adx'] = adx

        return data
    except Exception as e:
        logger.exception(e)

def compute_ao(data):
    try:
        #ao = talib.MA(data.close, timeperiod=5, matype=talib.MA_Type.SMA) - talib.MA(data.close, timeperiod=34, matype=talib.MA_Type.SMA)
        ao = talib.SMA(data.close, timeperiod=5) - talib.SMA(data.close, timeperiod=34)
        data.loc[:, 'ao'] = ao

        return data
    except Exception as e:
        logger.exception(e)

def compute_cci(data):
    try:
        cci = talib.CCI(data.high, data.low, data.close, timeperiod=20)
        data.loc[:, 'cci'] = cci

        return data
    except Exception as e:
        logger.exception(e)

def calc_uo( data):
    try:
        high = data.high
        low = data.low
        close = data.close

        uo = talib.ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28)
        data['uo'] = uo

        return data
    except Exception as e:
        logger.exception(e)

def calc_bbp( data):
    try:
        high = data.high
        low = data.low
        close = data.close

        bull_power = high - talib.EMA(close, timeperiod=15)
        bear_power = low - talib.EMA(close, timeperiod=15)
        #bull_power = talib.SUM(data.loc[:, 'indicator'] > 70, 15)
        #bear_power = talib.SUM(data.loc[:, 'indicator'] < 30, 15)  

        data.loc[:, 'bull_power'] = bull_power
        data.loc[:, 'bear_power'] = bear_power

        return data
    except Exception as e:
        logger.exception(e)

def calc_momentum(data):
    try:
        momentum = talib.MOM(data.close, timeperiod=10)
        data.loc[:, 'momentum'] = momentum
        return data
    except Exception as e:
        logger.exception(e)

def compute_rsi(data):
    try:
        indicator = talib.RSI(data.close, 14)
        data.loc[:, 'indicator'] = indicator

        return data
    except Exception as e:
        logger.exception(e)

def compute_stoch_rsi(data):
    try:
        # Calculate Stochastic RSI
        stoch_rsi = talib.STOCHRSI(data.indicator, 14, 3, 3, 0)
        data.loc[:, 'Stoch_RSI_%K'] = stoch_rsi[0]
        data.loc[:, 'Stoch_RSI_%D'] = stoch_rsi[1]

        return data
    except Exception as e:
        logger.exception(e)

def compute_vwma(data):
    try:
        vwma = data.close.ewm(span=20, min_periods=20 - 1).mean()
        data.loc[:, 'vwma'] = vwma

        return data
    except Exception as e:
        logger.exception(e)

def compute_ichimoku_base_line(data):
    try:

        nine_period_high = talib.MAX(data.high, timeperiod=9)
        nine_period_low = talib.MIN(data.low, timeperiod=9)
        ichimoku_base_line = (nine_period_high + nine_period_low) / 2
        data.loc[:, 'ichimoku_base_line'] = ichimoku_base_line

        return data
    except Exception as e:
        logger.exception(e)

def compute_hull_moving_average(data):
    try:
        hma = talib.WMA(2 * talib.WMA(data.close, 9 // 2) - talib.WMA(data.close, 9), int(9 ** 0.5))
        data.loc[:, 'hma'] = hma

        return data
    except Exception as e:
        logger.exception(e)

def compute_ema(data, timeperiod):
    try:
        ema = talib.EMA(data.close, timeperiod)
        data.loc[:, f'ema{timeperiod}'] = ema
        return data
    except Exception as e:
        logger.exception(e)

def compute_sma(data, timeperiod):
    try:
        sma = talib.SMA(data.close, timeperiod)
        data.loc[:, f'sma{timeperiod}'] = sma

        return data
    except Exception as e:
        logger.exception(e)

def compute_mfi(data):
    try:
        # Calculate Money Flow Index
        mfi = talib.MFI(data.high, data.low, data.close, data.volume, timeperiod=14)
        data.loc[:, 'mfi'] = mfi
        return data
    except Exception as e:
        logger.exception(e)

def compute_bb_bands(data):
    try:
        # Calculate Bollinger Bands
        upper_band, middle_band, lower_band = talib.BBANDS(data.close, timeperiod=20)
        data.loc[:, 'upper_band'] = upper_band
        data.loc[:, 'middle_band'] = middle_band
        data.loc[:, 'lower_band'] = lower_band
        return data
    except Exception as e:
        logger.exception(e)

def compute_sar(data):
    try:
        # Calculate Parabolic SAR
        sar = talib.SAR(data.high, data.low, acceleration=0.02, maximum=0.2)
        data.loc[:, 'sar'] = sar
        return data
    except Exception as e:
        logger.exception(e)

def compute_hma(data):
    try:
        # Calculate Hull Moving Average (9)
        hma = talib.HMA(data.close, timeperiod=9)
        data.loc[:, 'hma'] = hma
        return data
    except Exception as e:
        logger.exception(e)

