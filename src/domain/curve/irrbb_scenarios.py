"""
Шесть стандартных сценариев IRRBB (Basel, BCBS d368).
Параметры для рубля по умолчанию: parallel=400, short=500, long=300 б.п.
(именно они воспроизводят непараллельный сдвиг из Excel-эталона).
"""
import math

IRRBB_SCENARIOS = [
    # (code, name, scenario_type)
    ("parallel_up", "Параллельный сдвиг вверх", "parallel"),
    ("parallel_down", "Параллельный сдвиг вниз", "parallel"),
    ("short_up", "Рост краткосрочных ставок", "short_rate"),
    ("short_down", "Снижение краткосрочных ставок", "short_rate"),
    ("steepener", "Увеличение наклона (steepener)", "twist"),
    ("flattener", "Уменьшение наклона (flattener)", "twist"),
]


def shift_bp_at(code, years, parallel=400, short=500, long=300):
    """Сдвиг в б.п. для тенора `years` (в годах) по формулам BCBS."""
    short_weight = math.exp(-years / 4)   # 1 в начале кривой, 0 на длинном конце
    long_weight = 1 - short_weight

    if code == "parallel_up":
        return parallel
    if code == "parallel_down":
        return -parallel
    if code == "short_up":
        return short * short_weight
    if code == "short_down":
        return -short * short_weight
    if code == "steepener":
        return -0.65 * short * short_weight + 0.9 * long * long_weight
    if code == "flattener":
        return 0.8 * short * short_weight - 0.6 * long * long_weight
    raise ValueError(f"Unknown scenario code: {code}")


def build_shifts(code, max_tenor_months=360, **params):
    """Сдвиги по каждому месяцу 1..360 в формате для scenario_repo.create_scenario."""
    return [
        {
            "tenor_months": months,
            "shift_bp": round(shift_bp_at(code, months / 12, **params), 4),
        }
        for months in range(1, max_tenor_months + 1)
    ]
