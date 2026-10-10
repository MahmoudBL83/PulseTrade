"""Market data service: tickers, candles, order books and trades.

Resolution order for every call:
  1. in-process TTL cache (keeps hot pages fast and exchanges happy)
  2. public ccxt endpoint (no API keys) on the requested exchange, then the
     configured fallbacks (geo-blocked / down exchanges are skipped for 60s)
  3. a deterministic synthetic market, so demo deploys, tests and offline
     development always have coherent, "live" looking data.

MARKET_DATA=auto (default) | live | synthetic
MARKET_DATA_EXCHANGE=binance            reference exchange for paper/demo
MARKET_DATA_FALLBACKS=okx,kucoin,bybit  tried in order when the first fails
"""
import hashlib
import logging
import math
import os
import threading
import time

import ccxt

from crypto.cache import TTLCache

log = logging.getLogger("pulsetrade.market")

STABLES = {"USDT", "USDC", "BUSD", "TUSD", "USDP", "USDK", "PAX", "USDS", "DAI", "FDUSD", "USD"}
QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "TUSD", "BTC", "ETH", "BNB", "EUR", "TRY", "USD", "DAI")

TIMEFRAMES = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "12h": 43200,
    "1d": 86400, "3d": 259200, "1w": 604800, "1W": 604800, "1M": 2592000,
}

_ticker_cache = TTLCache(ttl=8)
_tickers_cache = TTLCache(ttl=20)
_ohlcv_cache = TTLCache(ttl=30)
_book_cache = TTLCache(ttl=3)
_markets_cache = TTLCache(ttl=3600)
_down = TTLCache(ttl=60)
_clients = {}
_clients_lock = threading.Lock()


# --------------------------------------------------------------------------- config

def mode():
    return os.environ.get("MARKET_DATA", "auto").strip().lower()


def default_exchange():
    return os.environ.get("MARKET_DATA_EXCHANGE", "binance").strip().lower() or "binance"


def _fallbacks():
    raw = os.environ.get("MARKET_DATA_FALLBACKS", "okx,kucoin,bybit")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def normalize_exchange(name):
    n = (name or "").strip().lower()
    if n in ("okex", "okx", "okex5"):
        return "okx"
    if n in ("", "paper", "all", "demo", "none", "null", "undefined"):
        return default_exchange()
    return n


def normalize_symbol(symbol):
    """'btcusdt' / 'BTC-USDT' / 'BTC_USDT' / 'BTC/USDT' -> 'BTC/USDT'."""
    s = (symbol or "").strip().upper().replace("-", "/").replace("_", "/")
    if ":" in s:  # TradingView style 'OKX:BTCUSDT'
        s = s.split(":", 1)[1]
    if "/" in s:
        base, quote = s.split("/", 1)
        return f"{base}/{quote}"
    for q in QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[:-len(q)]}/{q}"
    return f"{s}/USDT" if s else "BTC/USDT"


def split_symbol(symbol):
    base, quote = normalize_symbol(symbol).split("/", 1)
    return base, quote


def timeframe_seconds(tf):
    return TIMEFRAMES.get(tf, TIMEFRAMES.get(str(tf).lower(), 3600))


# --------------------------------------------------------------------------- live

def client(name):
    name = normalize_exchange(name)
    with _clients_lock:
        ex = _clients.get(name)
        if ex is None:
            if name not in ccxt.exchanges:
                raise ValueError(f"unsupported exchange: {name}")
            ex = getattr(ccxt, name)({"enableRateLimit": True, "timeout": 7000})
            _clients[name] = ex
        return ex


def _chain(exchange):
    first = normalize_exchange(exchange)
    out = [first]
    for x in [default_exchange()] + _fallbacks():
        if x not in out:
            out.append(x)
    return [x for x in out if x in ccxt.exchanges]


def _live(exchange, call):
    """Run ``call(client)`` on the first healthy exchange. Returns (result, name)
    or None when every live source failed (caller falls back to synthetic)."""
    if mode() == "synthetic":
        return None
    for name in _chain(exchange):
        if _down.get(name):
            continue
        try:
            return call(client(name)), name
        except (ccxt.BadSymbol, ccxt.BadRequest) as e:
            log.debug("symbol not on %s: %s", name, e)
            continue
        except Exception as e:  # network, geo-block, rate limit, ...
            log.info("market source %s unavailable: %s", name, str(e)[:160])
            _down.set(name, True)
            continue
    return None


def _f(v):
    try:
        if v is None:
            return 0.0
        v = float(v)
        return 0.0 if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return 0.0


