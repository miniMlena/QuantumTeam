"""
Сверка с Excel-эталоном (файл "3108": дисконтирование платежа 100
в базовом и стрессовом сценарии) и проверка логики ЭКпрбк.
"""
from types import SimpleNamespace

import pytest

from domain.valuation import (
    interpolate, shift_curve, discount_factor, build_cash_flows,
    calculate_npv, calculate_nii, calculate_all_scenarios,
    find_economic_capital, normalize_rates,
)
from domain.curve.irrbb_scenarios import shift_bp_at, build_shifts

# --- данные из Excel ---------------------------------------------------
TENORS_YEARS = [0.0028, 0.0417, 0.1667, 0.375, 0.625, 0.875, 1.25, 1.75, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 12.5, 17.5, 25]
BASE_RATES = [13.27, 13.27, 13.27, 13.3, 13.44, 13.63, 14.04, 14.45, 15.04, 15.35, 15.66, 15.92, 15.92, 15.94, 15.96, 16.04, 16.13, 16.2, 16.34]
STRESS_RATES = [10.0241635426, 10.0817065458, 10.2628702898, 10.5824633498, 11.0506953025, 11.5490406866, 12.3868870078, 13.3083912678, 14.5551945003, 15.5696709829, 16.4283178192, 17.115604405, 17.4483755325, 17.7275379473, 17.9493738388, 18.1865637892, 18.5685752449, 18.8251005537, 19.0285137979]
BASE_DCF = [99.96511692, 99.48174822, 97.94427279, 95.42535489, 92.42109588, 89.42184354, 84.85520543, 78.96276642, 70.44948414, 60.66502823, 51.96077909, 44.37403805, 38.279881, 32.97997178, 28.40404835, 24.3347371, 15.42391682, 7.22591351, 2.27391127]
STRESS_DCF = [99.97325523, 99.60026137, 98.38458018, 96.29808538, 93.65893147, 90.87980578, 86.41824605, 80.36026704, 71.19721936, 60.26240099, 50.43548457, 41.9390702, 35.15559132, 29.40455001, 24.58029341, 20.44574752, 11.89542557, 4.88772391, 1.28447225]


@pytest.mark.parametrize("years, rate, expected", list(zip(TENORS_YEARS, BASE_RATES, BASE_DCF)))
def test_discounting_matches_excel_base(years, rate, expected):
    assert 100 * discount_factor(rate, years) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("years, rate, expected", list(zip(TENORS_YEARS, STRESS_RATES, STRESS_DCF)))
def test_discounting_matches_excel_stress(years, rate, expected):
    assert 100 * discount_factor(rate, years) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("years, base_rate, stress_rate", list(zip(TENORS_YEARS, BASE_RATES, STRESS_RATES)))
def test_steepener_formula_matches_excel_shift(years, base_rate, stress_rate):
    """Сдвиг из Excel = steepener BCBS (short 500, long 300). Допуск 1 б.п.: базовые ставки в Excel округлены."""
    excel_shift_bp = (stress_rate - base_rate) * 100
    assert shift_bp_at("steepener", years) == pytest.approx(excel_shift_bp, abs=1.0)


# --- отдельные функции --------------------------------------------------
def test_interpolate_between_and_outside():
    values = {12: 10.0, 24: 20.0}
    assert interpolate(18, values) == pytest.approx(15.0)
    assert interpolate(1, values) == 10.0     # левее края
    assert interpolate(100, values) == 20.0   # правее края


def test_interpolate_empty_raises():
    with pytest.raises(ValueError):
        interpolate(12, {})


def test_shift_curve_converts_bp_to_percent():
    curve = {12: 10.0, 60: 12.0}
    shifted = shift_curve(curve, {12: 100, 60: -50})
    assert shifted[12] == pytest.approx(11.0)    # +100 б.п. = +1%
    assert shifted[60] == pytest.approx(11.5)


def test_normalize_rates_fractions_to_percent():
    assert normalize_rates({12: 0.13}) == {12: pytest.approx(13.0)}
    assert normalize_rates({12: 13.0}) == {12: 13.0}


