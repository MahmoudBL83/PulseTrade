"""Hit every registered route as anonymous / user / admin and assert the server
never crashes (unhandled exception / HTTP 500). Deliberate 502 (exchange
unreachable — the network is blocked, see conftest) and 503 (feature not
configured) answers are fine."""
import pytest

from crypto import app as _app

# Routes that would destroy the shared test database or block forever.
SKIP = {"/drop_all/"}

ARG_VALUES = {
    "exchange_name": "binance",
    "token": "invalid-token",
    "job": "price",
    "category_id": "1",
}


def _build(rule):
    url = rule.rule
    for arg in rule.arguments:
        conv = rule._converters.get(arg)
        value = ARG_VALUES.get(arg, "1" if conv is not None and conv.__class__.__name__ == "IntegerConverter" else "x")
        url = url.replace(f"<int:{arg}>", value).replace(f"<{arg}>", value)
    return url


def _cases():
    out = []
    for rule in _app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.rule in SKIP:
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            out.append(pytest.param(method, _build(rule), id=f"{method} {rule.rule}"))
    return out


CASES = _cases()


def _call(client, method, url):
    kwargs = {"json": {}} if method in ("POST", "PUT", "DELETE", "PATCH") else {}
    try:
        res = client.open(url, method=method, **kwargs)
    except Exception as e:  # unhandled exception == bug
        return None, repr(e)
    return res.status_code, res.get_data()[:300].decode("utf-8", "replace")


@pytest.mark.parametrize("method,url", CASES)
def test_anonymous(client, method, url):
    status, body = _call(client, method, url)
    assert status is not None and status != 500, f"{method} {url} -> {status}: {body}"


@pytest.mark.parametrize("method,url", CASES)
def test_user(user_client, method, url):
    status, body = _call(user_client, method, url)
    assert status is not None and status != 500, f"{method} {url} -> {status}: {body}"


@pytest.mark.parametrize("method,url", CASES)
def test_admin(admin_client, method, url):
    status, body = _call(admin_client, method, url)
    assert status is not None and status != 500, f"{method} {url} -> {status}: {body}"
