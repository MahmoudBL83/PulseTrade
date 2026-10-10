from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
import os
import math
import statistics
from flask_login import UserMixin
import json
from crypto import db, login_manager, scheduler
from datetime import datetime, timedelta
import ccxt
import numpy as np
try:
    from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
except ImportError:  # itsdangerous>=2.1 removed it; emulate via URLSafeTimedSerializer
    from itsdangerous import URLSafeTimedSerializer as _URLSafeSerializer

    class Serializer(_URLSafeSerializer):
        def __init__(self, secret_key, expires_in=3600, **kwargs):
            super().__init__(secret_key, **kwargs)
            self.expires_in = expires_in

        def loads(self, token, **kwargs):
            kwargs.setdefault('max_age', self.expires_in)
            return super().loads(token, **kwargs)
from crypto import app
from crypto.functions import getPrice_assets
import time

PAPER_EXCHANGE = "paper"


def _iso(value):
    return value.isoformat() if value else None


def _round(value, digits=2):
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return round(v, digits)
    except (TypeError, ValueError):
        return 0.0


class Exchange2(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exchange = db.Column(db.String(120), nullable=False)
    isActive = db.Column(db.Boolean, default=False)

    def serialize(self):
        return {
            'id': self.id,
            'exchange': self.exchange,
            'isActive': self.isActive,
        }

    def __init__(self, exchange,isActive=False):
        self.exchange = exchange
        self.isActive = isActive

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # Notional value in USD (amount * price, converted for non-USDT quotes).
    value = db.Column(db.Float, default=0)
    price = db.Column(db.Float)
    type = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    exchange = db.Column(db.String(120))
    amount = db.Column(db.Float)
    symbol = db.Column(db.String(32))
    status = db.Column(db.Boolean, default = True)
    err_msg = db.Column(db.JSON, default=None)
    #linked bot
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.bot_id'), index=True)
    bot = db.relationship('Bot', back_populates='transactions', overlaps="transactions_owned")
    #linked sma
    sma_id = db.Column(db.Integer, db.ForeignKey('smarttrades.id'), index=True)
    sma = db.relationship('SmartTrade', back_populates='transactions', overlaps="transactions_owned_sma")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def serialize(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'value': self.value,
            'price': self.price,
            'type': self.type,
            'user_id': self.user_id,
            'exchange': self.exchange,
            'amount': self.amount,
            'symbol': self.symbol,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'bot_id': self.bot_id,
            'sma_id': self.sma_id,
            'status':self.status,
            'err_msg': self.err_msg,
        }

    def __init__(self, type, user_id, exchange, amount, symbol, value=0, err_msg=None, status=True, bot_id=None, sma_id=None):
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            amount = 0.0
        self.type = type
        self.user_id = user_id
        self.exchange = exchange
        self.amount = amount
        self.symbol = symbol
        self.status = status
        self.err_msg = err_msg
        self.bot_id = bot_id
        self.sma_id = sma_id
        try:
            unit_price = float(value or 0)
        except (TypeError, ValueError):
            unit_price = 0.0
        parts = str(symbol or "").split("/")
        quote = parts[1] if len(parts) == 2 else "USDT"
        try:
            if quote != "USDT":
                base_usd = float(getPrice_assets(exchange or "", parts[0] + "/USDT") or 0)
                quote_usd = float(getPrice_assets(exchange or "", quote + "/USDT") or 0)
                if not unit_price and quote_usd:
                    unit_price = base_usd / quote_usd
                self.value = unit_price * amount * quote_usd if quote_usd else base_usd * amount
            else:
                self.value = unit_price * amount if value is not None else amount
        except Exception:
            self.value = unit_price * amount if value is not None else amount
        self.price = unit_price or None


class UserCount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer)

    def serialize(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'count': self.count,
        }

    def __init__(self, count):
        self.count = count

class BotCount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer)

    def serialize(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'count': self.count,
        }

    def __init__(self, count):
        self.count = count

