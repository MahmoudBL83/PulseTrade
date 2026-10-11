"""Engine batches must visit every active record when earlier records stop."""


def test_stopping_first_page_does_not_skip_remaining_bots(app, monkeypatch):
    from crypto import db
    from crypto import bots, engine
    from crypto.models import Bot

    with app.app_context():
        existing = {id for (id,) in db.session.query(Bot.id).filter(
            Bot.isActive == True, Bot.is_hidden == False
        ).all()}
        batch = [
            Bot(name=f"batch-{i}", isActive=True, is_hidden=False)
            for i in range(101)
        ]
        db.session.add_all(batch)
        db.session.commit()
        batch_ids = {bot.id for bot in batch}

        visited = []

        def stop_bot(bot):
            visited.append(bot.id)
            bot.isActive = False
            db.session.flush()
            return "stopped"

        monkeypatch.setattr(bots, "run_bot_once", stop_bot)
        result = engine.tick(jobs=("bots",))

        assert result["bots"]["stopped"] == len(existing) + 101
        assert batch_ids <= set(visited)
        assert not set(db.session.query(Bot.id).filter(
            Bot.id.in_(batch_ids), Bot.isActive == True
        ).all())
        for bot_id in existing:
            db.session.get(Bot, bot_id).isActive = True
        db.session.commit()


def test_completing_first_page_does_not_skip_remaining_smart_trades(app, monkeypatch):
    from crypto import db
    from crypto import smartTrade, engine
    from crypto.models import SmartTrade

    with app.app_context():
        existing = {id for (id,) in db.session.query(SmartTrade.id).filter(
            SmartTrade.isActive == True, SmartTrade.is_hidden == False
        ).all()}
        db.session.bulk_insert_mappings(SmartTrade, [
            {"name": f"batch-{i}", "isActive": True, "is_hidden": False}
            for i in range(101)
        ])
        db.session.commit()
        batch_ids = {id for (id,) in db.session.query(SmartTrade.id).filter(
            SmartTrade.name.like("batch-%")
        ).all()} - existing

        visited = []

        def complete_trade(st):
            visited.append(st.id)
            st.isActive = False
            db.session.flush()
            return "completed"

        monkeypatch.setattr(smartTrade, "run_smart_trade_once", complete_trade)
        result = engine.tick(jobs=("smart",))

        assert result["smart"]["completed"] == len(existing) + 101
        assert batch_ids <= set(visited)
        assert not set(db.session.query(SmartTrade.id).filter(
            SmartTrade.id.in_(batch_ids), SmartTrade.isActive == True
        ).all())
        for st_id in existing:
            db.session.get(SmartTrade, st_id).isActive = True
        db.session.commit()
