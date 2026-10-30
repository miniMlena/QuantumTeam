"""Шесть сценариев из 8-МР (2020), глава 3, и IRRBB (2016), Annex 2.

Калибровка ниже взята именно из приложенного 8-МР, таблица 3.
Это не автоматическое обновление действующих регуляторных требований.
"""
import math

from domain.constants import STANDARD_TENORS_MONTHS
from domain.curve.validation import finite_number, nonnegative_number

SCENARIOS = (
    "parallel_up", "parallel_down", "steepener",
    "flattener", "short_up", "short_down",
)

# Параллельный / короткий / длинный шок, базисные пункты.
SHOCK_SIZES_BP = {
    "ARS": (400, 500, 300), "AUD": (300, 450, 200),
    "BRL": (400, 500, 300), "CAD": (200, 300, 150),
    "CHF": (100, 150, 100), "CNY": (250, 300, 150),
    "EUR": (200, 250, 100), "GBP": (250, 300, 150),
    "HKD": (200, 250, 100), "IDR": (400, 500, 350),
    "INR": (400, 500, 350), "JPY": (100, 100, 100),
    "KRW": (300, 400, 200), "MXN": (400, 500, 300),
    "RUB": (400, 500, 300), "SAR": (200, 300, 150),
    "SEK": (200, 300, 150), "SGD": (150, 200, 100),
    "TRY": (400, 500, 300), "USD": (200, 300, 150),
    "ZAR": (400, 500, 300), "OTHER": (400, 500, 300),
}


def irrbb_shift_bp(
    tenor_years: float, scenario: str, currency: str = "RUB",
    shock_sizes: tuple[float, float, float] | None = None,
) -> float:
    """Сдвиг на сроке в годах, в б.п. Пользовательские размеры — неотрицательные."""
    t = nonnegative_number(tenor_years, "tenor_years")
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown IRRBB scenario: {scenario}")
    if shock_sizes is None:
        currency = currency.upper()
        if currency not in SHOCK_SIZES_BP:
            raise ValueError("Unknown currency; use OTHER or specify shock_sizes")
        shock_sizes = SHOCK_SIZES_BP[currency]
    if len(shock_sizes) != 3:
        raise ValueError("shock_sizes must contain parallel, short and long shocks")
    parallel, short, long = (
        nonnegative_number(v, "shock_size_bp") for v in shock_sizes
    )
    short_part = short * math.exp(-t / 4.0)
    long_part = long * -math.expm1(-t / 4.0)
    shifts = {
        "parallel_up": parallel,
        "parallel_down": -parallel,
        "short_up": short_part,
        "short_down": -short_part,
        "steepener": -0.65 * short_part + 0.9 * long_part,
        "flattener": 0.8 * short_part - 0.6 * long_part,
    }
    return finite_number(shifts[scenario], "shift_bp")


def build_irrbb_shift_map(
    scenario: str, currency: str = "RUB", target_tenors: list[int] | None = None,
    shock_sizes: tuple[float, float, float] | None = None,
) -> dict[int, float]:
    """Рассчитать сценарий точно в каждом узле заданной сетки (месяцы)."""
    tenors = STANDARD_TENORS_MONTHS if target_tenors is None else target_tenors
    return {
        t: irrbb_shift_bp(nonnegative_number(t, "tenor_months") / 12.0,
                          scenario, currency, shock_sizes)
        for t in tenors
    }


def default_scenarios(currency: str = "RUB") -> list[dict]:
    """Описание сценариев в формате существующего репозитория БД."""
    currency = currency.upper()
    return [{
        "code": f"irrbb_{currency.lower()}_{code}",
        "name": f"IRRBB {currency} {code}",
        "scenario_type": code,
        "is_regulatory": True,
        "description": "8-МР 2020, глава 3 и таблица 3; IRRBB 2016, Annex 2",
        "shifts": [{"tenor_months": tenor, "shift_bp": shift}
                   for tenor, shift in build_irrbb_shift_map(code, currency).items()],
    } for code in SCENARIOS]
