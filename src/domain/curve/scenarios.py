"""
Стандартные сценарии Basel IRRBB для рубля.
Сдвиги считаются по формулам на середине каждого бакета и сохраняются
в scenario_shift как обычные табличные сценарии.
"""
import math
from domain.constants import BUCKETS

# Размеры шоков для RUB, базисные пункты
PARALLEL_SHOCK_BP = 400.0
SHORT_SHOCK_BP = 500.0
LONG_SHOCK_BP = 300.0

# Скорость затухания короткого шока, лет
DECAY_YEARS = 4.0


def _short_weight(tenor_years: float) -> float:
    return math.exp(-tenor_years / DECAY_YEARS)


def _short_shift(tenor_years: float) -> float:
    return SHORT_SHOCK_BP * _short_weight(tenor_years)


def _long_shift(tenor_years: float) -> float:
    return LONG_SHOCK_BP * (1 - _short_weight(tenor_years))


BASEL_SHIFTS = {
    "parallel_up": lambda t: PARALLEL_SHOCK_BP,
    "parallel_down": lambda t: -PARALLEL_SHOCK_BP,
    "short_up": _short_shift,
    "short_down": lambda t: -_short_shift(t),
    "steepener": lambda t: -0.65 * _short_shift(t) + 0.9 * _long_shift(t),
    "flattener": lambda t: 0.8 * _short_shift(t) - 0.6 * _long_shift(t),
}


def basel_shift_bp(code: str, tenor_years: float) -> float:
    """Сдвиг сценария на сроке tenor_years, базисные пункты."""
    return BASEL_SHIFTS[code](tenor_years)


def default_scenarios() -> list[dict]:
    """Шесть сценариев Basel в формате scenario_repo.create_scenario."""
    return [
        {
            "code": code,
            "name": f"Basel RUB {code}",
            "scenario_type": "parallel" if code.startswith("parallel") else "non_parallel",
            "is_regulatory": True,
            "description": None,
            "shifts": [
                {"tenor_years": bucket.tenor_years,
                 "shift_bp": basel_shift_bp(code, bucket.tenor_years)}
                for bucket in BUCKETS
            ],
        }
        for code in BASEL_SHIFTS
    ]
