"""Price alerts: evaluated by the engine tick, delivered as notifications
(in-app, real-time socket, and any configured Discord/Slack/Telegram channel)."""
from datetime import datetime

from crypto import db, market
from crypto.models import PriceAlert

CONDITIONS = ("above", "below", "change_pct")


def condition_met(alert, price):
    if not price:
        return False
    if alert.condition == "above":
        return price >= alert.target
    if alert.condition == "below":
        return price <= alert.target
    if alert.condition == "change_pct" and alert.reference_price:
        return abs(price - alert.reference_price) / alert.reference_price * 100 >= alert.target
    return False


def describe(alert, price):
    sym = alert.symbol
    if alert.condition == "above":
        return f"{sym} rose above {alert.target:g} (now {price:.8g})"
    if alert.condition == "below":
        return f"{sym} fell below {alert.target:g} (now {price:.8g})"
    move = (price - alert.reference_price) / alert.reference_price * 100 if alert.reference_price else 0
    return f"{sym} moved {move:+.2f}% (now {price:.8g})"


def check_alerts(now=None):
    """Evaluate every active alert once. Alerts are edge-triggered: a repeating
    alert fires again only after its condition was false in between."""
    from crypto.notify import send_notification
    now = now or datetime.utcnow()
    alerts = PriceAlert.query.filter_by(active=True).all()
    prices = {}
    fired = 0
    for alert in alerts:
        key = (alert.exchange, alert.symbol)
        if key not in prices:
            try:
                prices[key] = market.price(alert.exchange, alert.symbol)
            except Exception:
                prices[key] = 0
        price = prices[key]
        if not price:
            continue
        was_met = alert.last_price is not None and condition_met(alert, alert.last_price)
        is_met = condition_met(alert, price)
        alert.last_price = price
        if is_met and not (was_met and alert.repeat):
            fired += 1
            alert.triggered_at = now
            alert.trigger_count = (alert.trigger_count or 0) + 1
            note = f" — {alert.note}" if alert.note else ""
            send_notification(f"🔔 {describe(alert, price)}{note}***Alert", alert.user_id, alert.exchange)
            if alert.repeat:
                if alert.condition == "change_pct":
                    alert.reference_price = price
            else:
                alert.active = False
    db.session.commit()
    return fired
