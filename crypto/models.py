from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import os
from flask_login import UserMixin
from datetime import datetime
import json
from flask_login import UserMixin
from crypto import db,login_manager,scheduler
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
    value = db.Column(db.Integer,default=0)
    type = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    exchange = db.Column(db.String(120))
    amount = db.Column(db.Float)
    symbol = db.Column(db.String(10))
    status = db.Column(db.Boolean, default = True)
    err_msg = db.Column(db.JSON, default = "")
    #linked bot
    bot_id = db.Column(db.Integer, db.ForeignKey('bots.bot_id'))
    bot = db.relationship('Bot', back_populates='transactions')
    #linked sma
    sma_id = db.Column(db.Integer, db.ForeignKey('smarttrades.id'))
    sma = db.relationship('SmartTrade', back_populates='transactions')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def serialize(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'value': self.value,
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
    
    def __init__(self, type, user_id, exchange, amount, symbol, value=0, err_msg="", status=True, bot_id=None, sma_id=None):
        amount = float(amount)
        self.type = type
        self.user_id = user_id
        self.exchange = exchange
        self.amount = amount
        self.symbol = symbol
        self.status = status
        self.err_msg = err_msg
        if symbol.split("/")[1] != "USDT":
            p1 = float(getPrice_assets(exchange,symbol.split("/")[0]+"/USDT"))
            p2 = float(getPrice_assets(exchange,symbol.split("/")[1]+"/USDT"))
            print(p1,p2)
            print(amount)
            self.value = p1/p2*amount
        else:
            try:
                self.value = value*amount
            except:
                self.value = amount
        

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
    img = db.Column(db.String(120),default="/static/assets/images/avatars/01.png")
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
        return check_password_hash(self.password_hash, password)
        
    def append_to_open_orders(self, item):
        open_orders_list = json.loads(self.open_orders)
        open_orders_list.append(item)
        self.open_orders = json.dumps(open_orders_list)

    def remove_from_open_orders(self, item):
        open_orders_list = json.loads(self.open_orders)
        open_orders_list.remove(item)
        self.open_orders = json.dumps(open_orders_list)

    def update_profit(self):
        # Retrieve the balance history records for the last 24 hours and 30 days
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_30d = now - timedelta(days=30)
        balance_history_24h = BalanceHistory.query.filter_by(owner_id=self.id).filter(BalanceHistory.timestamp >= last_24h).all()
        balance_history_30d = BalanceHistory.query.filter_by(owner_id=self.id).filter(BalanceHistory.timestamp >= last_30d).all()

        # Calculate daily profit
        self.profit_daily_btc = (self.balance_btc - balance_history_24h[0].balance_btc) if balance_history_24h else 0.0
        self.profit_daily_usd = (self.balance_usd - balance_history_24h[0].balance_usd) if balance_history_24h else 0.0

        # Calculate monthly profit
        self.profit_monthly_btc = (self.balance_btc - balance_history_30d[0].balance_btc) if balance_history_30d else 0.0
        self.profit_monthly_usd = (self.balance_usd - balance_history_30d[0].balance_usd) if balance_history_30d else 0.0

        # Calculate daily profit percentages
        self.profit_daily_percent_btc = (self.profit_daily_btc / self.balance_btc) * 100 if self.balance_btc != 0 else 0.0
        self.profit_daily_percent_usd = (self.profit_daily_usd / self.balance_usd) * 100 if self.balance_usd != 0 else 0.0

        # Calculate monthly profit percentages
        self.profit_monthly_percent_btc = (self.profit_monthly_btc / self.balance_btc) * 100 if self.balance_btc != 0 else 0.0
        self.profit_monthly_percent_usd = (self.profit_monthly_usd / self.balance_usd) * 100 if self.balance_usd != 0 else 0.0

        # Calculate overall profit
        self.profit_overall_btc = self.balance_btc - balance_history_30d[0].balance_btc if balance_history_30d else 0.0
        self.profit_overall_usd = self.balance_usd - balance_history_30d[0].balance_usd if balance_history_30d else 0.0

        # Calculate Sharpe ratio
        risk_free_rate = 0.0  # Set the risk-free rate according to your requirements
        daily_returns = np.array([self.profit_daily_btc, self.profit_daily_usd])
        daily_std = np.std(daily_returns)
        self.sharpe_ratio = (np.mean(daily_returns) - risk_free_rate) / daily_std if daily_std != 0 else 0.0

        # Calculate deviation
        self.deviation = np.std(daily_returns)

        # Calculate Sortino ratio
        downside_returns = np.where(daily_returns < 0, daily_returns, 0)
        downside_std = np.std(downside_returns)
        self.sortino_ratio = (np.mean(daily_returns) - risk_free_rate) / downside_std if downside_std != 0 else 0.0

        # Save the changes to the database
        db.session.commit()

    def update_balance(self):
        print("Updating balance for user with ID:", self.id)
        assets_json = []
        for exchange in self.exchanges.all():
            try:
                api_key,api_secret,password = exchange.get_creds()
                if exchange.password:
                    exchangeNow = getattr(ccxt, exchange.name)({
                        'apiKey': api_key,
                        'secret': api_secret,
                        'password':password,
                    })
                else:
                    exchangeNow = getattr(ccxt, exchange.name)({
                        'apiKey': api_key,
                        'secret': api_secret,
                    })
                if exchange.demo:
                    exchangeNow.set_sandbox_mode(True)

                time.sleep (exchangeNow.describe()['rateLimit'] / 1000)
                balance = exchangeNow.fetch_balance()
                
                #totBalUSD = 0
                #totBalBTC = 0
                '''for asset, amount in balance["total"].items():
                    price = getPrice_assets(exchange.name,asset+'/USDT')
                    totBalUSD = totBalUSD + amount*price

                for asset, amount in balance["total"].items():
                    price = getPrice_assets(exchange.name,asset+'/BTC')
                    totBalBTC = totBalBTC + amount*price'''

                
                BTCUSDT = exchangeNow.fetch_ticker('BTC/USDT')['last']
                print(BTCUSDT)
                print("99999999999999999999")
                #BTCUSDT = getPrice_assets(exchange.name,'BTC/USDT')
                for asset, amount in balance["total"].items():
                    price = getPrice_assets(exchange.name,asset+'/USDT')
                    #price2 = getPrice_assets(exchange.name,asset+'/BTC')
                    if BTCUSDT != 0:
                        price2 = price/BTCUSDT
                    else:
                        price2 = 0
                    if not price:
                        price = 0
                    if not price2:
                        price2=0
                    if check_assets_json(assets_json, asset):
                        for asset_json in assets_json:
                            if asset_json['currency'] == asset:
                                asset_json['free'] += balance["free"][asset]
                                asset_json['used'] += balance["used"][asset]
                                asset_json['total'] += amount
                                asset_json['eqUSD'] += amount*price
                                asset_json['eqBTC'] += amount*price2
                    else:
                        assets_json.append({"currency":asset,"free":balance["free"][asset],"used":balance["used"][asset],"total":amount,"price":price,'eqUSD':amount*price,'eqBTC':amount*price2})
            except Exception as e:
                print(f'Error fetching balance for {exchange.name}: {e}')

        totBalUSD = 0
        totBalBTC = 0
        for asset_json in assets_json:
            totBalUSD = totBalUSD + asset_json['eqUSD']
            totBalBTC = totBalBTC + asset_json['eqBTC']

        new_balance_usd = totBalUSD
        new_balance_btc = totBalBTC
        '''if getPrice_assets(exchange.name,'BTC/USDT') != 0:
            new_balance_btc = totBalUSD / getPrice_assets(exchange.name,'BTC/USDT')'''
        self.balance_usd = new_balance_usd
        self.balance_btc = new_balance_btc

        # Create a new BalanceHistory record
        if len(self.balance_history.all()) != 0:
            if self.balance_history.all()[-1].balance_usd != new_balance_usd or self.balance_history.all()[-1].balance_btc != new_balance_btc:
                balance_history = BalanceHistory(owner_id=self.id, balance_usd=new_balance_usd, balance_btc=new_balance_btc)
                db.session.add(balance_history)
                self.balance_history.append(balance_history)
        else:
            balance_history = BalanceHistory(owner_id=self.id, balance_usd=new_balance_usd, balance_btc=new_balance_btc)
            db.session.add(balance_history)
            self.balance_history.append(balance_history)

        # Calculate and update the profit
        self.update_profit()

        db.session.commit()

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
    users = db.relationship('User')

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

    def __init__(self,subject, user_id, status="open", messages=[]):
        self.subject = subject
        self.user_id = user_id
        self.status = status
        self.messages = messages

    def serialize(self):
        return {
            'id': self.id,
            'subject': self.subject,
            'status': self.status,
            'user': User.query.filter(User.id == self.user_id).first().serialize(),
            'messages':[message.serialize() for message in Message.query.filter(Message.ticket_id == self.id).all()],
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean)
    ticket = db.relationship('Ticket')
    user_id = db.Column(db.Integer, nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self,content, user_id, ticket_id, is_admin, created_at=datetime.utcnow):
        self.content = content
        self.user_id = user_id
        self.ticket_id = ticket_id
        self.created_at = created_at
        self.is_admin = is_admin

    def serialize(self):
        return {
            'id': self.id,
            'content': self.content,
            'is_admin': self.is_admin,
            'user_id': self.user_id,
            'user': User.query.filter(User.id == self.user_id).first().serialize(),
            'ticket_id': self.ticket_id,
            #'ticket': Ticket.query.filter(Ticket.id == self.ticket_id).first().serialize(),
            'created_at': self.created_at,
            "subject": Ticket.query.filter(Ticket.id == self.ticket_id).first().subject,
        }
    
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.relationship('Category')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
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
        self.lang = lang

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
    
    def serialize(self):
        return {
            'id': self.id,
            'title': self.title,
            'views': self.views,
            'img': self.img,
            'title_ar': self.title_ar,
            'posts':[post.serialize() for post in Post.query.filter(Post.category_id == self.id).all()],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class BalanceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.relationship('User')
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    balance_usd = db.Column(db.Float)
    balance_btc = db.Column(db.Float)
    balance_usd24h = db.Column(db.Float)
    balance_btc24h = db.Column(db.Float)
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

class BotHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner = db.relationship('User')
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
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
    owner = db.relationship('User')
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
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
    base_currency = db.Column(db.String(10))
    quote_currency = db.Column(db.String(10))
    allocation = db.Column(db.Float)
    conditions = db.Column(db.JSON)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    buy_price = db.Column(db.Float)
    bought_price = db.Column(db.Float)
    buy_trigger_price = db.Column(db.Float)
    order_type = db.Column(db.String(10))
    units = db.Column(db.Float)
    amount = db.Column(db.Float)
    stop_loss = db.Column(db.Boolean,default=False)
    take_profit = db.Column(db.Boolean,default=False)
    stop_loss_type = db.Column(db.String(10))
    stop_loss_price_percent = db.Column(db.Float)
    stop_loss_price = db.Column(db.Float)
    trailing_take_profit = db.Column(db.Boolean,default=False)
    trailing_stop_loss = db.Column(db.Boolean,default=False)
    last_take_profit = db.Column(db.Boolean,default=False)
    take_profit_index = db.Column(db.Integer, default=0)
    trailing_deviation = db.Column(db.Float)
    take_profit_quantities = db.Column(db.JSON)
    tpTriggerType = db.Column(db.String(10))
    trailing_order_id = db.Column(db.Integer)
    buy_order_id = db.Column(db.Integer)
    sell_order_ids = db.Column(db.JSON)
    stop_loss_id = db.Column(db.Integer)
    last_take_profit_id = db.Column(db.Integer)
    last_price = db.Column(db.Float,default=0.0)
    isActive = db.Column(db.Boolean,default=True)
    deal_started = db.Column(db.Boolean,default=False)
    stop_loss_time_out = db.Column(db.Boolean,default=False)
    stop_loss_time_out_runned = db.Column(db.Boolean,default=False)
    stop_loss_time_out_time = db.Column(db.Integer)
    move_to_break_even = db.Column(db.Boolean,default=False)
    total_profit = db.Column(db.Float,default=0.0)
    total_profit_percent = db.Column(db.Float,default=0.0)
    last_total_profit_time = db.Column(db.DateTime, default=datetime.utcnow)
    price_now = db.Column(db.Float)
    use_assets = db.Column(db.Boolean,default=False)
    is_hidden = db.Column(db.Boolean,default=False)
    transactions = db.relationship('Transaction',backref='transactions_owned_sma',lazy='dynamic', cascade='all, delete')
    
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
        self.take_profit_quantities = take_profit_quantities
        self.tpTriggerType = tpTriggerType
        self.trailing_deviation = trailing_deviation
        self.units = units
        self.amount = amount
        self.order_type = order_type
        self.sell_order_ids = sell_order_ids
        self.trailing_order_id = trailing_order_id
        self.buy_order_id = buy_order_id
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

        
    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'strategy': self.strategy,
            'exchange': self.exchange,
            'base_currency': self.base_currency,
            'quote_currency': self.quote_currency,
            'allocation': self.allocation,
            'conditions': self.conditions,
            'buy_price': round(self.buy_price, 2),
            'order_type': self.order_type,
            'units': self.units,
            'amount': self.amount,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'last_price': self.price_now,
            'price_now':self.last_price if self.last_price else self.buy_price,
            'stop_loss_price': round(self.stop_loss_price, 2),
            'trailing_take_profit': self.trailing_take_profit,
            'take_profit_quantities': self.take_profit_quantities,
            'created_at': self.created_at.isoformat(),
            'exchange' : self.exchange,
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
            'total_profit': self.total_profit,
            'total_profit_percent': self.total_profit_percent,
            'last_total_profit_time': self.last_total_profit_time.isoformat() if self.last_total_profit_time else None,
            'take_profit_index': self.take_profit_index,
            'use_assets': self.use_assets,
            'transactions':[transaction.serialize() for transaction in Transaction.query.filter(Transaction.sma_id == self.id).all()],

        }

class Exchange(db.Model,UserMixin):
    __tablename__ = "exchanges"
    id = db.Column('exchange_id',db.Integer, primary_key=True)
    number = db.Column(db.Integer())
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'))
    owner = db.relationship('User')
    name = db.Column(db.String(120))
    api_key = db.Column(db.String(120))
    api_secret = db.Column(db.String(120))
    password = db.Column(db.String(120))
    demo = db.Column(db.Boolean,default=False)
    isActive = db.Column(db.Boolean,default=False)

    def set_creds(self, api_key, api_secret, password):
        fernet_key = os.environ.get('FERNET_KEY', '')
        if not fernet_key:
            raise RuntimeError('FERNET_KEY env var is required')
        cipher_suite = Fernet(fernet_key.encode())
        encrypted_api_key = cipher_suite.encrypt(api_key.encode())
        encrypted_api_secret = cipher_suite.encrypt(api_secret.encode())
        encrypted_password = cipher_suite.encrypt(password.encode())
        self.api_key = encrypted_api_key.decode()
        self.api_secret = encrypted_api_secret.decode()
        self.password = encrypted_password.decode()

    def get_creds(self):
        fernet_key = os.environ.get('FERNET_KEY', '')
        if not fernet_key:
            raise RuntimeError('FERNET_KEY env var is required')
        cipher_suite = Fernet(fernet_key.encode())
        decrypted_api_key = cipher_suite.decrypt(self.api_key.encode())
        decrypted_api_secret = cipher_suite.decrypt(self.api_secret.encode())
        decrypted_password = cipher_suite.decrypt(self.password.encode())
        return decrypted_api_key.decode(), decrypted_api_secret.decode(), decrypted_password.decode()

    def serialize(self):
        # Never expose credential material (even encrypted) to the frontend.
        return {
            'id': self.id,
            'number': self.number,
            'owner_id': self.owner_id,
            'name': self.name,
            'has_api_key': bool(self.api_key),
            'has_api_secret': bool(self.api_secret),
            'has_password': bool(self.password),
            'demo': self.demo,
            'isActive': self.isActive,
        }


class Notification(db.Model,UserMixin):
    __tablename__ = "notifications"
    id = db.Column('notification_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'))
    owner = db.relationship('User')
    content = db.Column(db.String())
    type = db.Column(db.String(120))
    date = db.Column(db.String(120))
    exchange = db.Column(db.String(120))
    read = db.Column(db.Boolean,default=False)

