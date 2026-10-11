"""New features: market data/TA, watchlist, alerts, journal, backtest,
smart trades, portfolio, notifications, knowledge base and admin API."""
import pytest


# ------------------------------------------------------------------ market & TA

def test_symbol_normalisation():
    from crypto.market import normalize_symbol, normalize_exchange
    assert normalize_symbol("btcusdt") == "BTC/USDT"
    assert normalize_symbol("ETH-BTC") == "ETH/BTC"
    assert normalize_symbol("OKX:SOLUSDT") == "SOL/USDT"
    assert normalize_exchange("okex") == "okx"
    assert normalize_exchange("paper") == "binance"


def test_synthetic_market_is_deterministic_and_coherent():
    from crypto.market import synthetic
    t = 1_760_000_000
    assert synthetic.price_at("BTC/USDT", t) == synthetic.price_at("BTC/USDT", t)
    candles = synthetic.ohlcv("ETH/USDT", "1h", 50)
    assert len(candles) == 50
    for ts, o, h, l, c, v in candles:
        assert l <= min(o, c) <= max(o, c) <= h and v > 0
    assert candles[1][0] - candles[0][0] == 3_600_000
    cross = synthetic.price_at("ETH/BTC", t)
    assert cross == pytest.approx(synthetic.price_at("ETH/USDT", t) / synthetic.price_at("BTC/USDT", t))


def test_market_endpoints(client):
    tickers = client.get("/api/v2/market/tickers?limit=5").get_json()["data"]
    assert len(tickers) == 5 and tickers[0]["quoteVolume"] >= tickers[-1]["quoteVolume"]
    candles = client.get("/api/v2/market/ohlcv?symbol=BTC/USDT&timeframe=15m&limit=100").get_json()["data"]
    assert len(candles) == 100
    book = client.get("/api/v2/market/orderbook?symbol=BTC/USDT").get_json()["data"]
    assert book["bids"][0][0] < book["asks"][0][0]
    ov = client.get("/api/v2/market/overview").get_json()["data"]
    assert ov["gainers"][0]["percentage"] >= ov["losers"][0]["percentage"]


def test_technical_analysis_shape(client):
    a = client.get("/api/v2/market/analysis?symbol=BTC/USDT&interval=1h").get_json()["data"]
    assert a["summary"]["RECOMMENDATION"] in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")
    assert a["summary"]["BUY"] + a["summary"]["SELL"] + a["summary"]["NEUTRAL"] == 26
    assert 0 <= a["indicators"]["RSI"] <= 100


def test_legacy_price_and_indicator_endpoints_have_data(client):
    p = client.get("/getPrice/?symbol=BTCUSDT&exchange=okx&interval=15m").get_json()
    assert p["price"] > 0 and p["rsi_signal"] in ("buy", "sell", "neutral")
    orders = client.get("/openOrders/?symbol=BTCUSDT&exchange=okex&side=buy").get_json()
    assert isinstance(orders, list) and {"price", "amount"} <= set(orders[0])
    trades = client.get("/lastTrades/?symbol=BTCUSDT&exchange=okex").get_json()
    assert isinstance(trades, list) and trades[0]["price"] > 0


# ------------------------------------------------------------------ watchlist / alerts / journal

def test_watchlist_crud(user_client):
    a = user_client.post("/api/v2/watchlist", json={"symbol": "solusdt"}).get_json()["data"]
    assert a["symbol"] == "SOL/USDT"
    user_client.post("/api/v2/watchlist", json={"symbol": "BTC/USDT"})
    dup = user_client.post("/api/v2/watchlist", json={"symbol": "SOL/USDT"}).get_json()
    assert dup["message"] == "Already in your watchlist"
    items = user_client.get("/api/v2/watchlist").get_json()["data"]
    assert [i["symbol"] for i in items] == ["SOL/USDT", "BTC/USDT"] and items[0]["ticker"]["last"] > 0
    user_client.put("/api/v2/watchlist/order", json={"ids": [items[1]["id"], items[0]["id"]]})
    assert user_client.get("/api/v2/watchlist").get_json()["data"][0]["symbol"] == "BTC/USDT"
    assert user_client.delete(f"/api/v2/watchlist/{a['id']}").status_code == 200


