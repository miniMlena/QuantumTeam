"""Линейная интерполяция ставок; за границами — продолжение крайнего отрезка."""
from bisect import bisect_left

from domain.constants import STANDARD_TENORS_MONTHS
from domain.curve.validation import finite_number, nonnegative_number


def interpolate_curve(
    known_points: list[dict], target_tenors: list[int] | None = None,
) -> list[dict]:
    targets = STANDARD_TENORS_MONTHS if target_tenors is None else target_tenors
    if not known_points:
        raise ValueError("known_points must not be empty")
    known = sorted(
        (nonnegative_number(p["tenor_months"], "tenor_months"),
         finite_number(p["rate"], "rate"))
        for p in known_points
    )
    xs, ys = map(list, zip(*known))
    if len(set(xs)) != len(xs):
        raise ValueError("Duplicate known tenors")
    result = []
    for tenor in targets:
        x = nonnegative_number(tenor, "tenor_months")
        kind = ("observed" if x in xs else
                "extrapolated" if x < xs[0] or x > xs[-1] else "interpolated")
        result.append({"tenor_months": tenor, "rate": _linear_at(x, xs, ys),
                       "point_type": kind})
    return result


def _linear_at(x: float, xs: list[float], ys: list[float]) -> float:
    if len(xs) == 1:
        return ys[0]
    right = min(max(bisect_left(xs, x), 1), len(xs) - 1)
    left = right - 1
    weight = (x - xs[left]) / (xs[right] - xs[left])
    return finite_number(ys[left] + weight * (ys[right] - ys[left]), "rate")
