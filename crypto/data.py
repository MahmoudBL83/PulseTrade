from flask import jsonify, request
import json
import os
from crypto import app
import math
from search_crypto import search

def _computed_price_payload(symbol_val, interval, exchange):
    """/getPrice/ payload computed from market data + the TA engine, used when
    the TradingView socket workers have not written pricesData files."""
    from crypto import market, ta
    sym = market.normalize_symbol(symbol_val)
    t = market.ticker(exchange, sym)
    a = ta.analysis(exchange, sym, interval if interval in market.TIMEFRAMES else "15m")
    ind = a["indicators"]

    def v(key, digits=2, scale=1.0):
        val = ind.get(key)
        return round(val / scale, digits) if isinstance(val, (int, float)) else 0

    price = t["last"]
    out = {
        "symbol": symbol_val, "price": price, "volume": t["baseVolume"],
        "market_cap_dominance": 0, "price_change": t["percentage"], "market_cap": 0,
        "percent_change_24h": t["percentage"], "circulating_supply": 0, "cmc_rank": 0,
        "total_supply": 0, "max_supply": 0, "full_market_cap": 0,
        "bp": v("BBPower"), "adx": v("ADX"), "ao": v("AO"), "cci": v("CCI20"), "wpr": v("W.R"),
        "ma": v("SMA20"), "stoch": v("Stoch.K"), "obv": 0, "bb_middle": v("BB.middle"),
        "bb_lower": v("BB.lower"), "bb_upper": v("BB.upper"), "trix": 0, "macd": v("MACD.macd"),
        "rsi": v("RSI"), "source": t.get("source"),
    }
    for n in (10, 20, 30, 50, 100, 200):
        out[f"ema{n}"], out[f"sma{n}"] = v(f"EMA{n}"), v(f"SMA{n}")
    out.update({
        "rsi_signal": rsi_signal(out["rsi"]),
        "macd_signal": macd_signal(out["macd"], v("MACD.signal")),
        "wpr_signal": wpr_signal(out["wpr"]), "cci_signal": cci_signal(out["cci"]),
        "adx_signal": adx_signal(out["adx"]), "ma_signal": ma_signal(price, out["ma"]),
        "stoch_signal": stoch_signal(out["stoch"], v("Stoch.D")),
    })
    for n in (10, 20, 30, 50, 100, 200):
        out[f"sma{n}_signal"] = ma_signal(price, out[f"sma{n}"])
        out[f"ema{n}_signal"] = ma_signal(price, out[f"ema{n}"])
    if os.environ.get("DEMO", "0") == "1":
        out["demo"] = True
    return out


