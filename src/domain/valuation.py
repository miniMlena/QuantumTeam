"""
Расчёт NPV, NII и ЭКпрбк под сценариями.

Договорённости:
  * ставки везде в ПРОЦЕНТАХ (13.27 значит 13.27%), как в Excel-эталоне;
  * сдвиги в базисных пунктах (100 б.п. = 1%);
  * сумма позиции: актив со знаком "+", пассив со знаком "-".
"""


def interpolate(tenor_months, values):
    """
    values: {tenor_months: число}. Линейная интерполяция между соседними
    тенорами, за краями берём крайнее значение (без экстраполяции).
    """
    if not values:
        raise ValueError("values is empty")

    tenors = sorted(values)
    if tenor_months <= tenors[0]:
        return values[tenors[0]]
    if tenor_months >= tenors[-1]:
        return values[tenors[-1]]

    for left, right in zip(tenors, tenors[1:]):
        if left <= tenor_months <= right:
            weight = (tenor_months - left) / (right - left)
            return values[left] * (1 - weight) + values[right] * weight


def normalize_rates(curve):
    """
    Защита от путаницы с единицами: если все ставки меньше 1,
    считаем, что они в долях (0.13), и переводим в проценты (13.0).
    """
    if curve and max(curve.values()) < 1:
        return {tenor: rate * 100 for tenor, rate in curve.items()}
    return curve


def shift_curve(base_curve, shift_bp_by_tenor):
    """Сдвинутая кривая: ставка + сдвиг/100 (б.п. -> проценты)."""
    return {
        tenor: rate + interpolate(tenor, shift_bp_by_tenor) / 100
        for tenor, rate in base_curve.items()
    }


def discount_factor(rate_percent, years):
    """Коэффициент дисконтирования, как в Excel: 1 / (1 + r)^t."""
    return 1 / (1 + rate_percent / 100) ** years


def build_cash_flows(position):
    """
    Денежные потоки позиции: проценты раз в год, тело долга в конце срока.
    Возвращает список (месяцев до платежа, сумма).
    Для последнего неполного года проценты считаются пропорционально.
    """
    amount = float(position.amount)
    yearly_interest = amount * float(position.rate) / 100
    maturity = position.maturity_months

    cash_flows = []
    month = 12
    while month < maturity:
        cash_flows.append((month, yearly_interest))
        month += 12

    last_coupon_month = month - 12
    last_period_years = (maturity - last_coupon_month) / 12
    cash_flows.append((maturity, amount + yearly_interest * last_period_years))
    return cash_flows


def calculate_npv(positions, curve):
    """NPV портфеля = сумма потоков, дисконтированных по кривой."""
    npv = 0.0
    for position in positions:
        for months, amount in build_cash_flows(position):
            rate = interpolate(months, curve)
            npv += amount * discount_factor(rate, months / 12)
    return npv


def calculate_nii(positions, base_curve, scenario_curve):
    """
    Упрощённый NII на горизонте 12 месяцев:
      процентный доход по текущим ставкам договоров
      + эффект переоценки для позиций, у которых ставка пересматривается
        раньше чем через год (метод разрывов / gap).
    """
    nii = 0.0
    for position in positions:
        amount = float(position.amount)
        nii += amount * float(position.rate) / 100

        repricing_months = position.repricing_months
        if repricing_months < 12:
            rate_change = (
                interpolate(repricing_months, scenario_curve)
                - interpolate(repricing_months, base_curve)
            )
            months_after_repricing = 12 - repricing_months
            nii += amount * rate_change / 100 * months_after_repricing / 12
    return nii


def calculate_all_scenarios(positions, base_curve, scenarios):
    """
    scenarios: [{"code", "name", "scenario_type", "shift_bp": {tenor: bp}}, ...]

    Возвращает {"base_npv", "base_nii", "scenarios": [...]}, где у каждого
    сценария есть npv, delta_npv, nii, delta_nii и кривая для графика.
    """
    base_npv = calculate_npv(positions, base_curve)
    base_nii = calculate_nii(positions, base_curve, base_curve)

    results = []
    for scenario in scenarios:
        shifted_curve = shift_curve(base_curve, scenario["shift_bp"])
        npv = calculate_npv(positions, shifted_curve)
        nii = calculate_nii(positions, base_curve, shifted_curve)

        results.append({
            "code": scenario["code"],
            "name": scenario["name"],
            "scenario_type": scenario["scenario_type"],
            "npv": npv,
            "delta_npv": npv - base_npv,
            "nii": nii,
            "delta_nii": nii - base_nii,
            "curve": [
                {
                    "tenor_months": tenor,
                    "base_rate": base_curve[tenor],
                    "shifted_rate": shifted_curve[tenor],
                }
                for tenor in sorted(base_curve)
            ],
        })

    return {"base_npv": base_npv, "base_nii": base_nii, "scenarios": results}


def find_economic_capital(scenario_results):
    """
    ЭКпрбк = минимальное значение ΔNPV среди всех сценариев
    (самое отрицательное изменение = самый тяжёлый сценарий).
    """
    if not scenario_results:
        return None
    worst = min(scenario_results, key=lambda result: result["delta_npv"])
    return {
        "scenario_code": worst["code"],
        "scenario_name": worst["name"],
        "value": worst["delta_npv"],
    }
