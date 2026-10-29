from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Date, ForeignKey, Integer, Numeric, String, Text,
    TIMESTAMP, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.models.base import Base


class CurveSnapshot(Base):
    __tablename__ = "curve_snapshot"
    __table_args__ = (UniqueConstraint("trade_date", "source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="moex_iss")

    b1: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    b2: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    b3: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    t1: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)

    g1: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g2: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g3: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g4: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g5: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g6: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g7: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g8: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    g9: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    base_points: Mapped[list["BaseCurvePoint"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    shifted_points: Mapped[list["ShiftedCurvePoint"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class BaseCurvePoint(Base):
    __tablename__ = "base_curve_point"
    __table_args__ = (UniqueConstraint("snapshot_id", "tenor_months"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("curve_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    point_type: Mapped[str] = mapped_column(String(20), nullable=False)

    snapshot: Mapped[CurveSnapshot] = relationship(back_populates="base_points")


class ShiftedCurvePoint(Base):
    __tablename__ = "shifted_curve_point"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "scenario_id", "tenor_months"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("curve_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False
    )
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    shifted_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    shift_bp: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    point_type: Mapped[str] = mapped_column(String(20), nullable=False)

    snapshot: Mapped[CurveSnapshot] = relationship(back_populates="shifted_points")