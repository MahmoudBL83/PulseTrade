from flask import render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import login_user, logout_user
from crypto import app, db, jwt_required, auth_required, issue_token, get_current_user
from crypto.models import User,Ticket,Message,Post,Category,Exchange2,Bot,UserCount,BotCount,Pair, Transaction, Subscription, TransactionHistory,Exchange, TokenBlocklist
from crypto.errors import wants_json
from crypto.auth_core import (  # noqa: F401  (several names re-exported for older imports)
    mail_verification_required, mail_configured, frontend_url, generate_otp, send_otp_email,
    validate_ip_address, start_pending_login, pending_login, clear_pending_login, check_pending_code,
    login_blocked, record_failure, clear_failures, log_event, valid_email, password_problem, client_ip,
)
import json
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
from datetime import timedelta
from functools import wraps

stripe.api_key = os.environ.get('STRIPE_API_KEY', '')

FRONTEND_URL = frontend_url()

OTP_EMAIL_TITLE = "ip login notification"
OTP_EMAIL_BODY = "A new ip address has been logged in to your account, Use this OTP code in the login process:"


def _body():
    return request.get_json(silent=True) or {}


def is_admin():
    return bool(session.get('admin'))


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            if wants_json():
                return jsonify({"message": "admin authentication required", "ok": False}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_or_user_required(f):
    """Admin session or a logged-in user (support desk endpoints)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin() and get_current_user() is None:
            return jsonify({"message": "authentication required", "ok": False}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin')
@admin_required
def admin_home():
    open_tickets = 0
    for ticket in Ticket.query.all():
        last = ticket.messages.order_by(Message.id.desc()).first()
        if last is not None and not last.is_admin:
            open_tickets += 1
    since = datetime.utcnow() - timedelta(days=1)
    volume = db.session.query(db.func.coalesce(db.func.sum(Transaction.value), 0)).filter(Transaction.created_at > since).scalar() or 0
    return render_template('admin_home.html',
                            bots_count= Bot.query.filter(Bot.isActive==True).count(),
                            users_count=User.query.count(),
                            tickets_opened=open_tickets,
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
    return render_template('admin_transactions.html',transactions=Transaction.query.order_by(Transaction.id.desc()).limit(2000).all(),exchanges = Exchange2.query.filter(Exchange2.isActive==True).all())


_HAS_CACHE = {}
REQUIRED_CAPS = ('fetchOHLCV', 'fetchTickers', 'fetchBalance', 'createOrder', 'cancelOrder')


def exchange_capabilities(name):
    """ccxt 'has' map for an exchange id (cached; instantiation is slow)."""
    if name not in _HAS_CACHE:
        try:
            _HAS_CACHE[name] = getattr(ccxt, name)().describe()['has']
        except Exception:
            _HAS_CACHE[name] = None
    return _HAS_CACHE[name]


# exchanges activatign and deactivating
@app.route('/admin/exchanges', methods=['GET'])
@admin_required
def admin_exchanges_get():
    exchanges_json = []
    for exchange in Exchange2.query.all():
        has_json = exchange_capabilities(exchange.exchange)
        if has_json and all(has_json.get(k) for k in REQUIRED_CAPS):
            ex = exchange.serialize()
            ex['has'] = has_json
            exchanges_json.append(ex)
    return render_template('admin_exchanges.html',exchanges=exchanges_json)

@app.route('/toggle_exchange', methods=['POST'])
@admin_required
def toggle_exchange():
    body = _body()
    exchange = body['exchange']
    status = bool(body['status'])
    updated = Exchange2.query.filter(Exchange2.exchange==exchange).update(dict(isActive=status))
    if not updated and exchange in ccxt.exchanges:
        db.session.add(Exchange2(exchange=exchange, isActive=status))
        updated = 1
    db.session.commit()
    return jsonify({'message': f'{exchange} {"enabled" if status else "disabled"}', 'ok': bool(updated)})

@app.route('/toggle_pair', methods=['POST'])
@admin_required
def toggle_pair():
    body = _body()
    pair = body['pair']
    status = bool(body['status'])
    updated = Pair.query.filter(Pair.pair==pair).update(dict(isActive=status))
    if not updated and '/' in str(pair):
        db.session.add(Pair(pair=pair, isActive=status))
        updated = 1
    db.session.commit()
    return jsonify({'message': f'{pair} {"enabled" if status else "disabled"}', 'ok': bool(updated)})

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

@app.route('/admin/pairs')
@admin_required
def admin_pairs():
    return render_template('admin_pairs.html',pairs=[pair.serialize() for pair in Pair.query.all()])

###################################################pricing####################################################

@app.route('/admin/pricing', methods=['GET'])
@admin_required
def admin_pricing():
    return render_template('admin_pricing.html',subscriptions=Subscription.query.all())

@app.route('/admin/pricing', methods=['POST'])
@admin_required
def admin_pricing_post():
    body = _body()
    subscription = db.session.get(Subscription, body.get('id')) if body.get('id') is not None else None
    if subscription is None:
        return jsonify({'message': 'subscription not found', 'ok': False}), 404
    max_sma = body.get('max_sma')
    max_bots = body.get('max_bots')
    subscription.max_sma = 10**9 if max_sma in (None, "") else int(max_sma)
    subscription.max_bots = 10**9 if max_bots in (None, "") else int(max_bots)
    subscription.price = float(body.get('price') or 0)
    subscription.stripe_id = body.get('stripe_id')
    subscription.type = body.get('name_en') or subscription.type
    subscription.type_ar = body.get('name_ar')
    subscription.trial_days = int(body.get('trial_days') or 0)
    db.session.commit()
    return jsonify({'message':'the subscription has been added','ok':True}), 201

@app.route('/api/admin/v1/subscribtion/edit', methods=['POST'])
@admin_required
def admin_subscribtion_edit():
    body = _body()
    user = db.session.get(User, body.get('user_id')) if body.get('user_id') is not None else None
    subscription = db.session.get(Subscription, body.get('sub_type_id')) if body.get('sub_type_id') is not None else None
    if user is None or subscription is None:
        return jsonify({'message': 'user or subscription not found', 'ok': False}), 404
    user.subType = subscription
    user.subType_id = subscription.id
    user.sub_date = datetime.utcnow()
    db.session.commit()
    return jsonify({'message':'the subscription has been changed','ok':True})

@app.route("/api/v1/get_subscriptions_and_invoices", methods=['GET'])
@admin_required
def get_subscriptions_and_invoices_user():
    user_id = request.args.get("user_id")
    user = db.session.get(User, int(user_id)) if user_id and str(user_id).isdigit() else None
    if user is None:
        return jsonify({'message': 'user_id is required', 'ok': False}), 400
    if not user.stripe_customer_id or not stripe.api_key:
        return jsonify({'message': 'User does not have a Stripe customer ID', 'ok': False}), 403
    try:
        subscription_list = [{
            'subscription_id': s.id, 'status': s.status,
            'current_period_start': getattr(s, 'current_period_start', None),
            'current_period_end': getattr(s, 'current_period_end', None),
        } for s in stripe.Subscription.list(customer=user.stripe_customer_id, status='all').data]
        invoice_list = [{
            'invoice_id': inv.id, 'amount_due': inv.amount_due, 'status': inv.status, 'created': inv.created,
            'billing_reason': inv.billing_reason, 'paid': getattr(inv, 'paid', inv.status == 'paid'),
            'currency': inv.currency, 'url': getattr(inv, 'hosted_invoice_url', None) or inv.lines.url,
        } for inv in stripe.Invoice.list(customer=user.stripe_customer_id).data]
        return jsonify({'subscriptions': subscription_list, 'invoices': invoice_list, 'ok': True})
    except Exception as e:
        return jsonify({'message': str(e), 'ok': False}), 502

###################################################tickets##################################################

def _owned_ticket(ticket_id):
    """Ticket visible to the caller (admin: any; user: own) or None."""
    ticket = db.session.get(Ticket, ticket_id) if ticket_id is not None else None
    if ticket is None:
        return None
    if is_admin():
        return ticket
    user = get_current_user()
    return ticket if user is not None and ticket.user_id == user.id else None


@app.route('/admin/support/tickets', methods=['GET'])
@admin_or_user_required
def admin_support_tickets_get():
    if is_admin():
        user_id = request.args.get("user_id")
        q = Ticket.query.filter(Ticket.user_id == int(user_id)) if user_id and str(user_id).isdigit() else Ticket.query
    else:
        # Users only ever see their own tickets, whatever user_id they send.
        q = Ticket.query.filter(Ticket.user_id == get_current_user().id)
    return jsonify([ticket.serialize() for ticket in q.order_by(Ticket.id.desc()).all()])

@app.route('/admin/support/messages', methods=['GET'])
@admin_or_user_required
def admin_support_messages_get():
    ticket_id = request.args.get('ticket_id')
    ticket = _owned_ticket(int(ticket_id)) if ticket_id and str(ticket_id).isdigit() else None
    if ticket is None:
        return jsonify({'message': 'ticket not found', 'ok': False}), 404
    return jsonify([message.serialize() for message in ticket.messages.order_by(Message.id.asc()).all()])

@app.route('/admin/support/tickets', methods=['POST'])
@jwt_required
def open_ticket():
    current_user = get_current_user()
    body = _body()
    subject = str(body.get('subject') or '').strip()[:120]
    content = str(body.get('content') or '').strip()
    if not subject or not content:
        return jsonify({'message': 'Subject and message are required', 'ok': False}), 400
    ticket = Ticket(subject=subject, user_id=current_user.id)
    ticket.updated_at = datetime.utcnow()
    db.session.add(ticket)
    db.session.flush()
    db.session.add(Message(content=content, user_id=current_user.id, ticket_id=ticket.id, is_admin=False, created_at=datetime.utcnow()))
    db.session.commit()
    return jsonify(ticket.serialize()), 201

@app.route('/admin/support/tickets/<int:ticket_id>/close', methods=['PUT'])
@admin_or_user_required
def close_ticket(ticket_id):
    ticket = _owned_ticket(ticket_id)
    if ticket is None:
        return jsonify({'error': 'Ticket not found', 'ok': False}), 404
    ticket.status = 'closed'
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(ticket.serialize())

@app.route('/admin/support/tickets/<int:ticket_id>/messages', methods=['POST'])
@admin_or_user_required
def send_message(ticket_id):
    ticket = _owned_ticket(ticket_id)
    if ticket is None:
        return jsonify({'message': 'Ticket not found', 'ok': False}), 404
    content = str(_body()['content']).strip()
    if not content:
        return jsonify({'message': 'Message is empty', 'ok': False}), 400
    # is_admin can only be asserted by an admin session; everyone else posts as themselves.
    as_admin = bool(_body().get('is_admin')) and is_admin()
    user = get_current_user()
    if not as_admin and user is None:
        as_admin = is_admin()
    message = Message(content=content, user_id=ticket.user_id if as_admin else user.id, ticket_id=ticket.id,
                      is_admin=as_admin, created_at=datetime.utcnow())
    db.session.add(message)
    ticket.updated_at = datetime.utcnow()
    if ticket.status == 'closed' and not as_admin:
        ticket.status = 'open'
    db.session.commit()
    if as_admin:
        send_notification(f"you have a new message from the support team ({content[:120]})***system", ticket.user_id)
    return jsonify(message.serialize()), 201

@app.route('/admin/support/tickets/<int:ticket_id>/messages/<int:message_id>/reply', methods=['POST'])
@admin_required
def reply_to_message(ticket_id, message_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    message = Message.query.get_or_404(message_id)
    content = str(_body().get('content') or '').strip()
    if ticket.id != message.ticket_id:
        return jsonify({'error': 'Invalid message for the ticket'}), 400
    if not content:
        return jsonify({'message': 'Message is empty', 'ok': False}), 400
    reply = Message(content=content, user_id=ticket.user_id, ticket_id=ticket.id, is_admin=True, created_at=datetime.utcnow())
    ticket.updated_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()
    send_notification(f"you have a new message from the support team ({content[:120]})***system", ticket.user_id)
    return jsonify(reply.serialize()), 201

###################################################posts######################################################

@app.route('/admin/blog/posts', methods=['GET'])
def admin_blog_posts_get():
    post_id = request.args.get("post_id")
    if post_id:
        post = db.session.get(Post, int(post_id)) if str(post_id).isdigit() else None
        if post is None:
            return jsonify({'message': 'post not found', 'ok': False}), 404
        return jsonify(post.serialize())
    return jsonify([post.serialize() for post in Post.query.all()])

@app.route('/admin/blog/posts', methods=['POST'])
@admin_required
def admin_blog_posts_post():
    body = _body()
    category = db.session.get(Category, body.get('category_id')) if body.get('category_id') is not None else None
    if category is None:
        return jsonify({'message': 'Choose a category first', 'ok': False}), 400
    title, content = str(body.get('title') or '').strip(), body.get('content') or ''
    if not title or not content:
        return jsonify({'message': 'Title and content are required', 'ok': False}), 400
    post = Post(title=title[:120], content=content, writer=body.get('writer') or 'PulseTrade', img=body.get('img'), lang=body.get('lang'))
    post.category_id = category.id
    db.session.add(post)
    db.session.commit()
    return jsonify({'message':'the post has been published','ok':True,'id':post.id}), 201

@app.route('/admin/blog/posts/<int:post_id>', methods=['PUT'])
@admin_required
def admin_blog_posts_put(post_id):
    post = Post.query.get_or_404(post_id)
    body = _body()
    post.title = body.get('title') or post.title
    post.content = body.get('content') or post.content
    post.writer = body.get('writer') or post.writer
    post.img = body.get('img')
    if body.get('category_id') is not None and db.session.get(Category, body.get('category_id')):
        post.category_id = body.get('category_id')
    if body.get('lang'):
        post.lang = body.get('lang')
    db.session.commit()
    return jsonify({'message':'the post has been updated','ok':True}), 201

@app.route('/admin/blog/posts/<int:post_id>', methods=['DELETE'])
@admin_required
def admin_blog_posts_delete(post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        return jsonify({'message':'the post has not been deleted','ok':False}), 404
    db.session.delete(post)
    db.session.commit()
    return jsonify({'message':'the post has been deleted','ok':True}), 201

@app.route('/admin/blog/cats', methods=['POST'])
@admin_required
def admin_blog_cats_new():
    body = _body()
    title = str(body.get('title') or '').strip()
    if not title:
        return jsonify({'message': 'Title is required', 'ok': False}), 400
    cat = Category(title=title[:120],img=body.get('img'),title_ar=body.get('title_ar'))
    db.session.add(cat)
    db.session.commit()
    return jsonify({'message':'the category has been created','ok':True,'id':cat.id}), 201

@app.route('/admin/blog/cats/<int:cat_id>', methods=['DELETE'])
@admin_required
def admin_blog_cats_del(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'message':'the category has been deleted','ok':True}), 201

@app.route('/admin/blog/cats/edit/<int:cat_id>', methods=['POST'])
@admin_required
def admin_blog_cats_edit(cat_id):
    cat = Category.query.get_or_404(cat_id)
    body = _body()
    cat.title = body.get('title') or cat.title
    cat.img = body.get('img')
    if body.get('title_ar') is not None:
        cat.title_ar = body.get('title_ar')
    db.session.commit()
    return jsonify({'message':'the category has been edited','ok':True}), 201
###############################################################################################################

def complete_login(user, remember=False):
    """Final step of every successful user login."""
    login_user(user, remember=bool(remember))
    clear_failures(user.email)
    clear_pending_login()
    log_event(user, "login", True)
    return issue_token(user)


def begin_user_login(email, password, remember=False, totp=None):
    """Shared password step for /login and /api/v2/auth/login.

    Returns (status, payload) where status is one of
    ok | otp_required | totp_required | unverified | invalid | blocked."""
    email = (email or "").strip().lower()
    if login_blocked(email):
        return "blocked", {"message": "Too many failed attempts. Try again in 15 minutes."}
    user = User.query.filter(db.func.lower(User.email) == email).first() if email else None
    if not user or not user.check_password(password):
        record_failure(email)
        if user is not None:
            log_event(user, "login", False)
        return "invalid", {"message": "Invalid email or password."}

    if mail_verification_required() and not user.is_verified:
        token = generate_verification_token(user.email)
        send_otp_email(user.email, None, "PulseTrade Email Verification",
                       "PulseTrade Email Verification: click this link to complete the verification process:",
                       f'{FRONTEND_URL}/verify_email/{token}')
        return "unverified", {"message": "Please Check your email to verify your email address"}

    if user.totp_enabled and user.totp_secret:
        from crypto.auth_core import verify_totp
        if totp and verify_totp(user.totp_secret, totp):
            return "ok", {"user": user, "access_token": complete_login(user, remember)}
        start_pending_login(user.email, "totp", remember=remember)
        return "totp_required", {"message": "Enter the 6-digit code from your authenticator app."}

    # IP-check OTP only when the flag is on, mail can deliver the code and
    # the login comes from an address we have not seen before.
    ip = client_ip()
    if user.ip_check in (True, "true", 1) and mail_configured() and validate_ip_address(ip) and user.last_ip != ip:
        otp = generate_otp(user.email)
        if send_otp_email(user.email, otp, OTP_EMAIL_TITLE, OTP_EMAIL_BODY):
            start_pending_login(user.email, "email", otp, remember)
            return "otp_required", {"message": "We emailed you a one-time code to confirm this new IP address."}

    if validate_ip_address(ip):
        user.last_ip = ip
        db.session.commit()
    return "ok", {"user": user, "access_token": complete_login(user, remember)}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        body = _body()
        if body.get('admin'):
            return _admin_login(body)
        status, payload = begin_user_login(body.get('email'), body.get('password'), body.get('remember'), body.get('totp'))
        if status == "ok":
            return jsonify(access_token=payload["access_token"], ok=True)
        if status in ("otp_required", "totp_required"):
            return jsonify({"message": payload["message"], "ok": False, "otp_required": True,
                            "method": "totp" if status == "totp_required" else "email",
                            "redirect": url_for('verify_otp')})
        code = 429 if status == "blocked" else 200
        return jsonify({"message": payload["message"], "ok": False}), code
    return render_template('sign-in.html')


def _admin_login(body):
    email = body.get('email')
    password = body.get('password')
    expected = os.environ.get('ADMIN_PASSWORD', '')
    if login_blocked('admin'):
        return jsonify({'message': 'Too many failed attempts. Try again in 15 minutes.', 'ok': False}), 429
    if not (email == 'admin' and expected and password == expected):
        record_failure('admin')
        return jsonify({'message': 'Invalid username or password', 'ok': False}), 401
    clear_failures('admin')
    if os.environ.get("ADMIN_TOTP_SECRET"):
        start_pending_login("admin", "admin_totp")
        return jsonify({'message': 'Enter the code from your authenticator app', 'ok': True, 'otp_required': True, 'method': 'totp'}), 200
    admin_email = os.environ.get('ADMIN_EMAIL', '')
    if mail_configured() and admin_email:
        otp = generate_otp(admin_email)
        if send_otp_email(admin_email, otp, OTP_EMAIL_TITLE, OTP_EMAIL_BODY):
            start_pending_login("admin", "admin_email", otp)
            return jsonify({'message': 'Admin logged in successfully', 'ok': True, 'otp_required': True, 'method': 'email'}), 200
    # No second factor available on this deploy (no SMTP, no ADMIN_TOTP_SECRET).
    session['admin'] = True
    return jsonify({'message': 'Admin logged in successfully', 'ok': True, 'otp_required': False, 'redirect': url_for('admin_home')}), 200


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'GET' and is_admin():
        return redirect(url_for('admin_home'))
    if request.method == 'POST':
        code = request.form.get('otp') or _body().get('otp') or _body().get('code')
        data = check_pending_code(code)
        if data:
            if data["email"] != "admin":
                user = User.query.filter_by(email=data["email"]).first()
                if user is None:
                    clear_pending_login()
                    return redirect(url_for('login'))
                ip = client_ip()
                if validate_ip_address(ip):
                    user.last_ip = ip
                token = complete_login(user, data.get("remember", True))
                if request.is_json:
                    return jsonify(access_token=token, ok=True)
                return redirect(url_for('dashboard'))
            clear_pending_login()
            session['admin'] = True
            if request.is_json:
                return jsonify(ok=True, redirect=url_for('admin_home'))
            return redirect(url_for('admin_home'))
        if request.is_json:
            return jsonify({"message": "Invalid or expired code", "ok": False}), 400
        flash('Invalid OTP')
    data = pending_login()
    return render_template('verify_otp2.html', method=(data or {}).get("method", "email"))

@app.route('/resend_otp')
def resend_otp():
    data = pending_login()
    if data and data.get("method") in ("email", "admin_email"):
        to = data["email"] if data["email"] != "admin" else os.environ.get('ADMIN_EMAIL', '')
        otp = generate_otp(to)
        if send_otp_email(to, otp, OTP_EMAIL_TITLE, OTP_EMAIL_BODY):
            start_pending_login(data["email"], data["method"], otp, data.get("remember"))
            flash('OTP resent')
    return redirect(url_for('verify_otp'))


def register_user(email, firstName, lastName, password, confirm_password):
    """Shared by /register and /api/v2/auth/register. Returns (ok, message, user)."""
    email = (email or "").strip().lower()
    if not valid_email(email):
        return False, 'Please enter a valid email address.', None
    if password != confirm_password:
        return False, 'Passwords do not match.', None
    problem = password_problem(password)
    if problem:
        return False, problem, None
    if User.query.filter(db.func.lower(User.email) == email).first():
        return False, 'Email already taken.', None

    user = User(email=email, password=password, firstName=(firstName or '').strip()[:120], lastName=(lastName or '').strip()[:120])
    subscription = Subscription.query.filter_by(type="free").first()
    if subscription is None:
        # Fresh DB without seed data — create the default free plan inline.
        subscription = Subscription(type='free', max_bots=5, max_sma=10)
        db.session.add(subscription)
        db.session.flush()
    user.subType = subscription
    db.session.add(user)
    try:
        db.session.commit()
    except Exception:
        # Concurrent duplicate-email race (unique constraint) or flush error.
        db.session.rollback()
        return False, 'Email already taken.', None
    if mail_verification_required():
        token = generate_verification_token(user.email)
        send_otp_email(user.email, None,"PulseTrade Email Verification","PulseTrade Email Verification: click this link to complete the verification process:",f'{FRONTEND_URL}/verify_email/{token}')
        msg = 'Registration successful. Please check your email to verify your account.'
    else:
        user.is_verified = True
        db.session.commit()
        msg = 'Registration successful. You can now sign in.'
    log_event(user, "register", True)
    return True, msg, user


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        body = _body()
        ok, message, _ = register_user(body.get('email'), body.get('firstName'), body.get('lastName'),
                                       body.get('password'), body.get('confirm_password'))
        return jsonify({'message': message, 'ok': ok})
    return render_template('sign-up.html')

def generate_verification_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

@app.route('/verify_email/<token>')
def verify_email(token):
    try:
        serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        email = serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=24 * 3600)
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
    # Verify the reset password token
    try:
        s = Serializer(app.config['SECRET_KEY'])
        user = db.session.get(User, s.loads(token, max_age=600)['user_id'])
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        user = None
    if user is None:
        if request.method == 'POST':
            return jsonify({'message': 'Invalid or expired token. Please request a new password reset.', 'ok': False}), 400
        flash('Invalid or expired token. Please request a new password reset.')
        return redirect(url_for('reset_password'))

    if request.method == 'POST':
        body = _body()
        password = body.get('password')
        if password != body.get('confirm_password'):
            return jsonify({'message': 'Passwords do not match. Please try again.', 'ok': False})
        problem = password_problem(password)
        if problem:
            return jsonify({'message': problem, 'ok': False})
        user.set_password(password)
        db.session.commit()
        log_event(user, "password_reset", True)
        login_user(user)
        return jsonify({'message': 'Your Password has been changed','ok':True})

    return render_template('reset_password_token.html', token=token)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = str(_body().get('email') or '').strip().lower()
        user = User.query.filter(db.func.lower(User.email) == email).first() if email else None
        if user:
            send_password_reset_email(user)
        # Same answer either way so the endpoint cannot be used to probe emails.
        return jsonify({'message': 'If that email is registered, reset instructions are on their way.','ok':True})
    else:
        return render_template('reset_password.html')


def _revoke_current_token():
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return
    from flask_jwt_extended import decode_token
    try:
        jti = decode_token(header.split(None, 1)[1].strip()).get("jti")
        if jti and not TokenBlocklist.query.filter_by(jti=jti).first():
            db.session.add(TokenBlocklist(jti=jti))
            db.session.commit()
    except Exception:
        db.session.rollback()


@app.route('/logout')
def logout():
    _revoke_current_token()
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/v1/logout', methods=['POST'])
def logout2():
    _revoke_current_token()
    logout_user()
    return jsonify({'message': 'logged out', 'ok': True})

@app.route('/logout_admin')
@admin_required
def logout_admin():
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/send_mail_from_admin', methods=['POST'])
@admin_required
def send_mail_from_admin():
    body = _body()
    subject = body['subject']
    text = body['body']
    if body.get('email'):
        sent = int(send_otp_email(body['email'], None,subject,text,None))
    else:
        sent = sum(int(send_otp_email(user.email, None,subject,text,None)) for user in User.query.all())
    if not sent and not mail_configured():
        return jsonify({'message': 'Mail server is not configured (MAIL_USERNAME / MAIL_PASSWORD)', 'ok': False}), 503
    return jsonify({'message': 'Email sent successfully','ok':True, 'sent': sent})

# Define a function to send a password reset email
def send_password_reset_email(user):
    token = user.get_reset_password_token()
    link = f"{FRONTEND_URL}{url_for('reset_password_token', token=token)}"
    return send_otp_email(user.email, None, 'Password Reset Request',
                          'To reset your password, use the button below. The link expires in 10 minutes.\n'
                          'If you did not make this request then simply ignore this email and no changes will be made.',
                          link)
