# --- 1) build the React app ---------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite outputs to ../crypto/static/app
RUN mkdir -p ../crypto/static && npm run build

# --- 2) python runtime ----------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crypto/ ./crypto/
COPY --from=frontend /build/crypto/static/app ./crypto/static/app
COPY search_crypto.py search_crypto.json wsgi.py run.py ./

EXPOSE 8000
# One process (so the in-process engine runs once) with threads for concurrency.
ENV START_SCHEDULER=1 ENGINE=scheduler
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "16", "-b", "0.0.0.0:8000", "--timeout", "120", "wsgi:app"]
