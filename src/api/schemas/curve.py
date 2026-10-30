from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class CurvePointOut(BaseModel):
    bucket_code: str
    tenor_years: Decimal
    rate: Decimal


class ShiftedPointOut(BaseModel):
    bucket_code: str
    tenor_years: Decimal
    shifted_rate: Decimal
    shift_bp: Decimal


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trade_date: date
    fetched_at: datetime
    status: str