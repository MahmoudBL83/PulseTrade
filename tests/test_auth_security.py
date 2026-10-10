"""Authentication flows and regression tests for the security fixes."""
import uuid

import pyotp
import pytest


def _email():
    return f"sec-{uuid.uuid4().hex[:10]}@example.com"


def register(client, email, password="Secret123!"):
    return client.post("/register", json={"email": email, "firstName": "A", "lastName": "B",
                                          "password": password, "confirm_password": password}).get_json()


def test_register_validates_input(client):
    assert register(client, "not-an-email")["ok"] is False
    assert register(client, _email(), "short")["ok"] is False
    email = _email()
    assert register(client, email)["ok"] is True
    assert register(client, email)["ok"] is False                       # duplicate
    assert register(client, email.upper())["ok"] is False               # case-insensitive duplicate


def test_login_issues_working_bearer_token(app, client):
    email = _email()
    register(client, email)
    data = client.post("/login", json={"email": email, "password": "Secret123!", "admin": False}).get_json()
    assert data["ok"] and data["access_token"]
    fresh = app.test_client()
    me = fresh.get("/api/v2/auth/me", headers={"Authorization": "Bearer " + data["access_token"]}).get_json()
    assert me["data"]["email"] == email
    # legacy views using flask_login.current_user also accept the bearer token
    res = fresh.get("/api/v1/exchanges/", headers={"Authorization": "Bearer " + data["access_token"]})
    assert res.status_code == 200


def test_logout_revokes_token(app, client):
    email = _email()
    register(client, email)
    token = client.post("/api/v2/auth/login", json={"email": email, "password": "Secret123!"}).get_json()["data"]["access_token"]
    c = app.test_client()
    h = {"Authorization": "Bearer " + token}
    assert c.get("/api/v2/auth/me", headers=h).status_code == 200
    assert c.post("/api/v2/auth/logout", headers=h).status_code == 200
    assert app.test_client().get("/api/v2/auth/me", headers=h).status_code == 401


def test_bruteforce_lockout(client):
    email = _email()
    register(client, email)
    for _ in range(10):
        client.post("/login", json={"email": email, "password": "wrong-password", "admin": False})
    res = client.post("/login", json={"email": email, "password": "Secret123!", "admin": False})
    assert res.status_code == 429


def test_totp_two_factor_flow(app, client):
    email = _email()
    register(client, email)
    token = client.post("/api/v2/auth/login", json={"email": email, "password": "Secret123!"}).get_json()["data"]["access_token"]
    h = {"Authorization": "Bearer " + token}
    secret = client.post("/api/v2/auth/2fa/setup", headers=h).get_json()["data"]["secret"]
    assert client.post("/api/v2/auth/2fa/enable", headers=h, json={"code": "000000"}).status_code == 400
    assert client.post("/api/v2/auth/2fa/enable", headers=h, json={"code": pyotp.TOTP(secret).now()}).status_code == 200

    c = app.test_client()
    step1 = c.post("/api/v2/auth/login", json={"email": email, "password": "Secret123!"}).get_json()
    assert step1["ok"] is False and step1["otp_required"] and step1["method"] == "totp"
    assert c.post("/api/v2/auth/verify", json={"code": "123456"}).status_code == 400
    step2 = c.post("/api/v2/auth/verify", json={"code": pyotp.TOTP(secret).now()}).get_json()
    assert step2["ok"] and step2["data"]["access_token"]
    # one-shot login with the code included also works
    c2 = app.test_client()
    one = c2.post("/api/v2/auth/login", json={"email": email, "password": "Secret123!", "totp": pyotp.TOTP(secret).now()}).get_json()
    assert one["ok"]
    events = c2.get("/api/v2/auth/security-log", headers={"Authorization": "Bearer " + one["data"]["access_token"]}).get_json()["data"]
    assert any(e["event"] == "2fa_enabled" for e in events)


