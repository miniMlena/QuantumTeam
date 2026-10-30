from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from db.engine import init_db
from api.routers import curves, health, portfolio, results, scenarios


STATIC_DIR = Path(__file__).parent / "static"


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
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")

# Подключается последним: иначе перехватит пути API
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
