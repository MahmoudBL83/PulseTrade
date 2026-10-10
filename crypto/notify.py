import json
import os
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask import jsonify, request
from flask_login import current_user
from flask_socketio import join_room

from crypto import app, db, celery, socketio, auth_required, get_current_user
from crypto.models import Notification, Exchange, User


def user_room(user_id):
    return f"user_{user_id}"


def _user_from_socket_auth(auth):
    """Socket.IO clients may authenticate with the session cookie (legacy
    pages) or pass ``{token: <jwt>}`` in the handshake (React app)."""
    user = get_current_user()
    if user is None and isinstance(auth, dict) and auth.get("token"):
        from flask_jwt_extended import decode_token
        from crypto import token_revoked
        try:
            data = decode_token(auth["token"])
            if not token_revoked(data.get("jti")):
                ident = data.get("sub")
                email = ident.get("email") if isinstance(ident, dict) else (data.get("email") or ident)
                user = User.query.filter_by(email=email).first()
        except Exception:
            user = None
    return user


@socketio.on('connect')
def handle_connect(auth=None):
    user = _user_from_socket_auth(auth)
    if user is not None:
        join_room(user_room(user.id))


@socketio.on('disconnect')
def handle_disconnect(*args):
    pass


@socketio.on('subscribe_market')
def handle_subscribe_market(*args):
    """Live ticker updates from the ccxt.pro streamer (see crypto/stream.py)."""
    join_room("market")


@socketio.on('unsubscribe_market')
def handle_unsubscribe_market(*args):
    from flask_socketio import leave_room
    leave_room("market")

@socketio.on('notification')
def handle_notification(message):
    print('Notification received:', message)


def emit_to_user(event, payload, user_id=None):
    """Emit to one user's room (or broadcast public market data)."""
    try:
        if user_id:
            socketio.emit(event, payload, to=user_room(user_id))
        else:
            socketio.emit(event, payload)
    except Exception as e:
        print(f"socketio emit skipped: {e}")


# --------------------------------------------------------------------------- external channels

ALLOWED_WEBHOOK_HOSTS = ("discord.com", "discordapp.com", "hooks.slack.com")


def valid_webhook(url):
    """Only HTTPS webhooks on known chat services (prevents SSRF)."""
    try:
        p = urlparse(url or "")
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_WEBHOOK_HOSTS)


def _post_external(user, text):
    prefs = user.get_preferences()
    channels = prefs.get("channels") or {}
    jobs = []
    hook = channels.get("webhook_url")
    if channels.get("webhook_enabled") and hook and valid_webhook(hook):
        jobs.append((hook, {"content": text, "text": text}))
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = channels.get("telegram_chat_id")
    if channels.get("telegram_enabled") and tg_token and chat_id:
        jobs.append((f"https://api.telegram.org/bot{tg_token}/sendMessage", {"chat_id": str(chat_id), "text": text}))
    if not jobs or os.environ.get("PULSE_TESTING") == "1":
        return len(jobs)

    def run():
        for url, body in jobs:
            try:
                requests.post(url, json=body, timeout=(4, 8))
            except Exception as e:
                print(f"notification channel failed: {e}")
    threading.Thread(target=run, daemon=True).start()
    return len(jobs)


# --------------------------------------------------------------------------- core

def send_notification(message,id=None,exchange=None):
    """Store a notification for a user and push it in real time.

    ``message`` may carry a type suffix: "text***Type". Type "system" marks
    platform messages (no exchange attached)."""
    with app.app_context():
        try:
            if id is None:
                owner = get_current_user()
            else:
                owner = db.session.get(User, int(id)) if str(id).isdigit() else User.query.filter_by(email=str(id)).first()
            if owner is None:
                print(f"notification dropped (no recipient): {message}")
                return None
            parts = str(message).split("***")
            content = parts[0].strip()
            kind = parts[1].strip() if len(parts) > 1 else ""
            ex_name = None if kind == "system" else (exchange if exchange is not None else owner.exchange)
            now = datetime.now(timezone.utc)
            emit_to_user('new_notification',
                         f"{owner.id}***{str(message)}***{now.strftime('%Y-%m-%d %H:%M:%S')}***{ex_name}",
                         owner.id)
            notification = Notification(content=content, type=kind, date=str(now), exchange=ex_name, owner_id=owner.id)
            db.session.add(notification)
            db.session.commit()
            _post_external(owner, f"PulseTrade: {content}")
            return notification
        except Exception as e:
            db.session.rollback()
            print(f"send_notification failed: {e}")
            return None

@app.route('/api/v1/read_notifications/')
@auth_required
def read_notifications():
    user = get_current_user()
    count = user.notifications.filter(Notification.read==False).update({Notification.read: True})
    db.session.commit()
    return jsonify({"ok": True, "updated": count})

@app.route('/api/v1/get_notifications/')
@auth_required
def get_notifications():
    user = get_current_user()
    limit = min(int(request.args.get("limit", 200)), 1000)
    notifications = user.notifications.order_by(Notification.id.desc()).limit(limit).all()
    return jsonify([notification.serialize() for notification in notifications])

@app.route('/api/v1/get_notifications_count/')
@auth_required
def get_notifications_count():
    user = get_current_user()
    return jsonify(user.notifications.filter(Notification.read==False).count())

@celery.task
def monitor_orders():
    """Legacy Celery loop: notify users when their tracked open orders fill."""
    from crypto.functions import build_exchange
    while True:
        time.sleep(1)
        with app.app_context():
            for user in User.query.all():
                try:
                    check_open_orders(user, build_exchange)
                except Exception as e:
                    db.session.rollback()
                    print(f"monitor_orders user {user.id}: {e}")


def check_open_orders(user, build_exchange):
    open_orders = user._open_orders_list()
    if not open_orders:
        return 0
    row = user.exchanges.filter(Exchange.isActive==True).first()
    if row is None:
        return 0
    exchange = build_exchange(row)
    done = 0
    for item in list(open_orders):
        try:
            order = exchange.fetch_order(item[0], symbol=item[1])
        except Exception:
            continue
        if order.get('status') in ('filled', 'closed'):
            send_notification(f"the {item[2]} order with id {item[0]} for {item[1]} has been filled***Order", user.id)
            user.remove_from_open_orders(item)
            done += 1
        elif order.get('status') in ('canceled', 'cancelled', 'expired', 'rejected'):
            user.remove_from_open_orders(item)
    db.session.commit()
    return done
