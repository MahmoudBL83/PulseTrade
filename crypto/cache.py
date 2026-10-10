"""Tiny thread-safe in-process TTL cache (no external dependency).

Used for market data, Stripe invoice checks and exchange credential checks so
hot request paths do not repeat slow network calls."""
import threading
import time

_MISSING = object()


class TTLCache:
    def __init__(self, ttl=10.0, maxsize=2048):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            item = self._data.get(key, _MISSING)
            if item is _MISSING:
                return default
            expires, value = item
            if expires < time.monotonic():
                self._data.pop(key, None)
                return default
            return value

    def set(self, key, value, ttl=None):
        with self._lock:
            if len(self._data) >= self.maxsize:
                self._evict()
            self._data[key] = (time.monotonic() + (self.ttl if ttl is None else ttl), value)
        return value

    def pop(self, key):
        with self._lock:
            self._data.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()

    def get_or_set(self, key, factory, ttl=None):
        value = self.get(key, _MISSING)
        if value is _MISSING:
            value = self.set(key, factory(), ttl)
        return value

    def _evict(self):
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)
        if len(self._data) >= self.maxsize:
            # drop the oldest-expiring quarter
            for k, _ in sorted(self._data.items(), key=lambda kv: kv[1][0])[: self.maxsize // 4]:
                self._data.pop(k, None)
