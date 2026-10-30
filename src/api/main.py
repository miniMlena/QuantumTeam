from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def demo_page():
    return FileResponse(STATIC_DIR / "index.html")
