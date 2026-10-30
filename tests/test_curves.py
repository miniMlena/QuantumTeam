import json
import math
from decimal import Decimal
from pathlib import Path
import unittest

from domain.constants import STANDARD_TENORS_MONTHS
from domain.curve.builder import build_base_curve, moex_rate, nelson_siegel_rate
from domain.curve.interpolation import interpolate_curve
from domain.curve.scenarios import (
    SCENARIOS, build_irrbb_shift_map, default_scenarios, irrbb_shift_bp,
)
from domain.curve.shifts import apply_irrbb_scenario, apply_shift
from domain.moex.client import parse_curve_params


class CurveTests(unittest.TestCase):
    def test_nelson_siegel_zero_and_small_tenor(self):
        for t in (0, 1e-14):
            self.assertAlmostEqual(nelson_siegel_rate(t, .1, -.02, .03, 2), .08)

    def test_ns_manual_one_tau(self):
        self.assertAlmostEqual(nelson_siegel_rate(2, .1, .02, .03, 2),
                               .1 + .02 * (1 - 1/math.e) + .03 * (1 - 2/math.e))

    def test_invalid_inputs(self):
        for bad in (0, -1, float("nan"), float("inf")):
            with self.subTest(tau=bad), self.assertRaises(ValueError):
                nelson_siegel_rate(1, 1000, 0, 0, bad)
        for bad in (-1, float("nan"), float("inf")):
            with self.subTest(tenor=bad), self.assertRaises(ValueError):
                nelson_siegel_rate(bad, 1000, 0, 0, 1)

    def test_moex_units_and_decimal_database_parameters(self):
        p = {"b1": Decimal("1000"), "b2": Decimal("0"),
             "b3": Decimal("0"), "t1": Decimal("1"), "g1": None}
        self.assertEqual(moex_rate(1, p), .1)

    def test_gaussian_correction_at_center(self):
        p = {"b1": 1000, "b2": 0, "b3": 0, "t1": 1, "g2": 100}
        self.assertAlmostEqual(moex_rate(.6, p), .11)

    def test_all_nine_corrections(self):
        p = {"b1": 0, "b2": 0, "b3": 0, "t1": 1}
        center, width = 0.0, .6
        for i in range(1, 10):
            with self.subTest(i=i):
                self.assertAlmostEqual(moex_rate(center, {**p, f"g{i}": 100}), .01)
            center += width
            width *= 1.6

    def test_published_moex_yields(self):
        payload = json.loads((Path(__file__).parent/"fixtures/moex_zcyc.json").read_text())
        p = parse_curve_params(payload)
        for row in payload["yearyields"]["data"]:
            with self.subTest(years=row[2]):
                self.assertAlmostEqual(math.expm1(moex_rate(row[2], p))*100,
                                       row[3], delta=.00005)

    def test_grid_and_classification(self):
        p = {"b1": 1000, "b2": 0, "b3": 0, "t1": 1}
        curve = build_base_curve(p)
        self.assertEqual([x["tenor_months"] for x in curve], STANDARD_TENORS_MONTHS)
        self.assertEqual(curve[0]["point_type"], "extrapolated")
        self.assertEqual(curve[-2]["point_type"], "observed")
        self.assertEqual(curve[-1]["point_type"], "extrapolated")
        self.assertEqual(build_base_curve(p, []), [])


