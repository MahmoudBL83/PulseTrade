"""Zero-config schema upkeep for existing deployments.

``db.create_all()`` creates missing tables but never alters existing ones, so
columns added to the models after a database was created are added here with
``ALTER TABLE ... ADD COLUMN``. On Postgres a few legacy columns that were too
narrow (or Integer where exchanges return string order ids) are widened.
Every statement is idempotent and failures are logged, never fatal."""
import logging

from sqlalchemy import inspect, text

log = logging.getLogger("pulsetrade.migrate")

# Postgres-only type fixes (SQLite ignores declared lengths/types).
PG_ALTERS = (
    'ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(512)',
    'ALTER TABLE users ALTER COLUMN img TYPE VARCHAR(512)',
    'ALTER TABLE exchanges ALTER COLUMN api_key TYPE VARCHAR(512)',
    'ALTER TABLE exchanges ALTER COLUMN api_secret TYPE VARCHAR(512)',
    'ALTER TABLE exchanges ALTER COLUMN password TYPE VARCHAR(512)',
    'ALTER TABLE transaction ALTER COLUMN symbol TYPE VARCHAR(32)',
    'ALTER TABLE transaction ALTER COLUMN value TYPE DOUBLE PRECISION',
    'ALTER TABLE "safetyOrders" ALTER COLUMN "orderId" TYPE VARCHAR(64) USING "orderId"::varchar',
    'ALTER TABLE smarttrades ALTER COLUMN buy_order_id TYPE VARCHAR(64) USING buy_order_id::varchar',
    'ALTER TABLE smarttrades ALTER COLUMN trailing_order_id TYPE VARCHAR(64) USING trailing_order_id::varchar',
    'ALTER TABLE smarttrades ALTER COLUMN stop_loss_id TYPE VARCHAR(64) USING stop_loss_id::varchar',
    'ALTER TABLE smarttrades ALTER COLUMN last_take_profit_id TYPE VARCHAR(64) USING last_take_profit_id::varchar',
    'ALTER TABLE smarttrades ALTER COLUMN base_currency TYPE VARCHAR(20)',
    'ALTER TABLE smarttrades ALTER COLUMN quote_currency TYPE VARCHAR(20)',
    'ALTER TABLE smarttrades ALTER COLUMN order_type TYPE VARCHAR(20)',
    'ALTER TABLE smarttrades ALTER COLUMN stop_loss_type TYPE VARCHAR(20)',
    'ALTER TABLE smarttrades ALTER COLUMN "tpTriggerType" TYPE VARCHAR(20)',
)


def _default_sql(col, dialect):
    default = col.default
    if default is None or not getattr(default, "is_scalar", False):
        return ""
    value = default.arg
    if isinstance(value, bool):
        if dialect == "postgresql":
            return " DEFAULT TRUE" if value else " DEFAULT FALSE"
        return " DEFAULT 1" if value else " DEFAULT 0"
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        return " DEFAULT '" + value.replace("'", "''") + "'"
    return ""


def add_missing_columns(db):
    engine = db.engine
    dialect = engine.dialect.name
    quote = engine.dialect.identifier_preparer.quote
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    added = []
    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in present or col.primary_key:
                continue
            col_type = col.type.compile(dialect=engine.dialect)
            ddl = f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(col.name)} {col_type}{_default_sql(col, dialect)}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
            except Exception as e:
                log.warning("could not add column %s.%s: %s", table.name, col.name, e)
    if added:
        log.info("schema upgraded, added columns: %s", ", ".join(added))
    return added


def widen_postgres(db):
    if db.engine.dialect.name != "postgresql":
        return
    for ddl in PG_ALTERS:
        try:
            with db.engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception as e:  # already the right type / table missing
            log.debug("migrate skipped (%s): %s", ddl, e)


def init_db(db):
    try:
        db.create_all()
    except Exception as e:
        log.error("db.create_all failed: %s", e)
    add_missing_columns(db)
    widen_postgres(db)
