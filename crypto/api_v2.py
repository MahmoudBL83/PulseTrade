"""JSON API v2 — used by the React app (frontend/) and available to any API
client with a Bearer token. Everything legacy (/api/v1, pages) still works;
v2 adds clean shapes for the new UI plus the new features."""
import csv
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, Response, jsonify, request, session
from flask_login import logout_user
from sqlalchemy import or_

import crypto
from crypto import app, db, get_current_user, market
from crypto.cache import TTLCache
from crypto.errors import ApiError
from crypto.models import (
    Bot, Category, Exchange, Exchange2, JournalEntry, LoginEvent, Message, Notification, PaperAccount, PaperOrder,
    Post, PriceAlert, SafetyOrder, SmartTrade, Subscription, Ticket, Transaction, User, WatchlistItem, PAPER_EXCHANGE,
)

bp = Blueprint("v2", __name__, url_prefix="/api/v2")
_signals_cache = TTLCache(ttl=120)


def ok(data=None, status=200, **extra):
    body = {"ok": True}
    if data is not None:
        body["data"] = data
    body.update(extra)
    return jsonify(body), status


def body():
    return request.get_json(silent=True) or {}


def need(payload, *keys):
    missing = [k for k in keys if payload.get(k) in (None, "")]
    if missing:
        raise ApiError(f"Missing field: {missing[0]}", 400, field=missing[0])


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = get_current_user()
        if user is None:
            raise ApiError("authentication required", 401)
        return fn(user, *a, **kw)
    return wrapper


