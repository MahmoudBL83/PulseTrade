"""Engine batches must visit every active record when earlier records stop."""


def test_stopping_first_page_does_not_skip_remaining_bots(app, monkeypatch):
    from crypto import db
    from crypto import bots, engine
    from crypto.models import Bot

    with app.app_context():
        db.session.add_all([
            Bot(name=f"batch-{i}", isActive=True, is_hidden=False)
            for i in range(101)
        ])
        db.session.commit()

        visited = []

        def stop_bot(bot):
            visited.append(bot.id)
            bot.isActive = False
            db.session.flush()
            return "stopped"

        monkeypatch.setattr(bots, "run_bot_once", stop_bot)
        result = engine.tick(jobs=("bots",))

        assert result["bots"]["stopped"] == 101
        assert len(set(visited)) == 101
        assert Bot.query.filter_by(isActive=True).count() == 0


def test_completing_first_page_does_not_skip_remaining_smart_trades(app, monkeypatch):
    from crypto import db
    from crypto import smartTrade, engine
    from crypto.models import SmartTrade

    with app.app_context():
        db.session.bulk_insert_mappings(SmartTrade, [
            {"name": f"batch-{i}", "isActive": True, "is_hidden": False}
            for i in range(101)
        ])
        db.session.commit()

        visited = []

        def complete_trade(st):
            visited.append(st.id)
            st.isActive = False
            db.session.flush()
            return "completed"

        monkeypatch.setattr(smartTrade, "run_smart_trade_once", complete_trade)
        result = engine.tick(jobs=("smart",))

        assert result["smart"]["completed"] == 101
        assert len(set(visited)) == 101
        assert SmartTrade.query.filter_by(isActive=True).count() == 0