def test_price_alert_fires_once(app, user_client, prices):
    prices.set("SOL", 100)
    alert = user_client.post("/api/v2/alerts", json={"symbol": "SOL/USDT", "condition": "above", "target": 110}).get_json()["data"]
    from crypto.alerts import check_alerts
    with app.app_context():
        assert check_alerts() == 0
    prices.set("SOL", 111)
    with app.app_context():
        assert check_alerts() == 1
        assert check_alerts() == 0                                    # one-shot alert disarmed
    rows = user_client.get("/api/v2/alerts").get_json()["data"]
    assert rows[0]["active"] is False and rows[0]["trigger_count"] == 1
    notes = user_client.get("/api/v2/notifications").get_json()["data"]
    assert any("SOL/USDT rose above" in n["content"] for n in notes)


def test_repeating_alert_is_edge_triggered(app, user_client, prices):
    prices.set("ETH", 3000)
    user_client.post("/api/v2/alerts", json={"symbol": "ETH/USDT", "condition": "below", "target": 2900, "repeat": True})
    from crypto.alerts import check_alerts
    with app.app_context():
        check_alerts()
        prices.set("ETH", 2800)
        assert check_alerts() == 1
        assert check_alerts() == 0                                    # still below: no spam
        prices.set("ETH", 3100)
        check_alerts()
        prices.set("ETH", 2850)
        assert check_alerts() == 1                                    # crossed again


def test_alert_validation(user_client):
    assert user_client.post("/api/v2/alerts", json={"symbol": "BTC/USDT", "condition": "sideways", "target": 1}).status_code == 400
    assert user_client.post("/api/v2/alerts", json={"symbol": "BTC/USDT", "target": -5}).status_code == 400
    assert user_client.post("/api/v2/alerts", json={"symbol": "BTC/USDT", "target": "abc"}).status_code == 400


def test_journal_crud_and_stats(user_client):
    e = user_client.post("/api/v2/journal", json={"title": "BTC breakout", "symbol": "btcusdt", "side": "long",
                                                  "entry_price": 100, "exit_price": 110, "amount": 2, "tags": "breakout, btc"}).get_json()["data"]
    assert e["pnl"] == pytest.approx(20) and e["tags"] == ["breakout", "btc"]
    user_client.post("/api/v2/journal", json={"title": "short fail", "side": "short", "entry_price": 50, "exit_price": 55, "amount": 1})
    stats = user_client.get("/api/v2/journal/stats").get_json()["data"]
    assert stats["closed"] == 2 and stats["pnl"] == pytest.approx(15) and stats["win_rate"] == pytest.approx(50)
    assert user_client.put(f"/api/v2/journal/{e['id']}", json={"title": ""}).status_code == 400
    assert user_client.get("/api/v2/journal?q=breakout").get_json()["data"][0]["id"] == e["id"]
    assert user_client.delete(f"/api/v2/journal/{e['id']}").status_code == 200


# ------------------------------------------------------------------ backtest

def test_backtest_runs_and_is_consistent(client):
    res = client.post("/api/v2/backtest", json={"symbol": "BTC/USDT", "timeframe": "1h", "limit": 400,
                                                "base_order": 100, "safety_order": 100, "max_safety_orders": 4,
                                                "deviation": 1.5, "take_profit": 1.5}).get_json()["data"]
    s = res["stats"]
    assert s["candles"] == 400 and s["deals"] == s["wins"] + s["losses"]
    assert s["max_capital"] == pytest.approx(500)
    assert sum(d["pnl"] for d in res["deals"]) == pytest.approx(s["realized_pnl"], rel=1e-6, abs=1e-6)
    for d in res["deals"]:
        assert d["safety_orders"] <= 4
        if d["reason"] == "take_profit":
            assert d["exit"] == pytest.approx(d["average"] * 1.015)


def test_backtest_rejects_bad_params(client):
    assert client.post("/api/v2/backtest", json={"take_profit": 0}).status_code == 400
    assert client.post("/api/v2/backtest", json={"base_order": "lots"}).status_code == 400


# ------------------------------------------------------------------ smart trades


