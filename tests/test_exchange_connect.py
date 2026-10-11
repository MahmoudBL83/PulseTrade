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
