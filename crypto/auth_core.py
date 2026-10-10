"""Authentication primitives shared by the legacy views (crypto.auth) and the
v2 JSON API: one-time codes, TOTP 2FA, brute-force throttling, the security
log and transactional email."""
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import time
from datetime import datetime

import pyotp
from flask import render_template, request, session
from flask_mail import Message as MailMessage
from markupsafe import Markup, escape

from crypto import app, db, mail
from crypto.cache import TTLCache

OTP_TTL = 300
OTP_MAX_ATTEMPTS = 5
LOGIN_MAX_FAILURES = 10
LOGIN_WINDOW = 15 * 60

_failures = TTLCache(ttl=LOGIN_WINDOW, maxsize=10000)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mail_verification_required():
    """Kill-switch: REQUIRE_EMAIL_VERIFICATION=1 enforces email verification
    on login/register. Default 0 (off) until real SMTP creds are configured."""
    return os.environ.get('REQUIRE_EMAIL_VERIFICATION', '0') == '1'


def mail_configured():
    """True only when SMTP creds exist — OTP-by-mail flows must not gate
    logins on unconfigured deploys (user would never receive the code)."""
    return bool(os.environ.get('MAIL_USERNAME') and os.environ.get('MAIL_PASSWORD'))


def frontend_url():
    return os.environ.get('FRONTEND_URL', 'https://pulse-trade-zeta.vercel.app').rstrip('/')


def client_ip():
    # X-Forwarded-For is only honoured via ProxyFix (VERCEL / TRUST_PROXY=1),
    # so clients cannot spoof their address to dodge throttling.
    return request.remote_addr or "unknown"


def valid_email(email):
    return bool(email and len(email) <= 120 and EMAIL_RE.match(email))


def password_problem(password):
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if len(password) > 256:
        return "Password is too long."
    return None


# --------------------------------------------------------------------------- throttling

def _fail_key(email):
    return (client_ip(), (email or "").lower())


def login_blocked(email):
    return (_failures.get(_fail_key(email)) or 0) >= LOGIN_MAX_FAILURES


def record_failure(email):
    key = _fail_key(email)
    _failures.set(key, (_failures.get(key) or 0) + 1)


def clear_failures(email):
    _failures.pop(_fail_key(email))


# --------------------------------------------------------------------------- one-time codes

def generate_otp(email=None):
    """Random 6-digit code. (The legacy implementation derived codes from a
    fixed public TOTP secret, so anyone could compute them.)"""
    return f"{secrets.randbelow(10 ** 6):06d}"


def _digest(code, email):
    key = (app.config["SECRET_KEY"] or "").encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def start_pending_login(email, method, code=None, remember=False):
    """Remember a half-finished login in the (signed) session. Only an HMAC
    of the code is stored — the session cookie is readable by the client."""
    session.pop("otp", None)
    session["pending_login"] = {
        "email": email, "method": method, "exp": time.time() + OTP_TTL,
        "attempts": 0, "remember": bool(remember), "hash": _digest(code, email) if code else None,
    }
    session["email"] = email  # legacy key used by older templates


def pending_login():
    data = session.get("pending_login")
    if not data or data.get("exp", 0) < time.time():
        return None
    return data


def clear_pending_login():
    session.pop("pending_login", None)
    session.pop("email", None)
    session.pop("otp", None)


def check_pending_code(code):
    """Validate ``code`` for the pending login. Returns the pending dict on
    success, None otherwise (attempts are limited)."""
    data = pending_login()
    code = (code or "").strip().replace(" ", "")
    if not data or not code:
        return None
    data["attempts"] = data.get("attempts", 0) + 1
    session["pending_login"] = data
    if data["attempts"] > OTP_MAX_ATTEMPTS:
        clear_pending_login()
        return None
    method = data.get("method")
    ok = False
    if method in ("email", "admin_email") and data.get("hash"):
        ok = hmac.compare_digest(data["hash"], _digest(code, data["email"]))
    elif method == "totp":
        from crypto.models import User
        user = User.query.filter_by(email=data["email"]).first()
        ok = bool(user and user.totp_secret and verify_totp(user.totp_secret, code))
    elif method == "admin_totp":
        secret = os.environ.get("ADMIN_TOTP_SECRET", "")
        ok = bool(secret and verify_totp(secret, code))
    return data if ok else None


# --------------------------------------------------------------------------- TOTP 2FA

def new_totp_secret():
    return pyotp.random_base32()


def totp_uri(secret, email):
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="PulseTrade")


def verify_totp(secret, code):
    try:
        return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)
    except Exception:
        return False


# --------------------------------------------------------------------------- security log

def log_event(user, event, success=True):
    from crypto.models import LoginEvent
    try:
        db.session.add(LoginEvent(user_id=user.id if user else None, event=event, success=success,
                                  ip=client_ip()[:64], user_agent=(request.user_agent.string or "")[:255]))
        if user is not None and event == "login" and success:
            user.last_login_at = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"security log failed: {e}")


# --------------------------------------------------------------------------- email

def send_otp_email(to_email, otp, msg_title, msg_body, link=None):
    """Send a branded transactional email (OTP code and/or action link).
    Returns False (never raises) when mail is not configured."""
    if not to_email:
        return False
    msg = MailMessage(msg_title, sender=app.config.get("MAIL_DEFAULT_SENDER"), recipients=[to_email])
    body_html = Markup("<br>").join(escape(line) for line in str(msg_body or "").split("\n"))
    msg.html = render_template("email/notification.html", title=msg_title, body_html=body_html,
                               otp=otp, link=link, year=datetime.utcnow().year)
    msg.body = "\n".join(x for x in (msg_title, str(msg_body or ""), otp or "", link or "") if x)
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
