"""Market-context data from free public sources, used *beside* ccxt
(which stays the single path for exchange connectivity and trading):

* CoinGecko        global market cap / dominance, coin rankings & logos, trending
                   (keyless public API; set COINGECKO_API_KEY for a free Demo key)
* alternative.me   Crypto Fear & Greed Index (attribution shown next to it in the UI)
* DefiLlama        DeFi TVL by chain and stablecoin supply (keyless open API)

Every call is cached, failing hosts are skipped for a while, and when a source
is unreachable (offline dev, tests, DEMO) a deterministic synthetic fallback
keeps the UI populated and is labelled ``"source": "synthetic"``.

EXTERNAL_DATA=auto (default) | off
"""
import logging
import math
import os
import time
from datetime import datetime, timezone

import requests

from crypto import market
from crypto.cache import TTLCache

log = logging.getLogger("pulsetrade.datasources")

COINGECKO = "https://api.coingecko.com/api/v3"
FNG = "https://api.alternative.me/fng/"
LLAMA = "https://api.llama.fi"
STABLES_API = "https://stablecoins.llama.fi"

_cache = TTLCache(ttl=300, maxsize=256)
_down = TTLCache(ttl=120)
_session = requests.Session()
_session.headers.update({"User-Agent": "PulseTrade/2.0 (+https://github.com/MahmoudBL83)", "Accept": "application/json"})

ATTRIBUTION = {
    "coingecko": {"name": "CoinGecko", "url": "https://www.coingecko.com"},
    "alternative.me": {"name": "alternative.me", "url": "https://alternative.me/crypto/fear-and-greed-index/"},
    "defillama": {"name": "DefiLlama", "url": "https://defillama.com"},
    "synthetic": {"name": "Demo data", "url": None},
}


def enabled():
    return os.environ.get("EXTERNAL_DATA", "auto").lower() != "off" and market.mode() != "synthetic"


def _get(url, params=None, host_key=None, headers=None):
    """GET JSON or None. Hosts that fail are skipped for 2 minutes."""
    host_key = host_key or url.split("/")[2]
    if not enabled() or _down.get(host_key):
        return None
    try:
        res = _session.get(url, params=params, headers=headers, timeout=(4, 8))
        if res.status_code == 429:
            _down.set(host_key, True, ttl=300)  # rate limited: back off longer
            return None
        res.raise_for_status()
        return res.json()
    except Exception as e:
        log.info("data source %s unavailable: %s", host_key, str(e)[:160])
        _down.set(host_key, True)
        return None


def _cg_headers():
    key = os.environ.get("COINGECKO_API_KEY", "").strip()
    return {"x-cg-demo-api-key": key} if key else None


def _cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit is None:
        hit = _cache.set(key, fn(), ttl)
    return hit


