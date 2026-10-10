import os

from crypto import app, start_background_engine

# Run the in-process engine in exactly one web process (gunicorn -w 1).
if os.environ.get("START_SCHEDULER") == "1":
    start_background_engine()

if __name__ == "__main__":
    app.run()
