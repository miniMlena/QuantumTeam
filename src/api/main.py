from contextlib import asynccontextmanager
from fastapi import FastAPI
from db.engine import init_db
from api.routers import curves, scenarios, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # создаём таблицы при старте
    yield


app = FastAPI(
    title="IRRBB Curves Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(scenarios.router, prefix="/api/v1")
app.include_router(curves.router, prefix="/api/v1")