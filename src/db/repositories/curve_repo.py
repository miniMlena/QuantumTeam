from datetime import date
from decimal import Decimal
from sqlalchemy import select, desc, delete
from sqlalchemy.orm import Session
from db.models import (
    CurveSnapshot, BaseCurvePoint, ShiftedCurvePoint,
)


def create_snapshot(session: Session, *, trade_date: date, params: dict) -> CurveSnapshot:
    """params: {b1,b2,b3,t1,g1..g9}"""
    snap = session.scalar(select(CurveSnapshot).where(
        CurveSnapshot.trade_date == trade_date,
        CurveSnapshot.source == "moex_iss",
    ))
    if snap is None:
        snap = CurveSnapshot(trade_date=trade_date, **params)
    else:
        for name, value in params.items():
            setattr(snap, name, value)
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
        .order_by(desc(CurveSnapshot.fetched_at))
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


def save_base_points(
    session: Session,
    snapshot_id: int,
    points: list[dict], # [{tenor_months, rate, point_type}]
) -> None:
    session.execute(delete(BaseCurvePoint).where(
        BaseCurvePoint.snapshot_id == snapshot_id
    ))
    session.add_all([
        BaseCurvePoint(
            snapshot_id=snapshot_id,
            tenor_months=p["tenor_months"],
            rate=Decimal(str(p["rate"])),
            point_type=p["point_type"],
        )
        for p in points
    ])
    session.commit()


def save_shifted_points(
    session: Session,
    snapshot_id: int,
    scenario_id: int,
    points: list[dict], # [{tenor_months, shifted_rate, shift_bp, point_type}]
) -> None:
    session.execute(delete(ShiftedCurvePoint).where(
        ShiftedCurvePoint.snapshot_id == snapshot_id,
        ShiftedCurvePoint.scenario_id == scenario_id,
    ))
    session.add_all([
        ShiftedCurvePoint(
            snapshot_id=snapshot_id,
            scenario_id=scenario_id,
            tenor_months=p["tenor_months"],
            shifted_rate=Decimal(str(p["shifted_rate"])),
            shift_bp=Decimal(str(p["shift_bp"])),
            point_type=p["point_type"],
        )
        for p in points
    ])
    session.commit()


def get_base_points(session: Session, snapshot_id: int) -> list[BaseCurvePoint]:
    return list(session.scalars(
        select(BaseCurvePoint)
        .where(BaseCurvePoint.snapshot_id == snapshot_id)
        .order_by(BaseCurvePoint.tenor_months)
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
        .order_by(ShiftedCurvePoint.tenor_months)
    ))