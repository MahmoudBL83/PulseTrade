"""Additions beside ccxt: external data sources, ccxt.pro streaming status,
backtest optimizer and analytics metrics."""
import pytest


def test_insights_fall_back_to_labelled_synthetic_data(client):
    data = client.get("/api/v2/insights").get_json()["data"]
    assert data["global"]["source"] == "synthetic"                 # network blocked in tests
    assert 0 < data["global"]["btc_dominance"] < 100
    fng = data["fear_greed"]
    assert 0 <= fng["current"]["value"] <= 100 and len(fng["history"]) == 30
    assert fng["current"]["classification"] in ("Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed")
    assert data["defi"]["total_tvl"] > 0 and data["defi"]["chains"]
    assert data["attribution"]["alternative.me"]["url"].startswith("https://")
    coins = client.get("/api/v2/insights/coins?limit=10").get_json()["data"]
    assert len(coins) == 10 and coins[0]["rank"] == 1 and coins[0]["market_cap"] >= coins[-1]["market_cap"]


def test_coingecko_payload_is_normalised(monkeypatch):
    from crypto import datasources
    datasources._cache.clear()
    monkeypatch.setattr(datasources, "enabled", lambda: True)

    def fake_get(url, params=None, host_key=None, headers=None):
        if url.endswith("/global"):
            return {"data": {"total_market_cap": {"usd": 3.1e12}, "total_volume": {"usd": 1e11},
                             "market_cap_percentage": {"btc": 57.2, "eth": 11.3},
                             "market_cap_change_percentage_24h_usd": -1.2, "active_cryptocurrencies": 17000, "markets": 1200}}
        if "fng" in url:
            return {"data": [{"value": "72", "value_classification": "Greed", "timestamp": "1760054400"},
                             {"value": "64", "value_classification": "Greed", "timestamp": "1759968000"}]}
        return None
    monkeypatch.setattr(datasources, "_get", fake_get)
    g = datasources.global_market()
    assert g["source"] == "coingecko" and g["btc_dominance"] == 57.2
    f = datasources.fear_greed(2)
    assert f["source"] == "alternative.me" and f["current"]["value"] == 72
    assert [h["value"] for h in f["history"]] == [64, 72]           # oldest first for charts
    datasources._cache.clear()


def test_coingecko_demo_key_header(monkeypatch):
    from crypto import datasources
    monkeypatch.setenv("COINGECKO_API_KEY", "CG-test")
    assert datasources._cg_headers() == {"x-cg-demo-api-key": "CG-test"}
    monkeypatch.delenv("COINGECKO_API_KEY")
    assert datasources._cg_headers() is None


def test_stream_disabled_by_default(client):
    s = client.get("/api/v2/market/stream").get_json()["data"]
    assert s["enabled"] is False and s["running"] is False


def test_backtest_optimizer_grid(client):
    res = client.post("/api/v2/backtest/optimize", json={
        "symbol": "BTC/USDT", "timeframe": "1h", "limit": 300, "base_order": 100, "safety_order": 100,
        "max_safety_orders": 3, "metric": "return_pct",
        "grid": {"take_profit": [1, 2], "deviation": {"min": 1, "max": 2, "step": 0.5}}}).get_json()
    data = res["data"]
    assert data["runs"] == 6 and len(data["top"]) == 6
    scores = [r["score"] for r in data["top"]]
    assert scores == sorted(scores, reverse=True)
    assert data["heatmap"]["x"] == "take_profit" and len(data["heatmap"]["cells"]) == 6


def test_backtest_optimizer_limits(client):
    big = {"take_profit": {"min": 0.5, "max": 10, "step": 0.1}, "deviation": {"min": 0.5, "max": 10, "step": 0.1}}
    assert client.post("/api/v2/backtest/optimize", json={"grid": big}).status_code == 400
    assert client.post("/api/v2/backtest/optimize", json={"grid": {"nope": [1]}}).status_code == 400
    assert client.post("/api/v2/backtest/optimize", json={"grid": {"take_profit": [1]}, "metric": "luck"}).status_code == 400


def test_backtest_trade_statistics(client):
    s = client.post("/api/v2/backtest", json={"symbol": "ETH/USDT", "limit": 500, "take_profit": 1.2,
                                              "max_safety_orders": 3}).get_json()["data"]["stats"]
    assert {"profit_factor", "expectancy", "avg_win", "avg_loss", "calmar", "exposure_pct"} <= set(s)
    assert 0 <= s["exposure_pct"] <= 100
    assert s["profit_factor"] is None or s["profit_factor"] >= 0


def test_risk_metrics():
    from crypto.analytics import risk
    flat = risk([100.0] * 10)
    assert flat["sharpe"] == 0 and flat["max_drawdown"] == 0
    series = [100 * (1.01 ** i) for i in range(40)]
    up = risk(series)
    assert up["return_pct"] == pytest.approx((1.01 ** 39 - 1) * 100, abs=1e-3)  # rounded to 4 dp
    assert up["max_drawdown"] == 0 and up["cagr"] > 0
    dd = risk([100, 120, 90, 95])
    assert dd["max_drawdown"] == pytest.approx(25)
    assert dd["cagr"] == 0                                         # too little history to annualise
