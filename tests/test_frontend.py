"""Проверки новых маршрутов демо-страницы без внешней БД и MOEX."""
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from api.deps import get_db
from api.main import app


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_db] = lambda: None

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        self.client.close()

    def test_page_and_local_assets(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="chart"', page.text)
        for asset in ("app.js", "style.css"):
            self.assertEqual(self.client.get("/static/" + asset).status_code, 200)

    def test_empty_snapshots(self):
        with patch("api.routers.curves.curve_repo.list_snapshots", return_value=[]):
            response = self.client.get("/api/v1/curves")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_rebuild_uses_existing_pipeline(self):
        with patch("worker.tasks.fetch_and_build_today", return_value={"status": "ok", "snapshot_id": 7}) as calculate:
            response = self.client.post("/api/v1/curves/rebuild")
        calculate.assert_called_once_with()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["snapshot_id"], 7)

    def test_upstream_errors_are_readable(self):
        for error in (httpx.ConnectError("Unavailable"), ValueError("Invalid MOEX data")):
            with self.subTest(error=error), patch("worker.tasks.fetch_and_build_today", side_effect=error):
                response = self.client.post("/api/v1/curves/rebuild")
                self.assertEqual(response.status_code, 502)
                self.assertIn("MOEX", response.json()["detail"])

    def test_routes_are_unique(self):
        paths = [(r.path, tuple(sorted(r.methods or []))) for r in app.routes if hasattr(r, "methods")]
        self.assertEqual(len(paths), len(set(paths)))


if __name__ == "__main__":
    unittest.main()
