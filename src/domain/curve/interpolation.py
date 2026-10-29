"""
Линейная интерполяция/экстраполяция ставок между известными узлами.
Используется, если строите кривую из сырых точек MOEX, а не из NS.
"""
from domain.constants import (
    STANDARD_TENORS_MONTHS,
    MOEX_OBSERVED_TENORS_MONTHS,
)


def interpolate_curve(
    known_points: list[dict],   # [{"tenor_months": int, "rate": float}, ...]
    target_tenors: list[int] | None = None,
) -> list[dict]:
    """
    Возвращает точки в target_tenors (по умолчанию — STANDARD_TENORS_MONTHS),
    полученные линейной интерполяцией/экстраполяцией.
    """
    target_tenors = target_tenors or STANDARD_TENORS_MONTHS
    known = sorted(known_points, key=lambda p: p["tenor_months"])
    if not known:
        return []

    known_tenors = [p["tenor_months"] for p in known]
    known_rates = [p["rate"] for p in known]
    min_t, max_t = known_tenors[0], known_tenors[-1]

    result = []
    for tenor in target_tenors:
        rate = _linear_at(tenor, known_tenors, known_rates)
        if tenor in known_tenors:
            ptype = "observed"
        elif tenor < min_t or tenor > max_t:
            ptype = "extrapolated"
        else:
            ptype = "interpolated"
        result.append({
            "tenor_months": tenor, "rate": rate, "point_type": ptype,
        })
    return result


def _linear_at(
    x: float, xs: list[float], ys: list[float]
) -> float:
    if x <= xs[0]:
        # экстраполяция влево: по первым двум точкам
        if len(xs) < 2:
            return ys[0]
        slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
        return ys[0] + slope * (x - xs[0])
    if x >= xs[-1]:
        if len(xs) < 2:
            return ys[-1]
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return ys[-1] + slope * (x - xs[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            w = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] * (1 - w) + ys[i + 1] * w
    return ys[-1]