def admin_only(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            raise ApiError("admin authentication required", 401)
        return fn(*a, **kw)
    return wrapper


def page_args(default=50, maximum=500):
    limit = max(1, min(int(request.args.get("limit", default)), maximum))
    offset = max(0, int(request.args.get("offset", 0)))
    return limit, offset


def _float(v, name):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a number", 400)
    if f != f or f in (float("inf"), float("-inf")):
        raise ApiError(f"{name} must be a number", 400)
    return f


# =============================================================================
# meta
# =============================================================================

@bp.get("/meta")
def meta():
    from crypto.auth_core import mail_configured
    import stripe
    return ok({
        "name": "PulseTrade", "build": crypto.BUILD_ID, "demo": os.environ.get("DEMO", "0") == "1",
        "serverless": crypto.IS_VERCEL, "engine": crypto.engine_mode(), "market_data": market.mode(),
        "default_exchange": market.default_exchange(),
        "features": {
            "mail": mail_configured(), "stripe": bool(stripe.api_key), "tap": bool(os.environ.get("TAP_API_KEY")),
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")), "paper": True, "realtime": not crypto.IS_VERCEL,
        },
        "time": datetime.utcnow().isoformat() + "Z",
    })


# =============================================================================
# auth
# =============================================================================

def user_payload(user):
    data = user.serialize()
    data["exchanges"] = [e.serialize() for e in user.exchanges.all()]
    data["active_exchange"] = next((e["name"] for e in data["exchanges"] if e["isActive"]), None)
    data["unread_notifications"] = user.notifications.filter(Notification.read == False).count()
    data["is_admin"] = bool(session.get("admin"))
    plan = user.subType
    data["plan"] = plan.serialize() if plan else None
    data["plan_expires"] = (user.sub_date + timedelta(days=30)).isoformat() if (user.sub_date and plan and plan.type != "free") else None
    return data


@bp.post("/auth/login")
def auth_login():
    from crypto.auth import begin_user_login
    p = body()
    need(p, "email", "password")
    status, payload = begin_user_login(p.get("email"), p.get("password"), p.get("remember", True), p.get("totp"))
    if status == "ok":
        return ok({"access_token": payload["access_token"], "user": user_payload(payload["user"])})
    if status in ("otp_required", "totp_required"):
        return jsonify({"ok": False, "otp_required": True, "method": "totp" if status == "totp_required" else "email",
                        "message": payload["message"]}), 200
    code = {"blocked": 429, "unverified": 403}.get(status, 401)
    raise ApiError(payload["message"], code)


@bp.post("/auth/verify")
def auth_verify():
    from crypto.auth import complete_login
    from crypto.auth_core import check_pending_code, clear_pending_login, client_ip, validate_ip_address
    data = check_pending_code(body().get("code"))
    if not data:
        raise ApiError("Invalid or expired code", 400)
    if data["email"] == "admin":
        clear_pending_login()
        session["admin"] = True
        return ok({"admin": True})
    user = User.query.filter_by(email=data["email"]).first()
    if user is None:
        raise ApiError("Account not found", 404)
    if validate_ip_address(client_ip()):
        user.last_ip = client_ip()
    token = complete_login(user, data.get("remember", True))
    return ok({"access_token": token, "user": user_payload(user)})


@bp.post("/auth/register")
def auth_register():
    from crypto.auth import register_user, complete_login
    from crypto.auth_core import mail_verification_required
    p = body()
    need(p, "email", "password")
    success, message, user = register_user(p.get("email"), p.get("firstName"), p.get("lastName"),
                                           p.get("password"), p.get("confirm_password", p.get("password")))
    if not success:
        raise ApiError(message, 400)
    if mail_verification_required():
        return ok({"verification_required": True}, message=message)
    token = complete_login(user, True)
    return ok({"access_token": token, "user": user_payload(user)}, 201, message=message)


@bp.post("/auth/logout")
def auth_logout():
    from crypto.auth import _revoke_current_token
    _revoke_current_token()
    logout_user()
    return ok()


@bp.get("/auth/me")
@login_required
def auth_me(user):
    return ok(user_payload(user))


@bp.patch("/auth/me")
@login_required
def auth_update_me(user):
    p = body()
    if "firstName" in p:
        user.firstName = str(p["firstName"] or "").strip()[:120]
    if "lastName" in p:
        user.lastName = str(p["lastName"] or "").strip()[:120]
    if "img" in p:
        img = str(p["img"] or "").strip()
        if len(img) > 512 or (img and not img.startswith(("https://", "http://", "/static/"))):
            raise ApiError("Avatar must be an http(s) URL or a /static path", 400)
        user.img = img or "/static/assets/images/avatars/01.png"
    if "ip_check" in p:
        user.ip_check = bool(p["ip_check"])
    if isinstance(p.get("preferences"), dict):
        prefs = user.get_preferences()
        incoming = p["preferences"]
        for key in ("theme", "lang", "currency", "dashboard"):
            if key in incoming:
                prefs[key] = incoming[key]
        if prefs.get("theme") not in ("dark", "light", "system"):
            prefs["theme"] = "dark"
        if prefs.get("lang") not in ("en", "ar"):
            prefs["lang"] = "en"
        user.preferences = prefs
    db.session.commit()
    return ok(user_payload(user))


@bp.post("/auth/password")
@login_required
def auth_change_password(user):
    from crypto.auth_core import password_problem, log_event
    p = body()
    need(p, "current_password", "new_password")
    if not user.check_password(p["current_password"]):
        log_event(user, "password_change", False)
        raise ApiError("Current password is incorrect", 400)
    problem = password_problem(p["new_password"])
    if problem:
        raise ApiError(problem, 400)
    user.set_password(p["new_password"])
    db.session.commit()
    log_event(user, "password_change", True)
    return ok(message="Password updated")


@bp.post("/auth/forgot")
def auth_forgot():
    from crypto.auth import send_password_reset_email
    email = str(body().get("email") or "").strip().lower()
    user = User.query.filter(db.func.lower(User.email) == email).first() if email else None
    if user:
        send_password_reset_email(user)
    return ok(message="If that email is registered, reset instructions are on their way.")


@bp.get("/auth/2fa")
@login_required
def twofa_status(user):
    return ok({"enabled": bool(user.totp_enabled)})


@bp.post("/auth/2fa/setup")
@login_required
def twofa_setup(user):
    from crypto.auth_core import new_totp_secret, totp_uri
    if user.totp_enabled:
        raise ApiError("Two-factor authentication is already enabled", 400)
    user.totp_secret = new_totp_secret()
    db.session.commit()
    return ok({"secret": user.totp_secret, "uri": totp_uri(user.totp_secret, user.email)})


@bp.post("/auth/2fa/enable")
@login_required
def twofa_enable(user):
    from crypto.auth_core import verify_totp, log_event
    if not user.totp_secret:
        raise ApiError("Start the setup first", 400)
    if not verify_totp(user.totp_secret, body().get("code")):
        raise ApiError("That code is not valid. Check your device clock and try again.", 400)
    user.totp_enabled = True
    db.session.commit()
    log_event(user, "2fa_enabled", True)
    return ok({"enabled": True})


@bp.post("/auth/2fa/disable")
@login_required
def twofa_disable(user):
    from crypto.auth_core import verify_totp, log_event
    p = body()
    if not user.check_password(p.get("password")):
        raise ApiError("Password is incorrect", 400)
    if user.totp_enabled and not verify_totp(user.totp_secret, p.get("code")):
        raise ApiError("That code is not valid", 400)
    user.totp_enabled = False
    user.totp_secret = None
    db.session.commit()
    log_event(user, "2fa_disabled", True)
    return ok({"enabled": False})


@bp.get("/auth/security-log")
@login_required
def security_log(user):
    rows = LoginEvent.query.filter_by(user_id=user.id).order_by(LoginEvent.id.desc()).limit(100).all()
    return ok([r.serialize() for r in rows])


@bp.post("/auth/admin")
def auth_admin():
    from crypto.auth import _admin_login
    p = body()
    resp = _admin_login({"email": "admin", "password": p.get("password")})
    return resp


@bp.get("/auth/admin")
def auth_admin_status():
    return ok({"admin": bool(session.get("admin"))})


@bp.post("/auth/admin/logout")
def auth_admin_logout():
    session.pop("admin", None)
    return ok()


# =============================================================================
# market data (public)
# =============================================================================

def _ex():
    return request.args.get("exchange") or market.default_exchange()


@bp.get("/market/exchanges")
def market_exchanges():
    rows = [{"id": e.exchange, "name": e.exchange.upper() if len(e.exchange) <= 4 else e.exchange.capitalize(), "active": True}
            for e in Exchange2.query.filter(Exchange2.isActive == True).all()]
    rows.insert(0, {"id": PAPER_EXCHANGE, "name": "Paper Trading", "active": True, "paper": True})
    return ok(rows)


@bp.get("/market/tickers")
def market_tickers():
    quote = (request.args.get("quote") or "USDT").upper()
    limit = min(int(request.args.get("limit", 100)), 2000)
    q = (request.args.get("q") or "").upper().strip()
    rows = market.tickers(_ex(), quote)
    if q:
        rows = [r for r in rows if q in r["symbol"]]
    return ok(rows[:limit])


@bp.get("/market/ticker")
def market_ticker():
    return ok(market.ticker(_ex(), request.args.get("symbol") or "BTC/USDT"))


@bp.get("/market/ohlcv")
def market_ohlcv():
    tf = request.args.get("timeframe") or "1h"
    limit = int(request.args.get("limit", 300))
    rows = market.ohlcv(_ex(), request.args.get("symbol") or "BTC/USDT", tf, limit)
    return ok(rows, timeframe=tf)


@bp.get("/market/orderbook")
def market_orderbook():
    return ok(market.order_book(_ex(), request.args.get("symbol") or "BTC/USDT", min(int(request.args.get("limit", 20)), 100)))


@bp.get("/market/trades")
def market_trades():
    return ok(market.trades(_ex(), request.args.get("symbol") or "BTC/USDT", min(int(request.args.get("limit", 30)), 200)))


@bp.get("/market/symbols")
def market_symbols():
    quote = request.args.get("quote")
    q = (request.args.get("q") or "").upper().strip()
    rows = market.symbols(_ex(), quote)
    if q:
        rows = [s for s in rows if q in s]
    return ok(rows[: min(int(request.args.get("limit", 500)), 5000)])


@bp.get("/market/overview")
def market_overview():
    return ok(market.overview(_ex(), (request.args.get("quote") or "USDT").upper(), min(int(request.args.get("top", 10)), 50)))


@bp.get("/market/analysis")
def market_analysis():
    from crypto import ta
    a = ta.analysis(_ex(), request.args.get("symbol") or "BTC/USDT", request.args.get("interval") or "1h")
    return ok({k: a[k] for k in ("symbol", "interval", "price", "summary", "oscillators", "moving_averages", "indicators")})


@bp.get("/market/signals")
def market_signals():
    from crypto import ta
    ex, interval = _ex(), request.args.get("interval") or "1h"
    top = min(int(request.args.get("top", 20)), 40)
    key = (ex, interval, top)
    hit = _signals_cache.get(key)
    if hit is None:
        symbols = [t["symbol"] for t in market.tickers(ex, "USDT", top)]

        def one(sym):
            try:
                a = ta.analysis(ex, sym, interval)
                return {"symbol": sym, "price": a["price"], **a["summary"],
                        "oscillators": a["oscillators"]["RECOMMENDATION"], "moving_averages": a["moving_averages"]["RECOMMENDATION"],
                        "rsi": a["indicators"].get("RSI")}
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            hit = _signals_cache.set(key, [r for r in pool.map(one, symbols) if r])
    return ok(hit)


# =============================================================================
# portfolio & analytics
# =============================================================================

@bp.get("/portfolio")
@login_required
def portfolio(user):
    from crypto import analytics
    data = analytics.balances(user, refresh=request.args.get("refresh") == "1")
    data["stats"] = {k: getattr(user, k) or 0 for k in (
        "balance_usd", "balance_btc", "profit_daily_usd", "profit_daily_percent_usd", "profit_monthly_usd",
        "profit_monthly_percent_usd", "profit_overall_usd", "profit_daily_btc", "profit_monthly_btc",
        "profit_overall_btc", "sharpe_ratio", "sortino_ratio", "deviation")}
    return ok(data)


@bp.get("/portfolio/history")
@login_required
def portfolio_history(user):
    from crypto import analytics
    return ok(analytics.history(user, min(int(request.args.get("days", 30)), 3650)))


@bp.get("/portfolio/performance")
@login_required
def portfolio_performance(user):
    from crypto import analytics
    return ok(analytics.performance(user, min(int(request.args.get("days", 90)), 3650)))


@bp.post("/portfolio/snapshot")
@login_required
def portfolio_snapshot(user):
    from crypto import analytics
    user.update_balance()
    return ok(analytics.balances(user, refresh=True))


# =============================================================================
# paper trading
# =============================================================================

def _paper_summary(user):
    from crypto import paper
    acc = PaperAccount.query.filter_by(user_id=user.id).first()
    connected = user.exchanges.filter(Exchange.name == PAPER_EXCHANGE).first() is not None
    if acc is None:
        return {"connected": connected, "account": None}
    ex = paper.PaperExchange(user.id)
    bal = ex.fetch_balance()
    value = 0.0
    assets = []
    for cur, total in bal["total"].items():
        if not total:
            continue
        price = market.usd_price(None, cur)
        value += total * price
        assets.append({"currency": cur, "free": bal["free"][cur], "used": bal["used"][cur], "total": total,
                       "price": price, "value": total * price})
    assets.sort(key=lambda a: a["value"], reverse=True)
    start = acc.starting_balance or paper.DEFAULT_START
    return {"connected": connected, "account": {
        "starting_balance": start, "equity": value, "pnl": value - start, "pnl_pct": (value - start) / start * 100 if start else 0,
        "fee_rate": acc.fee_rate, "assets": assets, "reset_at": acc.reset_at.isoformat() if acc.reset_at else None,
        "open_orders": PaperOrder.query.filter_by(user_id=user.id, status="open").count(),
    }}


@bp.get("/paper")
@login_required
def paper_account(user):
    return ok(_paper_summary(user))


@bp.post("/paper/connect")
@login_required
def paper_connect(user):
    from crypto.exchanges import connect_paper
    connect_paper(user)
    return ok(_paper_summary(user), message="Paper trading account connected")


@bp.post("/paper/reset")
@login_required
def paper_reset(user):
    from crypto import paper
    start = _float(body().get("starting_balance", paper.DEFAULT_START), "starting_balance")
    paper.reset_account(user.id, start)
    return ok(_paper_summary(user), message="Paper account reset")


@bp.get("/paper/orders")
@login_required
def paper_orders(user):
    from crypto import paper
    status = request.args.get("status")
    ex = paper.PaperExchange(user.id)
    rows = ex.fetch_orders(params={}) if not status else ex._list(status, request.args.get("symbol"), 500)
    return ok(rows)


# =============================================================================
# watchlist
# =============================================================================

@bp.get("/watchlist")
@login_required
def watchlist(user):
    items = WatchlistItem.query.filter_by(user_id=user.id).order_by(WatchlistItem.position.asc(), WatchlistItem.id.asc()).all()
    out = []
    for it in items:
        row = it.serialize()
        try:
            row["ticker"] = market.ticker(it.exchange, it.symbol)
        except Exception:
            row["ticker"] = None
        out.append(row)
    return ok(out)


@bp.post("/watchlist")
@login_required
def watchlist_add(user):
    p = body()
    need(p, "symbol")
    sym = market.normalize_symbol(p["symbol"])
    ex = market.normalize_exchange(p.get("exchange"))
    existing = WatchlistItem.query.filter_by(user_id=user.id, exchange=ex, symbol=sym).first()
    if existing:
        return ok(existing.serialize(), message="Already in your watchlist")
    if WatchlistItem.query.filter_by(user_id=user.id).count() >= 100:
        raise ApiError("Watchlist is limited to 100 symbols", 400)
    pos = (db.session.query(db.func.max(WatchlistItem.position)).filter_by(user_id=user.id).scalar() or 0) + 1
    item = WatchlistItem(user_id=user.id, exchange=ex, symbol=sym, note=str(p.get("note") or "")[:255] or None, position=pos)
    db.session.add(item)
    db.session.commit()
    return ok(item.serialize(), 201)


@bp.delete("/watchlist/<int:item_id>")
@login_required
def watchlist_remove(user, item_id):
    item = WatchlistItem.query.filter_by(id=item_id, user_id=user.id).first()
    if item is None:
        raise ApiError("Not found", 404)
    db.session.delete(item)
    db.session.commit()
    return ok()


@bp.put("/watchlist/order")
@login_required
def watchlist_reorder(user):
    ids = body().get("ids") or []
    items = {i.id: i for i in WatchlistItem.query.filter_by(user_id=user.id).all()}
    for pos, item_id in enumerate(ids):
        if item_id in items:
            items[item_id].position = pos
    db.session.commit()
    return ok()


# =============================================================================
# price alerts
# =============================================================================

@bp.get("/alerts")
@login_required
def alerts_list(user):
    rows = PriceAlert.query.filter_by(user_id=user.id).order_by(PriceAlert.active.desc(), PriceAlert.id.desc()).all()
    return ok([a.serialize() for a in rows])


@bp.post("/alerts")
@login_required
def alerts_create(user):
    from crypto.alerts import CONDITIONS
    p = body()
    need(p, "symbol", "target")
    condition = str(p.get("condition") or "above")
    if condition not in CONDITIONS:
        raise ApiError(f"condition must be one of {', '.join(CONDITIONS)}", 400)
    target = _float(p["target"], "target")
    if target <= 0:
        raise ApiError("target must be positive", 400)
    if PriceAlert.query.filter_by(user_id=user.id, active=True).count() >= 100:
        raise ApiError("You can have up to 100 active alerts", 400)
    sym = market.normalize_symbol(p["symbol"])
    ex = market.normalize_exchange(p.get("exchange"))
    ref = market.price(ex, sym)
    alert = PriceAlert(user_id=user.id, exchange=ex, symbol=sym, condition=condition, target=target,
                       reference_price=ref, note=str(p.get("note") or "")[:255] or None, repeat=bool(p.get("repeat")),
                       active=True)
    db.session.add(alert)
    db.session.commit()
    return ok(alert.serialize(), 201)


@bp.patch("/alerts/<int:alert_id>")
@login_required
def alerts_update(user, alert_id):
    alert = PriceAlert.query.filter_by(id=alert_id, user_id=user.id).first()
    if alert is None:
        raise ApiError("Not found", 404)
    p = body()
    if "active" in p:
        alert.active = bool(p["active"])
        if alert.active:
            alert.last_price = None
            alert.reference_price = market.price(alert.exchange, alert.symbol)
    if "target" in p:
        alert.target = _float(p["target"], "target")
    if "note" in p:
        alert.note = str(p["note"] or "")[:255] or None
    if "repeat" in p:
        alert.repeat = bool(p["repeat"])
    db.session.commit()
    return ok(alert.serialize())


@bp.delete("/alerts/<int:alert_id>")
@login_required
def alerts_delete(user, alert_id):
    alert = PriceAlert.query.filter_by(id=alert_id, user_id=user.id).first()
    if alert is None:
        raise ApiError("Not found", 404)
    db.session.delete(alert)
    db.session.commit()
    return ok()


# =============================================================================
# trading journal
# =============================================================================

def _journal_apply(entry, p):
    if "title" in p:
        entry.title = str(p.get("title") or "").strip()[:160]
    for key in ("body", "symbol", "side", "mood"):
        if key in p:
            val = p.get(key)
            setattr(entry, key, (str(val).strip() or None) if val is not None else None)
    if entry.symbol:
        entry.symbol = market.normalize_symbol(entry.symbol)
    for key in ("entry_price", "exit_price", "amount"):
        if key in p:
            val = p.get(key)
            setattr(entry, key, _float(val, key) if val not in (None, "") else None)
    if "tags" in p:
        tags = p.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        entry.tags = [str(t)[:32] for t in tags if str(t).strip()][:12]
    if not entry.title:
        raise ApiError("Title is required", 400)


@bp.get("/journal")
@login_required
def journal_list(user):
    q = JournalEntry.query.filter_by(user_id=user.id)
    text = (request.args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(JournalEntry.title.ilike(like), JournalEntry.body.ilike(like), JournalEntry.symbol.ilike(like)))
    rows = q.order_by(JournalEntry.created_at.desc()).limit(500).all()
    tag = request.args.get("tag")
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    return ok([r.serialize() for r in rows])


@bp.post("/journal")
@login_required
def journal_create(user):
    entry = JournalEntry(user_id=user.id, title="")
    _journal_apply(entry, body())
    db.session.add(entry)
    db.session.commit()
    return ok(entry.serialize(), 201)


@bp.put("/journal/<int:entry_id>")
@login_required
def journal_update(user, entry_id):
    entry = JournalEntry.query.filter_by(id=entry_id, user_id=user.id).first()
    if entry is None:
        raise ApiError("Not found", 404)
    _journal_apply(entry, body())
    db.session.commit()
    return ok(entry.serialize())


@bp.delete("/journal/<int:entry_id>")
@login_required
def journal_delete(user, entry_id):
    entry = JournalEntry.query.filter_by(id=entry_id, user_id=user.id).first()
    if entry is None:
        raise ApiError("Not found", 404)
    db.session.delete(entry)
    db.session.commit()
    return ok()


@bp.get("/journal/stats")
@login_required
def journal_stats(user):
    rows = JournalEntry.query.filter_by(user_id=user.id).all()
    closed = [r for r in rows if r.pnl is not None]
    tags = {}
    for r in closed:
        for t in r.tags or []:
            agg = tags.setdefault(t, {"tag": t, "trades": 0, "pnl": 0.0})
            agg["trades"] += 1
            agg["pnl"] += r.pnl
    wins = [r for r in closed if r.pnl > 0]
    return ok({"entries": len(rows), "closed": len(closed), "pnl": sum(r.pnl for r in closed),
               "win_rate": len(wins) / len(closed) * 100 if closed else 0,
               "avg_win": sum(r.pnl for r in wins) / len(wins) if wins else 0,
               "avg_loss": sum(r.pnl for r in closed if r.pnl <= 0) / max(1, len(closed) - len(wins)) if closed else 0,
               "by_tag": sorted(tags.values(), key=lambda x: x["pnl"], reverse=True)})


# =============================================================================
# backtesting
# =============================================================================

@bp.post("/backtest")
def backtest_run():
    from crypto import backtest
    try:
        params = backtest.params_from(body())
    except (TypeError, ValueError) as e:
        raise ApiError(f"Invalid parameters: {e}", 400)
    return ok(backtest.run(params))


@bp.post("/backtest/optimize")
def backtest_optimize():
    """Grid-search DCA parameters, e.g. {"grid": {"take_profit": [1, 1.5, 2],
    "deviation": {"min": 1, "max": 3, "step": 0.5}}, "metric": "return_pct"}."""
    from crypto import backtest
    p = body()
    grid = p.get("grid")
    if not isinstance(grid, dict) or not grid:
        raise ApiError("grid must map parameter names to value lists or {min,max,step} ranges", 400)
    try:
        base = backtest.params_from(p)
        result = backtest.optimize(base, grid, p.get("metric") or "return_pct", min(int(p.get("top", 10)), 50))
    except (TypeError, ValueError, KeyError) as e:
        raise ApiError(f"Invalid parameters: {e}", 400)
    return ok(result)


# =============================================================================
# market context beside ccxt (CoinGecko, alternative.me, DefiLlama, ccxt.pro)
# =============================================================================

@bp.get("/insights")
def insights_snapshot():
    from crypto import datasources
    return ok(datasources.snapshot())


@bp.get("/insights/global")
def insights_global():
    from crypto import datasources
    return ok(datasources.global_market())


@bp.get("/insights/coins")
def insights_coins():
    from crypto import datasources
    return ok(datasources.coins(request.args.get("limit", 100)))


@bp.get("/insights/trending")
def insights_trending():
    from crypto import datasources
    return ok(datasources.trending())


@bp.get("/insights/fear-greed")
def insights_fear_greed():
    from crypto import datasources
    return ok(datasources.fear_greed(request.args.get("limit", 30)))


@bp.get("/insights/defi")
def insights_defi():
    from crypto import datasources
    return ok(datasources.defi())


@bp.get("/market/stream")
def market_stream_status():
    from crypto import stream
    return ok(stream.status())


# =============================================================================
# bots (helpers for the new UI; create/edit/toggle/delete stay on /api/v1)
# =============================================================================

BOT_TEMPLATES = [
    {"id": "conservative", "name": "Conservative DCA", "description": "Small steps, wide safety net, modest target.",
     "tp_percent": 1.2, "safety_orders_count": 8, "safety_orders_count_max_active": 3, "safety_orders_deviation": 1.5,
     "safety_orders_deviation_scale": 1.2, "safety_orders_size_scale": 1.3, "stop_loss": False, "stop_loss_price_percent": 0},
    {"id": "balanced", "name": "Balanced DCA", "description": "The classic setup for liquid majors.",
     "tp_percent": 1.8, "safety_orders_count": 6, "safety_orders_count_max_active": 2, "safety_orders_deviation": 2.0,
     "safety_orders_deviation_scale": 1.1, "safety_orders_size_scale": 1.5, "stop_loss": False, "stop_loss_price_percent": 0},
    {"id": "aggressive", "name": "Aggressive scalper", "description": "Quick targets with a hard stop.",
     "tp_percent": 0.8, "safety_orders_count": 3, "safety_orders_count_max_active": 1, "safety_orders_deviation": 1.0,
     "safety_orders_deviation_scale": 1.0, "safety_orders_size_scale": 2.0, "stop_loss": True, "stop_loss_price_percent": 4},
    {"id": "trend", "name": "Trend follower", "description": "No averaging down, trailing take profit.",
     "tp_percent": 3.0, "safety_orders_count": 0, "safety_orders_count_max_active": 0, "safety_orders_deviation": 0,
     "safety_orders_deviation_scale": 1.0, "safety_orders_size_scale": 1.0, "stop_loss": True, "stop_loss_price_percent": 3,
     "trailing_take_profit": True, "trailing_deviation": 0.8},
]


@bp.get("/bots/templates")
def bot_templates():
    return ok(BOT_TEMPLATES)


@bp.post("/bots/preview")
def bot_preview():
    """Safety-order ladder and capital requirement for a draft configuration."""
    p = body()
    price = _float(p.get("price") or market.price(p.get("exchange"), p.get("symbol") or "BTC/USDT"), "price")
    base = _float(p.get("amount", 0), "amount")
    so_size = _float(p.get("safety_orders_size", 0), "safety_orders_size")
    count = int(_float(p.get("safety_orders_count", 0), "safety_orders_count"))
    dev = _float(p.get("safety_orders_deviation", 0), "safety_orders_deviation")
    step = _float(p.get("safety_orders_deviation_scale", 1), "safety_orders_deviation_scale")
    vol = _float(p.get("safety_orders_size_scale", 1), "safety_orders_size_scale")
    tp = _float(p.get("tp_percent", 0), "tp_percent")
    long = str(p.get("strategy", "long")).lower() != "short"
    count = max(0, min(count, 50))
    rows, cum, total_qty, total_cost = [], 0.0, base / price if price else 0, base
    for i in range(count):
        cum += dev * (step ** i)
        level = price * (1 - cum / 100) if long else price * (1 + cum / 100)
        size = so_size * (vol ** i)
        qty = size / level if level else 0
        total_qty += qty
        total_cost += size
        avg = total_cost / total_qty if total_qty else 0
        rows.append({"index": i + 1, "deviation": cum, "price": level, "size": size, "total_invested": total_cost,
                     "average": avg, "tp_price": avg * (1 + tp / 100) if long else avg * (1 - tp / 100)})
    return ok({"price": price, "levels": rows, "max_capital": total_cost,
               "max_deviation": cum, "first_tp": price * (1 + tp / 100) if long else price * (1 - tp / 100)})


@bp.get("/bots")
@login_required
def bots_list(user):
    rows = [b.serialize() for b in user.bots.filter(Bot.is_hidden == False).order_by(Bot.id.desc()).all()]
    active = [b for b in rows if b["isActive"]]
    return ok(rows, summary={"total": len(rows), "active": len(active), "in_deal": sum(1 for b in rows if b["deal_started"]),
                             "profit": sum(b["total_profit"] for b in rows), "deals": sum(b["total_trades"] for b in rows),
                             "limit": user.subType.max_bots if user.subType else None})


@bp.get("/bots/<int:bot_id>")
@login_required
def bots_get(user, bot_id):
    bot = Bot.query.filter_by(id=bot_id, owner_id=user.id).first()
    if bot is None:
        raise ApiError("Bot not found", 404)
    data = bot.serialize()
    data.update({k: getattr(bot, k) for k in (
        "safety_orders_size", "safety_orders_size_scale", "safety_orders_deviation", "safety_orders_deviation_scale",
        "safety_orders_count_max_active", "max_price", "min_price", "min_volume", "min_profit", "min_profit_type",
        "min_profit_percent", "close_deal_action", "timeout", "timeout_type", "Close_deal_after_timeout",
        "stop_loss_time_out", "stop_loss_time_out_time", "amount_type", "safety_orders_size_type")})
    data["safety_orders"] = [{"id": s.id, "isOpened": s.isOpened, "isClosed": s.isClosed, "isFilled": s.isFilled,
                              "orderId": s.orderId, "amount": s.amount, "price": s.price}
                             for s in bot.safetyOrders.order_by(SafetyOrder.id.asc()).all()]
    data["transactions"] = [t.serialize() for t in bot.transactions.order_by(Transaction.id.desc()).limit(200).all()]
    return ok(data)


@bp.post("/bots/<int:bot_id>/duplicate")
@login_required
def bots_duplicate(user, bot_id):
    bot = Bot.query.filter_by(id=bot_id, owner_id=user.id).first()
    if bot is None:
        raise ApiError("Bot not found", 404)
    limit = user.subType.max_bots if user.subType else None
    if limit and limit <= user.bots.filter(Bot.is_hidden == False, Bot.isActive == True).count():
        raise ApiError("You have reached your maximum number of bots. Upgrade your subscription to create more bots", 403)
    skip = {"id", "owner", "owner_id", "safetyOrders", "transactions", "created_at", "updated_at", "deal_started",
            "take_profit", "total_trades", "total_profit", "last_price", "sell_price", "price_now", "buy_price",
            "deal_start_price", "tp_price", "safety_orders_count_active", "last_error", "stop_loss_triggered_at",
            "last_open_trade_time", "last_total_profit_time"}
    from sqlalchemy import inspect as sa_inspect
    clone = Bot()
    for prop in sa_inspect(Bot).column_attrs:   # attribute names (Bot.id maps to column bot_id)
        if prop.key not in skip:
            setattr(clone, prop.key, getattr(bot, prop.key))
    clone.owner_id = user.id
    clone.name = f"{bot.name} (copy)"[:120]
    clone.isActive = False
    clone.is_hidden = False
    clone.units = bot.amount
    clone.total_volume = bot.amount
    clone.safety_orders_count_active = 0
    db.session.add(clone)
    db.session.flush()
    for _ in range(int(bot.safety_orders_count or 0)):
        db.session.add(SafetyOrder(owner_id=clone.id))
    db.session.commit()
    return ok(clone.serialize(), 201)


# =============================================================================
# transactions & exports
# =============================================================================

def _tx_query(user):
    q = Transaction.query.filter_by(user_id=user.id)
    for key in ("symbol", "type", "exchange"):
        if request.args.get(key):
            q = q.filter(getattr(Transaction, key) == request.args[key])
    if request.args.get("bot_id"):
        q = q.filter(Transaction.bot_id == int(request.args["bot_id"]))
    if request.args.get("sma_id"):
        q = q.filter(Transaction.sma_id == int(request.args["sma_id"]))
    return q.order_by(Transaction.id.desc())


@bp.get("/transactions")
@login_required
def transactions_list(user):
    limit, offset = page_args(50, 500)
    q = _tx_query(user)
    return ok([t.serialize() for t in q.offset(offset).limit(limit).all()], total=q.count(), limit=limit, offset=offset)


def _csv(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        # neutralise spreadsheet formula injection
        w.writerow([("'" + v) if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v for v in r])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/export/transactions.csv")
@login_required
def export_transactions(user):
    rows = _tx_query(user).limit(100000).all()
    return _csv("pulsetrade-transactions.csv",
                ["id", "date", "exchange", "symbol", "side", "amount", "price", "value_usd", "status", "error", "bot_id", "smart_trade_id"],
                [[t.id, t.created_at.isoformat() if t.created_at else "", t.exchange, t.symbol, t.type, t.amount, t.price,
                  t.value, "ok" if t.status else "failed", (t.err_msg or "") if isinstance(t.err_msg, str) else "", t.bot_id, t.sma_id]
                 for t in rows])


@bp.get("/export/journal.csv")
@login_required
def export_journal(user):
    rows = JournalEntry.query.filter_by(user_id=user.id).order_by(JournalEntry.created_at.desc()).all()
    return _csv("pulsetrade-journal.csv",
                ["date", "title", "symbol", "side", "entry", "exit", "amount", "pnl", "tags", "mood", "notes"],
                [[r.created_at.isoformat() if r.created_at else "", r.title, r.symbol, r.side, r.entry_price, r.exit_price,
                  r.amount, r.pnl, ",".join(r.tags or []), r.mood, r.body] for r in rows])


# =============================================================================
# notifications & channels
# =============================================================================

@bp.get("/notifications")
@login_required
def notifications_list(user):
    limit, offset = page_args(50, 500)
    q = user.notifications
    if request.args.get("unread") == "1":
        q = q.filter(Notification.read == False)
    rows = q.order_by(Notification.id.desc()).offset(offset).limit(limit).all()
    return ok([n.serialize() for n in rows], unread=user.notifications.filter(Notification.read == False).count())


@bp.post("/notifications/read")
@login_required
def notifications_read(user):
    ids = body().get("ids")
    q = user.notifications.filter(Notification.read == False)
    if ids:
        q = q.filter(Notification.id.in_([int(i) for i in ids]))
    count = q.update({Notification.read: True}, synchronize_session=False)
    db.session.commit()
    return ok({"updated": count})


@bp.delete("/notifications/<int:note_id>")
@login_required
def notifications_delete(user, note_id):
    n = user.notifications.filter(Notification.id == note_id).first()
    if n is None:
        raise ApiError("Not found", 404)
    db.session.delete(n)
    db.session.commit()
    return ok()


def _channels(user):
    ch = user.get_preferences().get("channels") or {}
    return ok({"webhook_url": ch.get("webhook_url") or "", "webhook_enabled": bool(ch.get("webhook_enabled")),
               "telegram_chat_id": ch.get("telegram_chat_id") or "", "telegram_enabled": bool(ch.get("telegram_enabled")),
               "telegram_available": bool(os.environ.get("TELEGRAM_BOT_TOKEN"))})


@bp.get("/notifications/channels")
@login_required
def channels_get(user):
    return _channels(user)


@bp.put("/notifications/channels")
@login_required
def channels_put(user):
    from crypto.notify import valid_webhook
    p = body()
    url = str(p.get("webhook_url") or "").strip()
    if url and not valid_webhook(url):
        raise ApiError("Webhook must be an https:// Discord or Slack webhook URL", 400)
    chat = str(p.get("telegram_chat_id") or "").strip()
    if chat and not chat.lstrip("-").isdigit():
        raise ApiError("Telegram chat id must be numeric", 400)
    prefs = user.get_preferences()
    prefs["channels"] = {"webhook_url": url, "webhook_enabled": bool(p.get("webhook_enabled")) and bool(url),
                         "telegram_chat_id": chat, "telegram_enabled": bool(p.get("telegram_enabled")) and bool(chat)}
    user.preferences = prefs
    db.session.commit()
    return _channels(user)


@bp.post("/notifications/test")
@login_required
def channels_test(user):
    from crypto.notify import send_notification
    send_notification("This is a test notification from PulseTrade 👋***system", user.id)
    return ok(message="Test notification sent")


# =============================================================================
# wallet helpers
# =============================================================================

@bp.get("/wallet/transfers")
@login_required
def wallet_transfers(user):
    from crypto.functions import connectExchange
    ex = connectExchange(request.args.get("exchange"))
    try:
        has = ex.describe()["has"].get("fetchTransfers")
        rows = ex.fetch_transfers() if has else []
    except Exception as e:
        raise ApiError(f"Transfers unavailable: {e}", 502)
    return ok(rows)


@bp.get("/wallet/capabilities")
@login_required
def wallet_capabilities(user):
    from crypto.functions import connectExchange
    ex = connectExchange(request.args.get("exchange"))
    has = ex.describe().get("has", {})
    keys = ("fetchDepositAddress", "withdraw", "transfer", "fetchDeposits", "fetchWithdrawals", "fetchLedger",
            "fetchPositions", "fetchTransfers", "fetchOpenOrders", "fetchClosedOrders", "createOrder")
    return ok({k: bool(has.get(k)) for k in keys})


# =============================================================================
# plans & billing
# =============================================================================

@bp.get("/plans")
def plans():
    return ok([s.serialize() for s in Subscription.query.order_by(Subscription.price.asc(), Subscription.id.asc()).all()])


@bp.get("/billing")
@login_required
def billing(user):
    from crypto import subscription_ok
    plan = user.subType
    expires = user.sub_date + timedelta(days=30) if (user.sub_date and plan and plan.type != "free") else None
    return ok({"plan": plan.serialize() if plan else None, "sub_date": user.sub_date.isoformat() if user.sub_date else None,
               "expires": expires.isoformat() if expires else None, "in_good_standing": subscription_ok(user),
               "usage": {"bots": user.bots.filter(Bot.is_hidden == False, Bot.isActive == True).count(),
                         "smart_trades": SmartTrade.query.filter_by(user_id=user.id, isActive=True, is_hidden=False).count()}})


# =============================================================================
# support & knowledge base
# =============================================================================

@bp.get("/support/tickets")
@login_required
def support_tickets(user):
    return ok([t.serialize() for t in Ticket.query.filter_by(user_id=user.id).order_by(Ticket.id.desc()).all()])


@bp.get("/kb/categories")
def kb_categories():
    cats = Category.query.order_by(Category.id.asc()).all()
    out = []
    for c in cats:
        row = c.serialize(with_posts=False)
        row["post_count"] = Post.query.filter_by(category_id=c.id).count()
        out.append(row)
    return ok(out)


@bp.get("/kb/posts")
def kb_posts():
    q = Post.query
    if request.args.get("category"):
        q = q.filter(Post.category_id == int(request.args["category"]))
    if request.args.get("lang"):
        q = q.filter(Post.lang == request.args["lang"])
    text = (request.args.get("q") or "").strip()
    if text:
        q = q.filter(or_(Post.title.ilike(f"%{text}%"), Post.content.ilike(f"%{text}%")))
    limit, offset = page_args(30, 200)
    rows = q.order_by(Post.created_at.desc()).offset(offset).limit(limit).all()
    return ok([{**p.serialize(), "content": None, "excerpt": _excerpt(p.content)} for p in rows])


def _excerpt(html, n=220):
    import re
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


@bp.get("/kb/posts/<int:post_id>")
def kb_post(post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        raise ApiError("Post not found", 404)
    post.views = (post.views or 0) + 1
    db.session.commit()
    return ok(post.serialize())


from crypto import api_v2_admin  # noqa: E402,F401  (registers admin routes on bp)

app.register_blueprint(bp)
