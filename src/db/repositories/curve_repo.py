from datetime import date
from decimal import Decimal
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from db.models import (
    CurveSnapshot, BaseCurvePoint, ShiftedCurvePoint, TermCurvePoint,
)


SNAPSHOT_SOURCE = "moex_iss"


def create_snapshot(session: Session, *, trade_date: date, params: dict) -> CurveSnapshot:
    """
    params: {b1,b2,b3,t1,g1..g9}
    Каждый импорт создаёт новую версию, включая повторный импорт за ту же дату.
    """
    snap = CurveSnapshot(trade_date=trade_date, source=SNAPSHOT_SOURCE, **params)
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
        .order_by(desc(CurveSnapshot.trade_date), desc(CurveSnapshot.id))
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


def copy_snapshot(session: Session, snapshot: CurveSnapshot) -> CurveSnapshot:
    """Новый снимок для пересчёта; исходные параметры и результаты не меняются."""
    params = {name: getattr(snapshot, name) for name in (
        "b1", "b2", "b3", "t1", *(f"g{i}" for i in range(1, 10))
    )}
    return create_snapshot(session, trade_date=snapshot.trade_date, params=params)


def list_snapshots(session: Session, limit: int = 100, offset: int = 0):
    return list(session.scalars(select(CurveSnapshot).order_by(
        desc(CurveSnapshot.trade_date), desc(CurveSnapshot.id)
    ).limit(limit).offset(offset)))


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
    session.flush()


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
    session.flush()


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


def save_term_points(session: Session, snapshot_id: int, scenario_code: str, points: list[dict]):
    session.add_all([TermCurvePoint(
        snapshot_id=snapshot_id, scenario_code=scenario_code,
        tenor_years=Decimal(str(p["tenor_years"])),
        rate=Decimal(str(p["rate"])), shift_bp=Decimal(str(p["shift_bp"])),
    ) for p in points])
    session.flush()


def get_term_points(session: Session, snapshot_id: int, scenario_code: str):
    return list(session.scalars(select(TermCurvePoint).where(
        TermCurvePoint.snapshot_id == snapshot_id,
        TermCurvePoint.scenario_code == scenario_code,
    ).order_by(TermCurvePoint.tenor_years)))


def get_term_scenario_codes(session: Session, snapshot_id: int):
    return list(session.scalars(select(TermCurvePoint.scenario_code).where(
        TermCurvePoint.snapshot_id == snapshot_id
    ).distinct().order_by(TermCurvePoint.scenario_code)))