def _norm_ticker(t, symbol, source):
    last = _f(t.get("last") or t.get("close"))
    open_ = _f(t.get("open"))
    change = _f(t.get("change")) or (last - open_ if open_ else 0.0)
    pct = _f(t.get("percentage")) or ((change / open_ * 100) if open_ else 0.0)
    base_vol = _f(t.get("baseVolume"))
    quote_vol = _f(t.get("quoteVolume")) or base_vol * last
    return {
        "symbol": t.get("symbol") or symbol,
        "last": last, "close": last,
        "bid": _f(t.get("bid")) or last, "ask": _f(t.get("ask")) or last,
        "high": _f(t.get("high")) or last, "low": _f(t.get("low")) or last,
        "open": open_ or last, "change": change, "percentage": pct,
        "baseVolume": base_vol, "quoteVolume": quote_vol,
        "timestamp": int(t.get("timestamp") or time.time() * 1000),
        "source": source,
    }


# --------------------------------------------------------------------------- public API

def ticker(exchange, symbol):
    sym = normalize_symbol(symbol)
    key = (normalize_exchange(exchange), sym)
    hit = _ticker_cache.get(key)
    if hit is not None:
        return hit
    base, quote = sym.split("/")
    if base in STABLES and quote in STABLES:
        out = synthetic.ticker(sym)
    else:
        res = _live(exchange, lambda c: c.fetch_ticker(sym))
        out = _norm_ticker(res[0], sym, res[1]) if res else synthetic.ticker(sym)
    return _ticker_cache.set(key, out)


def price(exchange, symbol):
    """Last price of ``symbol``. Handles inverted and cross pairs."""
    sym = normalize_symbol(symbol)
    base, quote = sym.split("/")
    if base == quote or (base in STABLES and quote in STABLES):
        return 1.0
    if base in STABLES:  # inverted pair, e.g. USDT/BTC
        p = ticker(exchange, f"{quote}/{base}")["last"]
        return 1.0 / p if p else 0.0
    return ticker(exchange, sym)["last"]


def usd_price(exchange, asset):
    asset = (asset or "").upper()
    if asset in STABLES:
        return 1.0
    return price(exchange, f"{asset}/USDT")


def tickers(exchange, quote="USDT", limit=None):
    ex = normalize_exchange(exchange)
    key = (ex, quote)
    hit = _tickers_cache.get(key)
    if hit is None:
        res = _live(ex, lambda c: c.fetch_tickers())
        rows = []
        if res:
            data, src = res
            for sym, t in data.items():
                if "/" not in sym or ":" in sym:
                    continue
                if quote and not sym.endswith("/" + quote):
                    continue
                n = _norm_ticker(t, sym, src)
                if n["last"] > 0:
                    rows.append(n)
        if not rows:
            rows = [synthetic.ticker(f"{b}/{quote or 'USDT'}") for b in synthetic.UNIVERSE]
        rows.sort(key=lambda r: r["quoteVolume"], reverse=True)
        hit = _tickers_cache.set(key, rows)
    return hit[:limit] if limit else hit


def ohlcv(exchange, symbol, timeframe="1h", limit=200, since=None):
    sym = normalize_symbol(symbol)
    tf = timeframe if timeframe in TIMEFRAMES else "1h"
    limit = max(10, min(int(limit or 200), 1000))
    key = (normalize_exchange(exchange), sym, tf, limit, since)
    hit = _ohlcv_cache.get(key)
    if hit is not None:
        return hit
    res = _live(exchange, lambda c: c.fetch_ohlcv(sym, tf.replace("1W", "1w"), since, limit))
    rows = [[int(r[0]), _f(r[1]), _f(r[2]), _f(r[3]), _f(r[4]), _f(r[5])] for r in res[0]] if res and res[0] else []
    if len(rows) < 10:
        rows = synthetic.ohlcv(sym, tf, limit)
    ttl = 10 if timeframe_seconds(tf) <= 300 else 30
    return _ohlcv_cache.set(key, rows, ttl)


def order_book(exchange, symbol, limit=20):
    sym = normalize_symbol(symbol)
    key = (normalize_exchange(exchange), sym, limit)
    hit = _book_cache.get(key)
    if hit is not None:
        return hit
    res = _live(exchange, lambda c: c.fetch_order_book(sym, limit))
    if res:
        ob = res[0]
        out = {"symbol": sym, "bids": [[_f(p), _f(a)] for p, a, *_ in ob.get("bids", [])[:limit]],
               "asks": [[_f(p), _f(a)] for p, a, *_ in ob.get("asks", [])[:limit]],
               "timestamp": ob.get("timestamp") or int(time.time() * 1000), "source": res[1]}
    else:
        out = synthetic.order_book(sym, limit)
    return _book_cache.set(key, out)


