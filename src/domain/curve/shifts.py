"""Применение пользовательских и стандартных сдвигов к непрерывным ставкам."""
from domain.curve.interpolation import _linear_at
from domain.curve.scenarios import build_irrbb_shift_map
from domain.curve.validation import finite_number, nonnegative_number


def apply_shift(
    base_points: list[dict], shift_map: dict[int, float],
    rate_floor: float | None = None,
) -> list[dict]:
    """Сдвиги в б.п., ставки в долях. Между узлами — линейно, вне — крайний сдвиг.

    Ограничение ставки снизу применяется только при явном rate_floor.
    shift_bp в результате — фактически применённый сдвиг после ограничения.
    """
    if rate_floor is not None:
        rate_floor = finite_number(rate_floor, "rate_floor")
    nodes = sorted(
        (nonnegative_number(t, "shift tenor"), finite_number(s, "shift_bp"))
        for t, s in shift_map.items()
    )
    xs = [t for t, _ in nodes]
    ys = [s for _, s in nodes]
    shifted = []
    for point in base_points:
        tenor = nonnegative_number(point["tenor_months"], "tenor_months")
        rate = finite_number(point["rate"], "rate")
        shift = 0.0 if not nodes else (
            ys[0] if tenor <= xs[0] else ys[-1] if tenor >= xs[-1]
            else _linear_at(tenor, xs, ys)
        )
        new_rate = finite_number(rate + shift / 10_000.0, "shifted_rate")
        if rate_floor is not None:
            new_rate = max(rate_floor, new_rate)
            shift = (new_rate - rate) * 10_000.0
        shifted.append({
            "tenor_months": point["tenor_months"],
            "shifted_rate": new_rate, "shift_bp": shift,
            "point_type": point["point_type"],
        })
    return shifted


def _interpolate_shift(tenor_months: int, shift_map: dict[int, float]) -> float:
    if not shift_map:
        return 0.0
    xs = sorted(shift_map)
    if tenor_months <= xs[0]:
        return float(shift_map[xs[0]])
    if tenor_months >= xs[-1]:
        return float(shift_map[xs[-1]])
    return _linear_at(tenor_months, xs, [float(shift_map[t]) for t in xs])


def apply_irrbb_scenario(
    base_points: list[dict], scenario: str, currency: str = "RUB",
    rate_floor: float | None = None,
    shock_sizes: tuple[float, float, float] | None = None,
) -> list[dict]:
    """Вычислить формулу IRRBB на каждом сроке без интерполяции формы шока."""
    tenors = [point["tenor_months"] for point in base_points]
    shifts = build_irrbb_shift_map(scenario, currency, tenors, shock_sizes)
    return apply_shift(base_points, shifts, rate_floor)