def test_failed_manual_smart_trade_close_keeps_position_active(app, paper_user, prices, monkeypatch):
    prices.set("ETH", 1000)
    created = paper_user.post("/api/v1/smart_trades/", json={
        "trade_type": "Smart Trade", "use_assets": False, "symbol": "ETH/USDT",
        "price": 1000, "triggerPrice": 0, "buy_type": "market", "amount": 1,
        "take_profits": [[5, 100]], "tpTriggerType": "market",
        "stop_loss": False, "take_profit": True, "stop_loss_type": "market",
        "trailing_take_profit": False, "trailing_stop_loss": False,
        "trailing_deviation": 0, "stop_loss_time_out": False,
        "exchange": "paper", "move_to_break_even": False,
    }).get_json()
    assert created["ok"], created

    class FailedExchange:
        def fetch_balance(self):
            return {"ETH": {"free": 1}}

        def create_order(self, *args):
            raise RuntimeError("exchange unavailable")

    from crypto.smartTrade import connectExchange as real_connect
    monkeypatch.setattr("crypto.smartTrade.connectExchange", lambda *args: FailedExchange())
    response = paper_user.post(f"/api/v1/smart_trades/close/{created['id']}")
    assert response.get_json()["ok"] is False

    from crypto import db
    from crypto.models import SmartTrade
    with app.app_context():
        st = db.session.get(SmartTrade, created["id"])
        assert st.isActive is True
        assert st.deal_started is True
        assert st.units > 0

    monkeypatch.setattr("crypto.smartTrade.connectExchange", real_connect)
    retried = paper_user.post(f"/api/v1/smart_trades/close/{created['id']}")
    assert retried.get_json()["ok"] is True
    with app.app_context():
        st = db.session.get(SmartTrade, created["id"])
        assert st.isActive is False
        assert st.deal_started is False
        assert st.units == 0


def test_unconfirmed_manual_close_does_not_submit_a_second_sell(app, paper_user, prices, monkeypatch):
    prices.set("ETH", 1000)
    created = paper_user.post("/api/v1/smart_trades/", json={
        "trade_type": "Smart Trade", "use_assets": False, "symbol": "ETH/USDT",
        "price": 1000, "triggerPrice": 0, "buy_type": "market", "amount": 1,
        "take_profits": [[5, 100]], "tpTriggerType": "market",
        "stop_loss": False, "take_profit": True, "stop_loss_type": "market",
        "trailing_take_profit": False, "trailing_stop_loss": False,
        "trailing_deviation": 0, "stop_loss_time_out": False,
        "exchange": "paper", "move_to_break_even": False,
    }).get_json()
    assert created["ok"], created

    class UnconfirmedExchange:
        def fetch_balance(self):
            return {"ETH": {"free": 1}}

        def create_order(self, *args):
            return {"id": "submitted-close"}

        def fetch_order(self, *args):
            raise RuntimeError("exchange lookup unavailable")

    monkeypatch.setattr("crypto.smartTrade.connectExchange", lambda *args: UnconfirmedExchange())
    response = paper_user.post(f"/api/v1/smart_trades/close/{created['id']}")
    assert response.get_json()["code"] == "close_unconfirmed"

    from crypto import db
    from crypto.models import SmartTrade
    with app.app_context():
        st = db.session.get(SmartTrade, created["id"])
        assert st.isActive is False  # prevent an automatic second sell
        assert st.deal_started is True
        assert st.units > 0  # preserve position for manual reconciliation


