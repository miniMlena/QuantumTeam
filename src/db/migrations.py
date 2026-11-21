"""Идемпотентная миграция PostgreSQL без удаления таблиц или записей.

Запускается init_db внутри транзакции под advisory lock. Новая установка
создаёт текущую схему; существующая сохраняет все снимки и рассчитанные точки.
"""
from sqlalchemy import inspect, text


def upgrade_history(connection) -> None:
    inspector = inspect(connection)
    if not inspector.has_table("curve_snapshot"):
        return
    constraints = inspector.get_unique_constraints("curve_snapshot")
    legacy = [c for c in constraints if set(c["column_names"]) == {"trade_date", "source"}]
    if connection.dialect.name != "postgresql":
        if legacy:
            raise RuntimeError("Legacy schema migration requires PostgreSQL; do not delete the database")
        return

    quote = connection.dialect.identifier_preparer.quote
    for constraint in legacy:
        connection.execute(text(
            f'ALTER TABLE curve_snapshot DROP CONSTRAINT {quote(constraint["name"])}'
        ))

    # Убираем каскадное удаление у существующих связей, не затрагивая строки.
    for table in ("base_curve_point", "shifted_curve_point", "scenario_shift"):
        if not inspector.has_table(table):
            continue
        for fk in inspector.get_foreign_keys(table):
            if (fk.get("options", {}).get("ondelete") or "").upper() != "CASCADE":
                continue
            name = quote(fk["name"])
            columns = ", ".join(quote(c) for c in fk["constrained_columns"])
            target_columns = ", ".join(quote(c) for c in fk["referred_columns"])
            target = quote(fk["referred_table"])
            if fk.get("referred_schema"):
                target = quote(fk["referred_schema"]) + "." + target
            connection.execute(text(f"ALTER TABLE {quote(table)} DROP CONSTRAINT {name}"))
            connection.execute(text(
                f"ALTER TABLE {quote(table)} ADD CONSTRAINT {name} FOREIGN KEY ({columns}) "
                f"REFERENCES {target} ({target_columns}) ON DELETE RESTRICT"
            ))
