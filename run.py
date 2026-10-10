"""Local / single-server entry point.

    python run.py                      web + in-process engine (bots, smart trades,
                                       alerts, paper orders) — no Redis needed
    ENGINE=celery python run.py        legacy mode: also starts a Celery worker
                                       (requires Redis) for /start_data_stream loops
"""
import os
import subprocess

from crypto import app, socketio, start_background_engine, engine_mode

if __name__ == '__main__':
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    if os.environ.get("VERCEL"):
        # Serverless: no Celery worker, no scheduler, no SocketIO long-run.
        # Background jobs run via Vercel Cron -> /api/cron/* instead.
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    else:
        worker = None
        if engine_mode() == "celery" or os.environ.get("START_CELERY") == "1":
            worker = subprocess.Popen(
                ['celery', '-A', 'crypto.celery', 'worker', '-l', 'info', '-P', 'gevent', '-c', '8']
            )
        start_background_engine()
        try:
            # use_reloader=False: the reloader runs the app twice, which would
            # double every engine tick (and every bot order).
            socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
        finally:
            if worker is not None:
                worker.terminate()
