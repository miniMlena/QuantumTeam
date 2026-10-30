from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from api.deps import get_db
from api.schemas.portfolio import PositionCreate, PositionOut
from db.repositories import portfolio_repo

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PositionOut])
def list_positions(db: Session = Depends(get_db)):
    return portfolio_repo.list_positions(db)


@router.post("", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
def create_position(payload: PositionCreate, db: Session = Depends(get_db)):
    return portfolio_repo.create_position(db, **payload.model_dump())
