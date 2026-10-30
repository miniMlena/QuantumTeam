"""
API и страница на временной базе SQLite, сеть и PostgreSQL не нужны.
Нужны зависимости проекта; без них тесты пропускаются.
"""
import importlib.util
from datetime import date
import unittest
from unittest.mock import patch

from test_curve_pipeline import moex_params

HAS_DEPS = all(
    importlib.util.find_spec(m) for m in ("fastapi", "httpx", "psycopg", "sqlalchemy")
)

if HAS_DEPS:
    import httpx
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api.deps import get_db
    from api.main import app
    from db.models.base import Base

FETCH = "services.curve_pipeline.fetch_curve_from_moex"


@unittest.skipUnless(HAS_DEPS, "нужны зависимости API")
class ApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)

        def override_db():
            with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def calculate(self):
        with patch(FETCH, return_value=moex_params()):
            return self.client.post("/api/v1/curves/calculate")

    def test_page_is_served(self):
        for path, text in (("/", "Рассчитать MOEX"), ("/app.js", "/curves/calculate")):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(text, response.text)

    def test_no_curves_yet(self):
        self.assertEqual(self.client.get("/api/v1/curves/latest").status_code, 404)

    def test_calculate_twice_and_read_results(self):
        first = self.calculate()
        second = self.calculate()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(second.json()["status"], "built")
        self.assertEqual(second.json()["trade_date"], date(2026, 8, 31).isoformat())

        snapshot_id = self.client.get("/api/v1/curves/latest").json()["id"]
        base = self.client.get(f"/api/v1/curves/{snapshot_id}/base").json()
        self.assertEqual(len(base), 19)

        scenarios = self.client.get("/api/v1/scenarios").json()
        self.assertEqual(len(scenarios), 6)
        shifted = self.client.get(
            f"/api/v1/curves/{snapshot_id}/scenarios/{scenarios[0]['id']}"
        ).json()
        self.assertEqual(len(shifted), 19)

    def test_moex_failure_returns_502(self):
        with patch(FETCH, side_effect=httpx.ConnectError("no network")):
            response = self.client.post("/api/v1/curves/calculate")
        self.assertEqual(response.status_code, 502)
        self.assertIn("MOEX", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
