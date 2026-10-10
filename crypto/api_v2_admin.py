"""Admin endpoints of API v2 (session-based admin login, same as /admin)."""
import os
from datetime import datetime, timedelta

import ccxt
from flask import request
from sqlalchemy import or_

import crypto
from crypto import db, market
from crypto.api_v2 import bp, ok, body, admin_only, page_args
from crypto.errors import ApiError
from crypto.models import (Bot, BotCount, Exchange2, Message, Pair, SmartTrade, Subscription, Ticket, Transaction,
                           TransactionHistory, User, UserCount, PaperAccount, PriceAlert)


@bp.get("/admin/stats")
@admin_only
def admin_stats():
    since = datetime.utcnow() - timedelta(days=1)
    volume_24h = db.session.query(db.func.coalesce(db.func.sum(Transaction.value), 0)).filter(Transaction.created_at > since).scalar() or 0
    open_tickets = 0
    for t in Ticket.query.filter(Ticket.status != "closed").all():
        last = t.messages.order_by(Message.id.desc()).first()
        if last is not None and not last.is_admin:
            open_tickets += 1
    plans = [{"id": s.id, "type": s.type, "users": User.query.filter(User.subType_id == s.id).count()}
             for s in Subscription.query.all()]
    new_7d = User.query.filter(User.created_at >= datetime.utcnow() - timedelta(days=7)).count()
    return ok({
        "users": User.query.count(), "new_users_7d": new_7d,
        "bots_active": Bot.query.filter(Bot.isActive == True, Bot.is_hidden == False).count(),
        "bots_total": Bot.query.filter(Bot.is_hidden == False).count(),
        "smart_trades_active": SmartTrade.query.filter(SmartTrade.isActive == True).count(),
        "paper_accounts": PaperAccount.query.count(), "alerts_active": PriceAlert.query.filter_by(active=True).count(),
        "transactions": Transaction.query.count(),
        "buys": Transaction.query.filter(Transaction.type == "buy").count(),
        "sells": Transaction.query.filter(Transaction.type == "sell").count(),
        "volume_24h": round(float(volume_24h), 2), "open_tickets": open_tickets, "plans": plans,
        "users_history": [u.serialize() for u in UserCount.query.order_by(UserCount.id.asc()).limit(365).all()],
        "bots_history": [b.serialize() for b in BotCount.query.order_by(BotCount.id.asc()).limit(365).all()],
        "volume_history": [t.serialize() for t in TransactionHistory.query.order_by(TransactionHistory.id.asc()).limit(365).all()],
    })


@bp.get("/admin/users")
@admin_only
def admin_users():
    limit, offset = page_args(50, 500)
    q = User.query
    text = (request.args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        q = q.filter(or_(User.email.ilike(like), User.firstName.ilike(like), User.lastName.ilike(like)))
    total = q.count()
    rows = q.order_by(User.id.desc()).offset(offset).limit(limit).all()
    out = []
    for u in rows:
        d = u.serialize()
        d["bots"] = u.bots.filter(Bot.is_hidden == False).count()
        d["exchanges"] = [e.name for e in u.exchanges.all()]
        out.append(d)
    return ok(out, total=total, limit=limit, offset=offset)


@bp.patch("/admin/users/<int:user_id>")
@admin_only
def admin_user_update(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError("User not found", 404)
    p = body()
    if "sub_type_id" in p:
        plan = db.session.get(Subscription, int(p["sub_type_id"]))
        if plan is None:
            raise ApiError("Plan not found", 404)
        user.subType = plan
        user.sub_date = datetime.utcnow()
    if "is_verified" in p:
        user.is_verified = bool(p["is_verified"])
    if "ip_check" in p:
        user.ip_check = bool(p["ip_check"])
    db.session.commit()
    return ok(user.serialize())


@bp.get("/admin/transactions")
@admin_only
def admin_transactions():
    limit, offset = page_args(100, 1000)
    q = Transaction.query
    if request.args.get("exchange"):
        q = q.filter(Transaction.exchange == request.args["exchange"])
    if request.args.get("type"):
        q = q.filter(Transaction.type == request.args["type"])
    total = q.count()
    rows = q.order_by(Transaction.id.desc()).offset(offset).limit(limit).all()
    emails = {u.id: u.email for u in User.query.filter(User.id.in_({t.user_id for t in rows})).all()} if rows else {}
    return ok([{**t.serialize(), "user_email": emails.get(t.user_id)} for t in rows], total=total)


@bp.get("/admin/exchanges")
@admin_only
def admin_exchanges():
    from crypto.auth import exchange_capabilities, REQUIRED_CAPS
    rows = {e.exchange: e for e in Exchange2.query.all()}
    show_all = request.args.get("all") == "1"
    names = sorted(set(rows) | (set(ccxt.exchanges) if show_all else set()))
    out = []
    for name in names:
        has = exchange_capabilities(name) if (name in rows or show_all) else None
        out.append({"exchange": name, "isActive": bool(rows[name].isActive) if name in rows else False,
                    "listed": name in rows, "supported": bool(has and all(has.get(k) for k in REQUIRED_CAPS)),
                    "testnet": False})
    return ok(out)


@bp.get("/admin/pairs")
@admin_only
def admin_pairs():
    q = Pair.query
    text = (request.args.get("q") or "").upper().strip()
    if text:
        q = q.filter(Pair.pair.ilike(f"%{text}%"))
    return ok([p.serialize() for p in q.order_by(Pair.pair.asc()).limit(2000).all()])


@bp.post("/admin/pairs/import")
@admin_only
def admin_pairs_import():
    """Add every spot pair of an exchange to the indicator pair catalogue."""
    ex = body().get("exchange") or market.default_exchange()
    quote = (body().get("quote") or "USDT").upper()
    existing = {p.pair for p in Pair.query.all()}
    added = 0
    for sym in market.symbols(ex, quote):
        if sym not in existing:
            db.session.add(Pair(pair=sym, isActive=False))
            added += 1
    db.session.commit()
    return ok({"added": added})


@bp.get("/admin/system")
@admin_only
def admin_system():
    from crypto.auth_core import mail_configured
    import stripe
    from sqlalchemy import inspect
    return ok({
        "engine": crypto.engine_mode(), "market_data": market.mode(), "reference_exchange": market.default_exchange(),
        "db_dialect": db.engine.dialect.name, "tables": len(inspect(db.engine).get_table_names()),
        "mail_configured": mail_configured(), "stripe_configured": bool(stripe.api_key),
        "tap_configured": bool(os.environ.get("TAP_API_KEY")), "cron_secret": bool(os.environ.get("CRON_SECRET")),
        "admin_totp": bool(os.environ.get("ADMIN_TOTP_SECRET")), "vercel": crypto.IS_VERCEL,
        "demo": os.environ.get("DEMO", "0") == "1", "build": crypto.BUILD_ID,
        "scheduler_running": bool(crypto.scheduler.running),
    })


@bp.post("/admin/engine/tick")
@admin_only
def admin_engine_tick():
    from crypto import engine
    return ok(engine.tick(budget=20))
