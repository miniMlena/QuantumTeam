"""Быстрая проверка расчётов без PostgreSQL, Redis и Airflow."""
import argparse
import json

from domain.curve.builder import build_base_curve
from domain.curve.scenarios import SCENARIOS
from domain.curve.shifts import apply_irrbb_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Загрузить параметры MOEX")
    args = parser.parse_args()
    # Плоская непрерывная ставка 10%, исходные параметры в б.п.
    params = {"b1": 1000, "b2": 0, "b3": 0, "t1": 1}
    if args.live:
        from domain.moex.client import fetch_curve_from_moex
        params = fetch_curve_from_moex()
    base = build_base_curve(params)
    print(json.dumps({
        "rate_basis": "continuous_decimal",
        "params": params,
        "base": base,
        "scenarios": {s: apply_irrbb_scenario(base, s) for s in SCENARIOS},
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
