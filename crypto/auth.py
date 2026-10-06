from flask import render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from crypto import app, db, jwt_required
from crypto.models import User,Ticket,Message,Post,Category,Exchange2,Bot,UserCount,BotCount,Pair, Transaction, Subscription, TransactionHistory,Exchange
from flask_mail import Mail, Message as MailMessage
from crypto import mail
import pyotp
import ipaddress
import json
import datetime
from flask_httpauth import HTTPBasicAuth
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
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from crypto.notify import send_notification
import ccxt
import stripe
import os
from datetime import datetime
from crypto import get_current_user
from datetime import timedelta

stripe.api_key = os.environ.get('STRIPE_API_KEY', '')

from flask_jwt_extended import (
    JWTManager, create_access_token,
    get_jwt_identity, verify_jwt_in_request
)
from functools import wraps
import math


def mail_verification_required():
    """Kill-switch: REQUIRE_EMAIL_VERIFICATION=1 enforces email verification
    on login/register. Default 0 (off) until real SMTP creds are configured."""
    return os.environ.get('REQUIRE_EMAIL_VERIFICATION', '0') == '1'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin' not in session or not session['admin']:
            return redirect(url_for('login'))  # Redirect to the login page or appropriate route
        return f(*args, **kwargs)
    return decorated_function

'''auth = HTTPBasicAuth()
@auth.verify_password
def verify_password(username,password):
    # Legacy stub — real check lives in crypto/__init__.py via ADMIN_STREAM_PASSWORD env.
    return False'''

'''@app.route('/admin/login')
@admin_required
def admin_login():
    return render_template('lock-screen.html')'''

@app.route('/admin')
@admin_required
def admin_home():
    tickets = []
    volume = 0 
    for ticket in Ticket.query.all():
        if not ticket.messages.all()[-1].serialize()["is_admin"]:
            tickets.append(ticket)
    print(tickets)
    for transaction in Transaction.query.filter(Transaction.created_at > datetime.utcnow() - timedelta(days=1)).all():
        volume += transaction.value
    return render_template('admin_home.html',
                            bots_count= Bot.query.filter(Bot.isActive==True).count(),
                            users_count=User.query.count(),
                            tickets_opened=len(tickets),
                            bots_history = json.dumps([bot.serialize() for bot in BotCount.query.all()]),
                            users_history = json.dumps([user.serialize() for user in UserCount.query.all()]),
                            transactions_count = Transaction.query.count(),
                            transactions_sell_count = Transaction.query.filter(Transaction.type=="sell").count(),
                            transactions_buy_count = Transaction.query.filter(Transaction.type=="buy").count(), 
                            transactions_volume_24h = round(volume,2),
                            transactions_history = json.dumps([transaction.serialize() for transaction in TransactionHistory.query.all()]),
                            free_count = User.query.filter(User.subType_id==1).count(),
                            advanced_count = User.query.filter(User.subType_id==2).count(),
                            pro_count = User.query.filter(User.subType_id==3).count(),
                           )

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    return render_template('admin_transactions.html',transactions=Transaction.query.all(),exchanges = Exchange2.query.filter(Exchange2.isActive==True).all())

# exchanges activatign and deactivating
@app.route('/admin/exchanges', methods=['GET'])
@admin_required
def admin_exchanges_get():
    exchanges_json = []
    for exchange in Exchange2.query.all():
        try:
            has_json = getattr(ccxt, exchange.exchange)().describe()['has']
            if 'fetchOHLCV' in has_json and 'fetchTickers' in has_json and 'fetchBalance' in has_json and 'createOrder' in has_json and 'cancelOrder' in has_json:
                if has_json['cancelOrder'] and has_json['createOrder'] and has_json['fetchBalance'] and has_json['fetchOHLCV'] and has_json['fetchTickers']:
                    exchanges_json.append(exchange.serialize())
            exchanges_json[-1]['has'] = has_json
        except:
            pass
        '''{'CORS': None,
                'spot': True,
                'margin': True,
                'swap': True,
                'future': True,
                'option': True,
                'addMargin': True,
                'borrowMargin': True,
                'cancelAllOrders': True,
                'cancelOrder': True,
                'cancelOrders': None,
                'createDepositAddress': False,
                'createOrder': True,
                'createPostOnlyOrder': True,
                'createReduceOnlyOrder': True,
                'createStopLimitOrder': True,
                'createStopMarketOrder': False,
                'createStopOrder': True,
                'editOrder': True,
                'fetchAccounts': None,
                'fetchBalance': True,
                'fetchBidsAsks': True,
                'fetchBorrowInterest': True,
                'fetchBorrowRate': True,
                'fetchBorrowRateHistories': False,
                'fetchBorrowRateHistory': True,
                'fetchBorrowRates': False,
                'fetchBorrowRatesPerSymbol': False,
                'fetchCanceledOrders': 'emulated',
                'fetchClosedOrder': False,
                'fetchClosedOrders': 'emulated',
                'fetchCurrencies': True,
                'fetchDeposit': False,
                'fetchDepositAddress': True,
                'fetchDepositAddresses': False,
                'fetchDepositAddressesByNetwork': False,
                'fetchDeposits': True,
                'fetchDepositsWithdrawals': False,
                'fetchDepositWithdrawFee': 'emulated',
                'fetchDepositWithdrawFees': True,
                'fetchFundingHistory': True,
                'fetchFundingRate': True,
                'fetchFundingRateHistory': True,
                'fetchFundingRates': True,
                'fetchIndexOHLCV': True,
                'fetchL3OrderBook': None,
                'fetchLastPrices': True,
                'fetchLedger': True,
                'fetchLeverage': False,
                'fetchLeverageTiers': True,
                'fetchMarketLeverageTiers': 'emulated',
                'fetchMarkets': True,
                'fetchMarkOHLCV': True,
                'fetchMyTrades': True,
                'fetchOHLCV': True,
                'fetchOpenInterest': True,
                'fetchOpenInterestHistory': True,
                'fetchOpenOrder': False,
                'fetchOpenOrders': True,
                'fetchOrder': True,
                'fetchOrderBook': True,
                'fetchOrderBooks': False,
                'fetchOrders': True,
                'fetchOrderTrades': True,
                'fetchPosition': True,
                'fetchPositions': True,
                'fetchPositionsRisk': True,
                'fetchPremiumIndexOHLCV': False,
                'fetchSettlementHistory': True,
                'fetchStatus': True,
                'fetchTicker': True,
                'fetchTickers': True,
                'fetchTime': True,
                'fetchTrades': True,
                'fetchTradingFee': True,
                'fetchTradingFees': True,
                'fetchTradingLimits': None,
                'fetchTransactionFee': None,
                'fetchTransactionFees': True,
                'fetchTransactions': False,
                'fetchTransfers': True,
                'fetchVolatilityHistory': False,
                'fetchWithdrawal': False,
                'fetchWithdrawals': True,
                'fetchWithdrawalWhitelist': False,
                'reduceMargin': True,
                'repayMargin': True,
                'setLeverage': True,
                'setMargin': False,
                'setMarginMode': True,
                'setPositionMode': True,
                'signIn': False,
                'transfer': True,
                'withdraw': True,
        }'''
        
    return render_template('admin_exchanges.html',exchanges=exchanges_json)

