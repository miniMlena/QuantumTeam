"""
Расчёт NPV, NII и ЭКпрбк по сценариям.

Договорённости, как в эталонном расчёте:
  * ставки в процентах (13.27 значит 13.27%);
  * поток попадает в свой бакет и дисконтируется по ставке этого бакета
    на срок его середины: 100 / (1 + ставка/100)^срок;
  * сумма позиции: актив со знаком "+", пассив со знаком "-".
"""
from domain.constants import BUCKETS, Bucket


def bucket_for(years: float) -> Bucket:
    """Бакет потока со сроком years: правая граница бакета включается."""
    for bucket in BUCKETS:
        if bucket.end_years is None or years <= bucket.end_years:
            return bucket
    raise ValueError(f"No bucket for {years} years")


def discount_factor(rate_percent: float, years: float) -> float:
    """Коэффициент дисконтирования: 1 / (1 + r)^t."""
    return 1 / (1 + rate_percent / 100) ** years


def build_cash_flows(position) -> list[tuple[int, float]]:
    """
    Денежные потоки позиции: проценты раз в год, тело долга в конце.
    Для плавающей ставки поток заканчивается на дате пересмотра: дальше
    ставка следует за рынком и на стоимость не влияет.
    Для последнего неполного года проценты считаются пропорционально.
    Возвращает список (месяцев до платежа, сумма).
    """
    amount = float(position.amount)
    yearly_interest = amount * float(position.rate) / 100
    end_month = min(position.maturity_months, position.repricing_months)

    cash_flows = []
    month = 12
    while month < end_month:
        cash_flows.append((month, yearly_interest))
        month += 12

    last_coupon_month = month - 12
    last_period_years = (end_month - last_coupon_month) / 12
    cash_flows.append((end_month, amount + yearly_interest * last_period_years))
    return cash_flows


def calculate_npv(positions, rates: dict[str, float]) -> float:
    """rates: {код бакета: ставка, %}. NPV = сумма дисконтированных потоков."""
    npv = 0.0
    for position in positions:
        for months, amount in build_cash_flows(position):
            bucket = bucket_for(months / 12)
            npv += amount * discount_factor(rates[bucket.code], bucket.tenor_years)
    return npv


def calculate_nii(positions, base_rates: dict[str, float], scenario_rates: dict[str, float]) -> float:
    """
    Упрощённый NII на горизонте 12 месяцев при постоянном балансе:
      процентный доход по ставкам договоров
      + эффект переоценки позиций, ставка которых пересматривается
        раньше чем через год (метод разрывов).
    """
    nii = 0.0
    for position in positions:
        amount = float(position.amount)
        nii += amount * float(position.rate) / 100

        repricing_months = position.repricing_months
        if repricing_months < 12:
            code = bucket_for(repricing_months / 12).code
            rate_change = scenario_rates[code] - base_rates[code]
            months_after_repricing = 12 - repricing_months
            nii += amount * rate_change / 100 * months_after_repricing / 12
    return nii


def calculate_all_scenarios(positions, base_rates: dict[str, float], scenarios: list[dict]) -> dict:
    """
    scenarios: [{"code", "name", "scenario_type", "rates": {код бакета: ставка}}, ...]
    Возвращает {"base_npv", "base_nii", "scenarios": [...]}, где у каждого
    сценария есть npv, delta_npv, nii, delta_nii.
    """
    base_npv = calculate_npv(positions, base_rates)
    base_nii = calculate_nii(positions, base_rates, base_rates)

    results = []
    for scenario in scenarios:
        npv = calculate_npv(positions, scenario["rates"])
        nii = calculate_nii(positions, base_rates, scenario["rates"])
        results.append({
            "code": scenario["code"],
            "name": scenario["name"],
            "scenario_type": scenario["scenario_type"],
            "npv": npv,
            "delta_npv": npv - base_npv,
            "nii": nii,
            "delta_nii": nii - base_nii,
        })

    return {"base_npv": base_npv, "base_nii": base_nii, "scenarios": results}


def find_economic_capital(scenario_results: list[dict]) -> dict | None:
    """ЭКпрбк = минимальное ΔNPV среди сценариев (самое отрицательное изменение)."""
    if not scenario_results:
        return None
    worst = min(scenario_results, key=lambda result: result["delta_npv"])
    return {
        "scenario_code": worst["code"],
        "scenario_name": worst["name"],
        "value": worst["delta_npv"],
    }
