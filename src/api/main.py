from fastapi import FastAPI
from api.routers import curves, scenarios, health

app = FastAPI(title="IRRBB Curves Service", version="0.1.0")

app.include_router(health.router)
app.include_router(scenarios.router, prefix="/api/v1")
app.include_router(curves.router, prefix="/api/v1")