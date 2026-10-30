"""Кривая MOEX: Nelson-Siegel и девять гауссовых поправок."""
import math

from domain.constants import STANDARD_TENORS_MONTHS, MOEX_OBSERVED_TENORS_MONTHS
from domain.curve.validation import finite_number, nonnegative_number


def nelson_siegel_rate(
    tenor_years: float, b1: float, b2: float, b3: float, t1: float
) -> float:
    """Чистая NS-модель. Результат в тех же единицах, что и b1, b2, b3."""
    t = nonnegative_number(tenor_years, "tenor_years")
    b1, b2, b3 = (finite_number(v, n) for v, n in zip(
        (b1, b2, b3), ("b1", "b2", "b3")
    ))
    tau = finite_number(t1, "t1")
    if tau <= 0:
        raise ValueError("t1 must be positive")
    x = t / tau
    if x == 0:
        return b1 + b2
    # expm1 сохраняет точность при малых t/tau.
    factor = -math.expm1(-x) / x
    return finite_number(b1 + b2 * factor + b3 * (factor - math.exp(-x)), "rate")


def moex_rate(tenor_years: float, params: dict) -> float:
    """Сырые B/G из ISS в б.п.; результат — непрерывная ставка в долях.

    Отсутствующие/NULL G считаются нулевыми поправками.
    Эффективная годовая доходность из yearyields равна expm1(rate).
    """
    t = nonnegative_number(tenor_years, "tenor_years")
    rate_bp = nelson_siegel_rate(t, *(params[n] for n in ("b1", "b2", "b3", "t1")))
    center, width = 0.0, 0.6
    for i in range(1, 10):
        value = params.get(f"g{i}")
        g = 0.0 if value is None else finite_number(value, f"g{i}")
        rate_bp += g * math.exp(-((t - center) / width) ** 2)
        center += width
        width *= 1.6
    return finite_number(rate_bp / 10_000.0, "rate")


def build_base_curve(params: dict, target_tenors: list[int] | None = None) -> list[dict]:
    """Построить кривую на сроках в месяцах, сохраняя формат точек БД.

    point_type описывает положение относительно опубликованной сетки MOEX;
    все ставки здесь рассчитаны по модели, а не скопированы из котировок.
    """
    tenors = STANDARD_TENORS_MONTHS if target_tenors is None else target_tenors
    min_obs, max_obs = min(MOEX_OBSERVED_TENORS_MONTHS), max(MOEX_OBSERVED_TENORS_MONTHS)
    points = []
    for tenor in tenors:
        t = nonnegative_number(tenor, "tenor_months") / 12.0
        points.append({
            "tenor_months": tenor,
            "rate": moex_rate(t, params),
            "point_type": _classify_point_type(tenor, min_obs, max_obs),
        })
    return points


def _classify_point_type(tenor_months: int, min_obs: int, max_obs: int) -> str:
    if tenor_months in MOEX_OBSERVED_TENORS_MONTHS:
        return "observed"
    if tenor_months < min_obs or tenor_months > max_obs:
        return "extrapolated"
    return "interpolated"