def _today_seed():
    return int(time.time() // 86400)


# --------------------------------------------------------------------------- CoinGecko

def global_market():
    def load():
        data = _get(f"{COINGECKO}/global", headers=_cg_headers(), host_key="coingecko")
        if data and data.get("data"):
            d = data["data"]
            return {
                "total_market_cap_usd": (d.get("total_market_cap") or {}).get("usd", 0),
                "total_volume_usd": (d.get("total_volume") or {}).get("usd", 0),
                "market_cap_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
                "btc_dominance": (d.get("market_cap_percentage") or {}).get("btc", 0),
                "eth_dominance": (d.get("market_cap_percentage") or {}).get("eth", 0),
                "active_cryptocurrencies": d.get("active_cryptocurrencies", 0),
                "markets": d.get("markets", 0),
                "source": "coingecko",
            }
        return _synthetic_global()
    return _cached("global", 300, load)


_SUPPLY = {"BTC": 19.9e6, "ETH": 120.4e6, "BNB": 145e6, "SOL": 470e6, "XRP": 57e9, "ADA": 35.6e9, "DOGE": 146e9,
           "AVAX": 410e6, "DOT": 1.5e9, "LINK": 640e6, "TRX": 86e9, "TON": 2.55e9, "LTC": 75e6, "POL": 9e9}


def _synthetic_global():
    btc = market.synthetic.ticker("BTC/USDT")
    eth = market.synthetic.ticker("ETH/USDT")
    btc_cap = btc["last"] * _SUPPLY["BTC"]
    eth_cap = eth["last"] * _SUPPLY["ETH"]
    total = btc_cap / 0.56
    return {"total_market_cap_usd": total, "total_volume_usd": total * 0.035,
            "market_cap_change_24h": btc["percentage"] * 0.9, "btc_dominance": btc_cap / total * 100,
            "eth_dominance": eth_cap / total * 100, "active_cryptocurrencies": 15_000, "markets": 1_100,
            "source": "synthetic"}


def coins(limit=100, vs="usd"):
    """Top coins by market cap with logos, ranks and 24h/7d change."""
    limit = max(1, min(int(limit), 250))

    def load():
        data = _get(f"{COINGECKO}/coins/markets", params={
            "vs_currency": vs, "order": "market_cap_desc", "per_page": limit, "page": 1,
            "sparkline": "false", "price_change_percentage": "24h,7d"}, headers=_cg_headers(), host_key="coingecko")
        if isinstance(data, list) and data:
            return [{
                "id": c.get("id"), "symbol": (c.get("symbol") or "").upper(), "name": c.get("name"),
                "image": c.get("image"), "rank": c.get("market_cap_rank"), "price": c.get("current_price") or 0,
                "market_cap": c.get("market_cap") or 0, "volume": c.get("total_volume") or 0,
                "change_24h": c.get("price_change_percentage_24h_in_currency") or c.get("price_change_percentage_24h") or 0,
                "change_7d": c.get("price_change_percentage_7d_in_currency") or 0,
                "circulating_supply": c.get("circulating_supply"), "ath": c.get("ath"),
                "ath_change": c.get("ath_change_percentage"), "source": "coingecko",
            } for c in data]
        return _synthetic_coins(limit)
    return _cached(("coins", limit, vs), 300, load)


def _synthetic_coins(limit):
    rows = []
    now = time.time()
    for base in market.synthetic.UNIVERSE:
        t = market.synthetic.ticker(f"{base}/USDT")
        supply = _SUPPLY.get(base) or (5e8 + 5e9 * market.synthetic._u(base, "supply"))
        week = market.synthetic.price_at(f"{base}/USDT", now - 7 * 86400)
        rows.append({"id": base.lower(), "symbol": base, "name": base, "image": None, "rank": None,
                     "price": t["last"], "market_cap": t["last"] * supply, "volume": t["quoteVolume"],
                     "change_24h": t["percentage"], "change_7d": (t["last"] - week) / week * 100 if week else 0,
                     "circulating_supply": supply, "ath": t["high"] * 1.6, "ath_change": -37.5, "source": "synthetic"})
    rows.sort(key=lambda r: r["market_cap"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows[:limit]


def trending():
    def load():
        data = _get(f"{COINGECKO}/search/trending", headers=_cg_headers(), host_key="coingecko")
        if data and data.get("coins"):
            out = []
            for entry in data["coins"][:15]:
                c = entry.get("item") or {}
                d = c.get("data") or {}
                pct = (d.get("price_change_percentage_24h") or {}).get("usd")
                out.append({"id": c.get("id"), "symbol": (c.get("symbol") or "").upper(), "name": c.get("name"),
                            "image": c.get("small") or c.get("thumb"), "rank": c.get("market_cap_rank"),
                            "price": d.get("price"), "change_24h": pct, "source": "coingecko"})
            return out
        ov = market.overview(None, "USDT", 8)
        return [{"id": r["symbol"], "symbol": r["symbol"].split("/")[0], "name": r["symbol"].split("/")[0],
                 "image": None, "rank": None, "price": r["last"], "change_24h": r["percentage"],
                 "source": "synthetic"} for r in ov["gainers"]]
    return _cached("trending", 600, load)


# --------------------------------------------------------------------------- Fear & Greed

def _classify(value):
    if value < 25:
        return "Extreme Fear"
    if value < 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value < 75:
        return "Greed"
    return "Extreme Greed"


def fear_greed(limit=30):
    limit = max(1, min(int(limit), 365))

    def load():
        data = _get(FNG, params={"limit": limit, "format": "json"}, host_key="alternative.me")
        if data and data.get("data"):
            rows = [{"value": int(r["value"]), "classification": r.get("value_classification") or _classify(int(r["value"])),
                     "timestamp": int(r["timestamp"])} for r in data["data"]]
            return {"current": rows[0], "history": rows[::-1], "source": "alternative.me"}
        return _synthetic_fng(limit)
    return _cached(("fng", limit), 3600, load)


def _synthetic_fng(limit):
    day = _today_seed()
    rows = []
    for k in range(limit - 1, -1, -1):
        t = (day - k) * 86400
        now_p = market.synthetic.price_at("BTC/USDT", t)
        week_p = market.synthetic.price_at("BTC/USDT", t - 7 * 86400)
        momentum = (now_p - week_p) / week_p if week_p else 0
        value = int(max(5, min(95, 50 + momentum * 400 + 6 * math.sin(day - k))))
        rows.append({"value": value, "classification": _classify(value), "timestamp": t})
    return {"current": rows[-1], "history": rows, "source": "synthetic"}


# --------------------------------------------------------------------------- DefiLlama

def defi():
    def load():
        chains = _get(f"{LLAMA}/v2/chains", host_key="defillama")
        stables = _get(f"{STABLES_API}/stablecoins", params={"includePrices": "false"}, host_key="defillama-stables")
        if isinstance(chains, list) and chains:
            top = sorted((c for c in chains if c.get("tvl")), key=lambda c: c["tvl"], reverse=True)[:12]
            total_tvl = sum(c.get("tvl") or 0 for c in chains)
            stable_supply = None
            if stables and stables.get("peggedAssets"):
                stable_supply = sum(((a.get("circulating") or {}).get("peggedUSD") or 0) for a in stables["peggedAssets"])
            return {"total_tvl": total_tvl, "stablecoin_supply": stable_supply,
                    "chains": [{"name": c.get("name"), "tvl": c.get("tvl"), "symbol": c.get("tokenSymbol"),
                                "share": (c.get("tvl") or 0) / total_tvl * 100 if total_tvl else 0} for c in top],
                    "source": "defillama"}
        return _synthetic_defi()
    return _cached("defi", 1800, load)


def _synthetic_defi():
    base = [("Ethereum", 62e9, "ETH"), ("Solana", 9.8e9, "SOL"), ("BSC", 5.6e9, "BNB"), ("Tron", 7.9e9, "TRX"),
            ("Bitcoin", 6.1e9, "BTC"), ("Base", 3.4e9, None), ("Arbitrum", 2.9e9, "ARB"), ("Avalanche", 1.4e9, "AVAX")]
    day = _today_seed()
    chains = [{"name": n, "tvl": v * (1 + 0.05 * math.sin(day / 9 + i)), "symbol": s} for i, (n, v, s) in enumerate(base)]
    total = sum(c["tvl"] for c in chains) / 0.92
    for c in chains:
        c["share"] = c["tvl"] / total * 100
    return {"total_tvl": total, "stablecoin_supply": 1.65e11 * (1 + 0.01 * math.sin(day / 30)),
            "chains": chains, "source": "synthetic"}


def snapshot():
    """Everything the dashboard's market-pulse panel needs in one call."""
    return {"global": global_market(), "fear_greed": fear_greed(30), "trending": trending()[:7],
            "defi": defi(), "attribution": ATTRIBUTION,
            "updated_at": datetime.now(timezone.utc).isoformat()}