# Create the User model
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    firstName = db.Column(db.String(120))
    lastName = db.Column(db.String(120))
    is_verified = db.Column(db.Boolean, default=False)
    img = db.Column(db.String(512),default="/static/assets/images/avatars/01.png")
    password_hash = db.Column(db.String(512), nullable=False)
    ip_check = db.Column(db.Boolean,default=True)
    last_ip = db.Column(db.String(120))
    subType_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))
    subType = db.relationship('Subscription', back_populates='users')
    sub_date =  db.Column(db.DateTime, default=datetime.utcnow)
    subscription_id = db.Column(db.String(120))
    exchange = db.Column(db.String(120))
    exchanges = db.relationship('Exchange',backref='Exchanges_owned',lazy='dynamic', cascade='all, delete')
    notifications = db.relationship('Notification',backref='Notifications_owned',lazy='dynamic', cascade='all, delete')
    chats = db.relationship('Chat',backref='Chats_owned',lazy='dynamic', cascade='all, delete')
    bots = db.relationship('Bot',backref='Bot_owned',lazy='dynamic', cascade='all, delete')
    balance_history = db.relationship('BalanceHistory', backref='bal_history', lazy='dynamic', cascade='all, delete')
    balance_history24h = db.relationship('BalanceHistory24h', backref='bal_history24h', lazy='dynamic', cascade='all, delete')
    bot_history = db.relationship('BotHistory', backref='bot_history', lazy='dynamic', cascade='all, delete')
    tickets = db.relationship('Ticket', backref='user', lazy='dynamic', cascade='all, delete')
    open_orders = db.Column(db.String)
    balance = db.Column(db.Float,default=0.0)
    balance_usd = db.Column(db.Float,default=0.0)
    balance_btc = db.Column(db.Float,default=0.0)
    profit_monthly_btc = db.Column(db.Float,default=0.0)
    profit_monthly_usd = db.Column(db.Float,default=0.0)
    profit_daily_btc = db.Column(db.Float,default=0.0)
    profit_daily_usd = db.Column(db.Float,default=0.0)
    profit_monthly_percent_btc = db.Column(db.Float,default=0.0)
    profit_monthly_percent_usd = db.Column(db.Float,default=0.0)
    profit_daily_percent_btc = db.Column(db.Float,default=0.0)
    profit_daily_percent_usd = db.Column(db.Float,default=0.0)
    profit_overall_btc = db.Column(db.Float,default=0.0)
    profit_overall_usd = db.Column(db.Float,default=0.0)
    sharpe_ratio = db.Column(db.Float,default=0.0)
    sortino_ratio = db.Column(db.Float,default=0.0)
    deviation = db.Column(db.Float,default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    stripe_customer_id = db.Column(db.String())
    # --- added in the 2026 modernization (auto-migrated onto existing DBs) ---
    demo = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(64))
    totp_enabled = db.Column(db.Boolean, default=False)
    preferences = db.Column(db.JSON)
    last_login_at = db.Column(db.DateTime)


    def __init__(self, email, password, firstName, lastName,img='/static/assets/images/avatars/01.png'):
        self.email = email
        self.firstName = firstName
        self.lastName = lastName
        self.img = img
        self.set_password(password)
        self.open_orders = json.dumps([])  # Initialize as an empty array

    def get_reset_password_token(self):
        s = Serializer(app.config['SECRET_KEY'], expires_in=600)
        token = s.dumps({'user_id': self.id})
        return token.decode('utf-8') if isinstance(token, bytes) else token

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        try:
            return check_password_hash(self.password_hash, password or "")
        except (ValueError, TypeError):
            return False

    def _open_orders_list(self):
        try:
            data = json.loads(self.open_orders or "[]")
            return data if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []

    def append_to_open_orders(self, item):
        open_orders_list = self._open_orders_list()
        open_orders_list.append(item)
        self.open_orders = json.dumps(open_orders_list)

    def remove_from_open_orders(self, item):
        open_orders_list = self._open_orders_list()
        if item in open_orders_list:
            open_orders_list.remove(item)
        self.open_orders = json.dumps(open_orders_list)

    def get_preferences(self):
        prefs = self.preferences if isinstance(self.preferences, dict) else {}
        return {"theme": "dark", "lang": "en", "currency": "USD", **prefs}

    @staticmethod
    def _daily_series(rows, attr):
        """Last value per calendar day, oldest first."""
        by_day = {}
        for r in rows:
            if r.timestamp is None:
                continue
            by_day[r.timestamp.date()] = getattr(r, attr) or 0.0
        return [by_day[d] for d in sorted(by_day)]

    @staticmethod
    def risk_metrics(values):
        """Annualised Sharpe/Sortino and daily-return deviation (%) from a
        daily balance series. Zero when there is not enough history."""
        returns = []
        for prev, cur in zip(values, values[1:]):
            if prev:
                returns.append((cur - prev) / prev)
        if len(returns) < 2:
            return 0.0, 0.0, 0.0
        mean = statistics.fmean(returns)
        std = statistics.pstdev(returns)
        downside = [r for r in returns if r < 0]
        dstd = math.sqrt(sum(r * r for r in downside) / len(returns)) if downside else 0.0
        ann = math.sqrt(365)
        sharpe = (mean / std) * ann if std else 0.0
        sortino = (mean / dstd) * ann if dstd else 0.0
        return round(sharpe, 4), round(sortino, 4), round(std * 100, 4)

    def update_profit(self):
        # Retrieve the balance history records for the last 24 hours and 30 days
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_30d = now - timedelta(days=30)
        first_24h = BalanceHistory.query.filter_by(owner_id=self.id).filter(BalanceHistory.timestamp >= last_24h).order_by(BalanceHistory.timestamp.asc()).first()
        first_30d = BalanceHistory.query.filter_by(owner_id=self.id).filter(BalanceHistory.timestamp >= last_30d).order_by(BalanceHistory.timestamp.asc()).first()
        first_ever = BalanceHistory.query.filter_by(owner_id=self.id).order_by(BalanceHistory.timestamp.asc()).first()
        bal_btc = self.balance_btc or 0.0
        bal_usd = self.balance_usd or 0.0

        # Calculate daily profit
        self.profit_daily_btc = (bal_btc - (first_24h.balance_btc or 0.0)) if first_24h else 0.0
        self.profit_daily_usd = (bal_usd - (first_24h.balance_usd or 0.0)) if first_24h else 0.0

        # Calculate monthly profit
        self.profit_monthly_btc = (bal_btc - (first_30d.balance_btc or 0.0)) if first_30d else 0.0
        self.profit_monthly_usd = (bal_usd - (first_30d.balance_usd or 0.0)) if first_30d else 0.0

        # Profit percentages are relative to the starting balance of each window
        def pct(profit, start):
            return (profit / start) * 100 if start else 0.0
        self.profit_daily_percent_btc = pct(self.profit_daily_btc, first_24h.balance_btc if first_24h else 0)
        self.profit_daily_percent_usd = pct(self.profit_daily_usd, first_24h.balance_usd if first_24h else 0)
        self.profit_monthly_percent_btc = pct(self.profit_monthly_btc, first_30d.balance_btc if first_30d else 0)
        self.profit_monthly_percent_usd = pct(self.profit_monthly_usd, first_30d.balance_usd if first_30d else 0)

        # Overall profit since the first recorded balance
        self.profit_overall_btc = bal_btc - (first_ever.balance_btc or 0.0) if first_ever else 0.0
        self.profit_overall_usd = bal_usd - (first_ever.balance_usd or 0.0) if first_ever else 0.0

        # Risk metrics from daily returns over the last 90 days
        rows = BalanceHistory.query.filter_by(owner_id=self.id).filter(
            BalanceHistory.timestamp >= now - timedelta(days=90)).order_by(BalanceHistory.timestamp.asc()).all()
        self.sharpe_ratio, self.sortino_ratio, self.deviation = self.risk_metrics(self._daily_series(rows, "balance_usd"))

        # Save the changes to the database
        db.session.commit()

    def update_balance(self):
        from crypto.functions import build_exchange
        assets_json = []
        for exchange in self.exchanges.all():
            try:
                exchangeNow = build_exchange(exchange)
                balance = exchangeNow.fetch_balance()
                BTCUSDT = getPrice_assets(exchange.name, 'BTC/USDT') or 0
                free_map = balance.get("free") or {}
                used_map = balance.get("used") or {}
                for asset, amount in (balance.get("total") or {}).items():
                    if not amount:
                        continue
                    price = getPrice_assets(exchange.name,asset+'/USDT') or 0
                    price2 = price/BTCUSDT if BTCUSDT else 0
                    free = free_map.get(asset) or 0
                    used = used_map.get(asset) or 0
                    if check_assets_json(assets_json, asset):
                        for asset_json in assets_json:
                            if asset_json['currency'] == asset:
                                asset_json['free'] += free
                                asset_json['used'] += used
                                asset_json['total'] += amount
                                asset_json['eqUSD'] += amount*price
                                asset_json['eqBTC'] += amount*price2
                    else:
                        assets_json.append({"currency":asset,"free":free,"used":used,"total":amount,"price":price,'eqUSD':amount*price,'eqBTC':amount*price2})
            except Exception as e:
                print(f'Error fetching balance for {exchange.name}: {e}')

        new_balance_usd = sum(a['eqUSD'] for a in assets_json)
        new_balance_btc = sum(a['eqBTC'] for a in assets_json)
        self.balance_usd = new_balance_usd
        self.balance_btc = new_balance_btc

        # Create a new BalanceHistory record when the balance changed
        last = self.balance_history.order_by(BalanceHistory.timestamp.desc()).first()
        if last is None or last.balance_usd != new_balance_usd or last.balance_btc != new_balance_btc:
            balance_history = BalanceHistory(owner_id=self.id, balance_usd=new_balance_usd, balance_btc=new_balance_btc)
            db.session.add(balance_history)

        # Calculate and update the profit
        self.update_profit()

        db.session.commit()
        return assets_json

    def reset_stats(self):
        self.profit_monthly_btc = 0.0
        self.profit_monthly_usd = 0.0
        self.profit_daily_btc = 0.0
        self.profit_daily_usd = 0.0
        self.profit_monthly_percent_btc = 0.0
        self.profit_monthly_percent_usd = 0.0
        self.profit_daily_percent_btc = 0.0
        self.profit_daily_percent_usd = 0.0
        self.profit_overall_btc = 0.0
        self.profit_overall_usd = 0.0
        self.sharpe_ratio = 0.0
        self.sortino_ratio = 0.0
        self.deviation = 0.0

        for balance in self.balance_history:
            db.session.delete(balance)

        db.session.commit()

    def serialize(self):
        return {
            'id': self.id,
            'email': self.email,
            'firstName': self.firstName,
            'lastName': self.lastName,
            'subType': self.subType.serialize() if self.subType else None,
            'img':self.img,
            'balance_usd': self.balance_usd,
            'balance_btc': self.balance_btc,
            'subscription_id': self.subscription_id,
            'stripe_customer_id': self.stripe_customer_id,
            'is_verified': bool(self.is_verified),
            'ip_check': bool(self.ip_check),
            'demo': bool(self.demo),
            'totp_enabled': bool(self.totp_enabled),
            'exchange': self.exchange,
            'sub_date': _iso(self.sub_date),
            'created_at': _iso(self.created_at),
            'last_login_at': _iso(self.last_login_at),
            'preferences': self.get_preferences(),
        }

