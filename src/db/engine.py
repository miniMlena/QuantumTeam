from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from os import getenv
from db.models import Base

DATABASE_URL = getenv(
    "DATABASE_URL",
    "postgresql+psycopg://user:pass@localhost:5432/irrbb",
)

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True,
    connect_args={"options": "-c timezone=Europe/Moscow"} if DATABASE_URL.startswith("postgresql") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def init_db():
    from db.migrations import upgrade_history
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # API и db-init могут стартовать одновременно: одна миграция за раз.
            connection.execute(text("SELECT pg_advisory_xact_lock(2026112101)"))
        upgrade_history(connection)
        Base.metadata.create_all(connection)
