import math
import random
import time
import unittest
from decimal import Decimal
from types import SimpleNamespace

from domain.constants import BUCKETS
from domain.curve.scenarios import BASEL_SHIFTS, default_scenarios
from domain.curve.shifts import apply_shift
from domain.valuation import (
    bucket_for, build_cash_flows, calculate_all_scenarios, calculate_nii,
    calculate_npv, discount_factor, find_economic_capital,
)


def flat(rate):
    return {bucket.code: rate for bucket in BUCKETS}


def position(amount, rate, maturity_months, repricing_months=None):
    return SimpleNamespace(
        amount=amount, rate=rate, maturity_months=maturity_months,
        repricing_months=repricing_months or maturity_months,
    )


def scenario(code, rates):
    return {"code": code, "name": code, "scenario_type": "parallel", "rates": rates}


# ---------------------------------------------------------------- найденные проблемы
class KnownBugs(unittest.TestCase):
    def test_extreme_negative_rate_gives_clear_error(self):
        """Сценарий со сдвигом в -15000 б.п. не должен ломать расчёт комплексными числами."""
        for rate in (-100, -150):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    discount_factor(rate, 0.875)

    def test_npv_is_always_a_real_number(self):
        npv = calculate_npv([position(100, 10, 12)], flat(-150))
        self.assertNotIsInstance(npv, complex)

    def test_economic_capital_is_not_a_gain(self):
        """Если все сценарии прибыльны, «ЭК» не должен быть положительным числом."""
        result = calculate_all_scenarios(
            [position(1000, 10, 60)], flat(10), [scenario("down", flat(5))]
        )
        capital = find_economic_capital(result["scenarios"])
        self.assertTrue(capital is None or capital["value"] <= 0, capital)

    def test_missing_bucket_in_scenario_is_value_error(self):
        rates = {code: 10 for code in flat(10) if code != "5y"}
        with self.assertRaises(ValueError):
            calculate_npv([position(1000, 10, 60)], rates)

    def test_par_bond_on_flat_curve_is_worth_par(self):
        """
        Облигация с купоном 10% при плоской кривой 10% должна стоить номинал.
        Сейчас дисконтирование идёт на середину бакета (0.875 года вместо 1),
        поэтому NPV завышен. Это соглашение эталонного Excel, но его надо
        согласовать с заказчиком и записать в документацию.
        """
        npv = calculate_npv([position(1000, 10, 36)], flat(10))
        self.assertAlmostEqual(npv, 1000, delta=5)


# ---------------------------------------------------------------- должны проходить
class ShiftInvariants(unittest.TestCase):
    base = [{"bucket_code": b.code, "tenor_years": b.tenor_years, "rate": 10.0} for b in BUCKETS]

    def test_parallel_100bp_moves_every_point_by_exactly_one_percent(self):
        shifted = apply_shift(self.base, {b.tenor_years: 100.0 for b in BUCKETS})
        for point in shifted:
            self.assertAlmostEqual(point["shifted_rate"], 11.0, places=12)

    def test_zero_shift_changes_nothing(self):
        for point in apply_shift(self.base, {b.tenor_years: 0.0 for b in BUCKETS}):
            self.assertEqual(point["shifted_rate"], 10.0)

    def test_does_not_mutate_input(self):
        before = [dict(p) for p in self.base]
        apply_shift(self.base, {1.0: 50.0})
        self.assertEqual(self.base, before)

    def test_interpolation_is_linear_and_clamped(self):
        shifts = {1.0: 0.0, 3.0: 200.0}
        by_tenor = {p["tenor_years"]: p["shift_bp"] for p in apply_shift(self.base, shifts)}
        self.assertEqual(by_tenor[0.0028], 0.0)          # левее: крайнее значение
        self.assertEqual(by_tenor[25.0], 200.0)          # правее: крайнее значение
        self.assertAlmostEqual(by_tenor[1.75], 75.0)     # 1.75 лежит на 37.5% пути от 1 до 3

    def test_empty_shift_map_is_zero_shift(self):
        for point in apply_shift(self.base, {}):
            self.assertEqual(point["shift_bp"], 0.0)

    def test_bucket_tenors_survive_database_rounding(self):
        """
        В БД tenor_years хранится как Numeric(8,4). Сдвиги ищутся по точному
        равенству float, поэтому округление не должно менять срок бакета.
        """
        for bucket in BUCKETS:
            stored = float(Decimal(str(bucket.tenor_years)).quantize(Decimal("0.0001")))
            self.assertEqual(stored, bucket.tenor_years, bucket.code)


class ScenarioOracle(unittest.TestCase):
    """Независимая проверка Basel-формул, записанных в тесте заново."""

    @staticmethod
    def expected(code, t):
        short = 500 * math.exp(-t / 4)
        long_ = 300 * (1 - math.exp(-t / 4))
        return {
            "parallel_up": 400, "parallel_down": -400,
            "short_up": short, "short_down": -short,
            "steepener": -0.65 * short + 0.9 * long_,
            "flattener": 0.8 * short - 0.6 * long_,
        }[code]

    def test_all_six_scenarios_on_all_buckets(self):
        for item in default_scenarios():
            for shift in item["shifts"]:
                with self.subTest(code=item["code"], tenor=shift["tenor_years"]):
                    self.assertAlmostEqual(
                        shift["shift_bp"], self.expected(item["code"], shift["tenor_years"]),
                        places=9,
                    )

    def test_codes_and_types(self):
        types = {s["code"]: s["scenario_type"] for s in default_scenarios()}
        self.assertEqual(set(types), set(BASEL_SHIFTS))
        self.assertEqual(sum(t == "parallel" for t in types.values()), 2)


