from datetime import date, datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator


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

    @field_validator("fetched_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite в тестах теряет tzinfo; PostgreSQL TIMESTAMPTZ его сохраняет.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class TermPointOut(BaseModel):
    tenor_years: Decimal
    rate: Decimal
    shift_bp: Decimal
