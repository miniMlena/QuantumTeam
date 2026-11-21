"""
Загрузка кривой MOEX и расчёт базовой и сдвинутых кривых.
Единый конвейер для DAG, воркера и демо-скрипта.
"""
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models import CurveSnapshot
from db.repositories import curve_repo, scenario_repo
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift
from domain.curve.term_structure import build_term_curve
from domain.moex.client import fetch_curve_from_moex


def load_curve(session: Session, trade_date: date | None = None) -> CurveSnapshot:
    """Скачать параметры MOEX (свежие или за trade_date) и создать снимок."""
    params = fetch_curve_from_moex(trade_date)
    trade_date = params.pop("trade_date")
    return curve_repo.create_snapshot(session, trade_date=trade_date, params=params)


def build_curves(session: Session, snapshot: CurveSnapshot) -> dict[str, int]:
    """
    Построить новый снимок одной транзакцией. Готовые снимки неизменяемы.
    Статус built ставится после сохранения всех сценариев, при ошибке — failed.
    Возвращает {код сценария: число сдвинутых точек}.
    """
    scenario_repo.ensure_default_scenarios(session)
    snapshot = session.scalar(select(CurveSnapshot).where(
        CurveSnapshot.id == snapshot.id
    ).with_for_update().execution_options(populate_existing=True))
    if snapshot.status != "pending":
        raise ValueError("Snapshot already processed; create a new version for rebuild")
    try:
        saved = _save_curves(session, snapshot)
    except Exception as exc:
        session.rollback()
        curve_repo.mark_snapshot_status(session, snapshot.id, "failed", str(exc))
        raise
    curve_repo.mark_snapshot_status(session, snapshot.id, "built")
    return saved


def _save_curves(session: Session, snapshot: CurveSnapshot) -> dict[str, int]:
    params = {
        "b1": snapshot.b1, "b2": snapshot.b2, "b3": snapshot.b3, "t1": snapshot.t1,
        **{f"g{i}": getattr(snapshot, f"g{i}") for i in range(1, 10)},
    }
    base_points = build_base_curve(params)

    curve_repo.save_base_points(session, snapshot.id, base_points)
    curve_repo.save_term_points(session, snapshot.id, "base", build_term_curve(params))

    saved = {}
    for scenario in scenario_repo.list_scenarios(session, only_active=True):
        if scenario.code == "base":
            raise ValueError("Scenario code 'base' is reserved")
        shift_map = scenario_repo.get_shift_map(session, scenario.id)
        shifted = apply_shift(base_points, shift_map)
        curve_repo.save_shifted_points(session, snapshot.id, scenario.id, shifted)
        curve_repo.save_term_points(session, snapshot.id, scenario.code, build_term_curve(
            params, code=scenario.code, regulatory=scenario.is_regulatory, shift_map=shift_map,
        ))
        saved[scenario.code] = len(shifted)

    return saved
