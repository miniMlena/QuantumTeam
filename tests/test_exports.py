import csv
import importlib.util
import io
import unittest
from datetime import date
from unittest.mock import patch

from test_curve_pipeline import moex_params

HAS_DEPS = all(importlib.util.find_spec(m) for m in ("sqlalchemy", "httpx"))

if HAS_DEPS:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from db.models import CurveSnapshot
    from db.models.base import Base
    from services.curve_export import (
        _add_months, export_bucket_curves, export_calculator_demo, export_moex_curves,
    )
    from services.curve_pipeline import build_curves, load_curve

SCENARIO_CODES = {"parallel_up", "parallel_down", "short_up", "short_down", "steepener", "flattener"}


def parse(text):
    return list(csv.DictReader(io.StringIO(text)))


@unittest.skipUnless(HAS_DEPS, "нужны sqlalchemy и httpx")
class AddMonthsTests(unittest.TestCase):
    def test_end_of_month_is_clamped(self):
        self.assertEqual(_add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(_add_months(date(2028, 1, 31), 1), date(2028, 2, 29))   # високосный год
        self.assertEqual(_add_months(date(2026, 8, 31), 1), date(2026, 9, 30))
        self.assertEqual(_add_months(date(2026, 3, 31), 11), date(2027, 2, 28))

    def test_year_rollover(self):
        self.assertEqual(_add_months(date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(_add_months(date(2026, 11, 30), 3), date(2027, 2, 28))

    def test_whole_years(self):
        self.assertEqual(_add_months(date(2026, 8, 31), 12), date(2027, 8, 31))
        self.assertEqual(_add_months(date(2026, 8, 31), 360), date(2056, 8, 31))

    def test_zero_months_is_same_day(self):
        self.assertEqual(_add_months(date(2026, 5, 17), 0), date(2026, 5, 17))


@unittest.skipUnless(HAS_DEPS, "нужны sqlalchemy и httpx")
class ExportTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session = Session(engine)
        self.addCleanup(self.session.close)
        with patch("services.curve_pipeline.fetch_curve_from_moex", return_value=moex_params()):
            self.snapshot = load_curve(self.session)
        build_curves(self.session, self.snapshot)

    # ------------------------------------------------------------ bucket curves csv
    def test_bucket_csv_header_and_size(self):
        text = export_bucket_curves(self.session, self.snapshot.id)
        self.assertEqual(text.splitlines()[0], "trade_date,scenario,bucket_code,tenor_years,rate")
        self.assertEqual(len(parse(text)), 19 * 7)          # база + 6 сценариев

    def test_moex_csv_contains_base_and_all_scenarios(self):
        rows = parse(export_moex_curves(self.session, self.snapshot.id))
        self.assertEqual({row["scenario"] for row in rows}, SCENARIO_CODES | {"base"})
        for code in SCENARIO_CODES | {"base"}:
            self.assertEqual(sum(row["scenario"] == code for row in rows), 19, code)

    def test_moex_csv_trade_date_is_snapshot_date(self):
        rows = parse(export_moex_curves(self.session, self.snapshot.id))
        self.assertEqual({row["trade_date"] for row in rows}, {"2026-08-31"})

    def test_bucket_csv_rates_are_fractions_not_percents(self):
        rows = parse(export_bucket_curves(self.session, self.snapshot.id))
        base_3y = next(r for r in rows if r["scenario"] == "base" and r["bucket_code"] == "3y")
        self.assertAlmostEqual(float(base_3y["rate"]), 0.1504, delta=0.00005)   # 15.04% -> 0.1504

    def test_bucket_csv_parallel_up_is_base_plus_four_percent(self):
        rows = parse(export_bucket_curves(self.session, self.snapshot.id))
        base = {r["bucket_code"]: float(r["rate"]) for r in rows if r["scenario"] == "base"}
        up = {r["bucket_code"]: float(r["rate"]) for r in rows if r["scenario"] == "parallel_up"}
        for code, rate in base.items():
            self.assertAlmostEqual(up[code] - rate, 0.04, places=6, msg=code)   # +400 б.п. = +0.04

    def test_moex_csv_scenarios_are_sorted(self):
        rows = parse(export_moex_curves(self.session, self.snapshot.id))
        order = []
        for row in rows:
            if row["scenario"] not in order:
                order.append(row["scenario"])
        self.assertEqual(order, ["base"] + sorted(SCENARIO_CODES))

    def test_moex_csv_is_repeatable(self):
        self.assertEqual(
            export_moex_curves(self.session, self.snapshot.id),
            export_moex_curves(self.session, self.snapshot.id),
        )

    def test_moex_csv_is_utf8_with_unix_line_endings(self):
        text = export_moex_curves(self.session, self.snapshot.id)
        text.encode("utf-8")                                 # не должно падать
        self.assertNotIn("\r", text)                         # перевод строки только \n

    # ------------------------------------------------------------ calculator-demo.csv
    def test_demo_csv_header_and_size(self):
        text = export_calculator_demo(self.session, self.snapshot.id, months=12)
        self.assertEqual(text.splitlines()[0], "indicator,date,rate,scenario")
        self.assertEqual(len(parse(text)), 12 * 7)

    def test_demo_csv_default_is_12_months(self):
        self.assertEqual(len(parse(export_calculator_demo(self.session, self.snapshot.id))), 12 * 7)

    def test_demo_csv_base_is_flat_ten_percent(self):
        rows = [r for r in parse(export_calculator_demo(self.session, self.snapshot.id, 6))
                if r["scenario"] == "base"]
        self.assertEqual([float(r["rate"]) for r in rows], [0.10] * 6)
        self.assertEqual({r["indicator"] for r in rows}, {"CBKEY1M"})

    def test_demo_csv_dates_start_one_month_after_snapshot(self):
        rows = [r for r in parse(export_calculator_demo(self.session, self.snapshot.id, 3))
                if r["scenario"] == "base"]
        self.assertEqual([r["date"] for r in rows], ["2026-09-30", "2026-10-31", "2026-11-30"])

    def test_demo_csv_parallel_up_adds_four_percent(self):
        rows = [r for r in parse(export_calculator_demo(self.session, self.snapshot.id, 24))
                if r["scenario"] == "parallel_up"]
        for row in rows:
            self.assertAlmostEqual(float(row["rate"]), 0.14, places=5, msg=row["date"])

    def test_demo_csv_parallel_down_subtracts_four_percent(self):
        rows = [r for r in parse(export_calculator_demo(self.session, self.snapshot.id, 24))
                if r["scenario"] == "parallel_down"]
        for row in rows:
            self.assertAlmostEqual(float(row["rate"]), 0.06, places=5, msg=row["date"])

    def test_demo_csv_covers_every_scenario_for_every_month(self):
        rows = parse(export_calculator_demo(self.session, self.snapshot.id, 5))
        for code in SCENARIO_CODES | {"base"}:
            self.assertEqual(sum(r["scenario"] == code for r in rows), 5, code)

    def test_demo_csv_month_limits(self):
        for months in (0, -1, 361):
            with self.subTest(months=months):
                with self.assertRaises(ValueError):
                    export_calculator_demo(self.session, self.snapshot.id, months)

    def test_demo_csv_accepts_limit_values(self):
        self.assertEqual(len(parse(export_calculator_demo(self.session, self.snapshot.id, 1))), 7)
        self.assertEqual(len(parse(export_calculator_demo(self.session, self.snapshot.id, 360))), 360 * 7)

    # ------------------------------------------------------------ ошибки
    def test_missing_snapshot_is_reported_as_not_found(self):
        for export in (export_moex_curves, export_calculator_demo):
            with self.subTest(export=export.__name__):
                with self.assertRaisesRegex(ValueError, "not found"):
                    export(self.session, 999)

    def test_unbuilt_snapshot_is_refused(self):
        snapshot = self.session.get(CurveSnapshot, self.snapshot.id)
        for status in ("pending", "failed"):
            snapshot.status = status
            self.session.commit()
            for export in (export_moex_curves, export_calculator_demo):
                with self.subTest(status=status, export=export.__name__):
                    with self.assertRaisesRegex(ValueError, "not built"):
                        export(self.session, self.snapshot.id)


if __name__ == "__main__":
    unittest.main()