def test_smart_trade_multi_level_take_profit(app, paper_user, prices):
    prices.set("ETH", 1000)
    res = paper_user.post("/api/v1/smart_trades/", json={
        "trade_type": "Smart Trade", "use_assets": False, "symbol": "ETH/USDT", "price": 1000, "triggerPrice": 0,
        "buy_type": "market", "amount": 1, "take_profits": [[5, 50], [10, 50]], "tpTriggerType": "market",
        "stop_loss": True, "take_profit": True, "stop_loss_type": "market", "stop_loss_price_percent": -5,
        "stop_loss_trigger_price": 0, "trailing_take_profit": False, "trailing_stop_loss": False,
        "trailing_deviation": 0, "stop_loss_time_out": False, "stop_loss_time_out_time": 0, "exchange": "paper",
        "move_to_break_even": True}).get_json()
    assert res["ok"], res
    st_id = res["id"]
    from crypto import db
    from crypto.models import SmartTrade
    from crypto.smartTrade import run_smart_trade_once

    def tick():
        with app.app_context():
            st = db.session.get(SmartTrade, st_id)
            return run_smart_trade_once(st), st.serialize(with_transactions=False)

    prices.set("ETH", 1051)
    status, st = tick()
    # 1 ETH bought (0.999 received after the 0.1% fee), 50% of the order sold at TP1
    assert status == "take-profit" and st["take_profit_index"] == 1 and st["units"] == pytest.approx(0.499)
    assert st["isActive"] is True                                     # second target still pending
    assert st["stop_loss_price"] == pytest.approx(st["buy_price"])    # moved to break-even
    prices.set("ETH", 1101)
    status, st = tick()
    assert status == "take-profit" and st["units"] == 0 and st["isActive"] is False
    assert st["total_profit"] > 0


def test_conditional_smart_trade_buys_on_trigger(app, paper_user, prices):
    prices.set("ADA", 1)
    res = paper_user.post("/api/v1/smart_trades/", json={
        "trade_type": "Smart Trade", "use_assets": False, "symbol": "ADA/USDT", "price": 1.06, "triggerPrice": 1.05,
        "buy_type": "cond.limit", "amount": 100, "take_profits": [[10, 100]], "tpTriggerType": "market",
        "stop_loss": False, "take_profit": True, "stop_loss_type": "market", "trailing_take_profit": False,
        "trailing_stop_loss": False, "trailing_deviation": 0, "stop_loss_time_out": False,
        "stop_loss_time_out_time": 0, "exchange": "paper", "move_to_break_even": False}).get_json()
    assert res["ok"]
    from crypto import db
    from crypto.models import SmartTrade
    from crypto.smartTrade import run_smart_trade_once
    with app.app_context():
        st = db.session.get(SmartTrade, res["id"])
        assert run_smart_trade_once(st) == "waiting"
    prices.set("ADA", 1.051)
    with app.app_context():
        st = db.session.get(SmartTrade, res["id"])
        assert run_smart_trade_once(st) == "opened"
        tx = st.transactions.all()
        assert tx[-1].type == "buy"                                   # legacy bug: conditional Smart Trades sold


# ------------------------------------------------------------------ portfolio / notifications

def test_portfolio_with_paper_account(app, paper_user, prices):
    prices.set("BTC", 50000)
    paper_user.post("/api/v1/order/", json={"symbol": "BTC/USDT", "type": "market", "amount": 0.1, "side": "buy"})
    data = paper_user.get("/api/v2/portfolio?refresh=1").get_json()["data"]
    cur = {a["currency"]: a for a in data["assets"]}
    assert cur["BTC"]["total"] == pytest.approx(0.0999)
    assert data["total_usd"] == pytest.approx(10000, rel=0.01)
    snap = paper_user.post("/api/v2/portfolio/snapshot").get_json()
    assert snap["ok"]
    assert len(paper_user.get("/api/v2/portfolio/history").get_json()["data"]) >= 1
    perf = paper_user.get("/api/v2/portfolio/performance").get_json()["data"]
    assert "sharpe" in perf and "bot_win_rate" in perf


def test_notifications_read_and_delete(app, user_client):
    user_client.post("/api/v2/notifications/test")
    data = user_client.get("/api/v2/notifications").get_json()
    assert data["unread"] >= 1
    nid = data["data"][0]["id"]
    user_client.post("/api/v2/notifications/read", json={"ids": [nid]})
    assert user_client.get("/api/v2/notifications?unread=1").get_json()["unread"] == data["unread"] - 1
    assert user_client.delete(f"/api/v2/notifications/{nid}").status_code == 200
    assert user_client.get("/api/v1/get_notifications_count/").get_json() >= 0


