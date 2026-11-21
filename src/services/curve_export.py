import csv
import io
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from db.repositories import curve_repo, scenario_repo


def _csv_text(header: list[str], rows: list[list]) -> str:
    """Сформировать CSV в UTF-8."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def _get_snapshot(session: Session, snapshot_id: int):
    snapshot = curve_repo.get_snapshot(session, snapshot_id)

    if snapshot is None:
        raise ValueError("Snapshot not found")

    if snapshot.status != "built":
        raise ValueError(
            "Snapshot is not built yet"
        )

    return snapshot


def _get_curves(session: Session, snapshot_id: int):
    """Получить базовую кривую и рассчитанные сценарии."""
    snapshot = _get_snapshot(session, snapshot_id)

    base = curve_repo.get_base_points(session, snapshot_id)
    if not base:
        raise ValueError("Base curve has no points")

    scenarios = {}

    for scenario in scenario_repo.list_scenarios(
        session, only_active=True
    ):
        points = curve_repo.get_shifted_points(
            session, snapshot_id, scenario.id
        )
        if points:
            scenarios[scenario.code] = points

    return snapshot, base, scenarios


def export_moex_curves(
    session: Session, snapshot_id: int
) -> str:
    """
    Экспорт реальных точек MOEX.

    Ставки переводятся из процентов в доли единицы.
    Ось X остаётся tenor_years: это НЕ прогноз CBKEY1M.
    """
    snapshot, base, scenarios = _get_curves(
        session, snapshot_id
    )

    rows = []

    for point in base:
        rows.append([
            snapshot.trade_date.isoformat(),
            "base",
            point.bucket_code,
            point.tenor_years,
            point.rate / Decimal("100"),
        ])

    for code, points in sorted(scenarios.items()):
        for point in points:
            rows.append([
                snapshot.trade_date.isoformat(),
                code,
                point.bucket_code,
                point.tenor_years,
                point.shifted_rate / Decimal("100"),
            ])

    return _csv_text(
        [
            "trade_date",
            "scenario",
            "bucket_code",
            "tenor_years",
            "rate",
        ],
        rows,
    )


def _add_months(start: date, months: int) -> date:
    """Прибавить месяцы с корректной обработкой конца месяца."""
    total = start.year * 12 + start.month - 1 + months
    year, month_zero = divmod(total, 12)
    month = month_zero + 1
    day = min(
        start.day,
        calendar.monthrange(year, month)[1]
    )
    return date(year, month, day)


def _demo_indicator_rate(
    base_points,
    scenario_points,
    tenor_years: float,
) -> Decimal:
    """
    ВРЕМЕННАЯ ЗАГЛУШКА — ТОЛЬКО ДЛЯ ДЕМОНСТРАЦИИ!

    TODO: согласовать с командами методику построения
    прогноза CBKEY1M из рыночных данных.

    Сейчас:
    1. Берём условную базовую ставку 10%.
    2. Находим ближайший тенор G-кривой MOEX.
    3. Применяем к условной ставке только величину
       стрессового сдвига на этом теноре.

    Это НЕ реальный прогноз ключевой ставки ЦБ!
    Не использовать для финансовых расчётов NII/NPV.
    """
    demo_anchor = Decimal("0.10")

    base_by_bucket = {
        p.bucket_code: p for p in base_points
    }

    nearest = min(
        scenario_points,
        key=lambda p: abs(
            float(p.tenor_years) - tenor_years
        ),
    )

    base_point = base_by_bucket[nearest.bucket_code]

    # Ставки в БД выражены в процентах.
    shift_decimal = (
        nearest.shifted_rate - base_point.rate
    ) / Decimal("100")

    return demo_anchor + shift_decimal


def export_calculator_demo(
    session: Session,
    snapshot_id: int,
    months: int = 12,
) -> str:
    """
    ДЕМОНСТРАЦИОННЫЙ экспорт в контракт калькулятора.

    Формат: indicator,date,rate,scenario

    TODO: заменить _demo_indicator_rate() на согласованную
    методику прогнозирования индикатора.

    Важно: CSV технически совместим с калькулятором,
    но значения пока не предназначены для расчёта рисков.
    """
    if not 1 <= months <= 360:
        raise ValueError("months must be between 1 and 360")

    snapshot, base, scenarios = _get_curves(
        session, snapshot_id
    )

    rows = []
    indicator = "CBKEY1M"

    # Для демонстрации используем дату снимка MOEX.
    # TODO: согласовать report_date с датой расчёта
    # портфеля, передаваемого калькулятору.
    report_date = snapshot.trade_date

    # Условный базовый прогноз.
    # TODO: заменить на прогноз реального индикатора.
    for month in range(1, months + 1):
        forecast_date = _add_months(report_date, month)
        rows.append([
            indicator,
            forecast_date.isoformat(),
            Decimal("0.10"),
            "base",
        ])

    for code, points in sorted(scenarios.items()):
        for month in range(1, months + 1):
            forecast_date = _add_months(
                report_date, month
            )

            rate = _demo_indicator_rate(
                base,
                points,
                month / 12.0,
            )

            rows.append([
                indicator,
                forecast_date.isoformat(),
                rate,
                code,
            ])

    return _csv_text(
        ["indicator", "date", "rate", "scenario"],
        rows,
    )