@app.route("/getPrice/")
def getPrice():
    symbol_val = request.args.get('symbol')
    interval = request.args.get('interval') or "15m"
    interval = interval.strip('"\'')
    exchange = request.args.get('exchange') or "okx"
    if not symbol_val:
        return jsonify({"error": "symbol parameter is required"}), 400
    symbol_val = "".join(ch for ch in symbol_val if ch.isalnum()).upper()
    symbol = f"OKX:{symbol_val}"

    # check if symbol exists in prices3.json
    if os.path.isfile("pricesData/"+f"OKX{symbol_val}.json"):
        with open("pricesData/"+f"OKX{symbol_val}.json", "r") as f:
            existing_data = json.load(f)
            if symbol in existing_data:
                price = existing_data[symbol][0]
                volume = existing_data[symbol][2]
                market_cap_dominance = existing_data[symbol][3]
                price_change = existing_data[symbol][4]
                market_cap = existing_data[symbol][5]
                percent_change_24h = existing_data[symbol][6]
                circulating_supply = existing_data[symbol][7]
                cmc_rank = existing_data[symbol][8]
                total_supply = existing_data[symbol][9]
                max_supply = existing_data[symbol][10]
                full_market_cap = existing_data[symbol][11]
                ema200 = get_ema(f"{symbol_val}",interval,200,exchange.lower().replace("okx","okex"))
                ema100 = get_ema(f"{symbol_val}",interval,100,exchange.lower().replace("okx","okex"))
                ema50 = get_ema(f"{symbol_val}",interval,50,exchange.lower().replace("okx","okex"))
                ema30 = get_ema(f"{symbol_val}",interval,30,exchange.lower().replace("okx","okex"))
                ema20 = get_ema(f"{symbol_val}",interval,20,exchange.lower().replace("okx","okex"))
                ema10 = get_ema(f"{symbol_val}",interval,10,exchange.lower().replace("okx","okex"))
                sma200 = get_sma(f"{symbol_val}",interval,200,exchange.lower().replace("okx","okex"))
                sma100 = get_sma(f"{symbol_val}",interval,100,exchange.lower().replace("okx","okex"))
                sma50 = get_sma(f"{symbol_val}",interval,50,exchange.lower().replace("okx","okex"))
                sma30 = get_sma(f"{symbol_val}",interval,30,exchange.lower().replace("okx","okex"))
                sma20 = get_sma(f"{symbol_val}",interval,20,exchange.lower().replace("okx","okex"))
                sma10 = get_sma(f"{symbol_val}",interval,10,exchange.lower().replace("okx","okex"))
                bp = get_bp(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                adx = get_adx(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                ao = get_ao(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                cci = get_cci(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                wpr = get_wpr(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                ma = get_ma(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                stochk = get_stochk(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                stochd = get_stochd(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                obv = get_obv(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                bb_middle = get_bb_middle(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                bb_lower = get_bb_lower(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                bb_upper = get_bb_upper(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                trix = get_trix(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                macd = get_macd(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                signal = get_signal(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))
                rsi = get_rsi(f"{symbol_val}",interval,exchange.lower().replace("okx","okex"))

                # replace NaN values with 0
                ema200 = 0 if math.isnan(ema200) else ema200
                ema100 = 0 if math.isnan(ema100) else ema100
                ema50 = 0 if math.isnan(ema50) else ema50
                ema30 = 0 if math.isnan(ema30) else ema30
                ema20 = 0 if math.isnan(ema20) else ema20
                ema10 = 0 if math.isnan(ema10) else ema10
                sma200 = 0 if math.isnan(sma200) else sma200
                sma100 = 0 if math.isnan(sma100) else sma100
                sma50 = 0 if math.isnan(sma50) else sma50
                sma30 = 0 if math.isnan(sma30) else sma30
                sma20 = 0 if math.isnan(sma20) else sma20
                sma10 = 0 if math.isnan(sma10) else sma10
                bp = 0 if math.isnan(bp) else bp
                adx = 0 if math.isnan(adx) else adx
                ao = 0 if math.isnan(ao) else ao
                cci = 0 if math.isnan(cci) else cci
                wpr = 0 if math.isnan(wpr) else wpr
                ma = 0 if math.isnan(ma) else ma
                stochk =0 if math.isnan(stochk) else stochk
                obv = 0 if math.isnan(obv) else obv
                bb_middle = 0 if math.isnan(bb_middle) else bb_middle
                bb_lower = 0 if math.isnan(bb_lower) else bb_lower
                bb_upper = 0 if math.isnan(bb_upper) else bb_upper
                trix = 0 if math.isnan(trix) else trix
                macd = 0 if math.isnan(macd) else macd
                rsi = 0 if math.isnan(rsi) else rsi
                
                return jsonify({
                    "symbol": symbol_val,
                    "price": price,
                    "volume": volume,
                    "market_cap_dominance": market_cap_dominance,
                    "price_change": percent_change_24h,
                    "market_cap": market_cap,
                    "percent_change_24h": percent_change_24h,
                    "circulating_supply": circulating_supply,
                    "cmc_rank": cmc_rank,
                    "total_supply": total_supply,
                    "max_supply": max_supply,
                    "full_market_cap": full_market_cap,
                    "ema200": ema200,
                    "ema100": ema100,
                    "ema50": ema50,
                    "ema30": ema30,
                    "ema20": ema20,
                    "ema10": ema10,
                    "sma200": sma200,
                    "sma100": sma100,
                    "sma50": sma50,
                    "sma30": sma30,
                    "sma20": sma20,
                    "sma10": sma10,
                    "bp": bp,
                    "adx": adx,
                    "ao": ao,
                    "cci": cci,
                    "wpr": wpr,
                    "ma": ma,
                    "stoch": stochk,
                    "obv": obv,
                    "bb_middle": bb_middle,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                    "trix": trix,
                    "macd": macd,
                    "rsi": rsi,
                    "rsi_signal": rsi_signal(rsi),
                    "macd_signal": macd_signal(macd,signal),
                    "wpr_signal": wpr_signal(wpr),
                    "cci_signal": cci_signal(cci),
                    "adx_signal": adx_signal(adx),
                    "ma_signal": ma_signal(price,ma),
                    "stoch_signal": stoch_signal(stochk,stochd),
                    "sma10_signal": ma_signal(price,sma10),
                    "sma20_signal": ma_signal(price,sma20),
                    "sma30_signal": ma_signal(price,sma30),
                    "sma50_signal": ma_signal(price,sma50),
                    "sma100_signal": ma_signal(price,sma100),
                    "sma200_signal": ma_signal(price,sma200),
                    "ema10_signal": ma_signal(price,ema10),
                    "ema20_signal": ma_signal(price,ema20),
                    "ema30_signal": ma_signal(price,ema30),
                    "ema50_signal": ma_signal(price,ema50),
                    "ema100_signal": ma_signal(price,ema100),
                    "ema200_signal": ma_signal(price,ema200),
                })
    return jsonify(_computed_price_payload(symbol_val, interval, exchange))


def _safe_name(value):
    return "".join(ch for ch in str(value or "") if ch.isalnum() or ch in "-_").upper()[:40]

@app.route("/openOrders/")
def openOrders():
    symbol = _safe_name(request.args.get("symbol"))
    exchange = _safe_name(request.args.get("exchange")).lower()
    side = _safe_name(request.args.get("side")).lower()
    if not symbol:
        return jsonify({"error": "symbol parameter is required"}), 400
    try:
        with open(f"orders/{side}_{symbol}_{exchange}.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        # Same shape as the worker files: a list of {price, amount} records for
        # one side, ordered so the legacy page's reverse() puts the best first.
        from crypto import market
        book = market.order_book(exchange or None, symbol, 20)
        if side == "sell":
            levels = sorted(book["asks"], key=lambda l: l[0], reverse=True)
        else:
            levels = sorted(book["bids"], key=lambda l: l[0])
        return jsonify([{"price": p, "amount": a, "side": side or "buy"} for p, a in levels])

@app.route("/lastTrades/")
def lastTrades():
    symbol = _safe_name(request.args.get("symbol"))
    exchange = _safe_name(request.args.get("exchange")).lower()
    if not symbol:
        return jsonify({"error": "symbol parameter is required"}), 400
    try:
        with open(f"trades/{symbol}_{exchange}.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        from crypto import market
        # oldest first, like the worker files (the page reverses it)
        return jsonify(market.trades(exchange or None, symbol, 30)[::-1])

##############################################################################

def get_rsi(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['indicator'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_macd(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['macd'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading macd data: {e}")
        return 0

def get_signal(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['signal'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading signal data: {e}")
        return 0

def get_wpr(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['wpr'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading wpr data: {e}")
        return 0

def get_trix(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['trix'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading trix data: {e}")
        return 0
    
def get_obv(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['obv']/1000,2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading obv data: {e}")
        return 0
    
def get_bb_middle(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['middle_band'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_bb_upper(path,interval,exchange):
    try:
        if os.path.isfile(f"bbData/bb_{path}_{interval}.json") and os.path.getsize(f"bbData/bb_{path}_{interval}.json") > 0:
            with open(f"bbData/bb_{path}_{interval}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['upper_band'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_bb_lower(path,interval,exchange):
    try:
        if os.path.isfile(f"bbData/bb_{path}_{interval}.json") and os.path.getsize(f"bbData/bb_{path}_{interval}.json") > 0:
            with open(f"bbData/bb_{path}_{interval}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['lower_band'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_stochk(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['slowk'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_stochd(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['slowd'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_cci(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['cci'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_ma(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['ma'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0
    
def get_ao(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['ao'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_adx(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['adx'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0
    
def get_bp(path,interval,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1]['bp'],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading RSI data: {e}")
        return 0

def get_sma(path,interval,period,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1][f"sma{period}"],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading sma data: {e}")
        return 0

def get_ema(path,interval,period,exchange):
    try:
        if os.path.isfile(f"stochData/stoch_{path}_{interval}_{exchange}.json") and os.path.getsize(f"stochData/stoch_{path}_{interval}_{exchange}.json") > 0:
            with open(f"stochData/stoch_{path}_{interval}_{exchange}.json", "r") as f:
                data = json.load(f)
            return round(data[-1][f"ema{period}"],2)
        else:
            return 0
    except Exception as e:
        print(f"Error loading ema data: {e}")
        return 0

###################signals###############################

def rsi_signal(rsi_value):
    if rsi_value < 30:
        return 'buy'
    elif rsi_value > 70:
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

def ma_signal(price, ma):
    if price > ma:
        return 'buy'
    elif price < ma:
        return 'sell'
    else:
        return 'neutral'
        