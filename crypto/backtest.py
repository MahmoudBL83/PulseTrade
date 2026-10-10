"""DCA strategy backtester (same model as the live DCA bots: base order,
safety orders with step/volume scaling, take profit from the average entry,
optional stop loss and RSI entry filter) over historical candles."""
from datetime import datetime, timezone

import numpy as np

from crypto import market
from crypto.talib_compat import talib

LIMITS = {"limit": (50, 1000), "max_safety_orders": (0, 25)}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def params_from(body):
    def f(key, default):
        v = body.get(key, default)
        return default if v in (None, "") else float(v)
    p = {
        "exchange": body.get("exchange") or market.default_exchange(),
        "symbol": market.normalize_symbol(body.get("symbol") or "BTC/USDT"),
        "timeframe": body.get("timeframe") if body.get("timeframe") in market.TIMEFRAMES else "1h",
        "limit": int(_clamp(f("limit", 500), *LIMITS["limit"])),
        "strategy": "short" if str(body.get("strategy", "long")).lower() == "short" else "long",
        "base_order": f("base_order", 100.0),
        "safety_order": f("safety_order", 100.0),
        "max_safety_orders": int(_clamp(f("max_safety_orders", 5), *LIMITS["max_safety_orders"])),
        "deviation": f("deviation", 1.5),
        "step_scale": f("step_scale", 1.0),
        "volume_scale": f("volume_scale", 1.0),
        "take_profit": f("take_profit", 1.5),
        "stop_loss": f("stop_loss", 0.0),
        "fee": f("fee", 0.1),
        "rsi_below": f("rsi_below", 0.0),
        "rsi_length": int(_clamp(f("rsi_length", 14), 2, 100)),
    }
    if p["base_order"] <= 0 or p["take_profit"] <= 0:
        raise ValueError("base_order and take_profit must be positive")
    return p


def _levels(p):
    """Cumulative deviation (%) and quote size of each safety order."""
    out, cum = [], 0.0
    for i in range(p["max_safety_orders"]):
        cum += p["deviation"] * (p["step_scale"] ** i)
        out.append((cum, p["safety_order"] * (p["volume_scale"] ** i)))
    return out


