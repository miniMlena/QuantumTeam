from datetime import date
from pydantic import BaseModel


class ScenarioResultOut(BaseModel):
    code: str
    name: str
    scenario_type: str
    npv: float
    delta_npv: float
    nii: float
    delta_nii: float


class EconomicCapitalOut(BaseModel):
    scenario_code: str
    scenario_name: str
    value: float           # минимальное ΔNPV среди сценариев


class ResultsOut(BaseModel):
    snapshot_id: int
    trade_date: date
    base_npv: float
    base_nii: float
    scenarios: list[ScenarioResultOut]
    economic_capital: EconomicCapitalOut | None