def test_legacy_notification_without_type_is_saved(app, user_client):
    """send_notification() used to drop any message without a '***type' suffix."""
    from crypto.notify import send_notification
    uid = user_client.get("/api/v2/auth/me").get_json()["data"]["id"]
    with app.app_context():
        assert send_notification("plain message", uid) is not None
    assert any(n["content"] == "plain message" for n in user_client.get("/api/v1/get_notifications/").get_json())


def test_preferences_roundtrip(user_client):
    res = user_client.patch("/api/v2/auth/me", json={"preferences": {"theme": "light", "lang": "ar"}, "firstName": "Ali"})
    data = res.get_json()["data"]
    assert data["preferences"]["theme"] == "light" and data["preferences"]["lang"] == "ar" and data["firstName"] == "Ali"
    bad = user_client.patch("/api/v2/auth/me", json={"img": "javascript:alert(1)"})
    assert bad.status_code == 400


# ------------------------------------------------------------------ kb / plans / admin

def test_knowledge_base_and_admin_blog(admin_client, client):
    cat = admin_client.post("/admin/blog/cats", json={"title": "Guides", "title_ar": "أدلة"}).get_json()
    post = admin_client.post("/admin/blog/posts", json={"title": "Getting started", "content": "<p>Hello <b>world</b></p>",
                                                       "writer": "Team", "category_id": cat["id"], "lang": "en"}).get_json()
    assert post["ok"]
    cats = client.get("/api/v2/kb/categories").get_json()["data"]
    assert any(c["id"] == cat["id"] and c["post_count"] == 1 for c in cats)
    posts = client.get(f"/api/v2/kb/posts?category={cat['id']}").get_json()["data"]
    assert posts[0]["excerpt"] == "Hello world"
    assert client.get(f"/api/v2/kb/posts/{post['id']}").get_json()["data"]["views"] == 1
    assert client.get(f"/knowledge_base_post/{post['id']}").status_code == 200


def test_admin_api(admin_client, user_client):
    stats = admin_client.get("/api/v2/admin/stats").get_json()["data"]
    assert stats["users"] >= 1 and {"plans", "volume_24h"} <= set(stats)
    users = admin_client.get("/api/v2/admin/users?limit=5").get_json()
    assert users["total"] >= 1
    uid = user_client.get("/api/v2/auth/me").get_json()["data"]["id"]
    plans = admin_client.get("/api/v2/plans").get_json()["data"]
    pro = next(p for p in plans if p["type"] == "pro")
    res = admin_client.patch(f"/api/v2/admin/users/{uid}", json={"sub_type_id": pro["id"]}).get_json()
    assert res["data"]["subType"]["type"] == "pro"
    assert admin_client.get("/api/v2/admin/system").get_json()["data"]["db_dialect"] == "sqlite"
    assert user_client.get("/api/v2/admin/stats").status_code == 401


def test_bot_duplicate_and_templates(app, paper_user, prices):
    from tests.test_bot_engine import make_bot
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, name="orig")
    dup = paper_user.post(f"/api/v2/bots/{bot_id}/duplicate").get_json()["data"]
    assert dup["name"] == "orig (copy)" and dup["isActive"] is False and dup["safety_orders_count"] == 2
    listing = paper_user.get("/api/v2/bots").get_json()
    assert listing["summary"]["total"] == 2
    assert len(paper_user.get("/api/v2/bots/templates").get_json()["data"]) >= 3


def test_transactions_pagination_and_export(app, paper_user, prices):
    prices.set("BTC", 40000)
    for _ in range(3):
        paper_user.post("/api/v1/order/", json={"symbol": "BTC/USDT", "type": "market", "amount": 0.01, "side": "buy"})
    page = paper_user.get("/api/v2/transactions?limit=2").get_json()
    assert page["total"] == 3 and len(page["data"]) == 2
    assert page["data"][0]["value"] == pytest.approx(0.01 * 40000 * 1.0002, rel=1e-3)
    csv_text = paper_user.get("/api/v2/export/transactions.csv").get_data(as_text=True)
    assert csv_text.count("\n") == 4 and "BTC/USDT" in csv_text


def test_engine_tick_runs_everything(app, paper_user, prices):
    from crypto import engine
    with app.app_context():
        stats = engine.tick()
    assert set(stats) >= {"paper", "alerts", "bots", "smart", "elapsed_ms"}
