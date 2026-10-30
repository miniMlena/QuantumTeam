"""
Построение базовой кривой из параметров Nelson-Siegel.
Формула NS (с учётом корректирующих членов G1..G9 опускаем —
их интерпретация зависит от методики MOEX; для прототипа
используем классическую NS-модель, а G-члены игнорируем).
"""
import math
from domain.constants import (
    STANDARD_TENORS_MONTHS,
    MOEX_OBSERVED_TENORS_MONTHS,
)


def nelson_siegel_rate(
    tenor_years: float, b1: float, b2: float, b3: float, t1: float
) -> float:
    """
    Классическая формула Нельсона-Сигеля:
      r(t) = b0 + b1 * ((1 - exp(-t/τ)) / (t/τ))
                + b2 * ((1 - exp(-t/τ)) / (t/τ) - exp(-t/τ))
    где b0 = b1 (в терминах MOEX), b1 = b2, b2 = b3, τ = t1.
    Возвращает ставку в долях (не в процентах).
    """
    tenor_years = float(tenor_years)
    b1 = float(b1)
    b2 = float(b2)
    b3 = float(b3)
    t1 = float(t1)
    
    if tenor_years <= 0:
        return b1 # предельное значение при t→0

    x = tenor_years / t1 if t1 > 0 else 0.0
    if x == 0:
        factor1, factor2 = 1.0, 0.0
    else:
        exp_neg = math.exp(-x)
        factor1 = (1 - exp_neg) / x
        factor2 = factor1 - exp_neg

    return b1 + b2 * factor1 + b3 * factor2


def build_base_curve(params: dict) -> list[dict]:
    """
    params: {b1, b2, b3, t1}
    Возвращает список точек:
      [{"tenor_months": int, "rate": float, "point_type": str}, ...]
    point_type:
      - "observed"     — тенор входит в эталонную сетку MOEX
      - "interpolated" — между эталонными узлами
      - "extrapolated" — за пределами эталонной сетки
    """
    b1, b2, b3, t1 = params["b1"], params["b2"], params["b3"], params["t1"]
    min_obs = min(MOEX_OBSERVED_TENORS_MONTHS)
    max_obs = max(MOEX_OBSERVED_TENORS_MONTHS)

    points = []
    for tenor_months in STANDARD_TENORS_MONTHS:
        tenor_years = tenor_months / 12.0
        rate = nelson_siegel_rate(tenor_years, b1, b2, b3, t1)
        points.append({
            "tenor_months": tenor_months,
            "rate": rate,
            "point_type": _classify_point_type(tenor_months, min_obs, max_obs),
        })
    return points


def _classify_point_type(
    tenor_months: int, min_obs: int, max_obs: int
) -> str:
    if tenor_months in MOEX_OBSERVED_TENORS_MONTHS:
        return "observed"
    if tenor_months < min_obs or tenor_months > max_obs:
        return "extrapolated"
    return "interpolated"