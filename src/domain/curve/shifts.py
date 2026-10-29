"""
Применение сценариев сдвига к базовой кривой.
"""
from domain.constants import STANDARD_TENORS_MONTHS


def apply_shift(
    base_points: list[dict], shift_map: dict[int, float]
) -> list[dict]:
    """
    base_points: [{"tenor_months": int, "rate": float, "point_type": str}, ...]
    shift_map:   {tenor_months: shift_bp}  — сдвиг в базисных пунктах

    Возвращает список сдвинутых точек:
      [{"tenor_months": int, "shifted_rate": float,
        "shift_bp": float, "point_type": str}, ...]

    point_type наследуется от базовой точки: сдвиг не меняет
    природу точки (интерполированная остаётся интерполированной).
    """
    shifted = []
    for p in base_points:
        tenor = p["tenor_months"]
        shift = _interpolate_shift(tenor, shift_map)
        # shift_bp в доли: 1 б.п. = 0.0001
        new_rate = p["rate"] + shift / 10_000.0
        shifted.append({
            "tenor_months": tenor,
            "shifted_rate": new_rate,
            "shift_bp": shift,
            "point_type": p["point_type"],
        })
    return shifted


def _interpolate_shift(tenor_months: int, shift_map: dict[int, float]) -> float:
    """
    Если для тенора нет явного сдвига в сценарии, линейно интерполируем
    между ближайшими известными тенорами. За границами берём крайнее значение.
    """
    if not shift_map:
        return 0.0
    if tenor_months in shift_map:
        return shift_map[tenor_months]

    tenors = sorted(shift_map)
    if tenor_months <= tenors[0]:
        return shift_map[tenors[0]]
    if tenor_months >= tenors[-1]:
        return shift_map[tenors[-1]]

    for i in range(len(tenors) - 1):
        t_left, t_right = tenors[i], tenors[i + 1]
        if t_left < tenor_months < t_right:
            w = (tenor_months - t_left) / (t_right - t_left)
            return shift_map[t_left] * (1 - w) + shift_map[t_right] * w
    return 0.0