"""Shared fixtures. The Flask app is a module-level singleton configured from
env vars at import time, so the environment is prepared before importing it.

Network is blocked for the whole session: ccxt, requests and the tradingview
screener all raise instead of reaching the internet, which keeps the suite
hermetic and exercises every "exchange unavailable" code path."""
import os
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="pulsetrade-tests-")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.update({
    "DATABASE_URL": "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/"),
    "DEMO": "1",
    "SECRET_KEY": "test-secret",
    "JWT_SECRET_KEY": "test-jwt-secret-that-is-long-enough-for-hs256",
    "SECURITY_PASSWORD_SALT": "test-salt",
    "FERNET_KEY": "Cu0bqF1cFjVYxVrQ5mlS0Lw0cE1fGZ0n2Z3aYp4w8Qs=",
    "ADMIN_PASSWORD": "admin-test-pass",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_STREAM_PASSWORD": "stream-test-pass",
    "PULSE_TESTING": "1",
    "VERCEL": "",
    "MARKET_DATA": "synthetic",
    "ENGINE": "off",
})
# Run relative-path data dirs (pricesData/, stochData/ ...) inside the temp dir.
os.chdir(_TMP)


class _Blocked(Exception):
    pass


def _block_network(monkeypatch):
    import ccxt
    import requests

    def _no_ccxt(self, *a, **kw):
        raise ccxt.NetworkError("network disabled in tests")

    def _no_requests(self, *a, **kw):
        raise requests.ConnectionError("network disabled in tests")

    monkeypatch.setattr(ccxt.Exchange, "fetch", _no_ccxt, raising=True)
    monkeypatch.setattr(requests.Session, "request", _no_requests, raising=True)


@pytest.fixture(scope="session")
def app():
    from crypto import app as flask_app, db
    flask_app.config.update(TESTING=True)
    with flask_app.app_context():
        db.create_all()
        from crypto.demo import seed_catalog
        seed_catalog()
    return flask_app


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    _block_network(monkeypatch)


@pytest.fixture()
def client(app):
    return app.test_client()


def _register_and_login(client, email, password="Secret123!"):
    client.post("/register", json={
        "email": email, "firstName": "Test", "lastName": "User",
        "password": password, "confirm_password": password,
    })
    res = client.post("/login", json={"email": email, "password": password, "admin": False})
    return res.get_json() or {}


@pytest.fixture()
def make_user_client(app):
    """Factory: every call registers and logs in a brand-new user."""
    import uuid

    def make():
        c = app.test_client()
        data = _register_and_login(c, f"user-{uuid.uuid4().hex[:8]}@example.com")
        c.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + (data.get("access_token") or "")
        return c
    return make


@pytest.fixture()
def user_client(make_user_client):
    return make_user_client()


@pytest.fixture()
def admin_client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s["admin"] = True
    return c


class PriceBoard:
    """Pins synthetic prices per base asset (USD) so engine tests are exact."""

    def __init__(self, monkeypatch):
        from crypto import market
        self.market = market
        self.prices = {}
        original = market.synthetic.usd

        def usd(asset, t):
            if asset in self.prices:
                return self.prices[asset]
            return original(asset, t)

        monkeypatch.setattr(market.synthetic, "usd", usd)
        market.clear_caches()

    def set(self, asset, price):
        self.prices[asset] = float(price)
        self.market.clear_caches()


@pytest.fixture()
def prices(monkeypatch):
    return PriceBoard(monkeypatch)


@pytest.fixture()
def paper_user(app, user_client):
    """A logged-in user with the paper exchange connected as active."""
    res = user_client.post("/api/v2/paper/connect")
    assert res.status_code == 200, res.get_data(as_text=True)
    return user_client


def current_user_id(client):
    return client.get("/api/v2/auth/me").get_json()["data"]["id"]
