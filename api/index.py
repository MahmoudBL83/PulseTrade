import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("VERCEL", "1")

from crypto import app

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