class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(120), nullable=False)
    type_ar = db.Column(db.String(120))
    price = db.Column(db.Float)
    duration = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    max_bots = db.Column(db.Integer, default=5)
    max_sma = db.Column(db.Integer, default=10)
    trial_days = db.Column(db.Integer, default=0)
    stripe_id = db.Column(db.String())
    users = db.relationship('User', back_populates='subType')

    def __init__(self,max_bots,max_sma, price=0.0, type='free'):
        self.type = type
        self.price = price
        self.max_bots = max_bots
        self.max_sma = max_sma

    def serialize(self):
        return {
            'id': self.id,
            'type': self.type,
            'type_ar': self.type_ar,
            'price': self.price,
            'duration': self.duration,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'max_bots': self.max_bots,
            'max_sma': self.max_sma,
            'trial_days': self.trial_days,
            'stripe_id': self.stripe_id,
        }

class Ticket(db.Model):
    __tablename__ = "tickets"
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(120), default="open")
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    messages = db.relationship('Message', backref='messages_owned', lazy='dynamic', cascade='all, delete')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def __init__(self,subject, user_id, status="open", messages=None):
        self.subject = subject
        self.user_id = user_id
        self.status = status

    def serialize(self):
        owner = db.session.get(User, self.user_id)
        return {
            'id': self.id,
            'subject': self.subject,
            'status': self.status,
            'user': owner.serialize() if owner else None,
            'messages':[message.serialize() for message in Message.query.filter(Message.ticket_id == self.id).order_by(Message.id.asc()).all()],
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean)
    ticket = db.relationship('Ticket', overlaps="messages,messages_owned")
    user_id = db.Column(db.Integer, nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self,content, user_id, ticket_id, is_admin=False, created_at=None):
        self.content = content
        self.user_id = user_id
        self.ticket_id = ticket_id
        self.created_at = created_at if isinstance(created_at, datetime) else datetime.utcnow()
        self.is_admin = bool(is_admin)

    def serialize(self):
        author = db.session.get(User, self.user_id) if self.user_id else None
        ticket = db.session.get(Ticket, self.ticket_id) if self.ticket_id else None
        return {
            'id': self.id,
            'content': self.content,
            'is_admin': self.is_admin,
            'user_id': self.user_id,
            'user': author.serialize() if author else None,
            'ticket_id': self.ticket_id,
            'created_at': self.created_at,
            "subject": ticket.subject if ticket else None,
        }

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.relationship('Category', overlaps="posts,posts_owned")
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), index=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    writer = db.Column(db.String(120), nullable=False)
    img = db.Column(db.Text)
    reviewer = db.Column(db.String(120))
    views = db.Column(db.Integer, default=0)
    lang = db.Column(db.String(10), default="en")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def __init__(self,title, content, writer,img, views=0,lang='en'):
        self.title = title
        self.content = content
        self.writer = writer
        self.views = views
        self.img = img
        self.lang = lang or 'en'

        #self.created_at = created_at

    def serialize(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'writer': self.writer,
            'views': self.views,
            'img': self.img,
            'lang': self.lang,
            'category_id': self.category_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    title_ar = db.Column(db.String(120))
    views = db.Column(db.Integer, default=0)
    img = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    posts = db.relationship('Post', backref='posts_owned', lazy='dynamic', cascade='all, delete')

    def __init__(self,title,title_ar,img=None, views=0):
        self.title = title
        self.views = views
        self.img = img
        self.title_ar = title_ar
        #self.created_at = created_at

    def serialize(self, with_posts=True):
        out = {
            'id': self.id,
            'title': self.title,
            'views': self.views,
            'img': self.img,
            'title_ar': self.title_ar,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if with_posts:
            out['posts'] = [post.serialize() for post in Post.query.filter(Post.category_id == self.id).all()]
        return out

class BalanceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.relationship('User', overlaps="bal_history,balance_history")
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    balance_usd = db.Column(db.Float)
    balance_btc = db.Column(db.Float)
    balance_usd24h = db.Column(db.Float)
    balance_btc24h = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def serialize(self):
        return {
            'id': self.id,
            'owner_id': self.owner_id,
            'balance_usd': self.balance_usd,
            'balance_btc': self.balance_btc,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }

    def __init__(self, owner_id, balance_usd, balance_btc):
        self.owner_id = owner_id
        self.balance_usd = balance_usd
        self.balance_btc = balance_btc

class BotHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.relationship('User', overlaps="bot_history")
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    profit = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'owner_id': self.owner_id,
            'profit': self.profit,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }

    def __init__(self, profit, owner_id):
        self.owner_id = owner_id
        self.profit = profit

class BalanceHistory24h(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.relationship('User', overlaps="bal_history24h,balance_history24h")
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    balance_usd = db.Column(db.Float)
    balance_btc = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'owner_id': self.owner_id,
            'balance_usd': self.balance_usd,
            'balance_btc': self.balance_btc,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }

    def __init__(self, owner_id, balance_usd, balance_btc):
        self.owner_id = owner_id
        self.balance_usd = balance_usd
        self.balance_btc = balance_btc

class TransactionHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'value': self.value,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }

    def __init__(self, value):
        self.value = value

