from datetime import date
from decimal import Decimal
from sqlalchemy import delete, select, desc, func
from sqlalchemy.orm import Session
from db.models import (
    CurveSnapshot, BaseCurvePoint, ShiftedCurvePoint,
)


SNAPSHOT_SOURCE = "moex_iss"


def create_snapshot(session: Session, *, trade_date: date, params: dict) -> CurveSnapshot:
    """
    params: {b1,b2,b3,t1,g1..g9}
    Если снимок за эту дату уже есть, обновляет его и возвращает на расчёт.
    """
    snap = session.scalar(select(CurveSnapshot).where(
        CurveSnapshot.trade_date == trade_date,
        CurveSnapshot.source == SNAPSHOT_SOURCE,
    ))
    if snap is None:
        snap = CurveSnapshot(trade_date=trade_date, source=SNAPSHOT_SOURCE, **params)
    else:
        for name, value in params.items():
            setattr(snap, name, value)
        snap.fetched_at = func.now()
        snap.status = "pending"
        snap.error_message = None
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return snap


def get_snapshot(session: Session, snapshot_id: int) -> CurveSnapshot | None:
    return session.get(CurveSnapshot, snapshot_id)


def get_latest_snapshot(session: Session) -> CurveSnapshot | None:
    return session.scalar(
        select(CurveSnapshot)
        .where(CurveSnapshot.status == "built")
        .order_by(desc(CurveSnapshot.trade_date))
        .limit(1)
    )


def mark_snapshot_status(
    session: Session, snapshot_id: int, status: str, error: str | None = None
) -> None:
    snap = session.get(CurveSnapshot, snapshot_id)
    if snap is None:
        return
    snap.status = status
    snap.error_message = error
    session.commit()


def delete_curve_points(session: Session, snapshot_id: int) -> None:
    """Удалить рассчитанные точки снимка перед пересчётом."""
    session.execute(delete(BaseCurvePoint).where(BaseCurvePoint.snapshot_id == snapshot_id))
    session.execute(delete(ShiftedCurvePoint).where(ShiftedCurvePoint.snapshot_id == snapshot_id))
    session.commit()


def save_base_points(
    session: Session,
    snapshot_id: int,
    points: list[dict], # [{bucket_code, tenor_years, rate}]
) -> None:
    session.add_all([
        BaseCurvePoint(
            snapshot_id=snapshot_id,
            bucket_code=p["bucket_code"],
            tenor_years=Decimal(str(p["tenor_years"])),
            rate=Decimal(str(p["rate"])),
        )
        for p in points
    ])
    session.commit()


def save_shifted_points(
    session: Session,
    snapshot_id: int,
    scenario_id: int,
    points: list[dict], # [{bucket_code, tenor_years, shifted_rate, shift_bp}]
) -> None:
    session.add_all([
        ShiftedCurvePoint(
            snapshot_id=snapshot_id,
            scenario_id=scenario_id,
            bucket_code=p["bucket_code"],
            tenor_years=Decimal(str(p["tenor_years"])),
            shifted_rate=Decimal(str(p["shifted_rate"])),
            shift_bp=Decimal(str(p["shift_bp"])),
        )
        for p in points
    ])
    session.commit()


def get_base_points(session: Session, snapshot_id: int) -> list[BaseCurvePoint]:
    return list(session.scalars(
        select(BaseCurvePoint)
        .where(BaseCurvePoint.snapshot_id == snapshot_id)
        .order_by(BaseCurvePoint.tenor_years)
    ))


def get_shifted_points(
    session: Session, snapshot_id: int, scenario_id: int
) -> list[ShiftedCurvePoint]:
    return list(session.scalars(
        select(ShiftedCurvePoint)
        .where(
            ShiftedCurvePoint.snapshot_id == snapshot_id,
            ShiftedCurvePoint.scenario_id == scenario_id,
        )
        .order_by(ShiftedCurvePoint.tenor_years)
    ))