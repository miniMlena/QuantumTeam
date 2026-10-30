from decimal import Decimal
from sqlalchemy import BigInteger, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from db.models.base import Base


class Position(Base):
    """Позиция портфеля банка: актив (сумма > 0) или пассив (сумма < 0)."""
    __tablename__ = "portfolio_position"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)   # % годовых
    maturity_months: Mapped[int] = mapped_column(Integer, nullable=False)
    repricing_months: Mapped[int] = mapped_column(Integer, nullable=False)  # через сколько месяцев пересмотр ставки