def test_legacy_login_redirects_to_code_page_for_2fa(app, client):
    email = _email()
    register(client, email)
    token = client.post("/api/v2/auth/login", json={"email": email, "password": "Secret123!"}).get_json()["data"]["access_token"]
    h = {"Authorization": "Bearer " + token}
    secret = client.post("/api/v2/auth/2fa/setup", headers=h).get_json()["data"]["secret"]
    client.post("/api/v2/auth/2fa/enable", headers=h, json={"code": pyotp.TOTP(secret).now()})
    c = app.test_client()
    data = c.post("/login", json={"email": email, "password": "Secret123!", "admin": False}).get_json()
    assert data["otp_required"] and data["redirect"] == "/verify-otp"
    assert b"authenticator" in c.get("/verify-otp").data
    # the legacy form post now redirects to the dashboard instead of rendering raw JSON
    res = c.post("/verify-otp", data={"otp": pyotp.TOTP(secret).now()})
    assert res.status_code == 302 and "/dashboard" in res.headers["Location"]


def test_email_otp_is_random_and_hashed(app, client, monkeypatch):
    from crypto import auth_core
    sent = {}
    monkeypatch.setenv("MAIL_USERNAME", "x")
    monkeypatch.setenv("MAIL_PASSWORD", "y")
    monkeypatch.setattr("crypto.auth.send_otp_email", lambda to, otp, *a, **k: sent.update(otp=otp) or True)
    email = _email()
    register(client, email)
    data = client.post("/login", json={"email": email, "password": "Secret123!", "admin": False}).get_json()
    assert data["otp_required"] and data["method"] == "email"
    code = sent["otp"]
    assert len(code) == 6 and code.isdigit()
    # the legacy implementation derived every code from one public constant secret
    assert len({auth_core.generate_otp() for _ in range(20)}) > 1
    with client.session_transaction() as s:
        assert "otp" not in s and code not in str(dict(s))          # only an HMAC is stored
    assert client.post("/api/v2/auth/verify", json={"code": "000000" if code != "000000" else "111111"}).status_code == 400
    assert client.post("/api/v2/auth/verify", json={"code": code}).get_json()["ok"]


def test_otp_attempts_are_limited(app, client, monkeypatch):
    monkeypatch.setenv("MAIL_USERNAME", "x")
    monkeypatch.setenv("MAIL_PASSWORD", "y")
    sent = {}
    monkeypatch.setattr("crypto.auth.send_otp_email", lambda to, otp, *a, **k: sent.update(otp=otp) or True)
    email = _email()
    register(client, email)
    client.post("/login", json={"email": email, "password": "Secret123!", "admin": False})
    for _ in range(5):
        client.post("/api/v2/auth/verify", json={"code": "999999" if sent["otp"] != "999999" else "888888"})
    assert client.post("/api/v2/auth/verify", json={"code": sent["otp"]}).status_code == 400


def test_user_stats_cannot_read_other_users(app, make_user_client):
    a, b = make_user_client(), make_user_client()
    a.post("/api/v2/paper/connect")
    b.post("/api/v2/paper/connect")
    b_id = b.get("/api/v2/auth/me").get_json()["data"]["id"]
    a_id = a.get("/api/v2/auth/me").get_json()["data"]["id"]
    res = a.post("/api/v1/user_stats/", json={"user_id": b_id}).get_json()
    assert all(e["owner_id"] == a_id for e in res["exchanges"])


def test_support_tickets_are_private(app, make_user_client):
    a, b = make_user_client(), make_user_client()
    t = a.post("/admin/support/tickets", json={"subject": "help", "content": "hi"}).get_json()
    assert b.get(f"/admin/support/messages?ticket_id={t['id']}").status_code == 404
    assert b.post(f"/admin/support/tickets/{t['id']}/messages", json={"content": "x"}).status_code == 404
    a_id = a.get("/api/v2/auth/me").get_json()["data"]["id"]
    listed = b.get(f"/admin/support/tickets?user_id={a_id}").get_json()
    assert all(x["id"] != t["id"] for x in listed)                    # user_id param ignored for users
    assert len(a.get("/admin/support/messages?ticket_id=%d" % t["id"]).get_json()) == 1


