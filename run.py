import os
from crypto import app, scheduler
from crypto import socketio
import subprocess

if __name__ == '__main__':
    if os.environ.get("VERCEL"):
        # Serverless: no Celery worker, no scheduler, no SocketIO long-run.
        # Background jobs run via Vercel Cron -> /api/cron/* instead.
        socketio.run(app, debug=False)
    else:
        celery_worker_process = subprocess.Popen(
            ['celery', '-A', 'crypto.celery', 'worker', '-l', 'info', '-P', 'gevent', '-c', '8']
        )
        scheduler.start()
        try:
            socketio.run(app, debug=True)
        finally:
            celery_worker_process.terminate()