def trades(exchange, symbol, limit=30):
    sym = normalize_symbol(symbol)
    key = ("trades", normalize_exchange(exchange), sym, limit)
    hit = _book_cache.get(key)
    if hit is not None:
        return hit
    res = _live(exchange, lambda c: c.fetch_trades(sym, None, limit))
    if res and res[0]:
        out = [{"id": str(t.get("id")), "timestamp": t.get("timestamp"), "price": _f(t.get("price")),
                "amount": _f(t.get("amount")), "side": t.get("side")} for t in res[0]][-limit:][::-1]
    else:
        out = synthetic.trades(sym, limit)
    return _book_cache.set(key, out)


def symbols(exchange, quote=None):
    ex = normalize_exchange(exchange)
    hit = _markets_cache.get(ex)
    if hit is None:
        res = _live(ex, lambda c: c.load_markets())
        out = []
        if res:
            for m in res[0].values():
                if m.get("spot") and m.get("active", True) is not False and "/" in m.get("symbol", ""):
                    out.append(m["symbol"])
        if not out:
            out = [f"{b}/{q}" for b in synthetic.UNIVERSE for q in ("USDT", "BTC") if b != q]
        hit = _markets_cache.set(ex, sorted(set(out)))
    if quote:
        return [s for s in hit if s.endswith("/" + quote.upper())]
    return hit


def overview(exchange, quote="USDT", top=10):
    rows = [r for r in tickers(exchange, quote) if r["quoteVolume"] > 0]
    if not rows:
        return {"gainers": [], "losers": [], "volume": [], "breadth": {"up": 0, "down": 0, "flat": 0}}
    liquid = rows[: max(50, top * 5)]
    by_pct = sorted(liquid, key=lambda r: r["percentage"], reverse=True)
    up = sum(1 for r in liquid if r["percentage"] > 0.05)
    down = sum(1 for r in liquid if r["percentage"] < -0.05)
    return {
        "gainers": by_pct[:top],
        "losers": by_pct[::-1][:top],
        "volume": liquid[:top],
        "breadth": {"up": up, "down": down, "flat": len(liquid) - up - down},
        "source": liquid[0].get("source"),
    }


def clear_caches():
    for c in (_ticker_cache, _tickers_cache, _ohlcv_cache, _book_cache, _markets_cache, _down):
        c.clear()


# --------------------------------------------------------------------------- synthetic

