"""Capability-aware account order reports shared by the old and new UIs."""
import re

import ccxt

from crypto.functions import build_exchange
from crypto.models import Bot, PaperOrder, SmartTrade, Transaction, WatchlistItem


_SYMBOL = re.compile(r"^[A-Z0-9._-]+/[A-Z0-9._-]+(?::[A-Z0-9._-]+)?$")


def valid_symbol(value):
    symbol = str(value or "").strip().upper()
    if symbol and (len(symbol) > 64 or not _SYMBOL.fullmatch(symbol)):
        raise ValueError("Symbol must look like BTC/USDT or BTC/USDT:USDT")
    return symbol


def known_symbols(user_id, exchange_name, maximum=8):
    """Recent account activity is a better pair seed than a market watchlist."""
    symbols = []

    def add(value):
        try:
            value = valid_symbol(value)
        except ValueError:
            return
        if value and value not in symbols and len(symbols) < maximum:
            symbols.append(value)

    for row in (Transaction.query.filter_by(user_id=user_id, exchange=exchange_name)
                .order_by(Transaction.id.desc()).limit(maximum).all()):
        add(row.symbol)
    for row in (SmartTrade.query.filter_by(user_id=user_id, exchange=exchange_name)
                .order_by(SmartTrade.id.desc()).limit(maximum).all()):
        add(row.symbol)
    for row in (Bot.query.filter_by(owner_id=user_id, exchange=exchange_name)
                .order_by(Bot.id.desc()).limit(maximum).all()):
        add(row.symbol or f"{row.base_currency}/{row.quote_currency}")
    if exchange_name == "paper":
        for row in (PaperOrder.query.filter_by(user_id=user_id)
                    .order_by(PaperOrder.id.desc()).limit(maximum).all()):
            add(row.symbol)
    for row in (WatchlistItem.query.filter_by(user_id=user_id, exchange=exchange_name)
                .order_by(WatchlistItem.id.desc()).limit(maximum).all()):
        add(row.symbol)
    return symbols


def _capable(exchange, feature):
    return bool(getattr(exchange, "has", {}).get(feature))


def _error(exc):
    if isinstance(exc, ccxt.PermissionDenied):
        return "The API key cannot read account orders. Check permissions."
    if isinstance(exc, ccxt.AuthenticationError):
        return "Authentication failed. Check API key permissions and IP allowlist."
    if isinstance(exc, ccxt.RateLimitExceeded):
        return "Exchange rate limit reached. Retry shortly."
    if isinstance(exc, ccxt.NetworkError):
        return "Exchange network request failed. Retry shortly."
    if isinstance(exc, ccxt.BadSymbol):
        return "This pair is unavailable on the exchange."
    return f"Exchange request failed ({type(exc).__name__})."


def _fetch(exchange, method, symbols, limit, force_symbol=False):
    """Try venue-wide history, then pair-scoped history when CCXT requires it."""
    fetch = getattr(exchange, method)
    if not force_symbol:
        try:
            return list(fetch(limit=limit)), False
        except ccxt.ArgumentsRequired:
            if not symbols:
                return [], True
    rows, skipped = [], []
    for symbol in symbols:
        try:
            rows.extend(fetch(symbol=symbol, limit=limit))
        except ccxt.BadSymbol as exc:
            if force_symbol:
                raise
            skipped.append(exc)
        except ccxt.NotSupported as exc:
            if force_symbol:
                raise
            skipped.append(exc)
    if skipped and len(skipped) == len(symbols):
        raise skipped[0]
    return rows, False


