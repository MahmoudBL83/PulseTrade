"""Demo mode: synthetic market data so the public dashboard renders
without exchange API keys or local JSON dumps.

Enabled with DEMO=1. Additive only — real paths untouched.
"""
import os
from flask import jsonify, send_from_directory
from crypto import app, db


def is_demo():
    return os.environ.get("DEMO", "0") == "1"


DEMO_PRICES = {
    "BTCUSDT": (67412.5, 28412.3, 2.41),
    "ETHUSDT": (3521.8, 14820.6, 1.87),
    "BNBUSDT": (598.4, 1820.1, 0.94),
    "SOLUSDT": (172.6, 8940.2, 3.12),
}

DEMO_ORDERBOOK = {
    "bids": [[67400.0, 0.42], [67390.5, 1.18], [67380.0, 0.75]],
    "asks": [[67420.0, 0.38], [67430.5, 0.92], [67440.0, 1.05]],
}

DEMO_TRADES = [
    {"price": 67412.5, "amount": 0.12, "side": "buy"},
    {"price": 67410.0, "amount": 0.05, "side": "sell"},
    {"price": 67415.2, "amount": 0.30, "side": "buy"},
]


def demo_price_payload(symbol_val):
    key = (symbol_val or "").replace("/", "").upper()
    price, volume, change = DEMO_PRICES.get(key, (100.0, 1000.0, 0.5))
    zeros = {k: 0 for k in (
        "market_cap_dominance", "market_cap", "circulating_supply",
        "cmc_rank", "total_supply", "max_supply", "full_market_cap",
        "ema200", "ema100", "ema50", "ema30", "ema20", "ema10",
        "sma200", "sma100", "sma50", "sma30", "sma20", "sma10",
        "bp", "adx", "ao", "cci", "wpr", "ma", "stoch", "obv",
        "bb_middle", "bb_lower", "bb_upper", "trix", "macd", "rsi",
    )}
    signals = {k: "neutral" for k in (
        "rsi_signal", "macd_signal", "wpr_signal", "cci_signal",
        "adx_signal", "ma_signal", "stoch_signal",
        "sma10_signal", "sma20_signal", "sma30_signal", "sma50_signal",
        "sma100_signal", "sma200_signal",
        "ema10_signal", "ema20_signal", "ema30_signal", "ema50_signal",
        "ema100_signal", "ema200_signal",
    )}
    return {
        "symbol": symbol_val,
        "price": price,
        "volume": volume,
        "price_change": change,
        "percent_change_24h": change,
        "demo": True,
        **zeros,
        **signals,
    }


@app.route("/api/demo/status")
def demo_status():
    return jsonify({"demo": is_demo()})


def seed_catalog():
    """Create tables + minimal catalog rows (subscriptions, exchanges).
    Idempotent."""
    from crypto.models import Subscription, Exchange2
    db.create_all()
    if Subscription.query.count() < 3:
        db.session.add(Subscription(type='free', max_bots=5, max_sma=10))
        db.session.add(Subscription(type='advanced', max_bots=25, max_sma=10**9))
        db.session.add(Subscription(type='pro', max_bots=100, max_sma=10**9))
    for name in ("binance", "okx", "bybit"):
        if not Exchange2.query.filter_by(exchange=name).first():
            db.session.add(Exchange2(exchange=name, isActive=(name == "binance")))
    db.session.commit()


@app.route("/api/demo/seed")
def demo_seed():
    """Safe to call repeatedly. Requires DEMO=1."""
    if not is_demo():
        return jsonify({"error": "DEMO=1 required"}), 403
    seed_catalog()
    return jsonify({"status": "seeded", "demo": True})


@app.route("/favicon.ico")
def favicon():
    directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")
    for candidate in ("logo2.png", "logo.png"):
        if os.path.isfile(os.path.join(directory, candidate)):
            return send_from_directory(directory, candidate)
    return ("", 204)


# Disabled AI routes (crypto/gpt.py references g4f, which is not installed).
# Explicit 410 so clients get a clear answer instead of a 500 NameError.
@app.route("/chat/", methods=["GET", "POST"])
@app.route("/llama/", methods=["GET", "POST"])
@app.route("/gpt", methods=["GET", "POST"])
@app.route("/binggpt/", methods=["GET", "POST"])
@app.route("/bardgpt/", methods=["GET", "POST"])
@app.route("/llamagpt/", methods=["GET", "POST"])
@app.route("/chat/completions", methods=["GET", "POST"])
def _ai_disabled():
    return jsonify({"error": "AI chat disabled: no backend configured"}), 410
