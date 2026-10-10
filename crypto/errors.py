"""Central error handling.

Every API failure becomes a JSON body ``{"message": ..., "ok": false}`` with a
meaningful status code; page requests get a redirect or a small error page.
Unexpected exceptions are logged with a traceback and never leak internals.
"""
import logging
import os
import traceback

from flask import jsonify, redirect, render_template_string, request, url_for
from werkzeug.exceptions import HTTPException

log = logging.getLogger("pulsetrade")


class ApiError(Exception):
    """Raise from any view to return a clean JSON error."""

    status = 400

    def __init__(self, message, status=None, **extra):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        self.extra = extra


class ExchangeNotConnected(ApiError):
    """The user has no (active / named) exchange connected. Page requests are
    redirected to the exchanges page, matching the legacy behaviour."""

    status = 400

    def __init__(self, exchange_name=None):
        msg = (f"{exchange_name} is not connected to your account" if exchange_name
               else "Connect an exchange first")
        super().__init__(msg, exchange=exchange_name)


def wants_json():
    if request.path.startswith(("/api/", "/admin/support/", "/admin/blog/")):
        return True
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _json(message, status, **extra):
    body = {"message": message, "ok": False}
    body.update(extra)
    return jsonify(body), status


_ERROR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ code }} · PulseTrade</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0e14;color:#e6e8ee;
font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}main{text-align:center;padding:24px}
h1{font-size:64px;margin:0;color:#f0b90b}a{color:#f0b90b}</style></head>
<body><main><h1>{{ code }}</h1><p>{{ message }}</p><p><a href="/">Home</a> · <a href="/app/">Open the app</a></p></main></body></html>"""


def error_page(code, message):
    return render_template_string(_ERROR_PAGE, code=code, message=message), code


def register_error_handlers(app):
    @app.errorhandler(ExchangeNotConnected)
    def _no_exchange(e):
        if wants_json():
            return _json(e.message, e.status, **e.extra)
        return redirect(url_for("exchanges"))

    @app.errorhandler(ApiError)
    def _api_error(e):
        if wants_json():
            return _json(e.message, e.status, **e.extra)
        return error_page(e.status, e.message)

    @app.errorhandler(KeyError)
    def _missing_field(e):
        # Raised by request.json["field"] lookups in the legacy views.
        field = e.args[0] if e.args else "?"
        log.info("missing field %r on %s %s", field, request.method, request.path)
        if wants_json():
            return _json(f"Missing field: {field}", 400, field=field)
        return error_page(400, f"Missing field: {field}")

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    def _bad_value(e):
        # float()/int() on user input. Logged with traceback so genuine bugs stay visible.
        log.warning("bad value on %s %s: %s\n%s", request.method, request.path, e, traceback.format_exc())
        if wants_json():
            return _json("Invalid value in request", 400)
        return error_page(400, "Invalid value in request")

    @app.errorhandler(HTTPException)
    def _http(e):
        if wants_json():
            return _json(e.description or e.name, e.code or 500)
        if e.code == 404:
            return error_page(404, "Page not found")
        return e

    @app.errorhandler(Exception)
    def _unhandled(e):
        log.error("unhandled error on %s %s\n%s", request.method, request.path, traceback.format_exc())
        try:
            from crypto import db
            db.session.rollback()
        except Exception:
            pass
        detail = {"error": repr(e)[:300]} if os.environ.get("PULSE_TESTING") == "1" else {}
        if wants_json():
            return _json("Something went wrong. Please try again.", 500, **detail)
        return error_page(500, "Something went wrong. Please try again." + (f" {detail['error']}" if detail else ""))
