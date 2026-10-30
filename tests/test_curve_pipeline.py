"""
Конвейер на временной базе SQLite, сеть и PostgreSQL не нужны.
Нужны зависимости проекта; без них тесты пропускаются.
"""
import importlib.util
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HAS_DEPS = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "httpx"))

if HAS_DEPS:
    from sqlalchemy import BigInteger, create_engine, func, select
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import Session

    from db.models import BaseCurvePoint, CurveSnapshot, Scenario, ShiftedCurvePoint
    from db.models.base import Base
    from services.curve_pipeline import build_curves, load_curve

    @compiles(BigInteger, "sqlite")
    def _sqlite_bigint(element, compiler, **kw):
        return "INTEGER"

FIXTURE = Path(__file__).parent / "fixtures" / "moex_zcyc_2026_08_31.json"


def moex_params():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = dict(zip(payload["params"]["columns"], payload["params"]["data"][0]))
    params = {
        key.lower(): value for key, value in row.items()
        if key not in ("tradedate", "tradetime")
    }
    return {"trade_date": date(2026, 8, 31), **params}


@unittest.skipUnless(HAS_DEPS, "нужны sqlalchemy и httpx")
class CurvePipelineTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.addCleanup(self.session.close)
        with patch("services.curve_pipeline.fetch_curve_from_moex", return_value=moex_params()):
            self.snapshot = load_curve(self.session)

    def count(self, model):
        return self.session.scalar(select(func.count()).select_from(model))

    def test_builds_all_scenarios_on_empty_database(self):
        saved = build_curves(self.session, self.snapshot)
        self.assertEqual(len(saved), 6)
        self.assertEqual(set(saved.values()), {19})
        self.assertEqual(self.snapshot.trade_date, date(2026, 8, 31))
        self.assertEqual(self.snapshot.status, "built")
        self.assertEqual(self.count(BaseCurvePoint), 19)
        self.assertEqual(self.count(ShiftedCurvePoint), 6 * 19)

    def test_rebuild_replaces_points(self):
        build_curves(self.session, self.snapshot)
        build_curves(self.session, self.snapshot)
        self.assertEqual(self.count(BaseCurvePoint), 19)
        self.assertEqual(self.count(ShiftedCurvePoint), 6 * 19)
        self.assertEqual(self.count(Scenario), 6)

    def test_same_date_reuses_snapshot(self):
        build_curves(self.session, self.snapshot)
        with patch("services.curve_pipeline.fetch_curve_from_moex", return_value=moex_params()):
            again = load_curve(self.session)
        self.assertEqual(again.id, self.snapshot.id)
        self.assertEqual(again.status, "pending")
        self.assertEqual(self.count(CurveSnapshot), 1)

    def test_failed_status_on_error(self):
        with patch("services.curve_pipeline.build_base_curve", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                build_curves(self.session, self.snapshot)
        self.assertEqual(self.snapshot.status, "failed")
        self.assertEqual(self.snapshot.error_message, "boom")

    def test_saved_rate_is_annual_percent(self):
        build_curves(self.session, self.snapshot)
        point = self.session.scalar(
            select(BaseCurvePoint).where(BaseCurvePoint.bucket_code == "3y")
        )
        self.assertAlmostEqual(float(point.rate), 15.04, delta=0.005)


if __name__ == "__main__":
    unittest.main()
