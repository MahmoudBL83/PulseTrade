"""Import talib with a pure-python fallback.

Local/Docker with TA-Lib installed: real C extension, zero behavior change.
Vercel (no C library): pandas/numpy approximations so imports and indicator
endpoints keep working. Approximations only matter where real TA-Lib absent.
"""
import numpy as _np
import pandas as _pd

try:
    import talib as _real_talib
    talib = _real_talib
except ImportError:
    _real_talib = None

    def _s(x):
        return _pd.Series(_np.asarray(x, dtype=float))

    def SMA(x, timeperiod=30):
        return _s(x).rolling(timeperiod).mean().to_numpy()

    def EMA(x, timeperiod=30):
        return _s(x).ewm(span=timeperiod, adjust=False).mean().to_numpy()

    def WMA(x, timeperiod=30):
        w = _np.arange(1, timeperiod + 1, dtype=float)
        return _s(x).rolling(timeperiod).apply(lambda v: _np.dot(v, w) / w.sum(), raw=True).to_numpy()

    def HMA(x, timeperiod=30):
        half = WMA(x, max(1, timeperiod // 2))
        full = WMA(x, timeperiod)
        return WMA(2 * half - full, max(1, int(timeperiod ** 0.5)))

    def SUM(x, timeperiod=30):
        return _s(x).rolling(timeperiod).sum().to_numpy()

    def MAX(x, timeperiod=30):
        return _s(x).rolling(timeperiod).max().to_numpy()

    def MIN(x, timeperiod=30):
        return _s(x).rolling(timeperiod).min().to_numpy()

    def MOM(x, timeperiod=10):
        return _s(x).diff(timeperiod).to_numpy()

    def RSI(x, timeperiod=14):
        d = _s(x).diff()
        gain = d.clip(lower=0).ewm(alpha=1 / timeperiod, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(alpha=1 / timeperiod, adjust=False).mean()
        return (100 - 100 / (1 + gain / loss)).to_numpy()

    def MACD(x, fastperiod=12, slowperiod=26, signalperiod=9):
        m = _s(x).ewm(span=fastperiod, adjust=False).mean() - _s(x).ewm(span=slowperiod, adjust=False).mean()
        sig = m.ewm(span=signalperiod, adjust=False).mean()
        return m.to_numpy(), sig.to_numpy(), (m - sig).to_numpy()

    def STOCH(high, low, close, fastk_period=5, slowk_period=3, slowk_matype=0,
               slowd_period=3, slowd_matype=0):
        h, l, c = _s(high), _s(low), _s(close)
        ll = l.rolling(fastk_period).min()
        hh = h.rolling(fastk_period).max()
        k = 100 * (c - ll) / (hh - ll)
        ks = k.rolling(slowk_period).mean()
        d = ks.rolling(slowd_period).mean()
        return k.to_numpy(), d.to_numpy()

    def STOCHRSI(x, timeperiod=14, fastk_period=5, fastd_period=3, fastd_matype=0):
        r = _s(RSI(x, timeperiod))
        ll = r.rolling(fastk_period).min()
        hh = r.rolling(fastk_period).max()
        k = 100 * (r - ll) / (hh - ll)
        d = k.rolling(fastd_period).mean()
        return k.to_numpy(), d.to_numpy()

    def WILLR(high, low, close, timeperiod=14):
        h, l, c = _s(high), _s(low), _s(close)
        hh = h.rolling(timeperiod).max()
        ll = l.rolling(timeperiod).min()
        return ((hh - c) / (hh - ll) * -100).to_numpy()

    def CCI(high, low, close, timeperiod=14):
        tp = (_s(high) + _s(low) + _s(close)) / 3
        sma = tp.rolling(timeperiod).mean()
        md = tp.rolling(timeperiod).apply(lambda v: _np.mean(_np.abs(v - v.mean())), raw=True)
        return ((tp - sma) / (0.015 * md)).to_numpy()

    def ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28):
        h, l, c = _s(high), _s(low), _s(close)
        pc = c.shift(1)
        bp = c - _pd.concat([l, pc], axis=1).min(axis=1)
        tr = _pd.concat([h, pc], axis=1).max(axis=1) - _pd.concat([l, pc], axis=1).min(axis=1)
        a1 = bp.rolling(timeperiod1).sum() / tr.rolling(timeperiod1).sum()
        a2 = bp.rolling(timeperiod2).sum() / tr.rolling(timeperiod2).sum()
        a3 = bp.rolling(timeperiod3).sum() / tr.rolling(timeperiod3).sum()
        return (100 * (4 * a1 + 2 * a2 + a3) / 7).to_numpy()

    def ADX(high, low, close, timeperiod=14):
        h, l, c = _s(high), _s(low), _s(close)
        up, dn = h.diff(), -l.diff()
        pdm = up.where((up > dn) & (up > 0), 0.0)
        mdm = dn.where((dn > up) & (dn > 0), 0.0)
        tr = _pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / timeperiod, adjust=False).mean()
        pdi = 100 * pdm.ewm(alpha=1 / timeperiod, adjust=False).mean() / atr
        mdi = 100 * mdm.ewm(alpha=1 / timeperiod, adjust=False).mean() / atr
        return (100 * (pdi - mdi).abs() / (pdi + mdi)).to_numpy()

    def MFI(high, low, close, volume, timeperiod=14):
        tp = (_s(high) + _s(low) + _s(close)) / 3
        mf = tp * _s(volume)
        pos = mf.where(tp.diff() > 0, 0.0).rolling(timeperiod).sum()
        neg = mf.where(tp.diff() < 0, 0.0).rolling(timeperiod).sum()
        return (100 - 100 / (1 + pos / neg)).to_numpy()

    def SAR(high, low, acceleration=0.02, maximum=0.2):
        h = _np.asarray(high, dtype=float)
        l = _np.asarray(low, dtype=float)
        out = _np.full_like(h, _np.nan)
        if len(h) < 2:
            return out
        up = h[1] > h[0]
        sar = l[0] if up else h[0]
        ep = h[0] if up else l[0]
        af = acceleration
        for i in range(1, len(h)):
            sar = sar + af * (ep - sar)
            if up:
                sar = min(sar, l[i - 1], l[i] if i > 1 else l[i - 1])
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + acceleration, maximum)
                if l[i] < sar:
                    up, sar, ep, af = False, ep, l[i], acceleration
            else:
                sar = max(sar, h[i - 1], h[i] if i > 1 else h[i - 1])
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + acceleration, maximum)
                if h[i] > sar:
                    up, sar, ep, af = True, ep, h[i], acceleration
            out[i] = sar
        return out

    def BBANDS(x, timeperiod=5, nbdevup=2, nbdevdn=2, matype=0):
        s = _s(x)
        mid = s.rolling(timeperiod).mean()
        std = s.rolling(timeperiod).std()
        return ((mid + nbdevup * std).to_numpy(), mid.to_numpy(), (mid - nbdevdn * std).to_numpy())

    class MA_Type:
        SMA, EMA, WMA, DEMA, TEMA, TRIMA, KAMA, MAMA, T3 = range(9)

    def MA(x, timeperiod=30, matype=0):
        if matype == MA_Type.WMA:
            return WMA(x, timeperiod)
        if matype == MA_Type.EMA:
            return EMA(x, timeperiod)
        return SMA(x, timeperiod)

    import types as _t
    talib = _t.SimpleNamespace(
        SMA=SMA, EMA=EMA, WMA=WMA, HMA=HMA, SUM=SUM, MAX=MAX, MIN=MIN,
        MOM=MOM, RSI=RSI, MACD=MACD, STOCH=STOCH, STOCHRSI=STOCHRSI,
        WILLR=WILLR, CCI=CCI, ULTOSC=ULTOSC, ADX=ADX, MFI=MFI, SAR=SAR,
        BBANDS=BBANDS, MA=MA, MA_Type=MA_Type,
    )
