from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from db.models import Base
from db.migrations import upgrade_history
from api.schemas.curve import SnapshotOut


class TimeTests(unittest.TestCase):
    def test_api_preserves_instant_and_normalizes_to_utc(self):
        from datetime import date
        value = SnapshotOut(id=1, trade_date=date(2026, 8, 31), status="built",
                            fetched_at=datetime(2026, 8, 31, 6, tzinfo=timezone(timedelta(hours=3))))
        self.assertEqual(value.fetched_at.hour, 3)
        self.assertEqual(value.fetched_at.utcoffset(), timedelta(0))


class MigrationTests(unittest.TestCase):
    def test_new_sqlite_schema_upgrade_is_idempotent(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            upgrade_history(connection)
            upgrade_history(connection)

    def test_postgres_upgrade_alters_constraints_without_deleting_data(self):
        connection = MagicMock()
        connection.dialect = postgresql.dialect()
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_unique_constraints.return_value = [{
            "name": "curve_snapshot_trade_date_source_key", "column_names": ["trade_date", "source"],
        }]
        inspector.get_foreign_keys.return_value = [{
            "name": "fk_snapshot", "constrained_columns": ["snapshot_id"],
            "referred_table": "curve_snapshot", "referred_columns": ["id"],
            "options": {"ondelete": "CASCADE"},
        }]
        with patch("db.migrations.inspect", return_value=inspector):
            upgrade_history(connection)
        sql = "\n".join(str(call.args[0]) for call in connection.execute.call_args_list)
        self.assertIn("DROP CONSTRAINT curve_snapshot_trade_date_source_key", sql)
        self.assertIn("ON DELETE RESTRICT", sql)
        for forbidden in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "UPDATE "):
            self.assertNotIn(forbidden, sql)