class Pair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pair = db.Column(db.String(120), nullable=False)
    isActive = db.Column(db.Boolean, default=False)

    def serialize(self):
        return {
            'id': self.id,
            'pair': self.pair,
            'isActive': self.isActive,
        }

    def __init__(self, pair, isActive=False):
        self.pair = pair
        self.isActive = isActive

class SmartTrade(db.Model):
    __tablename__ = "smarttrades"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    trade_type = db.Column(db.String(255))
    strategy = db.Column(db.String(255))
    exchange = db.Column(db.String(255))
    # NB: legacy naming — symbol is f"{quote_currency}/{base_currency}".
    base_currency = db.Column(db.String(20))
    quote_currency = db.Column(db.String(20))
    allocation = db.Column(db.Float)
    conditions = db.Column(db.JSON)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    buy_price = db.Column(db.Float)
    bought_price = db.Column(db.Float)
    buy_trigger_price = db.Column(db.Float)
    order_type = db.Column(db.String(20))
    units = db.Column(db.Float)
    amount = db.Column(db.Float)
    stop_loss = db.Column(db.Boolean,default=False)
    take_profit = db.Column(db.Boolean,default=False)
    stop_loss_type = db.Column(db.String(20))
    stop_loss_price_percent = db.Column(db.Float)
    stop_loss_price = db.Column(db.Float)
    trailing_take_profit = db.Column(db.Boolean,default=False)
    trailing_stop_loss = db.Column(db.Boolean,default=False)
    last_take_profit = db.Column(db.Boolean,default=False)
    take_profit_index = db.Column(db.Integer, default=0)
    trailing_deviation = db.Column(db.Float)
    take_profit_quantities = db.Column(db.JSON)
    tpTriggerType = db.Column(db.String(20))
    # Exchange order ids are strings on many venues (KuCoin, Bybit...).
    trailing_order_id = db.Column(db.String(64))
    buy_order_id = db.Column(db.String(64))
    sell_order_ids = db.Column(db.JSON)
    stop_loss_id = db.Column(db.String(64))
    last_take_profit_id = db.Column(db.String(64))
    last_price = db.Column(db.Float,default=0.0)
    isActive = db.Column(db.Boolean,default=True)
    deal_started = db.Column(db.Boolean,default=False)
    stop_loss_time_out = db.Column(db.Boolean,default=False)
    stop_loss_time_out_runned = db.Column(db.Boolean,default=False)
    stop_loss_time_out_time = db.Column(db.Integer)
    stop_loss_triggered_at = db.Column(db.DateTime)
    move_to_break_even = db.Column(db.Boolean,default=False)
    total_profit = db.Column(db.Float,default=0.0)
    total_profit_percent = db.Column(db.Float,default=0.0)
    last_total_profit_time = db.Column(db.DateTime, default=datetime.utcnow)
    price_now = db.Column(db.Float)
    use_assets = db.Column(db.Boolean,default=False)
    is_hidden = db.Column(db.Boolean,default=False)
    transactions = db.relationship('Transaction',backref='transactions_owned_sma',lazy='dynamic', cascade='all, delete', overlaps="sma")

    def __init__(self,bought_price,amount,move_to_break_even,order_type,trade_type,take_profit, exchange, base_currency, quote_currency, user_id, buy_price,buy_trigger_price, stop_loss,stop_loss_time_out_time, take_profit_quantities,units, trailing_order_id,buy_order_id,trailing_take_profit,trailing_stop_loss,stop_loss_type,stop_loss_price,tpTriggerType,trailing_deviation=None,stop_loss_price_percent=None,last_price=None,last_take_profit=None,stop_loss_time_out=None,sell_order_ids=None,stop_loss_id=None,last_take_profit_id=None,deal_started=False,isActive=True,use_assets=False,price_now=0,stop_loss_time_out_runned=False,total_profit=0,total_profit_percent=0,last_total_profit_time=None,take_profit_index=0,name=None):
        self.exchange = exchange
        self.bought_price = bought_price
        self.base_currency = base_currency
        self.trade_type = trade_type
        self.quote_currency = quote_currency
        self.user_id = user_id
        self.buy_price = buy_price
        self.buy_trigger_price = buy_trigger_price
        self.stop_loss_price_percent = stop_loss_price_percent
        self.take_profit_quantities = take_profit_quantities or []
        self.tpTriggerType = tpTriggerType
        self.trailing_deviation = trailing_deviation
        self.units = units
        self.amount = amount
        self.order_type = order_type
        self.sell_order_ids = sell_order_ids
        self.trailing_order_id = None if trailing_order_id in (None, 0, "0") else str(trailing_order_id)
        self.buy_order_id = None if buy_order_id is None else str(buy_order_id)
        self.stop_loss_id = stop_loss_id
        self.last_take_profit_id = last_take_profit_id
        self.trailing_stop_loss = trailing_stop_loss
        self.trailing_take_profit = trailing_take_profit
        self.stop_loss_type = stop_loss_type
        self.stop_loss_price = stop_loss_price
        self.stop_loss_time_out = stop_loss_time_out
        self.stop_loss_time_out_time = stop_loss_time_out_time
        self.deal_started = deal_started
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.isActive = isActive
        self.move_to_break_even = move_to_break_even
        self.price_now = price_now
        self.take_profit_index = 0
        self.use_assets = use_assets
        self.stop_loss_time_out_runned = stop_loss_time_out_runned
        self.last_price = last_price or 0.0
        self.name = name

    @property
    def symbol(self):
        return f"{self.quote_currency}/{self.base_currency}"

    def serialize(self, with_transactions=True):
        out = {
            'id': self.id,
            'name': self.name,
            'strategy': self.strategy,
            'exchange': self.exchange,
            'symbol': self.symbol,
            'base_currency': self.base_currency,
            'quote_currency': self.quote_currency,
            'allocation': self.allocation,
            'conditions': self.conditions,
            'buy_price': _round(self.buy_price, 8),
            'bought_price': self.bought_price,
            'order_type': self.order_type,
            'units': self.units or 0,
            'amount': self.amount or 0,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'last_price': self.price_now or 0,
            'price_now':self.last_price if self.last_price else (self.buy_price or 0),
            'stop_loss_price': _round(self.stop_loss_price, 8),
            'trailing_take_profit': self.trailing_take_profit,
            'take_profit_quantities': self.take_profit_quantities or [],
            'created_at': _iso(self.created_at),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'tpTriggerType': self.tpTriggerType,
            'trailing_deviation': self.trailing_deviation,
            'stop_loss_price_percent': self.stop_loss_price_percent,
            'isActive': self.isActive,
            'deal_started': self.deal_started,
            'stop_loss_time_out': self.stop_loss_time_out,
            'stop_loss_time_out_time': self.stop_loss_time_out_time,
            'trailing_stop_loss': self.trailing_stop_loss,
            'last_take_profit': self.last_take_profit,
            'stop_loss_type': self.stop_loss_type,
            'buy_trigger_price': self.buy_trigger_price,
            'trailing_order_id': self.trailing_order_id,
            'buy_order_id': self.buy_order_id,
            'sell_order_ids': self.sell_order_ids,
            'stop_loss_id': self.stop_loss_id,
            'last_take_profit_id': self.last_take_profit_id,
            'trade_type': self.trade_type,
            'move_to_break_even': self.move_to_break_even,
            'total_profit': self.total_profit or 0,
            'total_profit_percent': self.total_profit_percent or 0,
            'last_total_profit_time': self.last_total_profit_time.isoformat() if self.last_total_profit_time else None,
            'take_profit_index': self.take_profit_index or 0,
            'use_assets': self.use_assets,
            'is_hidden': bool(self.is_hidden),
        }
        if with_transactions:
            out['transactions'] = [transaction.serialize() for transaction in Transaction.query.filter(Transaction.sma_id == self.id).all()]
        return out

