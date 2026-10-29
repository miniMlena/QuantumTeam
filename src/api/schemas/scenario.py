from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class ScenarioShiftIn(BaseModel):
    tenor_months: int
    shift_bp: Decimal


class ScenarioCreate(BaseModel):
    code: str
    name: str
    scenario_type: str
    is_regulatory: bool = False
    description: str | None = None
    shifts: list[ScenarioShiftIn]


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    scenario_type: str
    is_regulatory: bool
    is_active: bool