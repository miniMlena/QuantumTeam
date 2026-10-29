from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from os import getenv
from db.models import Base

DATABASE_URL = getenv(
    "DATABASE_URL",
    "postgresql+psycopg://user:pass@localhost:5432/irrbb",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def init_db():
    Base.metadata.create_all(engine)