"""DCA bot engine against the paper exchange with pinned prices."""
from datetime import datetime, timedelta

import pytest

BOT = {
    "pair_type": "single", "symbol": "SOL/USDT", "symbols": [], "exchange_name": "paper", "name": "test bot",
    "amount": 1, "amount_type": 2, "start_order_type": "market", "strategy": "Long",
    "conds": [], "tp_conds": [], "tp_type": "Percent %", "tp_percent": 2, "tp_percent_type": "volume",
    "profit_currency": "quote", "trailing_take_profit": False, "trailing_deviation": 1,
    "trailing_stop_loss": False, "stop_loss": False, "stop_loss_price_percent": 10,
    "stop_loss_time_out": False, "stop_loss_time_out_time": 0, "Close_deal_after_timeout": False,
    "timeout": 0, "timeout_type": 1, "safety_orders_size": 1, "safety_orders_size_type": 2,
    "safety_orders_size_scale": 2, "safety_orders_deviation": 2, "safety_orders_deviation_scale": 1,
    "safety_orders_count": 2, "safety_orders_count_max_active": 1, "min_volume": "", "max_price": "",
    "min_price": "", "min_profit": False, "min_profit_type": "volume", "min_profit_percent": 0,
    "close_deal_action": 1, "cooldown_between_deals": "", "open_deals_and_stop": "",
}


def make_bot(client, **overrides):
    res = client.post("/api/v1/create_bot/", json={**BOT, **overrides})
    data = res.get_json()
    assert data["ok"], data
    return data["bot_id"]


def run(app, bot_id, now=None):
    from crypto import db
    from crypto.bots import run_bot_once
    from crypto.models import Bot
    with app.app_context():
        bot = db.session.get(Bot, bot_id)
        status = run_bot_once(bot, now=now)
        return status, bot.serialize(), {
            "buy_price": bot.buy_price, "total_volume": bot.total_volume, "stop": bot.stop_loss_price,
            "deal_start": bot.deal_start_price, "units": bot.units, "isActive": bot.isActive,
        }


def test_bot_without_conditions_opens_deal(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user)
    status, bot, raw = run(app, bot_id)
    assert status == "opened"
    assert bot["deal_started"] is True
    assert raw["deal_start"] == pytest.approx(100, rel=1e-3)
    assert bot["total_trades"] == 1


def test_safety_orders_average_down_then_take_profit(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user)
    run(app, bot_id)                                    # buy 1 @ ~100
    prices.set("SOL", 97.9)                             # past SO1 level (-2%)
    status, _, _ = run(app, bot_id)                     # places SO1 limit @ 98 -> fills immediately
    status, bot, raw = run(app, bot_id)                 # sees the fill
    # SO1 size 1 (scale applies from SO2); the 0.1% fee is taken in SOL on each buy
    assert raw["total_volume"] == pytest.approx(2 * 0.999)
    assert raw["buy_price"] == pytest.approx((100.02 + 97.9) / 2, rel=1e-3)
    assert bot["safety_orders_filled"] == 1

    prices.set("SOL", 96.5)                             # not yet SO2 (-4%: 96)
    run(app, bot_id)
    status, bot, raw = run(app, bot_id)
    assert raw["total_volume"] == pytest.approx(2 * 0.999)

    tp = raw["buy_price"] * 1.02
    prices.set("SOL", tp + 0.5)
    status, bot, raw = run(app, bot_id)
    assert status == "take-profit"
    assert bot["deal_started"] is False
    assert bot["isActive"] is False                    # legacy: stop after TP
    assert bot["total_profit"] > 0
    from crypto.paper import PaperExchange
    from tests.conftest import current_user_id
    with app.app_context():
        bal = PaperExchange(current_user_id(paper_user)).fetch_balance()
    # whole position (base + safety order, minus fees) was sold
    assert bal["total"].get("SOL", 0) < 0.01


def test_auto_restart_after_take_profit(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, auto_restart=True, safety_orders_count=0)
    run(app, bot_id)
    prices.set("SOL", 103)
    status, bot, raw = run(app, bot_id)
    assert status == "take-profit"
    assert bot["isActive"] is True and raw["units"] == pytest.approx(1)
    status, bot, _ = run(app, bot_id)
    assert status == "opened" and bot["total_trades"] == 2


def test_stop_loss_and_close_deal_action(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, stop_loss=True, stop_loss_price_percent=5, safety_orders_count=0, close_deal_action=2)
    run(app, bot_id)
    prices.set("SOL", 94)
    status, bot, _ = run(app, bot_id)
    assert status == "stop-loss"
    assert bot["isActive"] is False                   # action 2 = close deal & stop bot
    assert bot["total_profit"] < 0