def collect(user, kind, *, exchange_name=None, symbol=None, limit=100, conditional=False):
    """Return orders plus source diagnostics. No account failure masquerades as empty history."""
    if kind not in ("open", "history", "fills"):
        raise ValueError("Invalid order report")
    symbol = valid_symbol(symbol)
    limit = max(1, min(int(limit), 200))
    rows, sources = [], []
    connected = user.exchanges.all()
    if exchange_name:
        connected = [row for row in connected if row.name.lower() == exchange_name.lower()]
        if not connected:
            raise ValueError("Exchange is not connected")
    for row in connected:
        symbols = [symbol] if symbol else known_symbols(user.id, row.name)
        source = {"exchange": row.name, "status": "ok", "count": 0,
                  "symbols": symbols, "message": ""}
        sources.append(source)
        try:
            exchange = build_exchange(row)
        except Exception as exc:
            source.update(status="error", message=_error(exc))
            continue
        methods = ({"open": ["fetchOpenOrders"],
                    "history": ["fetchClosedOrders", "fetchCanceledOrders"],
                    "fills": ["fetchMyTrades"]})[kind]
        supported = [feature for feature in methods if _capable(exchange, feature)]
        if (kind == "history" and _capable(exchange, "fetchOrders")
                and getattr(exchange, "has", {}).get("fetchClosedOrders") == "emulated"
                and getattr(exchange, "has", {}).get("fetchCanceledOrders") == "emulated"):
            # Both CCXT emulations derive from fetchOrders; one call per pair
            # avoids fetching the same Binance order list twice.
            supported = ["fetchOrders"]
        if kind == "history" and not supported and _capable(exchange, "fetchOrders"):
            supported = ["fetchOrders"]
        if not supported:
            source.update(status="unsupported", message="This exchange does not provide this report through CCXT.")
            continue
        errors, requires_symbol = [], False
        for feature in supported:
            method = {"fetchOpenOrders": "fetch_open_orders",
                      "fetchClosedOrders": "fetch_closed_orders",
                      "fetchCanceledOrders": "fetch_canceled_orders",
                      "fetchOrders": "fetch_orders", "fetchMyTrades": "fetch_my_trades"}[feature]
            try:
                fetched, missing = _fetch(exchange, method, symbols, limit, force_symbol=bool(symbol))
                requires_symbol |= missing
                for item in fetched:
                    if not isinstance(item, dict):
                        continue
                    if kind == "history" and feature == "fetchOrders" and item.get("status") not in ("closed", "canceled", "cancelled"):
                        continue
                    if symbol and item.get("symbol") != symbol:
                        continue
                    rows.append({**item, "exchange": row.name})
            except ccxt.NotSupported as exc:
                if kind == "history" and feature == "fetchClosedOrders" and _capable(exchange, "fetchOrders"):
                    try:
                        fetched, missing = _fetch(exchange, "fetch_orders", symbols, limit, force_symbol=bool(symbol))
                        requires_symbol |= missing
                        rows.extend({**item, "exchange": row.name} for item in fetched
                                    if isinstance(item, dict) and item.get("status") in ("closed", "canceled", "cancelled")
                                    and (not symbol or item.get("symbol") == symbol))
                        continue
                    except Exception as fallback_exc:
                        exc = fallback_exc
                errors.append(_error(exc))
            except Exception as exc:
                errors.append(_error(exc))
        if kind == "open" and conditional and "fetchOpenOrders" in supported:
            # Legacy venues expose stop/trigger orders in separate order books.
            for order_type in ("limit", "market", "trigger"):
                params = {"stop": True, "ordType": order_type}
                try:
                    scopes = [symbol] if symbol else [None]
                    for scope in scopes:
                        for item in exchange.fetch_open_orders(symbol=scope, limit=limit, params=params):
                            if isinstance(item, dict):
                                rows.append({**item, "exchange": row.name})
                except ccxt.ArgumentsRequired:
                    for scope in symbols:
                        try:
                            for item in exchange.fetch_open_orders(symbol=scope, limit=limit, params=params):
                                if isinstance(item, dict):
                                    rows.append({**item, "exchange": row.name})
                        except ccxt.BaseError:
                            continue
                except ccxt.BaseError:
                    # Supplemental venue-specific book; the unified report may
                    # still be complete and must remain usable.
                    continue
        source["count"] = len([item for item in rows if item["exchange"] == row.name])
        if errors:
            source.update(status="partial" if source["count"] else "error", message=" ".join(dict.fromkeys(errors)))
        elif requires_symbol:
            source.update(status="pair_required", message="Enter a pair to fetch this exchange's history.")
    unique = {}
    for item in rows:
        key = (item["exchange"], item.get("id") or item.get("order"), item.get("symbol"))
        unique[key] = item
    for source in sources:
        source["count"] = sum(item["exchange"] == source["exchange"] for item in unique.values())
    result = sorted(unique.values(), key=lambda item: item.get("timestamp") or 0, reverse=True)[:limit]
    return result, sources
