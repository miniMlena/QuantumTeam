from sqlalchemy import select
from sqlalchemy.orm import Session
from db.models.portfolio import Position


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
