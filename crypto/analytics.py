"""Portfolio analytics: live balances across every connected exchange and
risk/performance statistics from the stored balance history."""
import math
import statistics
from datetime import datetime, timedelta

from crypto import db, market
from crypto.cache import TTLCache
from crypto.functions import build_exchange, getPrice_assets
from crypto.models import BalanceHistory, Bot, SmartTrade, Transaction

_balances_cache = TTLCache(ttl=30)


def balances(user, refresh=False):
    """Aggregated holdings: [{currency, free, used, total, price, value, exchanges}]."""
    key = user.id
    if not refresh:
        hit = _balances_cache.get(key)
        if hit is not None:
            return hit
    assets, errors = {}, []
    for row in user.exchanges.all():
        try:
            bal = build_exchange(row).fetch_balance()
        except Exception as e:
            errors.append({"exchange": row.name, "error": str(e)[:200]})
            continue
        free_map, used_map = bal.get("free") or {}, bal.get("used") or {}
        for cur, total in (bal.get("total") or {}).items():
            if not total:
                continue
            a = assets.setdefault(cur, {"currency": cur, "free": 0.0, "used": 0.0, "total": 0.0, "exchanges": []})
            a["free"] += float(free_map.get(cur) or 0)
            a["used"] += float(used_map.get(cur) or 0)
            a["total"] += float(total)
            a["exchanges"].append(row.name)
    btc_usd = market.usd_price(None, "BTC") or 0
    rows = []
    for a in assets.values():
        price = float(getPrice_assets(market.default_exchange(), a["currency"] + "/USDT") or 0)
        a["price"] = price
        a["value"] = a["total"] * price
        a["value_btc"] = a["value"] / btc_usd if btc_usd else 0
        rows.append(a)
    rows.sort(key=lambda r: r["value"], reverse=True)
    total = sum(r["value"] for r in rows)
    for r in rows:
        r["share"] = (r["value"] / total * 100) if total else 0
    out = {"assets": rows, "total_usd": total, "total_btc": total / btc_usd if btc_usd else 0,
           "errors": errors, "updated_at": datetime.utcnow().isoformat() + "Z"}
    return _balances_cache.set(key, out)


def history(user, days=30):
    since = datetime.utcnow() - timedelta(days=days)
    rows = BalanceHistory.query.filter(BalanceHistory.owner_id == user.id, BalanceHistory.timestamp >= since) \
        .order_by(BalanceHistory.timestamp.asc()).all()
    return [{"t": r.timestamp.isoformat() + "Z", "usd": r.balance_usd or 0, "btc": r.balance_btc or 0} for r in rows]


def _daily(points):
    by_day = {}
    for p in points:
        by_day[p["t"][:10]] = p["usd"]
    return [by_day[d] for d in sorted(by_day)]


def risk(series):
    """Stats from a daily equity series."""
    out = {"sharpe": 0.0, "sortino": 0.0, "volatility": 0.0, "max_drawdown": 0.0, "cagr": 0.0, "calmar": 0.0,
           "best_day": 0.0, "worst_day": 0.0, "return_pct": 0.0, "days": len(series)}
    if len(series) < 2:
        return out
    rets = [(b - a) / a for a, b in zip(series, series[1:]) if a]
    if series[0]:
        out["return_pct"] = (series[-1] - series[0]) / series[0] * 100
    peak, mdd = series[0], 0.0
    for v in series:
        peak = max(peak, v)
        if peak:
            mdd = max(mdd, (peak - v) / peak)
    out["max_drawdown"] = mdd * 100
    # QuantStats-style: compound annual growth and return per unit of drawdown
    # (only with 30+ days of history; shorter windows extrapolate into nonsense)
    years = (len(series) - 1) / 365
    if series[0] and series[-1] > 0 and len(series) >= 30:
        out["cagr"] = ((series[-1] / series[0]) ** (1 / years) - 1) * 100
        out["calmar"] = out["cagr"] / out["max_drawdown"] if out["max_drawdown"] else 0.0
    if len(rets) >= 2:
        mean, sd = statistics.fmean(rets), statistics.pstdev(rets)
        downside = math.sqrt(sum(r * r for r in rets if r < 0) / len(rets))
        ann = math.sqrt(365)
        out["sharpe"] = mean / sd * ann if sd else 0.0
        out["sortino"] = mean / downside * ann if downside else 0.0
        out["volatility"] = sd * ann * 100
    if rets:
        out["best_day"], out["worst_day"] = max(rets) * 100, min(rets) * 100
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def performance(user, days=90):
    hist = history(user, days)
    stats = risk(_daily(hist))
    bots = user.bots.filter(Bot.is_hidden == False).all()
    traded = [b for b in bots if (b.total_trades or 0) > 0]
    smart = SmartTrade.query.filter(SmartTrade.user_id == user.id, SmartTrade.is_hidden == False).all()
    since = datetime.utcnow() - timedelta(days=30)
    tx = db.session.query(db.func.count(Transaction.id), db.func.coalesce(db.func.sum(Transaction.value), 0)) \
        .filter(Transaction.user_id == user.id, Transaction.created_at >= since, Transaction.status == True).first()
    best = max(traded, key=lambda b: b.total_profit or 0, default=None)
    worst = min(traded, key=lambda b: b.total_profit or 0, default=None)
    stats.update({
        "bots_total": len(bots),
        "bots_active": sum(1 for b in bots if b.isActive),
        "bot_profit": sum(b.total_profit or 0 for b in bots),
        "bot_deals": sum(b.total_trades or 0 for b in bots),
        "bot_win_rate": (sum(1 for b in traded if (b.total_profit or 0) > 0) / len(traded) * 100) if traded else 0,
        "best_bot": {"id": best.id, "name": best.name, "profit": best.total_profit} if best else None,
        "worst_bot": {"id": worst.id, "name": worst.name, "profit": worst.total_profit} if worst else None,
        "smart_trades_total": len(smart),
        "smart_trades_active": sum(1 for s in smart if s.isActive),
        "smart_trade_profit": sum(s.total_profit or 0 for s in smart),
        "trades_30d": int(tx[0] or 0),
        "volume_30d": float(tx[1] or 0),
    })
    return stats