class InterpolationTests(unittest.TestCase):
    def test_linear_interpolation_and_extrapolation(self):
        points = [{"tenor_months": 12, "rate": .1}, {"tenor_months": 24, "rate": .12}]
        result = interpolate_curve(points[::-1], [0, 12, 18, 24, 36])
        for p, expected in zip(result, [.08, .1, .11, .12, .14]):
            self.assertAlmostEqual(p["rate"], expected)
        self.assertEqual([p["point_type"] for p in result],
                         ["extrapolated", "observed", "interpolated",
                          "observed", "extrapolated"])
        self.assertEqual(interpolate_curve(points, []), [])

    def test_single_point_is_flat(self):
        result = interpolate_curve([{"tenor_months": 12, "rate": Decimal(".1")}], [6, 24])
        self.assertEqual([p["rate"] for p in result], [.1, .1])

    def test_bad_nodes(self):
        for points in ([], [{"tenor_months": 12, "rate": .1}]*2,
                       [{"tenor_months": 1, "rate": float("nan")}]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                interpolate_curve(points)


class ScenarioTests(unittest.TestCase):
    def test_annex2_examples(self):
        # IRRBB Annex 2, печатная страница 45, t=3.5 года, JPY.
        self.assertAlmostEqual(irrbb_shift_bp(3.5, "short_up", "JPY"), 41.7, delta=.05)
        self.assertAlmostEqual(irrbb_shift_bp(3.5, "steepener", "JPY"), 25.4, delta=.05)
        self.assertAlmostEqual(irrbb_shift_bp(3.5, "flattener", "JPY"), -1.6, delta=.05)

    def test_rub_parallel_and_short_limits(self):
        for t in (0, 1, 10, 100):
            self.assertEqual(irrbb_shift_bp(t, "parallel_up"), 400)
            self.assertEqual(irrbb_shift_bp(t, "parallel_down"), -400)
        self.assertEqual(irrbb_shift_bp(0, "short_up"), 500)
        self.assertAlmostEqual(irrbb_shift_bp(1000, "short_up"), 0)
        self.assertEqual(irrbb_shift_bp(0, "steepener"), -325)
        self.assertAlmostEqual(irrbb_shift_bp(1000, "steepener"), 270)
        self.assertEqual(irrbb_shift_bp(0, "flattener"), 400)
        self.assertAlmostEqual(irrbb_shift_bp(1000, "flattener"), -180)

    def test_custom_shocks_and_cbr_calibration(self):
        self.assertEqual(irrbb_shift_bp(1, "parallel_up", shock_sizes=(100, 200, 50)), 100)
        self.assertAlmostEqual(irrbb_shift_bp(1000, "steepener", "INR"), 315)

    def test_invalid_scenario_inputs(self):
        for args in ((1, "typo", "RUB"), (1, "short_up", "RBU"),
                     (-1, "short_up", "RUB"), (float("nan"), "short_up", "RUB")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                irrbb_shift_bp(*args)
        with self.assertRaises(ValueError):
            irrbb_shift_bp(1, "short_up", shock_sizes=(100, -1, 50))

    def test_defaults_and_maps(self):
        defaults = default_scenarios()
        self.assertEqual(len(defaults), 6)
        self.assertEqual(len({d["code"] for d in defaults}), 6)
        for scenario in SCENARIOS:
            self.assertEqual(list(build_irrbb_shift_map(scenario)), STANDARD_TENORS_MONTHS)


class ShiftTests(unittest.TestCase):
    def setUp(self):
        self.base = [{"tenor_months": t, "rate": Decimal(".1"), "point_type": "observed"}
                     for t in (6, 12, 18, 24, 36)]

    def test_shift_interpolation_and_flat_ends(self):
        result = apply_shift(self.base, {12: Decimal("100"), 24: Decimal("-100")})
        for point, shift in zip(result, (100, 100, 0, -100, -100)):
            self.assertAlmostEqual(point["shifted_rate"], .1 + shift/10000)
            self.assertAlmostEqual(point["shift_bp"], shift)
        self.assertEqual(self.base[0]["rate"], Decimal(".1"))

    def test_empty_and_constant_shift(self):
        self.assertEqual([p["shifted_rate"] for p in apply_shift(self.base, {})], [.1]*5)
        self.assertEqual([p["shifted_rate"] for p in apply_shift(self.base, {12: 100})],
                         [.11]*5)

    def test_floor_reports_actual_shift(self):
        result = apply_shift(self.base, {12: -2000}, rate_floor=0)
        self.assertEqual(result[0]["shifted_rate"], 0)
        self.assertAlmostEqual(result[0]["shift_bp"], -1000)
        self.assertAlmostEqual(apply_shift(self.base, {12: -2000})[0]["shifted_rate"], -.1)

    def test_irrbb_evaluated_at_actual_tenor(self):
        result = apply_irrbb_scenario(self.base, "short_up")
        self.assertAlmostEqual(result[2]["shift_bp"], 500 * math.exp(-1.5/4))

    def test_bad_shift(self):
        with self.assertRaises(ValueError):
            apply_shift(self.base, {12: float("inf")})


if __name__ == "__main__":
    unittest.main()