def test_stop_loss_timeout_is_non_blocking(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, stop_loss=True, stop_loss_price_percent=5, safety_orders_count=0,
                      stop_loss_time_out=True, stop_loss_time_out_time=60)
    run(app, bot_id)
    prices.set("SOL", 94)
    t0 = datetime.utcnow()
    assert run(app, bot_id, now=t0)[0] == "stop-loss-pending"
    assert run(app, bot_id, now=t0 + timedelta(seconds=30))[0] == "stop-loss-pending"
    prices.set("SOL", 99)                             # recovered: timer resets
    assert run(app, bot_id, now=t0 + timedelta(seconds=40))[0] == "holding"
    prices.set("SOL", 94)
    t1 = t0 + timedelta(seconds=50)
    assert run(app, bot_id, now=t1)[0] == "stop-loss-pending"
    status, bot, _ = run(app, bot_id, now=t1 + timedelta(seconds=61))
    assert status == "stop-loss"
    assert bot["isActive"] is True                    # action 1 = close deal, keep running


def test_trailing_take_profit_locks_gain(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, trailing_take_profit=True, trailing_deviation=1, safety_orders_count=0)
    run(app, bot_id)
    prices.set("SOL", 103)                             # TP reached -> trailing armed
    status, bot, raw = run(app, bot_id)
    assert bot["take_profit"] is True and bot["deal_started"] is True
    assert raw["stop"] == pytest.approx(103 * 0.99)
    prices.set("SOL", 106)
    _, _, raw = run(app, bot_id)
    assert raw["stop"] == pytest.approx(106 * 0.99)
    prices.set("SOL", 104.5)                          # below trailing stop
    status, bot, _ = run(app, bot_id)
    assert status == "stop-loss"
    assert bot["deal_started"] is False and bot["total_profit"] > 0


def test_cooldown_between_deals(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, auto_restart=True, safety_orders_count=0, cooldown_between_deals=3600)
    t0 = datetime.utcnow()
    assert run(app, bot_id, now=t0)[0] == "opened"      # no cooldown before the first deal
    prices.set("SOL", 103)
    assert run(app, bot_id, now=t0 + timedelta(minutes=5))[0] == "take-profit"
    assert run(app, bot_id, now=t0 + timedelta(minutes=10))[0] == "waiting"
    assert run(app, bot_id, now=t0 + timedelta(minutes=64))[0] == "waiting"   # 59 min after the close
    assert run(app, bot_id, now=t0 + timedelta(minutes=66))[0] == "opened"


def test_deal_timeout_closes_position(app, paper_user, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user, safety_orders_count=0, Close_deal_after_timeout=True, timeout=1, timeout_type=1)
    t0 = datetime.utcnow()
    run(app, bot_id, now=t0)
    status, bot, _ = run(app, bot_id, now=t0 + timedelta(hours=2))
    assert status == "timeout"
    assert bot["deal_started"] is False


def test_rsi_entry_condition_is_evaluated(app, paper_user, prices):
    cond = [{"indicator": "RSI", "conds": {"Timeframe": "1h", "RSI Length": 14, "Condition": "Less than", "Signal Value": 0}}]
    bot_id = make_bot(paper_user, conds=cond)
    status, bot, _ = run(app, bot_id)
    assert status == "waiting"                          # RSI is never below 0
    assert bot["conds"][0].get("value") is not None     # latest value stored for the UI


def test_delete_idle_bot_does_not_sell_coins(app, paper_user, prices):
    prices.set("SOL", 100)
    paper_user.post("/api/v1/order/", json={"symbol": "SOL/USDT", "type": "market", "amount": 5, "side": "buy"})
    bot_id = make_bot(paper_user)                       # armed, no deal yet
    res = paper_user.post("/api/v1/delete_bot", json={"bot_id": bot_id})
    assert res.get_json()["ok"]
    from crypto.paper import PaperExchange
    from tests.conftest import current_user_id
    with app.app_context():
        assert PaperExchange(current_user_id(paper_user)).fetch_balance()["total"]["SOL"] == pytest.approx(5 * 0.999)


def test_bot_endpoints_owner_only(app, paper_user, make_user_client, prices):
    prices.set("SOL", 100)
    bot_id = make_bot(paper_user)
    intruder = make_user_client()
    for url in ("/api/v1/get_bot_stats?bot_id=%d" % bot_id, "/api/v2/bots/%d" % bot_id):
        assert intruder.get(url).status_code in (403, 404)
    for url in ("/api/v1/toggle_bot", "/api/v1/delete_bot", "/api/v1/edit_bot/"):
        res = intruder.post(url, json={"bot_id": bot_id, "state": False})
        assert res.status_code in (403, 404), url
    res = intruder.post("/api/v2/bots/%d/duplicate" % bot_id)
    assert res.status_code == 404


def test_bot_preview_ladder(client):
    res = client.post("/api/v2/bots/preview", json={"price": 100, "amount": 100, "safety_orders_size": 100,
                                                    "safety_orders_count": 3, "safety_orders_deviation": 2,
                                                    "safety_orders_deviation_scale": 2, "safety_orders_size_scale": 1,
                                                    "tp_percent": 1})
    levels = res.get_json()["data"]["levels"]
    assert [round(l["deviation"], 4) for l in levels] == [2, 6, 14]   # 2, 2+4, 2+4+8
    assert levels[0]["price"] == pytest.approx(98)
