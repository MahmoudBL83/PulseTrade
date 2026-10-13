import ccxt

from conftest import current_user_id


def _connect(app, client, name="binance"):
    from crypto import db
    from crypto.models import Exchange

    with app.app_context():
        db.session.add(Exchange(owner_id=current_user_id(client), name=name, isActive=True))
        db.session.commit()


class SymbolRequiredExchange:
    has = {"fetchOpenOrders": True, "fetchClosedOrders": "emulated",
           "fetchCanceledOrders": False, "fetchMyTrades": True}

    def __init__(self):
        self.calls = []

    def fetch_open_orders(self, symbol=None, limit=None):
        self.calls.append(("open", symbol))
        return []

    def fetch_closed_orders(self, symbol=None, limit=None):
        self.calls.append(("closed", symbol))
        if symbol is None:
            raise ccxt.ArgumentsRequired("symbol required")
        return [{"id": "123", "symbol": symbol, "status": "closed", "timestamp": 12,
                 "side": "buy", "type": "limit", "amount": 1, "price": 100,
                 "average": 100, "fee": {"cost": 0.1, "currency": "USDT"}}]

    def fetch_my_trades(self, symbol=None, limit=None):
        return [{"id": "fill-1", "order": "123", "symbol": symbol,
                 "timestamp": 12, "price": 100, "amount": 1}]


def test_binance_style_history_uses_known_pair(app, user_client, monkeypatch):
    from crypto import db
    from crypto.models import Transaction
    from crypto import order_history

    _connect(app, user_client)
    with app.app_context():
        db.session.add(Transaction(type="buy", user_id=current_user_id(user_client),
                                   exchange="binance", amount=1, symbol="BTC/USDT"))
        db.session.commit()
    fake = SymbolRequiredExchange()
    monkeypatch.setattr(order_history, "build_exchange", lambda row: fake)

    res = user_client.get("/api/v2/orders/history")
    assert res.status_code == 200
    body = res.get_json()
    assert body["data"][0]["id"] == "123"
    assert body["sources"][0]["status"] == "ok"
    assert fake.calls == [("closed", None), ("closed", "BTC/USDT")]

def test_manual_pair_fetches_unseen_orders(app, user_client, monkeypatch):
    from crypto import order_history
    _connect(app, user_client)
    fake = SymbolRequiredExchange()
    monkeypatch.setattr(order_history, "build_exchange", lambda row: fake)

    missing = user_client.get("/api/v2/orders/history").get_json()
    assert missing["data"] == []
    assert missing["sources"][0]["status"] == "pair_required"

    res = user_client.get("/api/v2/orders/history?symbol=ETH%2FUSDT")
    assert res.get_json()["data"][0]["symbol"] == "ETH/USDT"
    assert fake.calls[-1] == ("closed", "ETH/USDT")


def test_exchange_failure_is_reported(app, user_client, monkeypatch):
    from crypto import order_history
    _connect(app, user_client)

    class Failed(SymbolRequiredExchange):
        def fetch_open_orders(self, symbol=None, limit=None):
            raise ccxt.AuthenticationError("secret diagnostics")

    monkeypatch.setattr(order_history, "build_exchange", lambda row: Failed())
    res = user_client.get("/api/v2/orders/open").get_json()
    assert res["data"] == []
    assert res["sources"][0]["status"] == "error"
    assert "permissions" in res["sources"][0]["message"]
    assert "secret diagnostics" not in str(res)


def test_fills_and_symbol_validation(app, user_client, monkeypatch):
    from crypto import order_history
    _connect(app, user_client)
    monkeypatch.setattr(order_history, "build_exchange", lambda row: SymbolRequiredExchange())
    res = user_client.get("/api/v2/orders/fills?symbol=BTC%2FUSDT")
    assert res.get_json()["data"][0]["order"] == "123"
    assert user_client.get("/api/v2/orders/history?symbol=../../etc").status_code == 400


def test_separate_trigger_book_is_opt_in(app, user_client, monkeypatch):
    from crypto import order_history
    _connect(app, user_client)

    class TriggerExchange(SymbolRequiredExchange):
        def fetch_open_orders(self, symbol=None, limit=None, params=None):
            if params and params.get("ordType") == "trigger":
                return [{"id": "stop-1", "symbol": "BTC/USDT", "status": "open",
                         "type": "limit", "side": "sell", "amount": 1,
                         "triggerPrice": 90, "timestamp": 42}]
            return []

    monkeypatch.setattr(order_history, "build_exchange", lambda row: TriggerExchange())
    assert user_client.get("/api/v2/orders/open?symbol=BTC%2FUSDT").get_json()["data"] == []
    response = user_client.get("/api/v2/orders/open?symbol=BTC%2FUSDT&conditional=1").get_json()
    assert response["data"][0]["id"] == "stop-1"
    assert response["data"][0]["trigger_price"] == "90 USDT"


def test_emulated_history_uses_one_fetch_orders_call(app, user_client, monkeypatch):
    from crypto import order_history
    _connect(app, user_client)

    class Emulated:
        has = {"fetchClosedOrders": "emulated", "fetchCanceledOrders": "emulated", "fetchOrders": True}
        calls = 0

        def fetch_orders(self, symbol=None, limit=None):
            self.calls += 1
            assert symbol == "BTC/USDT"
            return [{"id": "1", "symbol": symbol, "status": "open"},
                    {"id": "2", "symbol": symbol, "status": "closed", "timestamp": 3},
                    {"id": "3", "symbol": symbol, "status": "canceled", "timestamp": 2}]

    exchange = Emulated()
    monkeypatch.setattr(order_history, "build_exchange", lambda row: exchange)
    response = user_client.get("/api/v2/orders/history?symbol=BTC%2FUSDT").get_json()
    assert [item["id"] for item in response["data"]] == ["2", "3"]
    assert exchange.calls == 1
