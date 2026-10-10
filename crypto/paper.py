"""Paper trading: a ccxt-compatible simulated exchange.

It implements the subset of the ccxt API PulseTrade uses (balances, markets,
tickers, candles, market/limit/trigger orders, order history), so dashboards,
manual trading, convert, DCA bots and smart trades all run against it with no
exchange account. Prices come from crypto.market (live public data or the
synthetic market), fills are instant for market orders and limit/trigger
orders are matched whenever the account is touched or the engine ticks.
"""
from datetime import datetime

import ccxt

from crypto import db, market
from crypto.models import PaperAccount, PaperOrder

NAME = "paper"
DEFAULT_START = 10000.0
EPS = 1e-12


# --------------------------------------------------------------------------- account

def get_account(user_id, lock=False):
    q = PaperAccount.query.filter_by(user_id=user_id)
    if lock:
        q = q.with_for_update()
    acc = q.first()
    if acc is None:
        acc = PaperAccount(user_id=user_id, balances={"USDT": {"free": DEFAULT_START, "used": 0.0}},
                           starting_balance=DEFAULT_START, fee_rate=0.001)
        db.session.add(acc)
        db.session.flush()
    return acc


def reset_account(user_id, starting_balance=DEFAULT_START):
    starting_balance = max(10.0, min(float(starting_balance or DEFAULT_START), 10_000_000.0))
    PaperOrder.query.filter_by(user_id=user_id, status="open").update({"status": "canceled", "reserved": 0.0})
    acc = get_account(user_id, lock=True)
    acc.balances = {"USDT": {"free": starting_balance, "used": 0.0}}
    acc.starting_balance = starting_balance
    acc.reset_at = datetime.utcnow()
    db.session.commit()
    return acc


def _balances(acc):
    out = {}
    for cur, b in (acc.balances or {}).items():
        out[cur] = {"free": float(b.get("free") or 0), "used": float(b.get("used") or 0)}
    return out


def _adjust(bal, cur, free=0.0, used=0.0):
    row = bal.setdefault(cur, {"free": 0.0, "used": 0.0})
    row["free"] = row["free"] + free
    row["used"] = row["used"] + used
    for k in ("free", "used"):
        if abs(row[k]) < EPS:
            row[k] = 0.0
    if row["free"] < -1e-9 or row["used"] < -1e-9:
        raise ccxt.InsufficientFunds(f"paper: insufficient {cur} balance")
    row["free"], row["used"] = max(row["free"], 0.0), max(row["used"], 0.0)


# --------------------------------------------------------------------------- orders

def _to_ccxt(o):
    ts = int((o.created_at or datetime.utcnow()).timestamp() * 1000)
    filled = o.filled or 0.0
    avg = o.average
    return {
        "id": str(o.id), "clientOrderId": None, "exchange": NAME,
        "timestamp": ts, "datetime": (o.created_at or datetime.utcnow()).isoformat() + "Z",
        "lastTradeTimestamp": int(o.updated_at.timestamp() * 1000) if o.updated_at and filled else None,
        "symbol": o.symbol, "type": o.type, "side": o.side,
        "price": o.price if o.price else avg, "average": avg,
        "amount": o.amount, "filled": filled, "remaining": max((o.amount or 0) - filled, 0.0),
        "cost": filled * (avg or 0.0), "status": o.status,
        "fee": {"cost": o.fee or 0.0, "currency": o.fee_currency} if filled else None,
        "triggerPrice": o.trigger_price, "stopPrice": o.trigger_price,
        "stopLossPrice": None, "takeProfitPrice": None, "reduceOnly": False,
        "timeInForce": "GTC", "postOnly": False, "trades": [], "info": {"paper": True},
    }