class _Synthetic:
    """Deterministic, time-continuous fake market. The same (symbol, time)
    always yields the same price, so candles, tickers and paper fills agree
    across requests and processes."""

    BASE = {
        "BTC": 67000.0, "ETH": 3500.0, "BNB": 590.0, "SOL": 165.0, "XRP": 0.58, "ADA": 0.45,
        "DOGE": 0.15, "AVAX": 34.0, "DOT": 7.1, "LINK": 15.2, "MATIC": 0.72, "POL": 0.55, "LTC": 82.0,
        "TRX": 0.12, "ATOM": 8.9, "UNI": 8.4, "XLM": 0.11, "NEAR": 6.2, "APT": 9.1, "ARB": 1.12,
        "OP": 2.4, "FIL": 5.6, "ETC": 27.0, "ICP": 11.5, "SHIB": 0.000024, "TON": 6.8, "SUI": 1.4,
        "INJ": 25.0, "AAVE": 95.0, "MKR": 2600.0, "LDO": 2.1, "PEPE": 0.000011, "WIF": 2.6,
        "SEI": 0.52, "TIA": 9.8, "RNDR": 7.5, "GRT": 0.27, "ALGO": 0.18, "HBAR": 0.09, "VET": 0.034,
    }
    UNIVERSE = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "POL", "LTC",
                "TRX", "ATOM", "UNI", "XLM", "NEAR", "APT", "ARB", "OP", "FIL", "ETC", "ICP", "SHIB",
                "TON", "SUI", "INJ", "AAVE", "MKR", "LDO", "PEPE", "WIF", "SEI", "TIA", "GRT", "ALGO"]
    WAVES = ((9 * 86400, 0.09), (40 * 3600, 0.04), (7 * 3600, 0.018), (3600, 0.007), (900, 0.003), (127, 0.001))

    @staticmethod
    def _u(*parts):
        h = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") / 2 ** 64

    def base_price(self, asset):
        if asset in STABLES:
            return 1.0
        if asset in self.BASE:
            return self.BASE[asset]
        return round(0.02 + 150 * self._u(asset, "p") ** 3, 6)

    def _x(self, asset, t):
        x = 0.0
        for i, (period, amp) in enumerate(self.WAVES):
            ph = self._u(asset, "ph", i) * 2 * math.pi
            x += amp * math.sin(2 * math.pi * t / period + ph)
            x += 0.45 * amp * math.sin(2 * math.pi * t / (period * 0.371) + ph * 1.7)
        m, frac = divmod(t / 60.0, 1.0)
        n0 = self._u(asset, int(m)) - 0.5
        n1 = self._u(asset, int(m) + 1) - 0.5
        x += 0.0016 * ((1 - frac) * n0 + frac * n1)
        return x

    def usd(self, asset, t):
        if asset in STABLES:
            return 1.0
        x = self._x(asset, t)
        if asset != "BTC":
            x = 0.65 * self._x("BTC", t) + 0.85 * x
        return self.base_price(asset) * math.exp(x)

    def price_at(self, symbol, t=None):
        t = time.time() if t is None else t
        base, quote = split_symbol(symbol)
        q = self.usd(quote, t)
        return self.usd(base, t) / q if q else 0.0

    def _daily_quote_volume(self, base):
        if base == "BTC":
            return 1.8e9
        if base == "ETH":
            return 9e8
        return 10 ** (6 + 2.6 * self._u(base, "v"))

    def ticker(self, symbol):
        sym = normalize_symbol(symbol)
        base, _ = sym.split("/")
        now = time.time()
        last = self.price_at(sym, now)
        open_ = self.price_at(sym, now - 86400)
        samples = [self.price_at(sym, now - k * 3600) for k in range(25)] + [last]
        qv = self._daily_quote_volume(base) * (0.8 + 0.4 * self._u(base, int(now // 3600)))
        spread = last * 0.0002
        return {
            "symbol": sym, "last": last, "close": last, "bid": last - spread, "ask": last + spread,
            "high": max(samples) * 1.002, "low": min(samples) * 0.998, "open": open_,
            "change": last - open_, "percentage": (last - open_) / open_ * 100 if open_ else 0.0,
            "baseVolume": qv / last if last else 0.0, "quoteVolume": qv,
            "timestamp": int(now * 1000), "source": "synthetic",
        }

    def ohlcv(self, symbol, timeframe="1h", limit=200):
        sym = normalize_symbol(symbol)
        base, _ = sym.split("/")
        tf = timeframe_seconds(timeframe)
        now = time.time()
        end = math.floor(now / tf) * tf
        vol_per_sec = self._daily_quote_volume(base) / 86400
        rows = []
        for i in range(limit):
            t0 = end - (limit - 1 - i) * tf
            t1 = min(t0 + tf, now)
            pts = [self.price_at(sym, t0 + (t1 - t0) * k / 8) for k in range(9)]
            o, c = pts[0], pts[-1]
            wick = 1 + 0.0015 * self._u(sym, t0, "w")
            h, l = max(pts) * wick, min(pts) / wick
            v = vol_per_sec * (t1 - t0) * (0.4 + 1.2 * self._u(sym, t0, "v")) / (c or 1)
            rows.append([int(t0 * 1000), o, h, l, c, v])
        return rows

    def order_book(self, symbol, limit=20):
        sym = normalize_symbol(symbol)
        now = time.time()
        mid = self.price_at(sym, now)
        tick = int(now // 2)
        bids, asks = [], []
        for i in range(1, limit + 1):
            step = 0.00012 * i + 0.00005 * self._u(sym, tick, i, "s")
            bids.append([mid * (1 - step), round(0.05 + 4 * self._u(sym, tick, i, "b") ** 2, 4)])
            asks.append([mid * (1 + step), round(0.05 + 4 * self._u(sym, tick, i, "a") ** 2, 4)])
        return {"symbol": sym, "bids": bids, "asks": asks, "timestamp": int(now * 1000), "source": "synthetic"}

    def trades(self, symbol, limit=30):
        sym = normalize_symbol(symbol)
        now = time.time()
        out = []
        for k in range(limit):
            t = math.floor(now) - k * 2
            out.append({
                "id": f"s{int(t)}", "timestamp": int(t * 1000), "price": self.price_at(sym, t),
                "amount": round(0.001 + 2 * self._u(sym, t, "amt") ** 3, 5),
                "side": "buy" if self._u(sym, t, "side") > 0.5 else "sell",
            })
        return out


synthetic = _Synthetic()
