"""
Дисконтирование сверяется со строками 8–9 эталонного Excel, остальное —
логика NPV, NII и ЭКпрбк. Эталонные значения и часть проверок перенесены
из ветки feature/npv-and-dashboard (автор Opik1704).
"""
from types import SimpleNamespace
import unittest

from domain.constants import BUCKETS
from domain.valuation import (
    bucket_for, build_cash_flows, calculate_all_scenarios, calculate_nii,
    calculate_npv, discount_factor, find_economic_capital,
)
from test_excel_reference import EXCEL_BASE, EXCEL_STEEPENER

# Строка 8 Excel: 100 ₽ по базовой кривой
EXCEL_BASE_PV = [
    99.96511692, 99.48174822, 97.94427279, 95.42535489, 92.42109588, 89.42184354,
    84.85520543, 78.96276642, 70.44948414, 60.66502823, 51.96077909, 44.37403805,
    38.279881, 32.97997178, 28.40404835, 24.3347371, 15.42391682, 7.22591351, 2.27391127,
]

# Строка 9 Excel: 100 ₽ по кривой steepener
EXCEL_STEEPENER_PV = [
    99.97325523, 99.60026137, 98.38458018, 96.29808538, 93.65893147, 90.87980578,
    86.41824605, 80.36026704, 71.19721936, 60.26240099, 50.43548457, 41.9390702,
    35.15559132, 29.40455001, 24.58029341, 20.44574752, 11.89542557, 4.88772391, 1.28447225,
]


def flat_rates(rate):
    return {bucket.code: rate for bucket in BUCKETS}


def position(amount, rate, maturity_months, repricing_months=None):
    return SimpleNamespace(
        amount=amount, rate=rate, maturity_months=maturity_months,
        repricing_months=repricing_months or maturity_months,
    )


class ExcelDiscountingTests(unittest.TestCase):
    def check(self, rates, expected):
        for bucket, pv in zip(BUCKETS, expected):
            with self.subTest(bucket=bucket.code):
                self.assertAlmostEqual(
                    100 * discount_factor(rates[bucket.code], bucket.tenor_years), pv, delta=1e-4
                )

    def test_base_row_8(self):
        self.check(EXCEL_BASE, EXCEL_BASE_PV)

    def test_steepener_row_9(self):
        self.check(EXCEL_STEEPENER, EXCEL_STEEPENER_PV)

    def test_npv_uses_bucket_rate_and_middle(self):
        # Единственный поток на 3 года попадает в бакет 3y
        self.assertAlmostEqual(
            calculate_npv([position(100, 0, 36)], EXCEL_BASE), EXCEL_BASE_PV[8], delta=1e-4
        )


class BucketTests(unittest.TestCase):
    def test_bucket_end_is_included(self):
        self.assertEqual(bucket_for(1.0).code, "1y")
        self.assertEqual(bucket_for(1.01).code, "1.5y")
        self.assertEqual(bucket_for(3.0).code, "3y")

    def test_long_flows_go_to_last_bucket(self):
        self.assertEqual(bucket_for(40).code, "30y")


class CashFlowTests(unittest.TestCase):
    def test_bullet_two_years(self):
        self.assertEqual(build_cash_flows(position(1000, 10, 24)), [(12, 100.0), (24, 1100.0)])

    def test_stub_period(self):
        flows = build_cash_flows(position(1000, 10, 18))
        self.assertEqual(flows[0], (12, 100.0))
        self.assertEqual(flows[1][0], 18)
        self.assertAlmostEqual(flows[1][1], 1050.0)

    def test_floating_ends_on_repricing_date(self):
        flows = build_cash_flows(position(600, 17, 36, repricing_months=3))
        self.assertEqual(len(flows), 1)
        self.assertEqual(flows[0][0], 3)
        self.assertAlmostEqual(flows[0][1], 625.5)


class NpvTests(unittest.TestCase):
    def test_falls_when_rates_rise_for_asset(self):
        p = [position(1000, 10, 60)]
        self.assertLess(calculate_npv(p, flat_rates(11)), calculate_npv(p, flat_rates(10)))

    def test_liability_has_opposite_sign(self):
        rates = flat_rates(10)
        self.assertAlmostEqual(
            calculate_npv([position(-1000, 8, 36)], rates),
            -calculate_npv([position(1000, 8, 36)], rates),
        )

    def test_floating_is_less_sensitive_than_fixed(self):
        fixed = [position(1000, 10, 36)]
        floating = [position(1000, 10, 36, repricing_months=3)]
        change = lambda p: calculate_npv(p, flat_rates(14)) - calculate_npv(p, flat_rates(10))
        self.assertLess(abs(change(floating)), abs(change(fixed)))


class NiiTests(unittest.TestCase):
    def test_unchanged_without_short_repricing(self):
        p = [position(1000, 10, 60)]
        self.assertAlmostEqual(calculate_nii(p, flat_rates(10), flat_rates(11)), 100.0)

    def test_gap_effect_for_short_repricing(self):
        # Актив 1000, пересмотр через 6 мес., +100 б.п.: 1000 * 1% * 6/12 = 5
        p = [position(1000, 10, 24, repricing_months=6)]
        self.assertAlmostEqual(calculate_nii(p, flat_rates(10), flat_rates(11)), 105.0)


class EconomicCapitalTests(unittest.TestCase):
    def test_is_minimum_delta_npv(self):
        scenarios = [
            {"code": code, "name": code, "scenario_type": "parallel", "rates": flat_rates(rate)}
            for code, rate in (("up", 11), ("down", 9), ("zero", 10))
        ]
        result = calculate_all_scenarios([position(1000, 10, 60)], flat_rates(10), scenarios)
        capital = find_economic_capital(result["scenarios"])
        deltas = {item["code"]: item["delta_npv"] for item in result["scenarios"]}

        self.assertEqual(capital["scenario_code"], "up")
        self.assertEqual(capital["value"], min(deltas.values()))
        self.assertAlmostEqual(deltas["zero"], 0.0)
        self.assertGreater(deltas["down"], 0)

    def test_empty(self):
        self.assertIsNone(find_economic_capital([]))


if __name__ == "__main__":
    unittest.main()
