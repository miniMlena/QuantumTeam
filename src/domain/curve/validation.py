"""Проверка числовых входных данных расчётов."""
import math


def finite_number(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def nonnegative_number(value, name: str) -> float:
    number = finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} must be nonnegative")
    return number