def test_admin_can_reply_and_user_is_notified(app, user_client, admin_client):
    t = user_client.post("/admin/support/tickets", json={"subject": "s", "content": "c"}).get_json()
    res = admin_client.post(f"/admin/support/tickets/{t['id']}/messages", json={"content": "on it", "is_admin": True})
    assert res.status_code == 201 and res.get_json()["is_admin"] is True
    notes = user_client.get("/api/v2/notifications").get_json()["data"]
    assert any("support team" in n["content"] for n in notes)
    assert admin_client.put(f"/admin/support/tickets/{t['id']}/close").get_json()["status"] == "closed"


def test_tap_success_requires_verified_charge(app, user_client, admin_client):
    from crypto import db
    from crypto.models import Subscription
    with app.app_context():
        pro = Subscription.query.filter_by(type="pro").first()
        pro.stripe_id = "price_pro_test"
        db.session.commit()
    user_client.get("/checkout_success_tab?session_id=price_pro_test")
    me = user_client.get("/api/v2/auth/me").get_json()["data"]
    assert me["plan"]["type"] == "free"                              # no free upgrades any more


def test_cron_requires_secret_when_configured(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert client.get("/api/cron/all").status_code == 401
    res = client.get("/api/cron/all", headers={"Authorization": "Bearer s3cret"})
    assert res.status_code == 200 and "stats" in res.get_json()


def test_drop_all_needs_confirmation(admin_client):
    assert admin_client.get("/drop_all/").status_code == 400


def test_admin_login_without_second_factor_configured(app, client):
    res = client.post("/login", json={"admin": True, "email": "admin", "password": "admin-test-pass"}).get_json()
    assert res["ok"] and res["otp_required"] is False
    assert client.get("/admin").status_code == 200
    assert client.post("/login", json={"admin": True, "email": "admin", "password": "nope"}).status_code == 401


def test_admin_totp(app, client, monkeypatch):
    secret = pyotp.random_base32()
    monkeypatch.setenv("ADMIN_TOTP_SECRET", secret)
    res = client.post("/login", json={"admin": True, "email": "admin", "password": "admin-test-pass"}).get_json()
    assert res["otp_required"] and res["method"] == "totp"
    assert client.get("/admin").status_code == 302
    assert client.post("/api/v2/auth/verify", json={"code": pyotp.TOTP(secret).now()}).get_json()["data"]["admin"]
    assert client.get("/admin").status_code == 200


def test_webhook_channels_reject_ssrf(user_client):
    res = user_client.put("/api/v2/notifications/channels", json={"webhook_url": "http://169.254.169.254/latest", "webhook_enabled": True})
    assert res.status_code == 400
    ok = user_client.put("/api/v2/notifications/channels", json={"webhook_url": "https://discord.com/api/webhooks/1/abc", "webhook_enabled": True})
    assert ok.get_json()["data"]["webhook_enabled"] is True


def test_csv_export_neutralises_formulas(app, paper_user, prices):
    from crypto import db
    from crypto.models import JournalEntry
    paper_user.post("/api/v2/journal", json={"title": "=HYPERLINK(\"http://evil\")", "symbol": "BTC/USDT"})
    csv_text = paper_user.get("/api/v2/export/journal.csv").get_data(as_text=True)
    assert "'=HYPERLINK" in csv_text


def test_unknown_api_route_is_json_404(client):
    res = client.get("/api/v2/does-not-exist")
    assert res.status_code == 404 and res.get_json()["ok"] is False
    page = client.get("/definitely-not-a-page")
    assert page.status_code == 404 and b"Page not found" in page.data