def _fill(acc, bal, order, fill_price):
    base, quote = market.split_symbol(order.symbol)
    amount = order.amount
    cost = amount * fill_price
    fee_rate = acc.fee_rate if acc.fee_rate is not None else 0.001
    if order.side == "buy":
        if order.reserved:
            # release the reservation; refund the difference if filled cheaper
            _adjust(bal, quote, free=order.reserved - cost, used=-order.reserved)
        else:
            _adjust(bal, quote, free=-cost)
        fee = amount * fee_rate
        _adjust(bal, base, free=amount - fee)
        order.fee, order.fee_currency = fee, base
    else:
        if order.reserved:
            _adjust(bal, base, used=-order.reserved)
        else:
            _adjust(bal, base, free=-amount)
        fee = cost * fee_rate
        _adjust(bal, quote, free=cost - fee)
        order.fee, order.fee_currency = fee, quote
    order.filled = amount
    order.average = fill_price
    order.status = "closed"
    order.reserved = 0.0
    order.updated_at = datetime.utcnow()


def _reserve(bal, order, ref_price):
    base, quote = market.split_symbol(order.symbol)
    if order.side == "buy":
        need = order.amount * (order.price or ref_price)
        _adjust(bal, quote, free=-need, used=need)
        order.reserved, order.reserved_currency = need, quote
    else:
        _adjust(bal, base, free=-order.amount, used=order.amount)
        order.reserved, order.reserved_currency = order.amount, base


def _release(bal, order):
    if order.reserved:
        _adjust(bal, order.reserved_currency, free=order.reserved, used=-order.reserved)
        order.reserved = 0.0


def _quote_price(reference, symbol, side):
    t = market.ticker(reference, symbol)
    px = (t.get("ask") if side == "buy" else t.get("bid")) or t.get("last") or 0.0
    if px <= 0:
        raise ccxt.ExchangeNotAvailable(f"paper: no price for {symbol}")
    return px


def match_orders(user_id, reference=None):
    """Fill limit orders and fire trigger orders whose price was reached."""
    reference = reference or market.default_exchange()
    opens = PaperOrder.query.filter_by(user_id=user_id, status="open").all()
    if not opens:
        return 0
    acc = get_account(user_id, lock=True)
    bal = _balances(acc)
    filled = 0
    for o in opens:
        try:
            last = market.price(reference, o.symbol)
        except Exception:
            continue
        if not last:
            continue
        if o.trigger_price:
            hit = last >= o.trigger_price if o.trigger_above else last <= o.trigger_price
            if not hit:
                continue
            o.trigger_price = None  # trigger fired -> behaves like a normal order now
            if o.type == "market":
                _fill(acc, bal, o, last)
                filled += 1
                continue
        if o.type == "limit" and o.price:
            if (o.side == "buy" and last <= o.price) or (o.side == "sell" and last >= o.price):
                _fill(acc, bal, o, o.price)
                filled += 1
    acc.balances = bal
    db.session.commit()
    return filled


def match_all(reference=None):
    users = [r[0] for r in db.session.query(PaperOrder.user_id).filter_by(status="open").distinct().all()]
    total = 0
    for uid in users:
        try:
            total += match_orders(uid, reference)
        except Exception as e:  # keep other users going
            db.session.rollback()
            print(f"paper match failed for user {uid}: {e}")
    return total


# --------------------------------------------------------------------------- exchange

