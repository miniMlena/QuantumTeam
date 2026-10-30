"""
Применение сценариев сдвига к базовой кривой.
"""


def apply_shift(
    base_points: list[dict], shift_map: dict[float, float]
) -> list[dict]:
    """
    base_points: [{"bucket_code": str, "tenor_years": float, "rate": float}, ...]
    shift_map:   {tenor_years: shift_bp}  — сдвиг в базисных пунктах

    Возвращает список сдвинутых точек:
      [{"bucket_code": str, "tenor_years": float,
        "shifted_rate": float, "shift_bp": float}, ...]
    """
    shifted = []
    for p in base_points:
        tenor = p["tenor_years"]
        shift = _interpolate_shift(tenor, shift_map)
        # shift_bp в доли: 1 б.п. = 0.0001
        new_rate = p["rate"] + shift / 10_000.0
        shifted.append({
            "bucket_code": p["bucket_code"],
            "tenor_years": tenor,
            "shifted_rate": new_rate,
            "shift_bp": shift,
        })
    return shifted


def _interpolate_shift(tenor_years: float, shift_map: dict[float, float]) -> float:
    """
    Если для тенора нет явного сдвига в сценарии, линейно интерполируем
    между ближайшими известными тенорами. За границами берём крайнее значение.
    """
    if not shift_map:
        return 0.0
    if tenor_years in shift_map:
        return shift_map[tenor_years]

    tenors = sorted(shift_map)
    if tenor_years <= tenors[0]:
        return shift_map[tenors[0]]
    if tenor_years >= tenors[-1]:
        return shift_map[tenors[-1]]

    for i in range(len(tenors) - 1):
        t_left, t_right = tenors[i], tenors[i + 1]
        if t_left < tenor_years < t_right:
            w = (tenor_years - t_left) / (t_right - t_left)
            return shift_map[t_left] * (1 - w) + shift_map[t_right] * w
    return 0.0
