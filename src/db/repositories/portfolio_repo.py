from sqlalchemy import select
from sqlalchemy.orm import Session
from db.models.portfolio import Position

# Тестовый портфель, суммы в млн руб.: актив "+", пассив "-"
DEMO_POSITIONS = (
    # name, amount, rate %, maturity_months, repricing_months
    ("Кредиты юрлицам (фикс)", 1000, 15.0, 60, 60),
    ("Ипотека", 800, 9.0, 120, 120),
    ("ОФЗ", 500, 12.0, 84, 84),
    ("Кредиты юрлицам (плавающая ставка)", 600, 17.0, 36, 3),
    ("Депозиты физлиц", -900, 12.0, 12, 12),
    ("Депозиты юрлиц", -500, 8.0, 6, 1),
    ("Выпущенные облигации", -400, 13.0, 36, 36),
    ("Межбанковские займы", -300, 15.0, 3, 3),
)


def list_positions(session: Session) -> list[Position]:
    return list(session.scalars(select(Position).order_by(Position.id)))


def create_position(
    session: Session, *, name: str, amount, rate,
    maturity_months: int, repricing_months: int,
) -> Position:
    position = Position(
        name=name, amount=amount, rate=rate,
        maturity_months=maturity_months, repricing_months=repricing_months,
    )
    session.add(position)
    session.commit()
    session.refresh(position)
    return position


def ensure_demo_portfolio(session: Session) -> int:
    """Заполняет пустой портфель тестовыми позициями, возвращает их число."""
    if list_positions(session):
        return 0
    for name, amount, rate, maturity_months, repricing_months in DEMO_POSITIONS:
        create_position(
            session, name=name, amount=amount, rate=rate,
            maturity_months=maturity_months, repricing_months=repricing_months,
        )
    return len(DEMO_POSITIONS)
