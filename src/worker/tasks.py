from datetime import date
from db.engine import SessionLocal
from db.repositories import scenario_repo, curve_repo
from domain.moex.client import fetch_curve_from_moex
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift


def rebuild_snapshot(snapshot_id: int) -> dict:
    """Пересчитать базовую и сдвинутые кривые для существующего снимка"""
    with SessionLocal() as session:
        snap = curve_repo.get_snapshot(session, snapshot_id)
        if snap is None:
            return {"status": "failed", "reason": "snapshot not found"}

        params = {
            "b1": snap.b1, "b2": snap.b2, "b3": snap.b3, "t1": snap.t1,
            **{f"g{i}": getattr(snap, f"g{i}") for i in range(1, 10)},
        }
        curve_repo.mark_snapshot_status(session, snapshot_id, "pending")
        base_points = build_base_curve(params)

        curve_repo.save_base_points(session, snapshot_id, base_points)

        scenario_repo.ensure_default_scenarios(session)
        scenarios = scenario_repo.list_scenarios(session, only_active=True)
        for sc in scenarios:
            shift_map = scenario_repo.get_shift_map(session, sc.id)
            shifted = apply_shift(base_points, shift_map)
            curve_repo.save_shifted_points(session, snapshot_id, sc.id, shifted)

        curve_repo.mark_snapshot_status(session, snapshot_id, "built")
        return {"status": "ok", "snapshot_id": snapshot_id}


def fetch_and_build_today() -> dict:
    """Скачать свежую кривую и построить всё (on-demand)"""
    with SessionLocal() as session:
        params = fetch_curve_from_moex()
        trade_date = params.pop("trade_date", date.today())
        snap = curve_repo.create_snapshot(
            session, trade_date=trade_date, params=params
        )
        curve_repo.mark_snapshot_status(session, snap.id, "pending")
    return rebuild_snapshot(snap.id)