class Exchange(db.Model,UserMixin):
    __tablename__ = "exchanges"
    id = db.Column('exchange_id',db.Integer, primary_key=True)
    number = db.Column(db.Integer())
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'), index=True)
    owner = db.relationship('User', overlaps="Exchanges_owned,exchanges")
    name = db.Column(db.String(120))
    api_key = db.Column(db.String(512))
    api_secret = db.Column(db.String(512))
    password = db.Column(db.String(512))
    demo = db.Column(db.Boolean,default=False)
    isActive = db.Column(db.Boolean,default=False)

    @property
    def is_paper(self):
        return (self.name or "").lower() == PAPER_EXCHANGE

    @staticmethod
    def _cipher():
        fernet_key = os.environ.get('FERNET_KEY', '')
        if not fernet_key:
            raise RuntimeError('FERNET_KEY env var is required')
        return Fernet(fernet_key.encode())

    def set_creds(self, api_key, api_secret, password):
        if self.is_paper:
            # Simulated account — nothing secret to store.
            self.api_key, self.api_secret, self.password = None, None, None
            return
        cipher_suite = self._cipher()
        self.api_key = cipher_suite.encrypt((api_key or "").encode()).decode()
        self.api_secret = cipher_suite.encrypt((api_secret or "").encode()).decode()
        self.password = cipher_suite.encrypt((password or "").encode()).decode()

    def get_creds(self):
        if self.is_paper:
            return "paper", "paper", ""
        cipher_suite = self._cipher()

        def dec(v):
            return cipher_suite.decrypt(v.encode()).decode() if v else ""
        return dec(self.api_key), dec(self.api_secret), dec(self.password)

    def serialize(self):
        # Never expose credential material (even encrypted) to the frontend.
        return {
            'id': self.id,
            'number': self.number,
            'owner_id': self.owner_id,
            'name': self.name,
            'has_api_key': bool(self.api_key) or self.is_paper,
            'has_api_secret': bool(self.api_secret) or self.is_paper,
            'has_password': bool(self.password),
            'demo': self.demo,
            'isActive': self.isActive,
            'paper': self.is_paper,
        }


