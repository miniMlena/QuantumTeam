"""Интеграция с PostgreSQL: запускать только на отдельной тестовой БД.

RUN_INTEGRATION_TESTS=1, DATABASE_URL=postgresql+psycopg://... .
Тест не удаляет схему и не использует рабочую базу по умолчанию.
"""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.getenv("RUN_INTEGRATION_TESTS") == "1",
                     "Set RUN_INTEGRATION_TESTS=1 for a dedicated PostgreSQL database")
class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from db.engine import init_db
        from domain.moex.client import parse_curve_params

        init_db()
        cls.params = parse_curve_params(json.loads(
            (Path(__file__).parent/"fixtures/moex_zcyc.json").read_text()
        ))

    def test_rebuild_twice_and_api(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import func, select
        from api.main import app
        from db.engine import SessionLocal
        from db.models import BaseCurvePoint, ShiftedCurvePoint
        from db.repositories import curve_repo, scenario_repo
        from worker.tasks import fetch_and_build_today, rebuild_snapshot

        with patch("worker.tasks.fetch_curve_from_moex", side_effect=lambda: dict(self.params)):
            first = fetch_and_build_today()
            second = fetch_and_build_today()
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        snapshot_id = first["snapshot_id"]
        self.assertEqual(rebuild_snapshot(snapshot_id)["status"], "ok")
        with SessionLocal() as session:
            snap = curve_repo.get_snapshot(session, snapshot_id)
            self.assertEqual(snap.trade_date, self.params["trade_date"])
            self.assertEqual(snap.status, "built")
            self.assertEqual(session.scalar(select(func.count()).select_from(BaseCurvePoint)
                .where(BaseCurvePoint.snapshot_id == snapshot_id)), 11)
            scenarios = scenario_repo.list_scenarios(session)
            standard = [s for s in scenarios if s.code.startswith("irrbb_rub_")]
            self.assertEqual(len(standard), 6)
            self.assertEqual(session.scalar(select(func.count()).select_from(ShiftedCurvePoint)
                .where(ShiftedCurvePoint.snapshot_id == snapshot_id)), 11*len(scenarios))
            scenario_id = standard[0].id
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok", "db": "ok"})
            self.assertEqual(client.get("/api/v1/curves/latest").json()["id"], snapshot_id)
            base = client.get(f"/api/v1/curves/{snapshot_id}/base")
            self.assertEqual(base.status_code, 200)
            self.assertEqual(len(base.json()), 11)
            shifted = client.get(f"/api/v1/curves/{snapshot_id}/scenarios/{scenario_id}")
            self.assertEqual(shifted.status_code, 200)
            self.assertEqual(len(shifted.json()), 11)
            self.assertEqual(client.get("/api/v1/curves/999999999/base").status_code, 404)
            self.assertEqual(client.get("/api/v1/scenarios").status_code, 200)

    def test_missing_snapshot(self):
        from worker.tasks import rebuild_snapshot
        self.assertEqual(rebuild_snapshot(999999999)["status"], "failed")
