"""Technical-analysis engine computed from OHLCV.

``analysis()`` returns the same structure the legacy TradingView screener
files used (summary / indicators / signals / signals2) so the old endpoints,
bot conditions and the new React UI can all consume it, with or without the
background screener workers."""
import math

import numpy as np
import pandas as pd

from crypto import market
from crypto.cache import TTLCache
from crypto.talib_compat import talib

_cache = TTLCache(ttl=30)


def frame(exchange, symbol, interval="1h", limit=300):
    rows = market.ohlcv(exchange, symbol, interval, limit)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["ts"], unit="ms").dt.strftime("%Y-%m-%d %H:%M:%S")
    return df[["time", "open", "high", "low", "close", "volume"]].astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float})


def _last(arr, back=0):
    try:
        v = float(np.asarray(arr, dtype=float)[-1 - back])
        return None if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return None


def _wma(x, n):
    s = pd.Series(np.asarray(x, dtype=float))
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda v: np.dot(v, w) / w.sum(), raw=True).to_numpy()


def _hma(x, n=9):
    half = _wma(x, max(1, n // 2))
    full = _wma(x, n)
    return _wma(2 * half - full, max(1, int(math.sqrt(n))))


def _rec(buy, sell, neutral):
    total = buy + sell + neutral
    if not total:
        return "NEUTRAL"
    score = (buy - sell) / total
    if score > 0.5:
        return "STRONG_BUY"
    if score > 0.1:
        return "BUY"
    if score < -0.5:
        return "STRONG_SELL"
    if score < -0.1:
        return "SELL"
    return "NEUTRAL"


def _side(cond_buy, cond_sell):
    if cond_buy:
        return "BUY"
    if cond_sell:
        return "SELL"
    return "NEUTRAL"


def _summary(signals):
    vals = list(signals.values())
    b, s, n = vals.count("BUY"), vals.count("SELL"), vals.count("NEUTRAL")
    return {"RECOMMENDATION": _rec(b, s, n), "BUY": b, "SELL": s, "NEUTRAL": n}


def compute(df):
    c, h, lo, v = df["close"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["volume"].to_numpy()
    price = _last(c) or 0.0
    ind = {"close": price, "open": _last(df["open"]), "high": _last(h), "low": _last(lo), "volume": _last(v)}

    rsi = talib.RSI(c, 14)
    ind["RSI"], ind["RSI[1]"] = _last(rsi), _last(rsi, 1)
    k, d = talib.STOCH(h, lo, c, 14, 3, 0, 3, 0)
    ind["Stoch.K"], ind["Stoch.D"] = _last(k), _last(d)
    srk, srd = talib.STOCHRSI(c, 14, 3, 3, 0)
    ind["Stoch.RSI.K"], ind["Stoch.RSI.D"] = _last(srk), _last(srd)
    cci = talib.CCI(h, lo, c, 20)
    ind["CCI20"], ind["CCI20[1]"] = _last(cci), _last(cci, 1)
    adx = talib.ADX(h, lo, c, 14)
    ind["ADX"] = _last(adx)
    median = (h + lo) / 2
    ao = pd.Series(median).rolling(5).mean().to_numpy() - pd.Series(median).rolling(34).mean().to_numpy()
    ind["AO"], ind["AO[1]"] = _last(ao), _last(ao, 1)
    mom = talib.MOM(c, 10)
    ind["Mom"], ind["Mom[1]"] = _last(mom), _last(mom, 1)
    macd, sig, hist = talib.MACD(c, 12, 26, 9)
    ind["MACD.macd"], ind["MACD.signal"], ind["MACD.hist"] = _last(macd), _last(sig), _last(hist)
    wr = talib.WILLR(h, lo, c, 14)
    ind["W.R"], ind["W.R[1]"] = _last(wr), _last(wr, 1)
    ema13 = talib.EMA(c, 13)
    bbp = (h - ema13) + (lo - ema13)
    ind["BBPower"] = _last(bbp)
    uo = talib.ULTOSC(h, lo, c, 7, 14, 28)
    ind["UO"] = _last(uo)
    mfi = talib.MFI(h, lo, c, v, 14)
    ind["MFI"] = _last(mfi)
    up, mid, low_b = talib.BBANDS(c, 20, 2, 2, 0)
    ind["BB.upper"], ind["BB.middle"], ind["BB.lower"] = _last(up), _last(mid), _last(low_b)
    for n in (10, 20, 30, 50, 100, 200):
        ind[f"EMA{n}"] = _last(talib.EMA(c, n)) if len(c) >= n else None
        ind[f"SMA{n}"] = _last(talib.SMA(c, n)) if len(c) >= n else None
    ind["Ichimoku.BLine"] = _last((pd.Series(h).rolling(26).max() + pd.Series(lo).rolling(26).min()).to_numpy() / 2)
    vw = (pd.Series(c * v).rolling(20).sum() / pd.Series(v).rolling(20).sum()).to_numpy()
    ind["VWMA"] = _last(vw)
    ind["HullMA9"] = _last(_hma(c, 9))
    ind["SAR"] = _last(talib.SAR(h, lo, 0.02, 0.2))

    def g(key, default=0.0):
        val = ind.get(key)
        return default if val is None else val

    osc = {
        "RSI": _side(g("RSI", 50) < 30 and g("RSI", 50) > g("RSI[1]", 50), g("RSI", 50) > 70 and g("RSI", 50) < g("RSI[1]", 50)),
        "STOCH.K": _side(g("Stoch.K", 50) < 20 and g("Stoch.D", 50) < 20 and g("Stoch.K") > g("Stoch.D"),
                         g("Stoch.K", 50) > 80 and g("Stoch.D", 50) > 80 and g("Stoch.K") < g("Stoch.D")),
        "CCI": _side(g("CCI20") < -100 and g("CCI20") > g("CCI20[1]"), g("CCI20") > 100 and g("CCI20") < g("CCI20[1]")),
        "ADX": _side(g("ADX") > 20 and g("Mom") > 0, g("ADX") > 20 and g("Mom") < 0),
        "AO": _side(g("AO") > 0 and g("AO") > g("AO[1]"), g("AO") < 0 and g("AO") < g("AO[1]")),
        "Mom": _side(g("Mom") > g("Mom[1]"), g("Mom") < g("Mom[1]")),
        "MACD": _side(g("MACD.macd") > g("MACD.signal"), g("MACD.macd") < g("MACD.signal")),
        "Stoch.RSI": _side(g("Stoch.RSI.K", 50) < 20 and g("Stoch.RSI.K") > g("Stoch.RSI.D"),
                           g("Stoch.RSI.K", 50) > 80 and g("Stoch.RSI.K") < g("Stoch.RSI.D")),
        "W%R": _side(g("W.R", -50) < -80 and g("W.R") > g("W.R[1]"), g("W.R", -50) > -20 and g("W.R") < g("W.R[1]")),
        "BBP": _side(g("BBPower") > 0, g("BBPower") < 0),
        "UO": _side(g("UO", 50) > 70, g("UO", 50) < 30),
    }

    def vs_price(key):
        val = ind.get(key)
        if val is None:
            return "NEUTRAL"
        return _side(price > val, price < val)

    mas = {f"{kind}{n}": vs_price(f"{kind}{n}") for kind in ("EMA", "SMA") for n in (10, 20, 30, 50, 100, 200)}
    mas["Ichimoku"] = vs_price("Ichimoku.BLine")
    mas["VWMA"] = vs_price("VWMA")
    mas["HullMA"] = vs_price("HullMA9")

    osc_sum, ma_sum = _summary(osc), _summary(mas)
    b, s, n = osc_sum["BUY"] + ma_sum["BUY"], osc_sum["SELL"] + ma_sum["SELL"], osc_sum["NEUTRAL"] + ma_sum["NEUTRAL"]
    return {
        "price": price,
        "summary": {"RECOMMENDATION": _rec(b, s, n), "BUY": b, "SELL": s, "NEUTRAL": n},
        "oscillators": {**osc_sum, "COMPUTE": osc},
        "moving_averages": {**ma_sum, "COMPUTE": mas},
        "indicators": ind,
        "signals": osc,
        "signals2": mas,
    }


def analysis(exchange, symbol, interval="1h"):
    sym = market.normalize_symbol(symbol)
    key = (market.normalize_exchange(exchange), sym, interval)
    hit = _cache.get(key)
    if hit is None:
        out = compute(frame(exchange, sym, interval, 300))
        out.update(symbol=sym, interval=interval)
        hit = _cache.set(key, out)
    return hit
