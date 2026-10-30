from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.results import ResultsOut
from db.repositories import curve_repo, portfolio_repo, scenario_repo
from domain.valuation import calculate_all_scenarios, find_economic_capital

router = APIRouter(prefix="/results", tags=["results"])


@router.get("", response_model=ResultsOut)
def get_results(snapshot_id: int | None = None, db: Session = Depends(get_db)):
    """NPV и NII по каждому сценарию и ЭКпрбк (минимальное ΔNPV)."""
    if snapshot_id is None:
        snapshot = curve_repo.get_latest_snapshot(db)
    else:
        snapshot = curve_repo.get_snapshot(db, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    positions = portfolio_repo.list_positions(db)
    if not positions:
        raise HTTPException(status_code=404, detail="Portfolio is empty")

    base_rates = {
        point.bucket_code: float(point.rate)
        for point in curve_repo.get_base_points(db, snapshot.id)
    }
    if not base_rates:
        raise HTTPException(status_code=404, detail="Snapshot has no base curve")

    scenarios = []
    for scenario in scenario_repo.list_scenarios(db, only_active=True):
        points = curve_repo.get_shifted_points(db, snapshot.id, scenario.id)
        if points:
            scenarios.append({
                "code": scenario.code,
                "name": scenario.name,
                "scenario_type": scenario.scenario_type,
                "rates": {p.bucket_code: float(p.shifted_rate) for p in points},
            })

    results = calculate_all_scenarios(positions, base_rates, scenarios)
    return {
        "snapshot_id": snapshot.id,
        "trade_date": snapshot.trade_date,
        **results,
        "economic_capital": find_economic_capital(results["scenarios"]),
    }
