import ccxt
import pytest

from tests.conftest import current_user_id


def _paper(app, client):
    from crypto.paper import PaperExchange
    return PaperExchange(current_user_id(client))


def test_market_buy_and_sell_with_fees(app, paper_user, prices):
    prices.set("BTC", 50_000)
    with app.app_context():
        ex = _paper(app, paper_user)
        start = ex.fetch_balance()
        assert start["total"]["USDT"] == pytest.approx(10_000)

        order = ex.create_order("BTC/USDT", "market", "buy", 0.1)
        assert order["status"] == "closed"
        bal = ex.fetch_balance()
        assert bal["free"]["USDT"] == pytest.approx(10_000 - 0.1 * 50_000 * 1.0002, rel=1e-3)
        assert bal["free"]["BTC"] == pytest.approx(0.1 * 0.999, rel=1e-6)  # 0.1% taker fee in BTC

        ex.create_order("BTC/USDT", "market", "sell", bal["free"]["BTC"])
        bal2 = ex.fetch_balance()
        assert bal2["total"].get("BTC", 0) == pytest.approx(0, abs=1e-12)
        assert bal2["free"]["USDT"] < 10_000  # round trip pays fees and spread


def test_limit_order_reserves_and_cancel_releases(app, paper_user, prices):
    prices.set("ETH", 3_000)
    with app.app_context():
        ex = _paper(app, paper_user)
        o = ex.create_order("ETH/USDT", "limit", "buy", 1, 2_500)
        assert o["status"] == "open"
        bal = ex.fetch_balance()
        assert bal["used"]["USDT"] == pytest.approx(2_500)
        assert [x["id"] for x in ex.fetch_open_orders()] == [o["id"]]

        ex.cancel_order(o["id"], "ETH/USDT")
        bal = ex.fetch_balance()
        assert bal["used"]["USDT"] == pytest.approx(0)
        assert bal["free"]["USDT"] == pytest.approx(10_000)
        assert ex.fetch_order(o["id"])["status"] == "canceled"


def test_limit_fills_when_price_reaches_it(app, paper_user, prices):
    prices.set("SOL", 100)
    with app.app_context():
        ex = _paper(app, paper_user)
        o = ex.create_order("SOL/USDT", "limit", "buy", 10, 90)
        assert ex.fetch_order(o["id"])["status"] == "open"
        prices.set("SOL", 89)
        filled = ex.fetch_order(o["id"])
        assert filled["status"] == "closed"
        assert filled["average"] == pytest.approx(90)
        bal = ex.fetch_balance()
        assert bal["free"]["SOL"] == pytest.approx(10 * 0.999)
        assert bal["free"]["USDT"] == pytest.approx(10_000 - 900)


def test_trigger_order_fires_on_cross(app, paper_user, prices):
    prices.set("BNB", 600)
    with app.app_context():
        ex = _paper(app, paper_user)
        o = ex.create_order("BNB/USDT", "market", "buy", 1, None, params={"triggerPrice": 650})
        assert o["status"] == "open" and o["triggerPrice"] == 650
        prices.set("BNB", 640)
        assert ex.fetch_order(o["id"])["status"] == "open"
        prices.set("BNB", 651)
        assert ex.fetch_order(o["id"])["status"] == "closed"


def test_insufficient_funds_rejected_without_side_effects(app, paper_user, prices):
    prices.set("BTC", 50_000)
    with app.app_context():
        ex = _paper(app, paper_user)
        with pytest.raises(ccxt.InsufficientFunds):
            ex.create_order("BTC/USDT", "market", "buy", 1)  # needs 50k, has 10k
        assert ex.fetch_balance()["free"]["USDT"] == pytest.approx(10_000)
        assert ex.fetch_open_orders() == []


def test_reset_account(app, paper_user, prices):
    prices.set("BTC", 50_000)
    paper_user.post("/api/v2/paper/reset", json={"starting_balance": 2500})
    data = paper_user.get("/api/v2/paper").get_json()["data"]
    assert data["connected"] is True
    assert data["account"]["starting_balance"] == 2500
    assert data["account"]["equity"] == pytest.approx(2500)


def test_legacy_order_endpoint_works_on_paper(app, paper_user, prices):
    prices.set("BTC", 40_000)
    res = paper_user.post("/api/v1/order/", json={"symbol": "BTC/USDT", "type": "market", "amount": 0.01, "side": "buy"})
    assert res.get_json()["ok"] is True, res.get_json()
    res = paper_user.post("/api/v1/order/", json={"symbol": "BTC/USDT", "type": "limit", "order_price": 30000,
                                                  "amount": 0.01, "side": "buy"})
    assert res.get_json()["ok"] is True
    oid = res.get_json()["order"]["id"]
    opens = paper_user.post("/api/v1/history/open_orders/").get_json()
    assert any(str(o["id"]) == oid for o in opens)
    closed = paper_user.post("/api/v1/history/orders/").get_json()
    assert len(closed) == 1  # market buy only; no duplicates from ordType passes
    res = paper_user.post("/api/v1/order/cancel", json={"id": oid, "symbol": "BTC/USDT"})
    assert res.get_json()["ok"] is True


def test_convert_and_assets_on_paper(app, paper_user, prices):
    prices.set("ETH", 2_000)
    res = paper_user.post("/api/v1/convert/", json={"amount": 1, "order_type": "market", "source_asset": "ETH",
                                                   "target_asset": "USDT", "side": "0"})
    assert res.get_json()["ok"] is True, res.get_json()
    assets = {a["currency"]: a for a in paper_user.get("/api/v1/assets?exchange=all").get_json()}
    assert assets["ETH"]["total"] == pytest.approx(0.999)