def test_parallel_scenarios_are_constant():
    assert shift_bp_at("parallel_up", 0.5) == 400
    assert shift_bp_at("parallel_down", 20) == -400


def test_unknown_scenario_code_raises():
    with pytest.raises(ValueError):
        shift_bp_at("magic", 1)


def test_build_shifts_has_every_month():
    shifts = build_shifts("short_up")
    assert len(shifts) == 360
    assert shifts[0]["tenor_months"] == 1
    assert shifts[0]["shift_bp"] > shifts[-1]["shift_bp"] > 0   # короткие сильнее длинных


def make_position(amount, rate, maturity_months, repricing_months=None):
    return SimpleNamespace(
        amount=amount, rate=rate, maturity_months=maturity_months,
        repricing_months=repricing_months or maturity_months,
    )


def test_cash_flows_bullet_two_years():
    flows = build_cash_flows(make_position(1000, 10, 24))
    assert flows == [(12, 100.0), (24, 1100.0)]


def test_cash_flows_stub_period():
    flows = build_cash_flows(make_position(1000, 10, 18))
    assert flows[0] == (12, 100.0)
    assert flows[1] == (18, pytest.approx(1050.0))   # тело + полгода процентов


def test_npv_at_par_equals_notional():
    """Облигация с купоном = ставке дисконтирования стоит ровно номинал."""
    flat_curve = {12: 10.0, 120: 10.0}
    assert calculate_npv([make_position(1000, 10, 36)], flat_curve) == pytest.approx(1000.0)


def test_npv_falls_when_rates_rise_for_asset():
    position = make_position(1000, 10, 60)
    base = {12: 10.0, 120: 10.0}
    assert calculate_npv([position], shift_curve(base, {12: 100, 120: 100})) < calculate_npv([position], base)


def test_liability_has_opposite_sign():
    curve = {12: 10.0, 120: 10.0}
    asset = calculate_npv([make_position(1000, 8, 36)], curve)
    liability = calculate_npv([make_position(-1000, 8, 36)], curve)
    assert liability == pytest.approx(-asset)


def test_nii_unchanged_without_short_repricing():
    position = make_position(1000, 10, 60, repricing_months=60)
    curve = {12: 10.0, 120: 10.0}
    shifted = shift_curve(curve, {12: 100, 120: 100})
    assert calculate_nii([position], curve, shifted) == pytest.approx(100.0)


def test_nii_gap_effect_for_short_repricing():
    """Актив 1000, пересмотр через 6 мес., +100 б.п.: доп. доход = 1000*1%*(6/12) = 5."""
    position = make_position(1000, 10, 24, repricing_months=6)
    curve = {1: 10.0, 120: 10.0}
    shifted = shift_curve(curve, {1: 100, 120: 100})
    assert calculate_nii([position], curve, shifted) == pytest.approx(100.0 + 5.0)


# --- ЭКпрбк = минимум по сценариям -------------------------------------
def test_economic_capital_is_minimum_delta_npv():
    positions = [make_position(1000, 10, 60)]
    base_curve = {12: 10.0, 360: 10.0}
    scenarios = [
        {"code": "up", "name": "Up", "scenario_type": "parallel", "shift_bp": {12: 100, 360: 100}},
        {"code": "down", "name": "Down", "scenario_type": "parallel", "shift_bp": {12: -100, 360: -100}},
        {"code": "zero", "name": "Zero", "scenario_type": "parallel", "shift_bp": {12: 0, 360: 0}},
    ]
    result = calculate_all_scenarios(positions, base_curve, scenarios)
    capital = find_economic_capital(result["scenarios"])

    delta_by_code = {item["code"]: item["delta_npv"] for item in result["scenarios"]}
    assert capital["value"] == min(delta_by_code.values())
    assert capital["scenario_code"] == "up"            # у актива NPV падает при росте ставок
    assert delta_by_code["zero"] == pytest.approx(0.0)
    assert delta_by_code["down"] > 0


def test_economic_capital_empty():
    assert find_economic_capital([]) is None