class ValuationOracle(unittest.TestCase):
    def test_hand_calculated_bullet_loan(self):
        # 1000 под 10% на 3 года: потоки 100 (12м), 100 (24м), 1100 (36м)
        # бакеты 1y (0.875), 2y (1.75), 3y (2.5), плоская ставка 10%
        expected = 100 / 1.1 ** 0.875 + 100 / 1.1 ** 1.75 + 1100 / 1.1 ** 2.5
        self.assertAlmostEqual(calculate_npv([position(1000, 10, 36)], flat(10)), expected, places=9)

    def test_zero_rate_npv_equals_sum_of_flows(self):
        for maturity in (1, 6, 12, 13, 18, 24, 37, 120, 360):
            with self.subTest(maturity=maturity):
                p = position(1000, 7, maturity)
                total = sum(amount for _, amount in build_cash_flows(p))
                self.assertAlmostEqual(calculate_npv([p], flat(0)), total, places=9)

    def test_principal_is_always_returned_once(self):
        for maturity in (1, 5, 11, 12, 13, 23, 24, 25, 60, 361):
            with self.subTest(maturity=maturity):
                flows = build_cash_flows(position(1000, 0, maturity))
                self.assertAlmostEqual(sum(a for _, a in flows), 1000)

    def test_npv_and_nii_are_additive_over_positions(self):
        a, b = position(1000, 10, 36), position(-400, 8, 18, 6)
        rates, base = flat(12), flat(10)
        self.assertAlmostEqual(
            calculate_npv([a, b], rates), calculate_npv([a], rates) + calculate_npv([b], rates)
        )
        self.assertAlmostEqual(
            calculate_nii([a, b], base, rates),
            calculate_nii([a], base, rates) + calculate_nii([b], base, rates),
        )

    def test_empty_portfolio_is_zero(self):
        self.assertEqual(calculate_npv([], flat(10)), 0)
        self.assertEqual(calculate_nii([], flat(10), flat(11)), 0)

    def test_rates_up_asset_down_liability_up(self):
        asset, liability = [position(1000, 10, 60)], [position(-1000, 10, 60)]
        self.assertLess(calculate_npv(asset, flat(12)), calculate_npv(asset, flat(10)))
        self.assertGreater(calculate_npv(liability, flat(12)), calculate_npv(liability, flat(10)))

    def test_nii_floating_asset_gains_when_rates_rise(self):
        delta = calculate_nii([position(1000, 10, 60, 3)], flat(10), flat(12)) \
            - calculate_nii([position(1000, 10, 60, 3)], flat(10), flat(10))
        self.assertAlmostEqual(delta, 1000 * 0.02 * 9 / 12)

    def test_nii_floating_liability_loses_when_rates_rise(self):
        p = [position(-1000, 10, 60, 3)]
        self.assertLess(calculate_nii(p, flat(10), flat(12)), calculate_nii(p, flat(10), flat(10)))

    def test_bucket_boundaries(self):
        expected = {1: "1m", 2: "3m", 3: "3m", 4: "6m", 6: "6m", 9: "9m", 12: "1y", 13: "1.5y",
                    18: "1.5y", 24: "2y", 36: "3y", 120: "10y", 121: "15y", 240: "20y", 241: "30y"}
        for months, code in expected.items():
            self.assertEqual(bucket_for(months / 12).code, code, months)


class EconomicCapital(unittest.TestCase):
    def test_equals_minimum_over_all_scenarios(self):
        random.seed(7)
        positions = [position(random.randint(-1000, 1000) or 1, random.uniform(1, 20),
                              m := random.randint(1, 120), random.randint(1, m))
                     for _ in range(200)]
        scenarios = [scenario(f"s{i}", flat(random.uniform(1, 25))) for i in range(30)]
        result = calculate_all_scenarios(positions, flat(10), scenarios)
        capital = find_economic_capital(result["scenarios"])
        self.assertEqual(capital["value"], min(s["delta_npv"] for s in result["scenarios"]))

    def test_base_scenario_has_zero_delta(self):
        result = calculate_all_scenarios([position(1000, 10, 60)], flat(10), [scenario("same", flat(10))])
        self.assertEqual(result["scenarios"][0]["delta_npv"], 0)
        self.assertEqual(result["scenarios"][0]["delta_nii"], 0)

    def test_no_scenarios_means_no_capital(self):
        result = calculate_all_scenarios([position(1000, 10, 60)], flat(10), [])
        self.assertIsNone(find_economic_capital(result["scenarios"]))


class Performance(unittest.TestCase):
    def test_100k_positions_six_scenarios_under_30_seconds(self):
        random.seed(1)
        positions = [position(random.randint(1, 1000), random.uniform(5, 20),
                              m := random.randint(1, 360), random.randint(1, m))
                     for _ in range(100_000)]
        scenarios = [scenario(f"s{i}", flat(10 + i)) for i in range(6)]
        started = time.perf_counter()
        calculate_all_scenarios(positions, flat(10), scenarios)
        self.assertLess(time.perf_counter() - started, 30)


if __name__ == "__main__":
    unittest.main()