class Notification(db.Model,UserMixin):
    __tablename__ = "notifications"
    id = db.Column('notification_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'), index=True)
    owner = db.relationship('User', overlaps="Notifications_owned,notifications")
    content = db.Column(db.String())
    type = db.Column(db.String(120))
    date = db.Column(db.String(120))
    exchange = db.Column(db.String(120))
    read = db.Column(db.Boolean,default=False)

    def serialize(self):
        return {
            'id': self.id,
            'owner_id': self.owner_id,
            'content': self.content,
            'type': self.type,
            'date': self.date,
            'exchange': self.exchange,
            'read': bool(self.read),
        }

class Bot(db.Model,UserMixin):
    __tablename__ = "bots"
    id = db.Column('bot_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'), index=True)
    owner = db.relationship('User', overlaps="Bot_owned,bots")
    name = db.Column(db.String(120))
    strategy = db.Column(db.String(255))
    start_order_type= db.Column(db.String(120))
    pair_type= db.Column(db.String(10))
    symbol= db.Column(db.String(120))
    symbols= db.Column(db.JSON)
    deal_started = db.Column(db.Boolean,default=False)
    take_profit = db.Column(db.Boolean,default=False)
    isActive = db.Column(db.Boolean,default=True)
    quote_currency = db.Column(db.String(120))
    base_currency = db.Column(db.String(120))
    exchange = db.Column(db.String(120))
    buy_price = db.Column(db.Float)
    price_now = db.Column(db.Float)
    take_profit_details = db.Column(db.String(120))
    deal_start_price = db.Column(db.Float)
    last_price = db.Column(db.Float,default=0.0)
    amount = db.Column(db.Float)
    units = db.Column(db.Float)
    total_volume = db.Column(db.Float)
    tp_type = db.Column(db.String(20))
    tp_percent = db.Column(db.Float)
    tp_percent_type = db.Column(db.String(20))
    tp_price = db.Column(db.Float)
    stop_loss_price = db.Column(db.Float)
    stop_loss_price_percent = db.Column(db.Float)
    stop_loss = db.Column(db.Boolean,default=False)
    trailing_take_profit = db.Column(db.Boolean,default=False)
    trailing_deviation = db.Column(db.Float)
    trailing_stop_loss = db.Column(db.Boolean,default=False)
    stop_loss_time_out = db.Column(db.Boolean,default=False)
    stop_loss_time_out_runned = db.Column(db.Boolean,default=False)
    stop_loss_time_out_time = db.Column(db.Integer)
    stop_loss_triggered_at = db.Column(db.DateTime)
    Close_deal_after_timeout = db.Column(db.Boolean,default=False)
    timeout = db.Column(db.Integer)
    without_conds = db.Column(db.Boolean,default=False)
    sell_price = db.Column(db.Float,default=0.0)
    safety_orders_size = db.Column(db.Float)
    safety_orders_size_scale = db.Column(db.Float)
    safety_orders_deviation = db.Column(db.Float)
    safety_orders_deviation_scale = db.Column(db.Float)
    safety_orders_count = db.Column(db.Integer)
    safety_orders_count_active = db.Column(db.Integer)
    safety_orders_count_max_active = db.Column(db.Integer)
    max_price = db.Column(db.Float)
    min_price = db.Column(db.Float)
    min_volume = db.Column(db.Float)
    min_profit = db.Column(db.Boolean,default=False)
    min_profit_type = db.Column(db.String(10))
    min_profit_percent = db.Column(db.Float)
    conds = db.Column(db.JSON)
    tp_conds = db.Column(db.JSON)
    # callable defaults: evaluated per row, not once at import time
    last_open_trade_time = db.Column(db.DateTime,default=datetime.utcnow)
    cooldown_between_deals = db.Column(db.Integer,default=0)
    open_deals_and_stop = db.Column(db.Integer,default=0)
    total_trades = db.Column(db.Integer,default=0)
    total_profit = db.Column(db.Float,default=0.0)
    last_total_profit_time = db.Column(db.DateTime,default=datetime.utcnow)
    close_deal_action = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    safetyOrders = db.relationship('SafetyOrder',backref='safetyOrders_owned',lazy='dynamic', cascade='all, delete')
    transactions = db.relationship('Transaction',backref='transactions_owned',lazy='dynamic', cascade='all, delete', overlaps="bot")
    timeout_type = db.Column(db.Integer)
    amount_type = db.Column(db.Integer)
    safety_orders_size_type = db.Column(db.Integer)
    is_hidden = db.Column(db.Boolean,default=False)
    # New: start the next deal automatically after a take profit.
    auto_restart = db.Column(db.Boolean, default=False)
    last_error = db.Column(db.String(255))

    def serialize(self):
        so = self.safetyOrders.all() if self.id else []
        return {
            'id': self.id,
            'name': self.name,
            'strategy': self.strategy,
            'exchange': self.exchange,
            'symbol': self.symbol or (f"{self.base_currency}/{self.quote_currency}" if self.base_currency else None),
            'symbols': self.symbols,
            'pair_type': self.pair_type,
            'base_currency': self.base_currency,
            'quote_currency': self.quote_currency,
            'start_order_type': self.start_order_type,
            'isActive': bool(self.isActive),
            'is_hidden': bool(self.is_hidden),
            'deal_started': bool(self.deal_started),
            'take_profit': bool(self.take_profit),
            'buy_price': self.buy_price or 0,
            'deal_start_price': self.deal_start_price or 0,
            'price_now': self.price_now or 0,
            'last_price': self.last_price or 0,
            'sell_price': self.sell_price or 0,
            'amount': self.amount or 0,
            'units': self.units or 0,
            'total_volume': self.total_volume or 0,
            'tp_type': self.tp_type,
            'tp_percent': self.tp_percent,
            'tp_percent_type': self.tp_percent_type,
            'tp_price': self.tp_price or 0,
            'stop_loss': bool(self.stop_loss),
            'stop_loss_price': self.stop_loss_price or 0,
            'stop_loss_price_percent': self.stop_loss_price_percent,
            'trailing_take_profit': bool(self.trailing_take_profit),
            'trailing_stop_loss': bool(self.trailing_stop_loss),
            'trailing_deviation': self.trailing_deviation,
            'safety_orders_count': self.safety_orders_count or 0,
            'safety_orders_count_active': self.safety_orders_count_active or 0,
            'safety_orders_filled': sum(1 for s in so if s.isClosed and not s.isOpened),
            'total_trades': self.total_trades or 0,
            'total_profit': self.total_profit or 0,
            'conds': self.conds or [],
            'tp_conds': self.tp_conds or [],
            'auto_restart': bool(self.auto_restart),
            'cooldown_between_deals': self.cooldown_between_deals or 0,
            'open_deals_and_stop': self.open_deals_and_stop or 0,
            'last_open_trade_time': _iso(self.last_open_trade_time),
            'last_error': self.last_error,
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }



