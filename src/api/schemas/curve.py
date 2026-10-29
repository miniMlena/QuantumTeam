from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class CurvePointOut(BaseModel):
    tenor_months: int
    rate: Decimal
    point_type: str


class ShiftedPointOut(BaseModel):
    tenor_months: int
    shifted_rate: Decimal
    shift_bp: Decimal
    point_type: str


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trade_date: date
    fetched_at: datetime
    status: str