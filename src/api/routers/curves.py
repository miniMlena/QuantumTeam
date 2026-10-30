from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.curve import CurvePointOut, ShiftedPointOut, SnapshotOut
from db.repositories import curve_repo, scenario_repo
from services.curve_pipeline import build_curves, load_curve

router = APIRouter(prefix="/curves", tags=["curves"])


@router.post("/calculate", response_model=SnapshotOut)
def calculate(db: Session = Depends(get_db)):
    """Загрузить свежую кривую MOEX и рассчитать все сценарии."""
    try:
        snap = load_curve(db)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Не удалось получить данные MOEX. Попробуйте позже."
        ) from exc
    build_curves(db, snap)
    return snap


@router.get("/latest", response_model=SnapshotOut)
def get_latest(db: Session = Depends(get_db)):
    snap = curve_repo.get_latest_snapshot(db)
    if snap is None:
        raise HTTPException(status_code=404, detail="No snapshots yet")
    return snap


@router.get("/{snapshot_id}/base", response_model=list[CurvePointOut])
def get_base(snapshot_id: int, db: Session = Depends(get_db)):
    if curve_repo.get_snapshot(db, snapshot_id) is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return curve_repo.get_base_points(db, snapshot_id)


@router.get(
    "/{snapshot_id}/scenarios/{scenario_id}",
    response_model=list[ShiftedPointOut],
)
def get_shifted(
    snapshot_id: int, scenario_id: int, db: Session = Depends(get_db)
):
    if curve_repo.get_snapshot(db, snapshot_id) is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if scenario_repo.get_scenario(db, scenario_id) is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return curve_repo.get_shifted_points(db, snapshot_id, scenario_id)