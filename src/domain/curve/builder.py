"""
Построение базовой кривой из параметров MOEX (G-кривая).
Формула и константы — по методике MOEX: Nelson-Siegel плюс 9 корректирующих
гауссовых членов G1..G9. Параметры заданы в базисных пунктах и дают ставку
с непрерывным начислением; на выходе — годовая ставка в процентах, как в
эталонном расчёте.
"""
import math
from domain.constants import BUCKETS, OPEN_BUCKET_RATE_YEARS, RATE_POINT, Bucket

G_TERMS_COUNT = 9
G_K = 1.6
G_A2 = 0.6


def _g_term_constants() -> tuple[list[float], list[float]]:
    """Константы G-членов: a1=0, a2=0.6, a(i+1)=a(i)+a2*k^(i-1); b1=a2, b(i+1)=b(i)*k."""
    a = [0.0, G_A2]
    for i in range(2, G_TERMS_COUNT):
        a.append(a[-1] + G_A2 * G_K ** (i - 1))
    b = [G_A2 * G_K ** i for i in range(G_TERMS_COUNT)]
    return a, b


G_A, G_B = _g_term_constants()


def g_curve_bp(tenor_years: float, params: dict) -> float:
    """
    G-кривая MOEX: ставка с непрерывным начислением в базисных пунктах.
      G(t) = b1 + (b2 + b3) * (t1 / t) * (1 - exp(-t/t1)) - b3 * exp(-t/t1)
                + сумма gi * exp(-(t - ai)^2 / bi^2)
    params: {b1, b2, b3, t1, g1..g9}; отсутствующие gi считаются нулевыми.
    tenor_years должен быть больше нуля.
    """
    b1, b2, b3, t1 = (float(params[name]) for name in ("b1", "b2", "b3", "t1"))

    x = tenor_years / t1
    exp_neg = math.exp(-x)
    rate = b1 + (b2 + b3) * (1 - exp_neg) / x - b3 * exp_neg

    for i in range(G_TERMS_COUNT):
        g = float(params.get(f"g{i + 1}") or 0.0)
        rate += g * math.exp(-((tenor_years - G_A[i]) ** 2) / G_B[i] ** 2)
    return rate


def annual_rate_pct(tenor_years: float, params: dict) -> float:
    """Годовая ставка в процентах: Y = exp(G / 10000) - 1."""
    return (math.exp(g_curve_bp(tenor_years, params) / 10_000.0) - 1) * 100.0


def rate_tenor_years(bucket: Bucket) -> float:
    """Срок, на который берётся ставка бакета, — см. RATE_POINT."""
    if RATE_POINT == "mid":
        return bucket.tenor_years
    return bucket.end_years if bucket.end_years is not None else OPEN_BUCKET_RATE_YEARS


def build_base_curve(params: dict) -> list[dict]:
    """
    params: {b1, b2, b3, t1, g1..g9}
    Возвращает по точке на каждый бакет:
      [{"bucket_code": str, "tenor_years": float, "rate": float}, ...]
    rate — годовая ставка в процентах (13.27 значит 13.27%),
    tenor_years — срок дисконтирования (середина бакета).
    """
    return [
        {
            "bucket_code": bucket.code,
            "tenor_years": bucket.tenor_years,
            "rate": annual_rate_pct(rate_tenor_years(bucket), params),
        }
        for bucket in BUCKETS
    ]
