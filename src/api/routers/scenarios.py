from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.scenario import ScenarioCreate, ScenarioOut
from db.repositories import scenario_repo

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioOut])
def list_scenarios(only_active: bool = True, db: Session = Depends(get_db)):
    return scenario_repo.list_scenarios(db, only_active)


@router.get("/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    sc = scenario_repo.get_scenario(db, scenario_id)
    if sc is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return sc


@router.post("", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)):
    if scenario_repo.get_scenario_by_code(db, payload.code):
        raise HTTPException(status_code=409, detail="Scenario code exists")
    return scenario_repo.create_scenario(
        db,
        code=payload.code,
        name=payload.name,
        scenario_type=payload.scenario_type,
        is_regulatory=payload.is_regulatory,
        description=payload.description,
        shifts=[s.model_dump() for s in payload.shifts],
    )