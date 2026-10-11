"""Connection errors must tell users whether the server or API key is at fault."""
import ccxt


class FailingBinance:
    def __init__(self, error):
        self.error = error

    def load_markets(self):
        raise self.error


def test_binance_restricted_server_location_is_explained(user_client, monkeypatch):
    monkeypatch.setattr(ccxt, "binance", lambda _: FailingBinance(
        ccxt.ExchangeNotAvailable(
            'binance GET https://api.binance.com/api/v3/exchangeInfo 451 '
            '{"msg":"Service unavailable from a restricted location"}'
        )
    ))
    response = user_client.post("/api/v1/connect/", json={
        "exchange_name": "binance", "api_key": "fake-key", "api_secret": "fake-secret", "demo": False,
    })
    result = response.get_json()
    assert response.status_code == 503
    assert result["ok"] is False
    assert "location" in result["message"].lower()
    assert "server" in result["message"].lower()


def test_binance_outage_is_distinct_from_bad_credentials(user_client, monkeypatch):
    monkeypatch.setattr(ccxt, "binance", lambda _: FailingBinance(
        ccxt.ExchangeNotAvailable("binance GET https://api.binance.com/api/v3/exchangeInfo 503")
    ))
    response = user_client.post("/api/v1/connect/", json={
        "exchange_name": "binance", "api_key": "fake-key", "api_secret": "fake-secret", "demo": False,
    })
    result = response.get_json()
    assert response.status_code == 503
    assert "temporarily" in result["message"].lower()
    assert "credentials" not in result["message"].lower()


def test_bad_exchange_key_does_not_expire_app_session(user_client, monkeypatch):
    monkeypatch.setattr(ccxt, "binance", lambda _: FailingBinance(
        ccxt.AuthenticationError("binance: invalid API key")
    ))
    response = user_client.post("/api/v1/connect/", json={
        "exchange_name": "binance", "api_key": "fake-key",
        "api_secret": "fake-secret", "demo": False,
    })
    result = response.get_json()
    assert response.status_code == 422  # React reserves 401 for app login expiry.
    assert result["code"] == "authentication_failed"
    assert "API key" in result["message"]


def test_missing_encryption_key_is_reported_before_exchange_request(user_client, monkeypatch):
    monkeypatch.delenv("FERNET_KEY")
    monkeypatch.setattr(ccxt, "binance", lambda _: (_ for _ in ()).throw(
        AssertionError("Binance must not be called when credentials cannot be saved")
    ))
    response = user_client.post("/api/v1/connect/", json={
        "exchange_name": "binance", "api_key": "fake-key",
        "api_secret": "fake-secret", "demo": False,
    })
    result = response.get_json()
    assert response.status_code == 503
    assert result["code"] == "server_configuration_error"
    assert "FERNET_KEY" in result["message"]