def run(p, candles=None):
    candles = candles or market.ohlcv(p["exchange"], p["symbol"], p["timeframe"], p["limit"])
    long = p["strategy"] == "long"
    fee = p["fee"] / 100
    levels = _levels(p)
    closes = [c[4] for c in candles]
    rsi = talib.RSI(np.asarray(closes, dtype=float), p["rsi_length"]) if p["rsi_below"] else None

    deals, equity = [], []
    realized = 0.0
    deal = None
    exposure = 0
    max_capital = p["base_order"] + sum(q for _, q in levels)

    def iso(ms):
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

    for i, (ts, o, h, l, c, v) in enumerate(candles):
        if deal is None:
            if rsi is not None and not (rsi[i] == rsi[i] and rsi[i] < p["rsi_below"]):
                equity.append({"t": ts, "equity": realized})
                continue
            qty = p["base_order"] / c
            deal = {"open_t": ts, "first": c, "qty": qty, "cost": p["base_order"], "filled": 0,
                    "fees": p["base_order"] * fee}
        else:
            # safety orders fill when the candle trades through their level
            while deal["filled"] < len(levels):
                dev, quote_size = levels[deal["filled"]]
                level = deal["first"] * (1 - dev / 100) if long else deal["first"] * (1 + dev / 100)
                if (long and l <= level) or (not long and h >= level):
                    q = quote_size / level
                    deal["qty"] += q
                    deal["cost"] += quote_size
                    deal["fees"] += quote_size * fee
                    deal["filled"] += 1
                else:
                    break
            avg = deal["cost"] / deal["qty"] if deal["qty"] else c
            tp = avg * (1 + p["take_profit"] / 100) if long else avg * (1 - p["take_profit"] / 100)
            sl = None
            if p["stop_loss"] > 0:
                sl = deal["first"] * (1 - p["stop_loss"] / 100) if long else deal["first"] * (1 + p["stop_loss"] / 100)
            exit_price, reason = None, None
            # conservative: when both are inside one candle assume the stop hit first
            if sl is not None and ((long and l <= sl) or (not long and h >= sl)):
                exit_price, reason = sl, "stop_loss"
            elif (long and h >= tp) or (not long and l <= tp):
                exit_price, reason = tp, "take_profit"
            if exit_price is not None:
                proceeds = deal["qty"] * exit_price
                fees = deal["fees"] + proceeds * fee
                pnl = (proceeds - deal["cost"] if long else deal["cost"] - proceeds) - fees
                realized += pnl
                deals.append({
                    "open_time": iso(deal["open_t"]), "close_time": iso(ts), "entry": deal["first"],
                    "average": avg, "exit": exit_price, "safety_orders": deal["filled"], "invested": deal["cost"],
                    "pnl": pnl, "pnl_pct": pnl / deal["cost"] * 100 if deal["cost"] else 0, "reason": reason,
                    "fees": fees, "duration_h": (ts - deal["open_t"]) / 3_600_000,
                })
                deal = None
        unreal = 0.0
        if deal is not None:
            exposure += 1
            mark = deal["qty"] * c
            unreal = (mark - deal["cost"]) if long else (deal["cost"] - mark)
        equity.append({"t": ts, "equity": realized + unreal})

    peak, mdd = 0.0, 0.0
    for e in equity:
        val = max_capital + e["equity"]
        peak = max(peak, val)
        if peak:
            mdd = max(mdd, (peak - val) / peak)
    wins = [d for d in deals if d["pnl"] > 0]
    losses = [d for d in deals if d["pnl"] <= 0]
    gross_win = sum(d["pnl"] for d in wins)
    gross_loss = -sum(d["pnl"] for d in losses)
    first_close, last_close = (closes[0], closes[-1]) if closes else (0, 0)
    hold = ((last_close - first_close) / first_close * 100) * (1 if long else -1) if first_close else 0
    open_deal = None
    if deal is not None:
        avg = deal["cost"] / deal["qty"] if deal["qty"] else 0
        open_deal = {"open_time": iso(deal["open_t"]), "average": avg, "safety_orders": deal["filled"],
                     "invested": deal["cost"], "unrealized": equity[-1]["equity"] - realized if equity else 0}
    return {
        "params": p,
        "stats": {
            "deals": len(deals), "wins": len(wins), "losses": len(deals) - len(wins),
            "win_rate": len(wins) / len(deals) * 100 if deals else 0,
            "realized_pnl": realized, "return_pct": realized / max_capital * 100 if max_capital else 0,
            "max_capital": max_capital, "max_drawdown_pct": mdd * 100,
            "avg_duration_h": sum(d["duration_h"] for d in deals) / len(deals) if deals else 0,
            "avg_safety_orders": sum(d["safety_orders"] for d in deals) / len(deals) if deals else 0,
            "buy_and_hold_pct": hold, "candles": len(candles),
            # QuantStats-style trade statistics
            # None = no losing deals (JSON has no Infinity); the UI renders it as "∞"
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win > 0 else 0),
            "expectancy": realized / len(deals) if deals else 0,
            "avg_win": gross_win / len(wins) if wins else 0,
            "avg_loss": -gross_loss / len(losses) if losses else 0,
            "calmar": (realized / max_capital * 100) / (mdd * 100) if mdd > 0 and max_capital else 0,
            "exposure_pct": exposure / len(candles) * 100 if candles else 0,
            "from": iso(candles[0][0]) if candles else None, "to": iso(candles[-1][0]) if candles else None,
        },
        "deals": deals[-200:],
        "open_deal": open_deal,
        "equity": equity[:: max(1, len(equity) // 400)],
        "source": "synthetic" if market.mode() == "synthetic" else "market",
    }


# ----------------------------------------------------------------------------- optimizer

OPTIMIZABLE = ("take_profit", "deviation", "max_safety_orders", "step_scale", "volume_scale", "stop_loss",
               "safety_order", "rsi_below")
METRICS = ("return_pct", "profit_factor", "win_rate", "calmar", "realized_pnl")
MAX_COMBINATIONS = 150


def _values(spec, name):
    """[1, 1.5, 2] or {"min": 1, "max": 3, "step": 0.5} -> list of numbers."""
    if isinstance(spec, (list, tuple)):
        vals = [float(v) for v in spec]
    elif isinstance(spec, dict):
        lo, hi, step = float(spec["min"]), float(spec["max"]), float(spec.get("step") or 1)
        if step <= 0 or hi < lo:
            raise ValueError(f"bad range for {name}")
        n = int(round((hi - lo) / step)) + 1
        vals = [round(lo + i * step, 10) for i in range(min(n, 50))]
    else:
        raise ValueError(f"{name} must be a list or a {{min,max,step}} range")
    if not vals:
        raise ValueError(f"{name} has no values")
    return vals


def optimize(base, grid, metric="return_pct", top=10):
    """Grid search over ``grid`` (param -> values) on one candle set.
    Inspired by freqtrade hyperopt / jesse optimize, kept deterministic and
    bounded (<= MAX_COMBINATIONS runs) so it fits in a web request."""
    import itertools
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {', '.join(METRICS)}")
    names = [k for k in OPTIMIZABLE if k in grid]  # stable axis order (JSON key order is not)
    if not names:
        raise ValueError(f"choose at least one of {', '.join(OPTIMIZABLE)}")
    axes = [_values(grid[k], k) for k in names]
    total = 1
    for a in axes:
        total *= len(a)
    if total > MAX_COMBINATIONS:
        raise ValueError(f"{total} combinations requested; the limit is {MAX_COMBINATIONS}")
    candles = market.ohlcv(base["exchange"], base["symbol"], base["timeframe"], base["limit"])
    results = []
    for combo in itertools.product(*axes):
        p = dict(base)
        for k, v in zip(names, combo):
            p[k] = int(v) if k == "max_safety_orders" else v
        if p["take_profit"] <= 0:
            continue
        s = run(p, candles)["stats"]
        score = s[metric]
        if score is None:  # profit factor without losing deals
            score = 1e9
        results.append({"params": {k: p[k] for k in names}, "score": score,
                        "stats": {k: s[k] for k in ("deals", "win_rate", "return_pct", "max_drawdown_pct",
                                                    "profit_factor", "calmar", "realized_pnl")}})
    results.sort(key=lambda r: r["score"], reverse=True)
    heatmap = None
    if len(names) == 2:
        heatmap = {"x": names[0], "y": names[1], "xs": axes[0], "ys": axes[1],
                   "cells": [[r["params"][names[0]], r["params"][names[1]], r["score"]] for r in results]}
    return {"metric": metric, "runs": len(results), "best": results[0] if results else None,
            "top": results[:top], "heatmap": heatmap, "candles": len(candles)}
