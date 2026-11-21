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

    from db.models import BaseCurvePoint, CurveSnapshot, Scenario, ShiftedCurvePoint, TermCurvePoint
    from db.repositories import curve_repo
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
        self.addCleanup(engine.dispose)
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

    def test_rebuild_preserves_previous_version(self):
        build_curves(self.session, self.snapshot)
        old_rate = curve_repo.get_base_points(self.session, self.snapshot.id)[0].rate
        new_snapshot = curve_repo.copy_snapshot(self.session, self.snapshot)
        build_curves(self.session, new_snapshot)
        self.assertNotEqual(new_snapshot.id, self.snapshot.id)
        self.assertEqual(self.snapshot.status, "built")
        self.assertEqual(curve_repo.get_base_points(self.session, self.snapshot.id)[0].rate, old_rate)
        self.assertEqual(self.count(BaseCurvePoint), 38)
        self.assertEqual(self.count(ShiftedCurvePoint), 2 * 6 * 19)
        self.assertEqual(self.count(TermCurvePoint), 2 * 7 * 19)
        self.assertEqual(self.count(Scenario), 6)

    def test_same_date_creates_new_snapshot(self):
        build_curves(self.session, self.snapshot)
        with patch("services.curve_pipeline.fetch_curve_from_moex", return_value=moex_params()):
            again = load_curve(self.session)
        self.assertNotEqual(again.id, self.snapshot.id)
        self.assertEqual(again.status, "pending")
        self.assertEqual(self.count(CurveSnapshot), 2)
        build_curves(self.session, again)
        self.assertEqual(curve_repo.get_latest_snapshot(self.session).id, again.id)

    def test_new_import_does_not_change_old_parameters(self):
        build_curves(self.session, self.snapshot)
        old_b1 = self.snapshot.b1
        changed = moex_params()
        changed["b1"] += 100
        with patch("services.curve_pipeline.fetch_curve_from_moex", return_value=changed):
            new_snapshot = load_curve(self.session)
        self.session.refresh(self.snapshot)
        self.assertEqual(self.snapshot.b1, old_b1)
        self.assertEqual(new_snapshot.b1, old_b1 + 100)

    def test_processed_snapshot_cannot_be_overwritten(self):
        build_curves(self.session, self.snapshot)
        with self.assertRaisesRegex(ValueError, "new version"):
            build_curves(self.session, self.snapshot)
        self.assertEqual(self.snapshot.status, "built")
        self.assertEqual(self.count(BaseCurvePoint), 19)

    def test_failure_after_saving_base_rolls_back_all_new_points(self):
        build_curves(self.session, self.snapshot)
        new_snapshot = curve_repo.copy_snapshot(self.session, self.snapshot)
        with patch("services.curve_pipeline.apply_shift", side_effect=ValueError("late failure")):
            with self.assertRaises(ValueError):
                build_curves(self.session, new_snapshot)
        self.assertEqual(new_snapshot.status, "failed")
        self.assertEqual(curve_repo.get_base_points(self.session, new_snapshot.id), [])
        self.assertEqual(curve_repo.get_term_points(self.session, new_snapshot.id, "base"), [])
        self.assertEqual(self.count(BaseCurvePoint), 19)
        self.assertEqual(self.snapshot.status, "built")

    def test_term_curves_reach_30_but_discount_buckets_stay_25(self):
        from domain.curve.builder import annual_rate_pct
        from domain.curve.scenarios import basel_shift_bp
        build_curves(self.session, self.snapshot)
        base = curve_repo.get_term_points(self.session, self.snapshot.id, "base")
        steepener = curve_repo.get_term_points(self.session, self.snapshot.id, "steepener")
        self.assertEqual(float(base[-1].tenor_years), 30)
        self.assertAlmostEqual(float(base[-1].rate), annual_rate_pct(30, moex_params()), places=5)
        self.assertAlmostEqual(float(steepener[-1].shift_bp), basel_shift_bp("steepener", 30), places=4)
        self.assertEqual(float(curve_repo.get_base_points(self.session, self.snapshot.id)[-1].tenor_years), 25)

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
