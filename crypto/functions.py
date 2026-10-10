import json
import os
import ccxt
from flask_login import current_user
from crypto import models
from crypto import market
from crypto.errors import ApiError, ExchangeNotConnected

CCXT_OPTIONS = {'timeout': 10000, 'enableRateLimit': True}


def build_exchange(exchange_row):
    """Instantiate a client for a user's connected exchange row (models.Exchange).
    Paper accounts get the built-in simulator; everything else goes to ccxt."""
    if exchange_row is None:
        raise ExchangeNotConnected()
    if exchange_row.is_paper:
        from crypto.paper import PaperExchange
        return PaperExchange(exchange_row.owner_id)
    name = exchange_row.name
    if name not in ccxt.exchanges:
        raise ApiError(f"unsupported exchange: {name}", 400)
    api_key, api_secret, password = exchange_row.get_creds()
    opts = {'apiKey': api_key, 'secret': api_secret, **CCXT_OPTIONS}
    if password:
        opts['password'] = password
    exchange = getattr(ccxt, name)(opts)
    if exchange_row.demo:
        exchange.set_sandbox_mode(True)
    return exchange


def resolve_user(id=None):
    if id:
        user = models.db.session.get(models.User, int(id))
    else:
        user = current_user if getattr(current_user, "is_authenticated", False) else None
    if user is None:
        raise ApiError("authentication required", 401)
    return user


def find_exchange_row(user, exchange_name=None):
    """The user's exchange row by name (case-insensitive) or the active one."""
    rows = user.exchanges
    if not exchange_name:
        row = rows.filter(models.Exchange.isActive == True).first() or rows.first()
        if row is None:
            raise ExchangeNotConnected()
        return row
    row = rows.filter(models.Exchange.name == exchange_name).first()
    if row is None:
        wanted = str(exchange_name).lower().replace("okex", "okx")
        for r in rows.all():
            if (r.name or "").lower().replace("okex", "okx") == wanted:
                return r
        raise ExchangeNotConnected(exchange_name)
    return row


def connectExchange(exchange_name=None,id=None):
    """Client for the current (or given) user's exchange. Raises
    ExchangeNotConnected (pages redirect to /exchanges, APIs get a 400)."""
    user = resolve_user(id)
    return build_exchange(find_exchange_row(user, exchange_name))


def _read_price_file(exchange_name, symbol):
    """Prices written by the Celery `update_price_data` workers, if present."""
    symbol_id = f"{exchange_name}{symbol.replace('/', '')}"
    path = os.path.join("pricesData", f"{symbol_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f).get(symbol)
        if data and data[0]:
            return data
    except (OSError, ValueError, AttributeError, IndexError):
        return None
    return None


def getPrice_assets(exchange_name,symbol,id=None,volume_par=False,full=False):
    """Price snapshot for ``symbol``. Reads worker price files first (legacy
    behaviour), then falls back to the cached market data service so prices
    work on serverless / demo deploys without background workers.

    Returns price, (price, volume) or the full 7-tuple depending on flags."""
    exchange_name = str(exchange_name or "").replace('okex','okx').upper()
    symbol = market.normalize_symbol(symbol)
    price = volume = change = percentage = high = low = open_price = 0
    base, quote = symbol.split("/")

    if base == quote or (base in market.STABLES and quote in market.STABLES):
        price, volume = 1, 1
    else:
        reversed_pair = base == 'USDT'
        lookup = f"{quote}/USDT" if reversed_pair else symbol
        data = _read_price_file(exchange_name, lookup)
        if data:
            price = data[0]
            volume, change, percentage, high, low, open_price = (list(data[1:7]) + [0] * 6)[:6]
        elif quote != 'USDT' and not reversed_pair:
            # cross pair from the two USDT legs when the workers have them
            leg_q = _read_price_file(exchange_name, f"{quote}/USDT")
            leg_b = _read_price_file(exchange_name, f"{base}/USDT")
            if leg_q and leg_b and leg_q[0]:
                price = leg_b[0] / leg_q[0]
        if not price:
            try:
                t = market.ticker(exchange_name.lower() or None, lookup)
                price = t["last"]
                volume, change, percentage = t["baseVolume"], t["change"], t["percentage"]
                high, low, open_price = t["high"], t["low"], t["open"]
            except Exception as e:
                print(f"price lookup failed for {symbol} on {exchange_name}: {e}")
        if reversed_pair:
            price = (1 / price) if price else 0

    if volume_par:
        return price,volume
    elif full:
        return price,volume,change,percentage,high,low,open_price
    else:
        return price


def getPrice(exchange_name,symbol,id=None,volume=False):
    """Last price via the user's own exchange connection, falling back to the
    market data service (which never needs credentials)."""
    try:
        exchange = connectExchange(str(exchange_name).lower(), id)
        data = exchange.fetch_ticker(symbol)
        price = data.get('close') or data.get('last')
        if volume:
            return price, data.get('baseVolume') or 0
        if price:
            return price
    except Exception:
        pass
    t = market.ticker(exchange_name, symbol)
    if volume:
        return t["last"], t["baseVolume"]
    return t["last"]


def getVolume(exchange_name,symbol,id=None):
    try:
        exchange = connectExchange(exchange_name,id)
        volume = exchange.fetch_ticker(symbol)['baseVolume']
    except Exception:
        volume = market.ticker(exchange_name, symbol)["baseVolume"]
    return volume
