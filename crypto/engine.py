"""Engine orchestration: one bounded pass over everything that needs periodic
evaluation (paper order matching, price alerts, DCA bots, smart trades).

Runs from the in-process scheduler (ENGINE=scheduler), from /api/cron/* on
serverless deploys (ENGINE=cron), or not at all when the legacy Celery loops
are used (ENGINE=celery)."""
import logging
import time

from crypto import app, db

log = logging.getLogger("pulsetrade.engine")

ALL_JOBS = ("paper", "alerts", "bots", "smart")


def _pages(runner, budget, start, per_page=100):
    stats, page = {}, 1
    while True:
        part = runner(page, per_page)
        for k, v in part.items():
            stats[k] = stats.get(k, 0) + v
        if sum(part.values()) < per_page:
            break
        if budget and time.monotonic() - start > budget:
            stats["truncated"] = True
            break
        page += 1
    return stats


def tick(jobs=ALL_JOBS, budget=None):
    from crypto import paper, alerts, bots, smartTrade
    start = time.monotonic()
    stats = {}
    for job in jobs:
        if budget and time.monotonic() - start > budget:
            stats[job] = "skipped (time budget)"
            continue
        try:
            if job == "paper":
                stats[job] = {"filled": paper.match_all()}
            elif job == "alerts":
                stats[job] = {"fired": alerts.check_alerts()}
            elif job == "bots":
                stats[job] = _pages(bots.run_bots_page, budget, start)
            elif job == "smart":
                stats[job] = _pages(smartTrade.run_smart_trades_page, budget, start)
        except Exception as e:
            db.session.rollback()
            log.exception("engine job %s failed", job)
            stats[job] = f"error: {e}"
    stats["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    return stats


def tick_in_app():
    """Scheduler entry point (runs outside any request)."""
    with app.app_context():
        try:
            return tick()
        finally:
            db.session.remove()