@app.route('/toggle_exchange', methods=['POST'])
@admin_required
def toggle_exchange():
    exchange = request.json['exchange']
    status = request.json['status']
    Exchange2.query.filter(Exchange2.exchange==exchange).update(dict(isActive=status))
    db.session.commit()

@app.route('/toggle_pair', methods=['POST'])
@admin_required
def toggle_pair():
    pair = request.json['pair']
    status = request.json['status']
    Pair.query.filter(Pair.pair==pair).update(dict(isActive=status))
    db.session.commit()

@app.route('/admin/list')
@admin_required
def admin_table():
    users=User.query.all()
    users_json = json.dumps([user.serialize() for user in users])
    return render_template('admin_user_list.html', users=users_json,subs=Subscription.query.all())

@app.route('/admin/blog')
@admin_required
def admin_blog():
    return render_template('admin_blog.html',posts=Post.query.all(),cats=Category.query.all())

@app.route('/admin/support')
@admin_required
def admin_support():
    return render_template('admin_support.html')

import time

@app.route('/admin/pairs')
@admin_required
def admin_pairs():
    pairs = []

    for pair in Pair.query.all():
        pairs.append(pair.serialize())

    return render_template('admin_pairs.html',pairs=pairs)

###################################################pricing####################################################

@app.route('/admin/pricing', methods=['GET'])
@admin_required
def admin_pricing():
    return render_template('admin_pricing.html',subscriptions=Subscription.query.all())

@app.route('/admin/pricing', methods=['POST'])
@admin_required
def admin_pricing_post():
    max_sma = request.json.get('max_sma')
    max_bots = request.json.get('max_bots')
    price = request.json.get('price')
    stripe_id = request.json.get('stripe_id')
    name_en = request.json.get('name_en')
    name_ar = request.json.get('name_ar')
    trial_days = request.json.get('trial_days')
    if max_sma == None:
        max_sma = math.inf
    if max_bots == None:
        max_bots = math.inf
    id = request.json.get('id')
    subscription = Subscription.query.filter(Subscription.id == id).first()
    subscription.max_sma = max_sma
    subscription.max_bots = max_bots
    subscription.price = price
    subscription.stripe_id = stripe_id
    subscription.type = name_en
    subscription.type_ar = name_ar
    subscription.trial_days = trial_days
    db.session.commit()
    return jsonify({'message':'the subscription has been added','ok':True}), 201

@app.route('/api/admin/v1/subscribtion/edit', methods=['POST'])
@admin_required
def admin_subscribtion_edit():
    user_id = request.json.get('user_id')
    sub_type_id = request.json.get('sub_type_id')
    user = User.query.filter(User.id == user_id).first()
    subscription = Subscription.query.filter(Subscription.id == sub_type_id).first()
    user.subType = subscription
    user.subType_id = subscription.id
    db.session.commit()
    return jsonify({'message':'the subscription has been changed','ok':True})

@app.route("/api/v1/get_subscriptions_and_invoices", methods=['GET'])
@admin_required
def get_subscriptions_and_invoices_user():
    try:
        user = get_current_user()
        if user.stripe_customer_id:
            # Retrieve all subscriptions (including canceled ones) associated with the customer ID
            subscriptions = stripe.Subscription.list(customer=user.stripe_customer_id, status='all')
            # Extract relevant information from each subscription
            subscription_list = []
            for subscription in subscriptions.data:
                subscription_data = {
                    'subscription_id': subscription.id,
                    'status': subscription.status,
                    'current_period_start': subscription.current_period_start,
                    'current_period_end': subscription.current_period_end,
                    # Add other relevant subscription information here
                }
                subscription_list.append(subscription_data)

            # Retrieve the invoices associated with the customer ID
            invoices = stripe.Invoice.list(customer=user.stripe_customer_id)
            
            # Extract relevant information from each invoice
            invoice_list = []
            for invoice in invoices.data:
                invoice_data = {
                    'invoice_id': invoice.id,
                    'amount_due': invoice.amount_due,
                    'status': invoice.status,
                    'created': invoice.created,
                    'billing_reason': invoice.billing_reason,
                    'paid': invoice.paid,
                    'currency': invoice.currency,
                    'url': invoice.lines.url,
                    # Add other relevant invoice information here
                }
                invoice_list.append(invoice_data)

            return jsonify({'subscriptions': subscription_list, 'invoices': invoice_list, 'ok': True})
        else:
            return jsonify({'message': 'User does not have a Stripe customer ID', 'ok': False}), 403
    except Exception as e:
        return jsonify({'message': str(e), 'ok': False}), 500

###################################################tickets##################################################

@app.route('/admin/support/tickets', methods=['GET'])
def admin_support_tickets_get():
    if request.args.get("user_id"):
        tickets_json = [ticket.serialize() for ticket in Ticket.query.filter(Ticket.user_id==int(request.args.get("user_id"))).all()]
    else:
      tickets_json = [ticket.serialize() for ticket in Ticket.query.all()]
    return jsonify(tickets_json)

@app.route('/admin/support/messages', methods=['GET'])
def admin_support_messages_get():
    ticket_id = request.args.get('ticket_id')
    messages_json = [message.serialize() for message in Ticket.query.filter(Ticket.id == ticket_id).first().messages.all()]
    return jsonify(messages_json)

@app.route('/admin/support/tickets', methods=['POST'])
def open_ticket():
    subject = request.json.get('subject')
    user_id = current_user.id
    ticket = Ticket(subject=subject, user_id=user_id)
    message = Message(content=request.json.get('content'), user_id=user_id, ticket_id=ticket.id, is_admin=False,created_at=datetime.utcnow())
    ticket.messages.append(message)
    ticket.updated_at = datetime.utcnow()
    db.session.add(message)
    db.session.add(ticket)
    db.session.commit()

    return jsonify(ticket.serialize()), 201

@app.route('/admin/support/tickets/<int:ticket_id>/close', methods=['PUT'])
@admin_required
def close_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)

    if ticket.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    ticket.status = 'closed'
    db.session.commit()

    return jsonify(ticket.serialize())