class Bot(db.Model,UserMixin):
    __tablename__ = "bots"
    id = db.Column('bot_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'))
    owner = db.relationship('User')
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
    last_open_trade_time = db.Column(db.DateTime,default=datetime.utcnow())
    cooldown_between_deals = db.Column(db.Integer,default=0)
    open_deals_and_stop = db.Column(db.Integer,default=0)
    total_trades = db.Column(db.Integer,default=0)
    total_profit = db.Column(db.Float,default=0.0)
    last_total_profit_time = db.Column(db.DateTime,default=datetime.utcnow())
    close_deal_action = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    safetyOrders = db.relationship('SafetyOrder',backref='safetyOrders_owned',lazy='dynamic', cascade='all, delete')
    transactions = db.relationship('Transaction',backref='transactions_owned',lazy='dynamic', cascade='all, delete')
    timeout_type = db.Column(db.Integer)
    amount_type = db.Column(db.Integer)
    safety_orders_size_type = db.Column(db.Integer)
    is_hidden = db.Column(db.Boolean,default=False)
    
    

class SafetyOrder(db.Model,UserMixin):
    __tablename__ = "safetyOrders"
    id = db.Column('safetyOrders_id',db.Integer, primary_key=True)
    orderId = db.Column(db.Integer())
    owner_id = db.Column(db.Integer(),db.ForeignKey('bots.bot_id'))
    owner = db.relationship('Bot')
    amount = db.Column(db.Float)
    price = db.Column(db.Float)
    isFilled = db.Column(db.Boolean,default=False)
    isOpened = db.Column(db.Boolean,default=False)
    isClosed = db.Column(db.Boolean,default=False)

class Chat(db.Model,UserMixin):
    __tablename__ = "chats"
    id = db.Column('chat_id',db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer(),db.ForeignKey('users.id'))
    owner = db.relationship('User')
    message = db.Column(db.String(255))
    role = db.Column(db.String(20))
    
# Load user function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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

