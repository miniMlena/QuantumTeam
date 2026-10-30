from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.curve import CurvePointOut, ShiftedPointOut, SnapshotOut
from db.repositories import curve_repo, scenario_repo
from redis import Redis
from rq import Queue
from worker.tasks import rebuild_snapshot

router = APIRouter(prefix="/curves", tags=["curves"])


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


redis_conn = Redis(host="redis", port=6379)
queue = Queue("curves", connection=redis_conn)


@router.post("/{snapshot_id}/rebuild", status_code=202)
def trigger_rebuild(snapshot_id: int):
    job = queue.enqueue(rebuild_snapshot, snapshot_id, job_timeout="10m")
    return {"task_id": job.id, "status": "queued"}