@app.route('/admin/support/tickets/<int:ticket_id>/messages', methods=['POST'])
def send_message(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    content = request.json['content']
    is_admin = bool(request.json['is_admin'])
    if is_admin == False:
        user_id = current_user.id
    else:
        user_id = request.json['user_id']
    print(request.json)
    ticket.updated_at = datetime.utcnow()
    if is_admin:
        send_notification(f"you have a new message from the support team ({content})***system",user_id)
    message = Message(content=content, user_id=user_id, ticket_id=ticket.id, is_admin=is_admin,created_at=datetime.utcnow())
    db.session.add(message)
    ticket.updated_at = datetime.utcnow()
    ticket.messages.append(message)
    db.session.commit()

    return jsonify(message.serialize()), 201

@app.route('/admin/support/tickets/<int:ticket_id>/messages/<int:message_id>/reply', methods=['POST'])
@admin_required
def reply_to_message(ticket_id, message_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    message = Message.query.get_or_404(message_id)
    content = request.json.get('content')
    user_id = current_user.id

    if ticket.id != message.ticket_id:
        return jsonify({'error': 'Invalid message for the ticket'}), 400

    reply = Message(content=content, user_id=user_id, ticket_id=ticket.id)
    ticket.updated_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()

    return jsonify(reply.serialize()), 201

###################################################posts######################################################

@app.route('/admin/blog/posts', methods=['GET'])
def admin_blog_posts_get():
    if request.args.get("post_id"):
        posts_json = Post.query.filter(Post.id==int(request.args.get("post_id"))).first().serialize()
    else:
        posts_json = [post.serialize() for post in Post.query.all()]
    return jsonify(posts_json)

@app.route('/admin/blog/posts', methods=['POST'])
def admin_blog_posts_post():
    title = request.json.get('title')
    content = request.json.get('content')
    writer = request.json.get('writer')
    category_id = request.json.get('category_id')

    post = Post(title=title, content=content, writer=writer, img=request.json.get('img'), lang=request.json.get('lang'))
    Category.query.filter(Category.id == category_id).first().posts.append(post)
    
    db.session.add(post)
    db.session.commit()

    return jsonify({'message':'the post has been published','ok':True,'id':post.id}), 201

@app.route('/admin/blog/posts/<int:post_id>', methods=['PUT'])
def admin_blog_posts_put(post_id):
    post = Post.query.get_or_404(post_id)
    title = request.json.get('title')
    content = request.json.get('content')
    writer = request.json.get('writer')

    post.title = title
    post.content = content
    post.writer = writer
    post.img = request.json.get('img')
    db.session.commit()

    return jsonify({'message':'the post has been updated','ok':True}), 201

@app.route('/admin/blog/posts/<int:post_id>', methods=['DELETE'])
def admin_blog_posts_delete(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        db.session.delete(post)
        db.session.commit()
        return jsonify({'message':'the post has been deleted','ok':True}), 201
    except:
        return jsonify({'message':'the post has not been deleted','ok':False}), 201

@app.route('/admin/blog/cats', methods=['POST'])
def admin_blog_cats_new():
    cat = Category(title=request.json.get('title'),img=request.json.get('img'),title_ar=request.json.get('title_ar'))
    db.session.add(cat)
    db.session.commit()
    return jsonify({'message':'the category has been created','ok':True,'id':cat.id}), 201

@app.route('/admin/blog/cats/<int:cat_id>', methods=['DELETE'])
def admin_blog_cats_del(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()	
    return jsonify({'message':'the category has been deleted','ok':True}), 201

@app.route('/admin/blog/cats/edit/<int:cat_id>', methods=['POST'])
def admin_blog_cats_edit(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat.title = request.json.get('title')
    cat.img = request.json.get('img')
    db.session.commit()	
    return jsonify({'message':'the category has been edited','ok':True}), 201
###############################################################################################################

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = None
        password = None
        remember = None
        admin = request.json['admin']
        if admin:
            email = request.json['email']
            password = request.json['password']
            if email == 'admin' and password == os.environ.get('ADMIN_PASSWORD', ''):
                admin_email = os.environ.get('ADMIN_EMAIL', '')
                # Generate the OTP
                otp = generate_otp(admin_email)

                # Send email with OTP
                send_otp_email(admin_email, otp,"ip login notification","A new ip address has been logged in to your account, Use this OTP code in the login process:")
                
                # Store the OTP in the session
                session['otp'] = otp
                session['email'] = "admin"
                return jsonify({'message': 'Admin logged in successfully','ok':True}), 200
            else:
                return jsonify({'message': 'Invalid username or password'}), 401
        else:
            email = request.json['email']
            password = request.json['password']
            remember = request.json.get('remember')
            user = User.query.filter_by(email=email).first()

            if user and user.check_password(password):
                if mail_verification_required() and user.is_verified == False:
                    token = generate_verification_token(user.email)
                    send_otp_email(
                        user.email,
                        None,
                        "PulseTrade Email Verification",
                        "PulseTrade Email Verification: click this link to complete the verification process:",
                        f'http://127.0.0.1:5000/verify_email/{token}',
                    )
                    return jsonify({"message": "Please Check your email to verify your email address", "ok": False})
                
                #if user.ip_check == "true" and ( user.last_ip is None or user.last_ip != request.remote_addr):
                if user.ip_check == "true":
                    client_ip = request.remote_addr
                    
                    # Perform IP address validation
                    if validate_ip_address(client_ip):
                        
                        # Update the last IP address in the user object
                        user.last_ip = client_ip
                        db.session.commit()

                        # Generate the OTP
                        otp = generate_otp(user.email)
                        
                        # Send email with OTP
                        send_otp_email(user.email, otp,"ip login notification","A new ip address has been logged in to your account, Use this OTP code in the login process:")
                        
                        # Store the OTP in the session
                        session['otp'] = otp
                        session['email'] = user.email
                        
                        # Redirect to the OTP verification page
                        return redirect(url_for('verify_otp'))
                    
                    else:

                        return jsonify({'message':'Access denied from your IP address.','ok':False})
                else:
                    # Perform the login action
                    login_user(user, remember=remember)
                    access_token = create_access_token(identity={'email': user.email, 'role': 'user'})
                    return jsonify(access_token=access_token,ok=True)
                
            return jsonify({'message':'Invalid email or password.','ok':False})
            
    return render_template('sign-in.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        otp = request.form['otp']
        email = session.get('email')
        stored_otp = session.get('otp')
        if email and stored_otp and otp == stored_otp:
            # Delete the stored OTP and email from the session
            session.pop('otp', None)
            session.pop('email', None)
            
            # Perform the login action
            if email != "admin":
                user = User.query.filter_by(email=email).first()
                login_user(user, remember=True)
                access_token = create_access_token(identity={'email': user.email, 'role': 'user'})
                return jsonify(access_token=access_token,ok=True)
            else:
                session['admin'] = True
                return redirect(url_for('admin_home'))
        
        flash('Invalid OTP')
    
    return render_template('verify_otp2.html')

@app.route('/resend_otp')
def resend_otp():
    if session.get('email'):
        otp = generate_otp(session.get('email'))
        send_otp_email(session.get('email') if session.get('email') != "admin" else os.environ.get('ADMIN_EMAIL', ''), otp,"ip login notification","A new ip address has been logged in to your account, Use this OTP code in the login process:")
        session['otp'] = otp
        flash('OTP resent')
    return redirect(url_for('verify_otp'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.json['email']
        firstName = request.json['firstName']
        lastName = request.json['lastName']
        password = request.json['password']
        confirm_password = request.json['confirm_password']
        if password != confirm_password:
            return jsonify({'message':'Passwords do not match.','ok':False})
        if User.query.filter_by(email=email).first():
            return jsonify({'message':'Email already taken.','ok':False})

        user = User(email=email, password=password, firstName=firstName, lastName=lastName)
        subscription = Subscription.query.filter_by(type="free").first()
        if subscription is None:
            # Fresh DB without seed data — create the default free plan inline.
            subscription = Subscription(type='free', max_bots=5, max_sma=10)
            db.session.add(subscription)
            db.session.flush()
        user.subType = subscription
        user.subType_id = subscription.id
        subscription.users.append(user)
        db.session.add(user)
        db.session.commit()
        if mail_verification_required():
            # Generate the verification token
            token = generate_verification_token(user.email)

            try:
                send_otp_email(user.email, None,"PulseTrade Email Verification","PulseTrade Email Verification: click this link to complete the verification process:",f'http://127.0.0.1:5000/verify_email/{token}')
            except Exception as e:
                # Mail server not configured — account already created,
                # user can verify later via /resend_otp once mail works.
                print(f"verification email skipped: {e}")
        else:
            user.is_verified = True
            db.session.commit()

        return jsonify({'message':'Registration successful. Please check your email to verify your account.','ok':True})
    
    return render_template('sign-up.html')

def generate_verification_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

@app.route('/verify_email/<token>')
def verify_email(token):
    try:
        serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=300)
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_verified = True
            db.session.commit()
            flash('Email verification successful. You can now log in.')
        else:
            flash('Invalid verification token.')
    except Exception as e:
        flash('Invalid verification token.')
    
    return redirect(url_for('login'))

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password_token(token):
    '''if current_user.is_authenticated:
        return redirect(url_for('exchanges'))'''
    
    # Verify the reset password token
    try:
        s = Serializer(app.config['SECRET_KEY'])
        user = User.query.get(s.loads(token)['user_id'])
    except (BadSignature, SignatureExpired):
        flash('Invalid or expired token. Please request a new password reset.')
        return redirect(url_for('reset_password'))
    
    if request.method == 'POST':
        # Handle the password reset form submission
        password = request.json['password']
        confirm_password = request.json['confirm_password']
        if password != confirm_password:
            return jsonify({'message': 'Passwords do not match. Please try again.'})
        
        # Set the new password for the user
        user.set_password(password)
        db.session.commit()

        login_user(user)
        
        #flash('Your password has been reset successfully. You can now log in with your new password.')
        return jsonify({'message': 'Your Password has been changed','ok':True})
    
    return render_template('reset_password_token.html', token=token)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.json['email']
        user = User.query.filter_by(email=email).first()
        if user:
            send_password_reset_email(user)
            return jsonify({'message': 'Instructions sent to email','ok':True})
        return jsonify({'message': 'Email not found'})
    else:
        return render_template('reset_password.html')


@app.route('/logout')
@jwt_required
def logout():
    logout_user()
    return redirect(url_for('exchanges'))

@app.route('/api/v1/logout', methods=['POST'])
@jwt_required
def logout2():
    logout_user()
    return redirect(url_for('exchanges'))

@app.route('/logout_admin')
@admin_required
def logout_admin():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/send_mail_from_admin', methods=['POST'])
@admin_required
def send_mail_from_admin():
    subject = request.json['subject']
    body = request.json['body']
    if 'email' in request.json:
        send_otp_email(request.json['email'], None,subject,body,None)
    else:
        for user in User.query.all():
            send_otp_email(user.email, None,subject,body,None)
    return jsonify({'message': 'Email sent successfully','ok':True})

# Define a function to send a password reset email
def send_password_reset_email(user):
    token = user.get_reset_password_token()
    msg = MailMessage('Password Reset Request', sender='noreply@example.com', recipients=[user.email])
    msg.body = f'''To reset your password, please visit the following link:
{url_for('reset_password_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    try:
        mail.send(msg)
    except Exception as e:
        # Mail server not configured — don't crash the request.
        print(f"password-reset email skipped: {e}")

def generate_otp(email):
    totp = pyotp.TOTP("JBSWY3DPEHPK3PXP", interval=300)
    return totp.now()

def send_otp_email(to_email, otp,msg_title,msg_body,link=None):
    msg = MailMessage(msg_title, sender='noreply@example.com', recipients=[to_email])
    #msg.body = f'Your OTP is: {otp}'
    #send html code here
    msg.html = f'''<table class="m_-8838481535829706560body" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;height:100%;width:100%;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" bgcolor="#F2F6FA">
      <tbody><tr style="vertical-align:top;padding:0" align="left">
        <td align="center" valign="top" style="word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0">
          <table class="m_-8838481535829706560show-for-large" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="68px" style="font-size:68px;line-height:68px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>
          <center style="width:100%;min-width:500px">
          

            
            <table class="m_-8838481535829706560container" align="center" style="    background: #202022;border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:center;width:500px;float:none;margin:0 auto;padding:0" bgcolor="#ffffff"><tbody><tr style="vertical-align:top;padding:0" align="left"><td style="word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left" valign="top">
              <table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="30px" style="font-size:30px;line-height:30px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>
              <table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
                <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
                  <a href="#">
                    <img class="m_-8838481535829706560header__logo CToWUd" width="100" src="https://upload.wikimedia.org/wikipedia/commons/0/0c/PulseTrade_logo_-_horizontal_version_%28default_color%29_%284%29.png" style="outline:none;text-decoration:none;max-width:100%;clear:both;display:block;width:100px;border:none" data-bit="iit">
                  </a>
                </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
              </tr></tbody></table>
              <table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="15px" style="font-size:15px;line-height:15px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>
            </td></tr></tbody></table>
            

            <table class="m_-8838481535829706560container" align="center" style="background:#202022;border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:center;width:500px;float:none;margin:0 auto;padding:0" bgcolor="#ffffff"><tbody><tr style="vertical-align:top;padding:0" align="left"><td style="word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left" valign="top">
              <table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <h1 style="color:inherit;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;word-wrap:normal;font-size:30px;margin:0 0 10px;padding:0" align="center">New IP Address Login Notification</h1>
  </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
</tr></tbody></table>

<table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="10px" style="font-size:10px;line-height:10px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>

<table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <p style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:180%;font-size:13px;margin:0;padding:0" align="left">We noticed a login attempt from a new IP. This could be due to using a dynamic IP (e.g., mobile data)</p>
  </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
</tr></tbody></table>

<table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="10px" style="font-size:10px;line-height:10px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>

<table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <p style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:180%;font-size:13px;margin:0;padding:0" align="left">Please use the confirmation code:</p>
  </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
</tr></tbody></table>

<table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <p style="color: #ff971d;font-family:Helvetica,Arial,sans-serif;font-weight:bold;line-height:180%;font-size:24px;margin:0;padding:0" align="center">
      {otp}
    </p>
  </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
</tr></tbody></table>

<table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="10px" style="font-size:10px;line-height:10px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>

<table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:445px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 55px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
<th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <p style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:180%;font-size:13px;margin:0;padding:0" align="left">
      Or confirm automatically:
    </p>
  </th>
<th class="m_-8838481535829706560expander" style="width:0;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table></th>
</tr></tbody></table>

<table class="m_-8838481535829706560row" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;display:table;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left">
  <th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
  <th class="m_-8838481535829706560small-12 m_-8838481535829706560columns" style="width:278.3333333333px;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0 auto;padding:0 27.5px 10px" align="left"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left">
    <table class="m_-8838481535829706560button" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;margin:0;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td style="word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left" valign="top"><table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td style="word-wrap:break-word;border-collapse:collapse!important;color:#ffffff;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;border-radius:3px;margin:0;padding:0;border:2px none #14c8a4" align="left" bgcolor="#14C8A4" valign="top"><a href="#" style="color:#ffffff;text-decoration:none;font-family:Helvetica,Arial,sans-serif;font-weight:400;text-align:center;line-height:130%;font-size:16px;letter-spacing:1px;display:inline-block;border-radius:3px;width:100%;padding:13px 0;border:0 solid #14c8a4;background:#ff971d;" target="_blank" data-saferedirecturl="https://www.google.com/url?q=https://app.3commas.io/ahoy/messages/dvc8Myif8o7xOtwDjlLSrn718rSb2r4S/click?signature%3Df7ce8969139b998d7feb693ca669fb94bf54e0a4%26url%3Dhttps%253A%252F%252Fapp.3commas.io%252Fauth%252Fcheck_ip%253Ftoken%253D585935%2526utm_source%253Demail%2526utm_medium%253Demail%2526utm_campaign%253Dip_confirmation_email&amp;source=gmail&amp;ust=1693311844000000&amp;usg=AOvVaw093jSmdd31_kYg3HMqowuF">
      Confirm new IP Address
    </a></td></tr></tbody></table></td></tr></tbody></table>
  </th></tr></tbody></table></th>
  <th style="color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;line-height:130%;font-size:14px;margin:0;padding:0" align="left"></th>
</tr></tbody></table>

<table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="10px" style="font-size:10px;line-height:10px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>



              <table style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:left;width:100%;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="30px" style="font-size:30px;line-height:30px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>
            </td></tr></tbody></table>

            
            

            <table align="center" style="border-spacing:0;border-collapse:collapse;vertical-align:top;text-align:center;width:100%;float:none;margin:0 auto;padding:0"><tbody><tr style="vertical-align:top;padding:0" align="left"><td height="20px" style="font-size:20px;line-height:20px;word-wrap:break-word;border-collapse:collapse!important;color:white;font-family:Helvetica,Arial,sans-serif;font-weight:normal;margin:0;padding:0" align="left" valign="top">&nbsp;</td></tr></tbody></table>

          
          </center>
        </td>
      </tr>
    </tbody></table>'''
    msg.html = '''
	<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
	<html xmlns="http://www.w3.org/1999/xhtml">
	<head>
		<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1.0">
		<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
		<meta name="format-detection" content="telephone=no" /> <!-- disable auto telephone linking in iOS -->
		<title>LeadTrain</title>
		<style type="text/css">
			/* RESET STYLES */
			html { background-color:#E1E1E1; margin:0; padding:0; }
			body, #bodyTable, #bodyCell, #bodyCell{height:100% !important; margin:0; padding:0; width:100% !important;font-family:Helvetica, Arial, "Lucida Grande", sans-serif;}
			table{border-collapse:collapse;}
			table[id=bodyTable] {width:100%!important;margin:auto;max-width:500px!important;color:#7A7A7A;font-weight:normal;}
			img, a img{border:0; outline:none; text-decoration:none;height:auto; line-height:100%;}
			a {text-decoration:none !important;border-bottom: 1px solid;}
			h1, h2, h3, h4, h5, h6{color:#5F5F5F; font-weight:normal; font-family:Helvetica; font-size:20px; line-height:125%; text-align:Left; letter-spacing:normal;margin-top:0;margin-right:0;margin-bottom:10px;margin-left:0;padding-top:0;padding-bottom:0;padding-left:0;padding-right:0;}

			/* CLIENT-SPECIFIC STYLES */
			.ReadMsgBody{width:100%;} .ExternalClass{width:100%;} /* Force Hotmail/Outlook.com to display emails at full width. */
			.ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div{line-height:100%;} /* Force Hotmail/Outlook.com to display line heights normally. */
			table, td{mso-table-lspace:0pt; mso-table-rspace:0pt;} /* Remove spacing between tables in Outlook 2007 and up. */
			#outlook a{padding:0;} /* Force Outlook 2007 and up to provide a "view in browser" message. */
			img{-ms-interpolation-mode: bicubic;display:block;outline:none; text-decoration:none;} /* Force IE to smoothly render resized images. */
			body, table, td, p, a, li, blockquote{-ms-text-size-adjust:100%; -webkit-text-size-adjust:100%; font-weight:normal!important;} /* Prevent Windows- and Webkit-based mobile platforms from changing declared text sizes. */
			.ExternalClass td[class="ecxflexibleContainerBox"] h3 {padding-top: 10px !important;} /* Force hotmail to push 2-grid sub headers down */

			/* /\/\/\/\/\/\/\/\/ TEMPLATE STYLES /\/\/\/\/\/\/\/\/ */

			/* ========== Page Styles ========== */
			h1{display:block;font-size:26px;font-style:normal;font-weight:normal;line-height:100%;}
			h2{display:block;font-size:20px;font-style:normal;font-weight:normal;line-height:120%;}
			h3{display:block;font-size:17px;font-style:normal;font-weight:normal;line-height:110%;}
			h4{display:block;font-size:18px;font-style:italic;font-weight:normal;line-height:100%;}
			.flexibleImage{height:auto;}
			.linkRemoveBorder{border-bottom:0 !important;}
			table[class=flexibleContainerCellDivider] {padding-bottom:0 !important;padding-top:0 !important;}

			body, #bodyTable{background-color:#E1E1E1;}
			#emailHeader{background-color:#E1E1E1;}
			#emailBody{background-color:#FFFFFF;}
			#emailFooter{background-color:#E1E1E1;}
			.nestedContainer{background-color:#F8F8F8; border:1px solid #CCCCCC;}
			.emailButton{background-color:#205478; border-collapse:separate;}
			.buttonContent{color:#FFFFFF; font-family:Helvetica; font-size:18px; font-weight:bold; line-height:100%; padding:15px; text-align:center;}
			.buttonContent a{color:#FFFFFF; display:block; text-decoration:none!important; border:0!important;}
			.emailCalendar{background-color:#FFFFFF; border:1px solid #CCCCCC;}
			.emailCalendarMonth{background-color:#205478; color:#FFFFFF; font-family:Helvetica, Arial, sans-serif; font-size:16px; font-weight:bold; padding-top:10px; padding-bottom:10px; text-align:center;}
			.emailCalendarDay{color:#205478; font-family:Helvetica, Arial, sans-serif; font-size:60px; font-weight:bold; line-height:100%; padding-top:20px; padding-bottom:20px; text-align:center;}
			.imageContentText {margin-top: 10px;line-height:0;}
			.imageContentText a {line-height:0;}
			#invisibleIntroduction {display:none !important;} /* Removing the introduction text from the view */

			/*FRAMEWORK HACKS & OVERRIDES */
			span[class=ios-color-hack] a {color:#275100!important;text-decoration:none!important;} /* Remove all link colors in IOS (below are duplicates based on the color preference) */
			span[class=ios-color-hack2] a {color:#205478!important;text-decoration:none!important;}
			span[class=ios-color-hack3] a {color:#8B8B8B!important;text-decoration:none!important;}
			/* A nice and clean way to target phone numbers you want clickable and avoid a mobile phone from linking other numbers that look like, but are not phone numbers.  Use these two blocks of code to "unstyle" any numbers that may be linked.  The second block gives you a class to apply with a span tag to the numbers you would like linked and styled.
			Inspired by Campaign Monitor's article on using phone numbers in email: http://www.campaignmonitor.com/blog/post/3571/using-phone-numbers-in-html-email/.
			*/
			.a[href^="tel"], a[href^="sms"] {text-decoration:none!important;color:#606060!important;pointer-events:none!important;cursor:default!important;}
			.mobile_link a[href^="tel"], .mobile_link a[href^="sms"] {text-decoration:none!important;color:#606060!important;pointer-events:auto!important;cursor:default!important;}


			/* MOBILE STYLES */
			@media only screen and (max-width: 480px){
				/*////// CLIENT-SPECIFIC STYLES //////*/
				body{width:100% !important; min-width:100% !important;} /* Force iOS Mail to render the email at full width. */

				/* FRAMEWORK STYLES */
				/*
				CSS selectors are written in attribute
				selector format to prevent Yahoo Mail
				from rendering media query styles on
				desktop.
				*/
				/*td[class="textContent"], td[class="flexibleContainerCell"] { width: 100%; padding-left: 10px !important; padding-right: 10px !important; }*/
				table[id="emailHeader"],
				table[id="emailBody"],
				table[id="emailFooter"],
				table[class="flexibleContainer"],
				td[class="flexibleContainerCell"] {width:100% !important;}
				td[class="flexibleContainerBox"], td[class="flexibleContainerBox"] table {display: block;width: 100%;text-align: left;}
				/*
				The following style rule makes any
				image classed with 'flexibleImage'
				fluid when the query activates.
				Make sure you add an inline max-width
				to those images to prevent them
				from blowing out.
				*/
				td[class="imageContent"] img {height:auto !important; width:100% !important; max-width:100% !important; }
				img[class="flexibleImage"]{height:auto !important; width:100% !important;max-width:100% !important;}
				img[class="flexibleImageSmall"]{height:auto !important; width:auto !important;}


				/*
				Create top space for every second element in a block
				*/
				table[class="flexibleContainerBoxNext"]{padding-top: 10px !important;}

				/*
				Make buttons in the email span the
				full width of their container, allowing
				for left- or right-handed ease of use.
				*/
				table[class="emailButton"]{width:100% !important;}
				td[class="buttonContent"]{padding:0 !important;}
				td[class="buttonContent"] a{padding:15px !important;}

			}

			/*  CONDITIONS FOR ANDROID DEVICES ONLY
			*   http://developer.android.com/guide/webapps/targeting.html
			*   http://pugetworks.com/2011/04/css-media-queries-for-targeting-different-mobile-devices/ ;
			=====================================================*/

			@media only screen and (-webkit-device-pixel-ratio:.75){
				/* Put CSS for low density (ldpi) Android layouts in here */
			}

			@media only screen and (-webkit-device-pixel-ratio:1){
				/* Put CSS for medium density (mdpi) Android layouts in here */
			}

			@media only screen and (-webkit-device-pixel-ratio:1.5){
				/* Put CSS for high density (hdpi) Android layouts in here */
			}
			/* end Android targeting */

			/* CONDITIONS FOR IOS DEVICES ONLY
			=====================================================*/
			@media only screen and (min-device-width : 320px) and (max-device-width:568px) {

			}
			/* end IOS targeting */
		</style>
		<!--
			Outlook Conditional CSS

			These two style blocks target Outlook 2007 & 2010 specifically, forcing
			columns into a single vertical stack as on mobile clients. This is
			primarily done to avoid the 'page break bug' and is optional.

			More information here:
			http://templates.mailchimp.com/development/css/outlook-conditional-css
		-->
		<!--[if mso 12]>
			<style type="text/css">
				.flexibleContainer{display:block !important; width:100% !important;}
			</style>
		<![endif]-->
		<!--[if mso 14]>
			<style type="text/css">
				.flexibleContainer{display:block !important; width:100% !important;}
			</style>
		<![endif]-->
	</head>
	<body bgcolor="#E1E1E1" leftmargin="0" marginwidth="0" topmargin="0" marginheight="0" offset="0">

		<!-- CENTER THE EMAIL // -->
		<!--
		1.  The center tag should normally put all the
			content in the middle of the email page.
			I added "table-layout: fixed;" style to force
			yahoomail which by default put the content left.

		2.  For hotmail and yahoomail, the contents of
			the email starts from this center, so we try to
			apply necessary styling e.g. background-color.
		-->
		<center style="background-color:#E1E1E1;">
			<table border="0" cellpadding="0" cellspacing="0" height="100%" width="100%" id="bodyTable" style="table-layout: fixed;max-width:100% !important;width: 100% !important;min-width: 100% !important;">
				<tr>
					<td align="center" valign="top" id="bodyCell">

						<!-- EMAIL HEADER // -->
						<!--
							The table "emailBody" is the email's container.
							Its width can be set to 100% for a color band
							that spans the width of the page.
						-->
						<table bgcolor="#E1E1E1" border="0" cellpadding="0" cellspacing="0" width="500" id="emailHeader">

							<!-- HEADER ROW // -->
							<tr>
								<td align="center" valign="top">
									<!-- CENTERING TABLE // -->
									<table border="0" cellpadding="0" cellspacing="0" width="100%">
										<tr>
											<td align="center" valign="top">
												<!-- FLEXIBLE CONTAINER // -->
												<table border="0" cellpadding="20" cellspacing="0" width="500" class="flexibleContainer">
													<tr>
														<td valign="top" width="500" class="flexibleContainerCell">

															<!-- CONTENT TABLE // -->
															<table align="left" border="0" cellpadding="0" cellspacing="0" width="100%">
																<tr>
																	<!--
																		The "invisibleIntroduction" is the text used for short preview
																		of the email before the user opens it (50 characters max). Sometimes,
																		you do not want to show this message depending on your design but this
																		text is highly recommended.

																		You do not have to worry if it is hidden, the next <td> will automatically
																		center and apply to the width 100% and also shrink to 50% if the first <td>
																		is visible.
																	-->
																	<td align="left" valign="middle" id="invisibleIntroduction" class="flexibleContainerBox" style="display:none !important; mso-hide:all;">
																		<table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:100%;">
																			<tr>
																				<td align="left" class="textContent">
																					<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#828282;text-align:center;line-height:120%;">
																						The introduction of your message preview goes here. Try to make it short.
																					</div>
																				</td>
																			</tr>
																		</table>
																	</td>
																	<td align="right" valign="middle" class="flexibleContainerBox">
																		<table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width:100%;">
																			<tr>
																				<td align="left" class="textContent">
																					<!-- CONTENT // -->
																					<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#828282;text-align:center;line-height:120%;">
																						<!--If you can't see this message, <a href="#" target="_blank" style="text-decoration:none;border-bottom:1px solid #828282;color:#828282;"><span style="color:#828282;">view&nbsp;it&nbsp;in&nbsp;your&nbsp;browser</span></a>.-->
																					</div>
																				</td>
																			</tr>
																		</table>
																	</td>
																</tr>
															</table>
														</td>
													</tr>
												</table>
												<!-- // FLEXIBLE CONTAINER -->
											</td>
										</tr>
									</table>
									<!-- // CENTERING TABLE -->
								</td>
							</tr>
							<!-- // END -->

						</table>
						<!-- // END -->

						<!-- EMAIL BODY // -->
						<!--
							The table "emailBody" is the email's container.
							Its width can be set to 100% for a color band
							that spans the width of the page.
						-->
						<table bgcolor="#FFFFFF"  border="0" cellpadding="0" cellspacing="0" width="500" id="emailBody">

							<!-- MODULE ROW // -->
							<!--
								To move or duplicate any of the design patterns
								in this email, simply move or copy the entire
								MODULE ROW section for each content block.
							-->
							<tr>
								<td align="center" valign="top">
									<!-- CENTERING TABLE // -->
									<!--
										The centering table keeps the content
										tables centered in the emailBody table,
										in case its width is set to 100%.
									-->
									<table border="0" cellpadding="0" cellspacing="0" width="100%" style="color:#FFFFFF;" bgcolor="#1f1f1f">
										<tr>
											<td align="center" valign="top">
												<!-- FLEXIBLE CONTAINER // -->
												<!--
													The flexible container has a set width
													that gets overridden by the media query.
													Most content tables within can then be
													given 100% widths.
												-->
												<table border="0" cellpadding="0" cellspacing="0" width="500" class="flexibleContainer">
													<tr>
														<td align="center" valign="top" width="500" class="flexibleContainerCell">

															<!-- CONTENT TABLE // -->
															<!--
															The content table is the first element
																that's entirely separate from the structural
																framework of the email.
															-->
															<table border="0" cellpadding="30" cellspacing="0" width="100%">
																<tr>
																	<td align="center" valign="top" class="textContent" style="padding-top: 14px;padding-bottom: 9px;">
																		<img style="height: 40px;" src="https://i.ibb.co/vdHQKsV/logo2.png" alt="PulseTrade" />
																		<!--<h1 style="color:#FFFFFF;line-height:100%;font-family:Helvetica,Arial,sans-serif;font-size:35px;font-weight:normal;margin-bottom:5px;text-align:center;">LeadTrain</h1>-->
																	</td>
																</tr>
															</table>
															<!-- // CONTENT TABLE -->

														</td>
													</tr>
												</table>
												<!-- // FLEXIBLE CONTAINER -->
											</td>
										</tr>
									</table>
									<!-- // CENTERING TABLE -->
								</td>
							</tr>
							<!-- // MODULE ROW -->

							<!-- MODULE ROW // -->
							<tr>
								<td align="center" valign="top">
									<!-- CENTERING TABLE // -->
									<table border="0" cellpadding="0" cellspacing="0" width="100%">
										<tr>
											<td align="center" valign="top">
												<!-- FLEXIBLE CONTAINER // -->
												<table border="0" cellpadding="0" cellspacing="0" width="500" class="flexibleContainer">
													<tr>
														<td align="center" valign="top" width="500" class="flexibleContainerCell">
															<table border="0" cellpadding="30" cellspacing="0" width="100%">
																<tr>
																	<td align="center" valign="top">

																		<!-- CONTENT TABLE // -->
																		<table border="0" cellpadding="0" cellspacing="0" width="100%">
																			<tr>
																				<td valign="top" class="textContent">
																					<h3 style="color:#5F5F5F;line-height:125%;font-family:Helvetica,Arial,sans-serif;font-size:20px;font-weight:normal;margin-top:0;margin-bottom:10px;text-align:left;">'''+msg_title+'''</h3>
																					<div style="text-align:left;font-family:Helvetica,Arial,sans-serif;font-size:15px;margin-bottom:0;margin-top:3px;color:#5F5F5F;line-height:135%;">
<b>'''+msg_body+'''</b><br/><br/>
<br  style="'''+('' if link or otp else 'display:none;')+'"'+'''/><br style="'''+('' if link or otp else 'display:none;')+'"'+'''/>
                                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="'''+('' if link or otp else 'display:none;')+'"'+'''>
    <tr style="'''+('' if link or otp else 'display:none;')+'"'+'''>
        <td align="center">
                  <a href="'''+(link if link else '#')+'"'+''' style="background-color:#FF971D;border-radius:5px;color:#ffffff;display:inline-block;font-family:sans-serif;font-size:15px;font-weight:bold;line-height:45px;text-align:center;text-decoration:none;width:200px;-webkit-text-size-adjust:none;">'''+(otp if otp else 'click Here')+'''</a>
        </td>
    </tr>
</table><br style="'''+('' if link or otp else 'display:none;')+'"'+'''/>

Thanks, <br/>
The PulseTrade Team <br/><br/>
                                            <p style="font-size:12px;">If you didn’t request that, please contact <a href="mailto: support@PulseTrade.com" style="color: #FF971D;"> support@PulseTrade.com. </p>
</div>
																				</td>
																			</tr>
																		</table>
																		<!-- // CONTENT TABLE -->

																	</td>
																</tr>
															</table>
														</td>
													</tr>
												</table>
												<!-- // FLEXIBLE CONTAINER -->
											</td>
										</tr>
									</table>
									<!-- // CENTERING TABLE -->
								</td>
							</tr>
							<!-- // MODULE ROW -->

						</table>
						<!-- // END -->

						<!-- EMAIL FOOTER // -->
						<!--
							The table "emailBody" is the email's container.
							Its width can be set to 100% for a color band
							that spans the width of the page.
						-->
						<table bgcolor="#E1E1E1" border="0" cellpadding="0" cellspacing="0" width="500" id="emailFooter">

							<!-- FOOTER ROW // -->
							<!--
								To move or duplicate any of the design patterns
								in this email, simply move or copy the entire
								MODULE ROW section for each content block.
							-->
							<tr>
								<td align="center" valign="top">
									<!-- CENTERING TABLE // -->
									<table border="0" cellpadding="0" cellspacing="0" width="100%">
										<tr>
											<td align="center" valign="top">
                        <table border="0" cellpadding="0" cellspacing="0" align="center"
	width="560" style="border-collapse: collapse; border-spacing: 0; padding: 0; width: inherit;
	max-width: 560px;" class="wrapper">

	<!-- SOCIAL NETWORKS -->
	<!-- Image text color should be opposite to background color. Set your url, image src, alt and title. Alt text should fit the image size. Real image size should be x2 -->
	<tr style="display:none;">
		<td align="center" valign="top" style="border-collapse: collapse; border-spacing: 0; margin: 0; padding: 0; padding-left: 6.25%; padding-right: 6.25%; width: 87.5%;
			padding-top: 25px;" class="social-icons"><table
			width="256" border="0" cellpadding="0" cellspacing="0" align="center" style="border-collapse: collapse; border-spacing: 0; padding: 0;">
			<tr>

				<!-- ICON 1 -->
				<td align="center" valign="middle" style="margin: 0; padding: 0; padding-left: 10px; padding-right: 10px; border-collapse: collapse; border-spacing: 0;"><a target="_blank"
					href="https://raw.githubusercontent.com/konsav/email-templates/"
				style="text-decoration: none;"><img border="0" vspace="0" hspace="0" style="padding: 0; margin: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; border: none;
					color: #000000;"
					alt="F" title="Facebook"
					width="44" height="44"
					src="https://raw.githubusercontent.com/konsav/email-templates/master/images/social-icons/facebook.png"></a></td>

				<!-- ICON 2 -->
				<td align="center" valign="middle" style="margin: 0; padding: 0; padding-left: 10px; padding-right: 10px; border-collapse: collapse; border-spacing: 0;"><a target="_blank"
					href="https://raw.githubusercontent.com/konsav/email-templates/"
				style="text-decoration: none;"><img border="0" vspace="0" hspace="0" style="padding: 0; margin: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; border: none;
					color: #000000;"
					alt="T" title="Twitter"
					width="44" height="44"
					src="https://raw.githubusercontent.com/konsav/email-templates/master/images/social-icons/twitter.png"></a></td>				

				<!-- ICON 3 -->
				<td align="center" valign="middle" style="margin: 0; padding: 0; padding-left: 10px; padding-right: 10px; border-collapse: collapse; border-spacing: 0;"><a target="_blank"
					href="https://raw.githubusercontent.com/konsav/email-templates/"
				style="text-decoration: none;"><img border="0" vspace="0" hspace="0" style="padding: 0; margin: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; border: none;
					color: #000000;"
					alt="G" title="Google Plus"
					width="44" height="44"
					src="https://raw.githubusercontent.com/konsav/email-templates/master/images/social-icons/googleplus.png"></a></td>		

				<!-- ICON 4 -->
				<td align="center" valign="middle" style="margin: 0; padding: 0; padding-left: 10px; padding-right: 10px; border-collapse: collapse; border-spacing: 0;"><a target="_blank"
					href="https://raw.githubusercontent.com/konsav/email-templates/"
				style="text-decoration: none;"><img border="0" vspace="0" hspace="0" style="padding: 0; margin: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; border: none;
					color: #000000;"
					alt="I" title="Instagram"
					width="44" height="44"
					src="https://raw.githubusercontent.com/konsav/email-templates/master/images/social-icons/instagram.png"></a></td>

			</tr>
			</table>
		</td>
	</tr>
                        </table>
												<!-- FLEXIBLE CONTAINER // -->
												<table border="0" cellpadding="0" cellspacing="0" width="500" class="flexibleContainer">
													<tr>
														<td align="center" valign="top" width="500" class="flexibleContainerCell">
															<table border="0" cellpadding="30" cellspacing="0" width="100%">
																<tr>
																	<td valign="top" bgcolor="#E1E1E1">

																		<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#828282;text-align:center;line-height:120%;">
																			<div>
                                        
                                       
                                        Copyright &#169; 2023 <a href="http://www.adventurebucketlist.com/" target="_blank" style="text-decoration:none;color:#828282;"><span style="color:#828282;">PulseTrade</span></a>. All&nbsp;rights&nbsp;reserved.</div>
																			<!--<div>If you do not want to recieve emails from us, you can <a href="#" target="_blank" style="text-decoration:none;color:#828282;"><span style="color:#828282;">unsubscribe</span></a>.</div>-->
																		</div>

																	</td>
																</tr>
															</table>
														</td>
													</tr>
												</table>
												<!-- // FLEXIBLE CONTAINER -->
											</td>
										</tr>
									</table>
									<!-- // CENTERING TABLE -->
								</td>
							</tr>

						</table>
						<!-- // END -->

					</td>
				</tr>
			</table>
		</center>
	</body>
</html>

    '''
    try:
        mail.send(msg)
        return True
    except Exception as e:
        # Mail server not configured — log and let the flow continue.
        print(f"otp email to {to_email} skipped: {e}")
        return False



def validate_ip_address(ip_address):
    try:
        ipaddress.ip_address(ip_address)
        return True
    except ValueError:
        return False