"""
Загрузка кривой MOEX и расчёт базовой и сдвинутых кривых.
Единый конвейер для DAG, воркера и демо-скрипта.
"""
from sqlalchemy.orm import Session

from db.models import CurveSnapshot
from db.repositories import curve_repo, scenario_repo
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift
from domain.moex.client import fetch_curve_from_moex


def load_curve(session: Session) -> CurveSnapshot:
    """Скачать параметры MOEX и создать снимок."""
    params = fetch_curve_from_moex()
    trade_date = params.pop("trade_date")
    return curve_repo.create_snapshot(session, trade_date=trade_date, params=params)


def build_curves(session: Session, snapshot: CurveSnapshot) -> dict[str, int]:
    """
    Построить кривые снимка, заменив уже посчитанные точки.
    Статус built ставится после сохранения всех сценариев, при ошибке — failed.
    Возвращает {код сценария: число сдвинутых точек}.
    """
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

    curve_repo.delete_curve_points(session, snapshot.id)
    curve_repo.save_base_points(session, snapshot.id, base_points)

    scenario_repo.ensure_default_scenarios(session)
    saved = {}
    for scenario in scenario_repo.list_scenarios(session, only_active=True):
        shift_map = scenario_repo.get_shift_map(session, scenario.id)
        shifted = apply_shift(base_points, shift_map)
        curve_repo.save_shifted_points(session, snapshot.id, scenario.id, shifted)
        saved[scenario.code] = len(shifted)

    return saved