class PaperExchange:
    id = NAME
    name = NAME
    rateLimit = 0
    has = {
        "spot": True, "createOrder": True, "cancelOrder": True, "fetchBalance": True, "fetchOrder": True,
        "fetchOpenOrders": True, "fetchClosedOrders": True, "fetchCanceledOrders": True, "fetchOrders": True,
        "fetchMyTrades": True, "fetchTicker": True, "fetchTickers": True, "fetchOHLCV": True,
        "fetchOrderBook": True, "fetchTrades": True, "fetchMarkets": True, "fetchCurrencies": True,
        "fetchLedger": False, "fetchPositions": False, "fetchDepositAddress": False, "fetchDeposits": False,
        "fetchWithdrawals": False, "withdraw": False, "transfer": False, "fetchTransfers": False,
    }

    def __init__(self, user_id, reference=None):
        self.user_id = user_id
        self.reference = market.normalize_exchange(reference)
        self.markets = None

    # -- metadata
    def describe(self):
        return {"id": NAME, "name": "Paper Trading", "rateLimit": 0, "urls": {}, "has": dict(self.has)}

    def set_sandbox_mode(self, enabled):
        return None

    def check_required_credentials(self, error=True):
        return True

    def load_markets(self, reload=False, params=None):
        if self.markets is None or reload:
            out = {}
            for sym in market.symbols(self.reference):
                base, quote = sym.split("/")
                out[sym] = {"id": sym.replace("/", ""), "symbol": sym, "base": base, "quote": quote,
                            "spot": True, "active": True, "type": "spot",
                            "precision": {"amount": 1e-8, "price": 1e-8},
                            "limits": {"amount": {"min": 1e-8, "max": None}, "cost": {"min": 1.0, "max": None}}}
            self.markets = out
        return self.markets

    def fetch_markets(self, params=None):
        return list(self.load_markets().values())

    def market(self, symbol):
        sym = market.normalize_symbol(symbol)
        m = self.load_markets().get(sym)
        if m is None:
            base, quote = sym.split("/")
            m = {"id": sym.replace("/", ""), "symbol": sym, "base": base, "quote": quote, "spot": True,
                 "active": True, "precision": {"amount": 1e-8, "price": 1e-8}}
        return m

    def fetch_currencies(self, params=None):
        codes = sorted({c for s in self.load_markets() for c in s.split("/")})
        return {c: {"id": c, "code": c, "name": c, "active": True, "deposit": False, "withdraw": False,
                    "precision": 1e-8, "networks": {}} for c in codes}

    # -- market data
    def fetch_ticker(self, symbol, params=None):
        return dict(market.ticker(self.reference, symbol))

    def fetch_tickers(self, symbols=None, params=None):
        rows = market.tickers(self.reference, "USDT")
        out = {r["symbol"]: dict(r) for r in rows}
        if symbols:
            out = {k: v for k, v in out.items() if k in symbols}
        return out

    def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None, params=None):
        return market.ohlcv(self.reference, symbol, timeframe, limit or 200, since)

    def fetch_order_book(self, symbol, limit=None, params=None):
        return market.order_book(self.reference, symbol, limit or 20)

    def fetch_trades(self, symbol, since=None, limit=None, params=None):
        return market.trades(self.reference, symbol, limit or 30)

    # -- account
    def fetch_balance(self, params=None):
        match_orders(self.user_id, self.reference)
        bal = _balances(get_account(self.user_id))
        out = {"info": {"paper": True}, "free": {}, "used": {}, "total": {}}
        for cur, b in bal.items():
            total = b["free"] + b["used"]
            out["free"][cur], out["used"][cur], out["total"][cur] = b["free"], b["used"], total
            out[cur] = {"free": b["free"], "used": b["used"], "total": total}
        return out

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        params = params or {}
        sym = market.normalize_symbol(symbol)
        type, side = str(type).lower(), str(side).lower()
        if type not in ("market", "limit"):
            raise ccxt.InvalidOrder(f"paper: unsupported order type {type}")
        if side not in ("buy", "sell"):
            raise ccxt.InvalidOrder(f"paper: unsupported side {side}")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ccxt.InvalidOrder("paper: invalid amount")
        if not amount > 0:
            raise ccxt.InvalidOrder("paper: amount must be positive")
        price = float(price) if price not in (None, "", 0) else None
        if type == "limit" and not price:
            raise ccxt.InvalidOrder("paper: limit orders need a price")
        trigger = params.get("triggerPrice") or params.get("stopPrice")
        trigger = float(trigger) if trigger else None

        acc = get_account(self.user_id, lock=True)
        bal = _balances(acc)
        last = market.price(self.reference, sym)
        order = PaperOrder(user_id=self.user_id, symbol=sym, side=side, type=type, price=price,
                           amount=amount, filled=0.0, status="open")
        if trigger:
            order.trigger_price = trigger
            order.trigger_above = trigger >= last
        try:
            if type == "market" and not trigger:
                _fill(acc, bal, order, _quote_price(self.reference, sym, side))
            else:
                _reserve(bal, order, last)
                marketable = (not trigger and type == "limit" and
                              ((side == "buy" and last <= price) or (side == "sell" and last >= price)))
                if marketable:
                    _fill(acc, bal, order, min(price, last) if side == "buy" else max(price, last))
        except ccxt.InsufficientFunds:
            db.session.rollback()
            raise
        acc.balances = bal
        db.session.add(order)
        db.session.commit()
        return _to_ccxt(order)

    def create_market_order(self, symbol, side, amount, price=None, params=None):
        return self.create_order(symbol, "market", side, amount, None, params)

    def create_limit_order(self, symbol, side, amount, price, params=None):
        return self.create_order(symbol, "limit", side, amount, price, params)

    def _get(self, id):
        try:
            oid = int(str(id))
        except (TypeError, ValueError):
            raise ccxt.OrderNotFound(f"paper: order {id} not found")
        o = PaperOrder.query.filter_by(id=oid, user_id=self.user_id).first()
        if o is None:
            raise ccxt.OrderNotFound(f"paper: order {id} not found")
        return o

    def fetch_order(self, id, symbol=None, params=None):
        o = self._get(id)
        if o.status == "open":
            match_orders(self.user_id, self.reference)
            o = self._get(id)
        return _to_ccxt(o)

    def cancel_order(self, id, symbol=None, params=None):
        o = self._get(id)
        if o.status != "open":
            raise ccxt.InvalidOrder(f"paper: order {id} is {o.status}")
        acc = get_account(self.user_id, lock=True)
        bal = _balances(acc)
        _release(bal, o)
        o.status = "canceled"
        o.updated_at = datetime.utcnow()
        acc.balances = bal
        db.session.commit()
        return _to_ccxt(o)

    def cancel_all_orders(self, symbol=None, params=None):
        return [self.cancel_order(o["id"]) for o in self.fetch_open_orders(symbol)]

    def _list(self, status, symbol=None, limit=None, params=None):
        params = params or {}
        ord_type = str(params.get("ordType") or "").lower()
        q = PaperOrder.query.filter_by(user_id=self.user_id)
        if status:
            q = q.filter_by(status=status)
        if symbol:
            q = q.filter_by(symbol=market.normalize_symbol(symbol))
        rows = q.order_by(PaperOrder.id.desc()).limit(int(limit) if limit else 500).all()
        if params.get("stop") or ord_type:
            # Legacy history pages query the same venue several times with
            # different ordType filters and merge the results; only the
            # "trigger" pass returns trigger orders so nothing is duplicated.
            rows = [o for o in rows if bool(o.trigger_price) == (ord_type == "trigger")] if ord_type == "trigger" else []
        return [_to_ccxt(o) for o in rows]

    def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        match_orders(self.user_id, self.reference)
        return self._list("open", symbol, limit, params)

    def fetch_closed_orders(self, symbol=None, since=None, limit=None, params=None):
        return self._list("closed", symbol, limit, params)

    def fetch_canceled_orders(self, symbol=None, since=None, limit=None, params=None):
        params = dict(params or {})
        kind = str(params.get("ordType") or "").lower()
        if kind == "limit":
            params = {}  # return every canceled order exactly once
        elif kind:
            return []
        return self._list("canceled", symbol, limit, params)

    def fetch_orders(self, symbol=None, since=None, limit=None, params=None):
        return self._list(None, symbol, limit, params)

    def fetch_my_trades(self, symbol=None, since=None, limit=None, params=None):
        out = []
        for o in self._list("closed", symbol, limit):
            out.append({"id": o["id"], "order": o["id"], "timestamp": o["timestamp"], "datetime": o["datetime"],
                        "symbol": o["symbol"], "side": o["side"], "price": o["average"], "amount": o["filled"],
                        "cost": o["cost"], "fee": o["fee"], "type": o["type"], "takerOrMaker": "taker"})
        return out

    # -- unsupported wallet operations (explicitly empty instead of crashing)
    def fetch_deposits(self, *a, **kw):
        return []

    def fetch_withdrawals(self, *a, **kw):
        return []

    def fetch_ledger(self, *a, **kw):
        return []

    def fetch_transfers(self, *a, **kw):
        return []

    def fetch_positions(self, *a, **kw):
        return []

    def fetch_deposit_withdraw_fees(self, *a, **kw):
        return {}

    def fetch_deposit_address(self, code, params=None):
        raise ccxt.NotSupported("paper accounts cannot receive deposits; use Reset balance instead")

    def withdraw(self, *a, **kw):
        raise ccxt.NotSupported("paper accounts cannot withdraw")

    def transfer(self, *a, **kw):
        raise ccxt.NotSupported("paper accounts have a single wallet")