class SafetyOrder(db.Model,UserMixin):
    __tablename__ = "safetyOrders"
    id = db.Column('safetyOrders_id',db.Integer, primary_key=True)
    orderId = db.Column(db.String(64))
    owner_id = db.Column(db.Integer(),db.ForeignKey('bots.bot_id'), index=True)
    owner = db.relationship('Bot', overlaps="safetyOrders,safetyOrders_owned")
    amount = db.Column(db.Float)
    price = db.Column(db.Float)
    isFilled = db.Column(db.Boolean,default=False)
    isOpened = db.Column(db.Boolean,default=False)
    isClosed = db.Column(db.Boolean,default=False)

class Chat(db.Model,UserMixin):
    __tablename__ = "chats"
    id = db.Column('chat_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'), index=True)
    owner = db.relationship('User', overlaps="Chats_owned,chats")
    message = db.Column(db.String(255))
    role = db.Column(db.String(20))


# =============================================================================
# New in the 2026 modernization
# =============================================================================

class TokenBlocklist(db.Model):
    """Revoked JWTs (logout). Checked on every Bearer-authenticated request."""
    __tablename__ = "token_blocklist"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LoginEvent(db.Model):
    """Security log: logins, failed attempts, 2FA changes, password changes."""
    __tablename__ = "login_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), index=True)
    event = db.Column(db.String(40), default="login")
    success = db.Column(db.Boolean, default=True)
    ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def serialize(self):
        return {"id": self.id, "event": self.event, "success": bool(self.success), "ip": self.ip,
                "user_agent": self.user_agent, "created_at": _iso(self.created_at)}


