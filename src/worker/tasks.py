from db.engine import SessionLocal
from db.repositories import curve_repo
from services.curve_pipeline import build_curves, load_curve


def rebuild_snapshot(snapshot_id: int) -> dict:
    """Пересчитать базовую и сдвинутые кривые для существующего снимка"""
    with SessionLocal() as session:
        snap = curve_repo.get_snapshot(session, snapshot_id)
        if snap is None:
            return {"status": "failed", "reason": "snapshot not found"}
        build_curves(session, snap)
        return {"status": "ok", "snapshot_id": snapshot_id}


def fetch_and_build_today() -> dict:
    """Скачать свежую кривую и построить всё (on-demand)"""
    with SessionLocal() as session:
        snap = load_curve(session)
        build_curves(session, snap)
        return {"status": "ok", "snapshot_id": snap.id}
