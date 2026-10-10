"""Optional real-time ticker streaming with ccxt.pro (bundled with ccxt).

MARKET_STREAM=1 starts one asyncio loop in a daemon thread (long-running
processes only — not on serverless) that watches the most liquid USDT pairs
plus every user's watchlist on MARKET_DATA_EXCHANGE. Each update:
  * refreshes crypto.market's ticker cache, so REST calls are skipped while
    the stream is healthy (entries expire after 30s if it stalls), and
  * is pushed (throttled to 1/s) to Socket.IO clients in the "market" room.
"""
import asyncio
import logging
import os
import threading
import time

from crypto import market

log = logging.getLogger("pulsetrade.stream")

MAX_SYMBOLS = int(os.environ.get("MARKET_STREAM_SYMBOLS", "40"))
_lock = threading.Lock()
_state = {"running": False, "thread": None, "exchange": None, "symbols": [], "updates": 0,
          "last_update": None, "last_error": None, "started_at": None}


def enabled():
    return os.environ.get("MARKET_STREAM", "0") == "1" and not os.environ.get("VERCEL")


def status():
    with _lock:
        return {k: v for k, v in _state.items() if k != "thread"} | {"enabled": enabled()}


def _wanted_symbols(app, exchange_id):
    """Top liquid pairs + all watchlisted symbols (deduplicated, capped)."""
    from crypto.models import WatchlistItem
    symbols = []
    try:
        with app.app_context():
            symbols += [w.symbol for w in WatchlistItem.query.with_entities(WatchlistItem.symbol).distinct().limit(200)]
    except Exception as e:
        log.debug("watchlist symbols unavailable: %s", e)
    symbols += [t["symbol"] for t in market.tickers(exchange_id, "USDT", MAX_SYMBOLS)]
    seen, out = set(), []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[:MAX_SYMBOLS]


async def _run(app, exchange_id):
    import ccxt.pro as ccxtpro
    from crypto.notify import emit_to_user  # noqa: F401  (ensures socket handlers are registered)
    from crypto import socketio

    ex = getattr(ccxtpro, exchange_id)({"enableRateLimit": True, "newUpdates": True})
    pending, last_emit, last_refresh = {}, 0.0, 0.0
    try:
        while _state["running"]:
            now = time.monotonic()
            if now - last_refresh > 60 or not _state["symbols"]:
                syms = await asyncio.to_thread(_wanted_symbols, app, exchange_id)
                with _lock:
                    _state["symbols"] = syms
                last_refresh = now
            try:
                if ex.has.get("watchTickers"):
                    updates = await ex.watch_tickers(_state["symbols"])
                else:
                    sym = _state["symbols"][_state["updates"] % len(_state["symbols"])]
                    updates = {sym: await ex.watch_ticker(sym)}
            except Exception as e:  # reconnects are handled by ccxt.pro; back off on hard errors
                with _lock:
                    _state["last_error"] = str(e)[:300]
                log.warning("stream error on %s: %s", exchange_id, e)
                await asyncio.sleep(5)
                continue
            for sym, t in (updates or {}).items():
                norm = market._norm_ticker(t, sym, f"{exchange_id}:ws")
                market._ticker_cache.set((exchange_id, sym), norm, ttl=30)
                pending[sym] = {"s": sym, "p": norm["last"], "c": norm["percentage"], "v": norm["quoteVolume"]}
            with _lock:
                _state["updates"] += len(updates or {})
                _state["last_update"] = time.time()
            if pending and time.monotonic() - last_emit >= 1.0:
                try:
                    socketio.emit("tickers", list(pending.values()), to="market")
                except Exception as e:
                    log.debug("socket emit skipped: %s", e)
                pending, last_emit = {}, time.monotonic()
    finally:
        await ex.close()


def start(app):
    """Start the streamer once per process (no-op unless MARKET_STREAM=1)."""
    if not enabled():
        return False
    exchange_id = market.default_exchange()
    import ccxt.pro as ccxtpro
    if exchange_id not in ccxtpro.exchanges:
        log.warning("ccxt.pro has no websocket support for %s; streaming disabled", exchange_id)
        return False
    with _lock:
        if _state["running"]:
            return True
        _state.update(running=True, exchange=exchange_id, started_at=time.time(), last_error=None)

    def target():
        try:
            asyncio.run(_run(app, exchange_id))
        except Exception as e:
            log.exception("market stream stopped")
            with _lock:
                _state["last_error"] = str(e)[:300]
        finally:
            with _lock:
                _state["running"] = False

    thread = threading.Thread(target=target, name="ccxt-pro-stream", daemon=True)
    with _lock:
        _state["thread"] = thread
    thread.start()
    log.info("ccxt.pro market stream started on %s", exchange_id)
    return True


def stop():
    with _lock:
        _state["running"] = False