class WatchlistItem(db.Model):
    __tablename__ = "watchlist"
    __table_args__ = (db.UniqueConstraint("user_id", "exchange", "symbol", name="uq_watch_user_symbol"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    exchange = db.Column(db.String(40), nullable=False, default="binance")
    symbol = db.Column(db.String(32), nullable=False)
    note = db.Column(db.String(255))
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {"id": self.id, "exchange": self.exchange, "symbol": self.symbol, "note": self.note,
                "position": self.position, "created_at": _iso(self.created_at)}


class PriceAlert(db.Model):
    __tablename__ = "price_alerts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    exchange = db.Column(db.String(40), nullable=False, default="binance")
    symbol = db.Column(db.String(32), nullable=False)
    # above | below | change_pct (abs % move from reference price)
    condition = db.Column(db.String(16), nullable=False, default="above")
    target = db.Column(db.Float, nullable=False)
    reference_price = db.Column(db.Float)
    note = db.Column(db.String(255))
    repeat = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True, index=True)
    triggered_at = db.Column(db.DateTime)
    trigger_count = db.Column(db.Integer, default=0)
    last_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {"id": self.id, "exchange": self.exchange, "symbol": self.symbol, "condition": self.condition,
                "target": self.target, "reference_price": self.reference_price, "note": self.note,
                "repeat": bool(self.repeat), "active": bool(self.active), "triggered_at": _iso(self.triggered_at),
                "trigger_count": self.trigger_count or 0, "last_price": self.last_price,
                "created_at": _iso(self.created_at)}


class PaperAccount(db.Model):
    """Simulated balances for the built-in 'paper' exchange."""
    __tablename__ = "paper_accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True, index=True)
    # {"USDT": {"free": 10000.0, "used": 0.0}, ...}
    balances = db.Column(db.JSON, nullable=False, default=dict)
    starting_balance = db.Column(db.Float, default=10000.0)
    fee_rate = db.Column(db.Float, default=0.001)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaperOrder(db.Model):
    __tablename__ = "paper_orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    symbol = db.Column(db.String(32), nullable=False)
    side = db.Column(db.String(4), nullable=False)
    type = db.Column(db.String(10), nullable=False)          # market | limit
    price = db.Column(db.Float)                              # limit price
    trigger_price = db.Column(db.Float)                      # stop / trigger
    trigger_above = db.Column(db.Boolean)                    # fire when price rises to trigger
    amount = db.Column(db.Float, nullable=False)
    filled = db.Column(db.Float, default=0.0)
    average = db.Column(db.Float)
    fee = db.Column(db.Float, default=0.0)
    fee_currency = db.Column(db.String(16))
    status = db.Column(db.String(10), default="open", index=True)  # open | closed | canceled
    reserved = db.Column(db.Float, default=0.0)
    reserved_currency = db.Column(db.String(16))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JournalEntry(db.Model):
    __tablename__ = "journal_entries"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text)
    symbol = db.Column(db.String(32))
    side = db.Column(db.String(8))
    entry_price = db.Column(db.Float)
    exit_price = db.Column(db.Float)
    amount = db.Column(db.Float)
    tags = db.Column(db.JSON)
    mood = db.Column(db.String(16))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id', ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def pnl(self):
        if self.entry_price and self.exit_price and self.amount:
            sign = -1 if (self.side or "").lower() in ("short", "sell") else 1
            return sign * (self.exit_price - self.entry_price) * self.amount
        return None

    def serialize(self):
        return {"id": self.id, "title": self.title, "body": self.body, "symbol": self.symbol, "side": self.side,
                "entry_price": self.entry_price, "exit_price": self.exit_price, "amount": self.amount,
                "tags": self.tags or [], "mood": self.mood, "transaction_id": self.transaction_id,
                "pnl": self.pnl, "created_at": _iso(self.created_at), "updated_at": _iso(self.updated_at)}


# Load user function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def check_assets_json(assets_json, currency):
  """
  Check if the array of assets_json contains json fiel which currency has teh assets value.

  Args:
    assets_json: The array of assets_json.
    currency: The currency to check.

  Returns:
    True if the array of assets_json contains json fiel which currency has teh assets value, False otherwise.
  """

  for asset in assets_json:
    if asset["currency"] == currency:
      return True
  return False
