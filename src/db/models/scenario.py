from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.models.base import Base


class Scenario(Base):
    __tablename__ = "scenario"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_regulatory: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)

    shifts: Mapped[list["ScenarioShift"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class ScenarioShift(Base):
    __tablename__ = "scenario_shift"
    __table_args__ = (UniqueConstraint("scenario_id", "tenor_years"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False
    )
    tenor_years: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    shift_bp: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)

    scenario: Mapped[Scenario] = relationship(back_populates="shifts")