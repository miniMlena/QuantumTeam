"""Кривые на фактических сроках до 30 лет, отдельно от середины бакетов."""
from domain.constants import BUCKETS, OPEN_BUCKET_RATE_YEARS
from domain.curve.builder import annual_rate_pct
from domain.curve.scenarios import BASEL_SHIFTS, basel_shift_bp
from domain.curve.shifts import _interpolate_shift

TERM_TENORS = tuple(
    b.end_years if b.end_years is not None else OPEN_BUCKET_RATE_YEARS
    for b in BUCKETS
)


def build_term_curve(params: dict, *, code: str = "base", regulatory: bool = False,
                     shift_map: dict[float, float] | None = None) -> list[dict]:
    points = []
    for tenor in TERM_TENORS:
        if code == "base":
            shift = 0.0
        elif regulatory and code in BASEL_SHIFTS:
            shift = basel_shift_bp(code, tenor)
        else:
            shift = _interpolate_shift(tenor, shift_map or {})
        points.append({
            "tenor_years": tenor,
            "rate": annual_rate_pct(tenor, params) + shift / 100.0,
            "shift_bp": shift,
        })
    return points
