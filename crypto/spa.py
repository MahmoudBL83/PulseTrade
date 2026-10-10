"""Serves the React app (frontend/ built into crypto/static/app) under /app.

Fingerprinted assets are cached forever; index.html is never cached so new
deploys are picked up immediately. Unknown /app/* paths fall back to
index.html for client-side routing."""
import os

from flask import redirect, render_template_string, send_from_directory

from crypto import app

DIST = os.path.join(app.root_path, "static", "app")


def has_build():
    return os.path.isfile(os.path.join(DIST, "index.html"))


_MISSING = """<!doctype html><html><head><meta charset="utf-8"><title>PulseTrade</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0e14;color:#e6e8ee;
font:16px/1.6 system-ui,sans-serif}main{max-width:560px;padding:24px}code{background:#1a1f2b;padding:2px 6px;border-radius:4px}</style>
</head><body><main><h1>The new app is not built yet</h1>
<p>Build it once with:</p><p><code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>
<p>Or run <code>npm run dev</code> in <code>frontend/</code> for hot reload on port 5173.</p>
<p><a href="/" style="color:#f0b90b">Back to the classic site</a></p></main></body></html>"""


@app.route("/app")
def react_app_root():
    return redirect("/app/", code=308)


@app.route("/app/", defaults={"path": ""})
@app.route("/app/<path:path>")
def react_app(path):
    if path and os.path.isfile(os.path.join(DIST, path)):
        resp = send_from_directory(DIST, path)
        if path.startswith("assets/"):
            resp.cache_control.public = True
            resp.cache_control.max_age = 31536000
            resp.cache_control.immutable = True
        return resp
    if not has_build():
        return render_template_string(_MISSING), 503
    resp = send_from_directory(DIST, "index.html")
    resp.cache_control.no_cache = True
    resp.cache_control.no_store = True
    return resp
