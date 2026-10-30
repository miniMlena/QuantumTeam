"""
Сверка с эталонным расчётом заказчика (Excel, лист «3108», 31.08.2026).
Сеть не нужна: параметры MOEX сохранены в tests/fixtures.
Запуск из корня проекта:
  PYTHONPATH=src python3 -m unittest discover -s tests -v
"""
import json
import math
from decimal import Decimal
from pathlib import Path
import unittest

from domain.constants import BUCKETS, RATE_POINT
from domain.curve.builder import annual_rate_pct, build_base_curve
from domain.curve.scenarios import BASEL_SHIFTS, basel_shift_bp, default_scenarios
from domain.curve.shifts import apply_shift

FIXTURE = Path(__file__).parent / "fixtures" / "moex_zcyc_2026_08_31.json"

# Строка 4 Excel: базовая ставка, %
EXCEL_BASE = dict(zip(
    [b.code for b in BUCKETS],
    [13.27, 13.27, 13.27, 13.30, 13.44, 13.63, 14.04, 14.45, 15.04, 15.35,
     15.66, 15.92, 15.92, 15.94, 15.96, 16.04, 16.13, 16.20, 16.34],
))

# Строка 5 Excel: «Непараллельный сдвиг (короткие вниз)», это steepener, %
EXCEL_STEEPENER = dict(zip(
    [b.code for b in BUCKETS],
    [10.02416354259008, 10.08170654577234, 10.26287028981304, 10.5824633497888,
     11.05069530252083, 11.54904068655009, 12.38688700776748, 13.30839126775404,
     14.55519450031201, 15.56967098291287, 16.42831781921782, 17.11560440496176,
     17.44837553253505, 17.72753794727268, 17.94937383881302, 18.18656378919655,
     18.56857524494072, 18.82510055365752, 19.02851379788945],
))

# Бакеты, чей конец совпадает со сроком из таблицы MOEX. Остальные 8 точек
# в Excel получены не из кривой MOEX, их источник уточняется у эксперта.
MOEX_TABLE_BUCKETS = ("3m", "6m", "9m", "1y", "2y", "3y", "5y", "7y", "10y", "15y", "20y")


def load_moex():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = dict(zip(payload["params"]["columns"], payload["params"]["data"][0]))
    params = {
        key.lower(): value for key, value in row.items()
        if key not in ("tradedate", "tradetime")
    }
    return params, payload["yearyields"]["data"]


def base_points_from_excel():
    return [
        {"bucket_code": b.code, "tenor_years": b.tenor_years, "rate": EXCEL_BASE[b.code]}
        for b in BUCKETS
    ]


class MoexFormulaTests(unittest.TestCase):
    def test_matches_published_yields(self):
        params, yields = load_moex()
        for row in yields:
            with self.subTest(years=row[2]):
                self.assertAlmostEqual(annual_rate_pct(row[2], params), row[3], delta=0.00006)

    def test_accepts_decimal_from_database(self):
        params, _ = load_moex()
        decimals = {k: Decimal(str(v)) for k, v in params.items()}
        self.assertAlmostEqual(
            annual_rate_pct(3, decimals), annual_rate_pct(3, params), places=9
        )


class BaseCurveTests(unittest.TestCase):
    @unittest.skipUnless(RATE_POINT == "end", "Excel берёт ставку на конце бакета")
    def test_matches_excel_on_moex_table_tenors(self):
        params, _ = load_moex()
        rates = {p["bucket_code"]: p["rate"] for p in build_base_curve(params)}
        for code in MOEX_TABLE_BUCKETS:
            with self.subTest(bucket=code):
                self.assertAlmostEqual(rates[code], EXCEL_BASE[code], delta=0.00501)

    def test_discount_tenor_is_bucket_middle(self):
        params, _ = load_moex()
        self.assertEqual(
            [p["tenor_years"] for p in build_base_curve(params)],
            [b.tenor_years for b in BUCKETS],
        )


class SteepenerTests(unittest.TestCase):
    def test_matches_excel_row_5(self):
        shift_map = {
            b.tenor_years: basel_shift_bp("steepener", b.tenor_years) for b in BUCKETS
        }
        for point in apply_shift(base_points_from_excel(), shift_map):
            with self.subTest(bucket=point["bucket_code"]):
                self.assertAlmostEqual(
                    point["shifted_rate"], EXCEL_STEEPENER[point["bucket_code"]], delta=1e-6
                )


class ScenarioShapeTests(unittest.TestCase):
    """Проверки формы. Это не эталон: для этих сценариев расчётов заказчика нет."""

    def test_six_scenarios_on_every_bucket(self):
        scenarios = default_scenarios()
        self.assertEqual(len(scenarios), 6)
        for scenario in scenarios:
            self.assertEqual(
                [s["tenor_years"] for s in scenario["shifts"]],
                [b.tenor_years for b in BUCKETS],
            )

    def test_up_and_down_are_mirrored(self):
        for name in ("parallel", "short"):
            for bucket in BUCKETS:
                self.assertEqual(
                    basel_shift_bp(f"{name}_up", bucket.tenor_years),
                    -basel_shift_bp(f"{name}_down", bucket.tenor_years),
                )

    def test_limits(self):
        far = 1000.0
        self.assertEqual(basel_shift_bp("short_up", 0), 500)
        self.assertAlmostEqual(basel_shift_bp("short_up", far), 0)
        self.assertEqual(basel_shift_bp("steepener", 0), -325)
        self.assertAlmostEqual(basel_shift_bp("steepener", far), 270)
        self.assertEqual(basel_shift_bp("flattener", 0), 400)
        self.assertAlmostEqual(basel_shift_bp("flattener", far), -180)

    def test_parallel_is_flat(self):
        self.assertEqual({BASEL_SHIFTS["parallel_up"](b.tenor_years) for b in BUCKETS}, {400.0})

    def test_steepener_and_flattener_cross_zero_once(self):
        for code in ("steepener", "flattener"):
            shifts = [basel_shift_bp(code, b.tenor_years) for b in BUCKETS]
            crossings = sum(math.copysign(1, a) != math.copysign(1, b)
                            for a, b in zip(shifts, shifts[1:]))
            self.assertEqual(crossings, 1, code)


if __name__ == "__main__":
    unittest.main()
