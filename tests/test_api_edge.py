import importlib.util
import unittest
from unittest.mock import patch

from test_curve_pipeline import moex_params

HAS_DEPS = all(
    importlib.util.find_spec(m) for m in ("fastapi", "httpx", "psycopg", "redis", "rq", "sqlalchemy")
)

if HAS_DEPS:
    import csv
    import io

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api.deps import get_db
    from api.main import app
    from db.models import CurveSnapshot, Scenario
    from db.models.base import Base
    from db.repositories import portfolio_repo

FETCH = "services.curve_pipeline.fetch_curve_from_moex"
SHIFT = {"tenor_years": 1, "shift_bp": 100}


def scenario_payload(**changes):
    payload = {"code": "custom_1", "name": "Custom", "scenario_type": "custom",
               "shifts": [SHIFT, {"tenor_years": 5, "shift_bp": -50}]}
    payload.update(changes)
    return payload


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

        def override_db():
            with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.clear)
        # 500 нужно видеть как статус, а не как исключение внутри теста
        self.client = TestClient(app, raise_server_exceptions=False)

    def calculate(self):
        with patch(FETCH, return_value=moex_params()):
            return self.client.post("/api/v1/curves/calculate")

    def with_demo_portfolio(self):
        with self.session_factory() as session:
            portfolio_repo.ensure_demo_portfolio(session)

    def set_snapshot_status(self, snapshot_id, status):
        with self.session_factory() as session:
            session.get(CurveSnapshot, snapshot_id).status = status
            session.commit()


@unittest.skipUnless(HAS_DEPS, "нужны зависимости API")
class KnownBugs(ApiTestCase):
    def test_results_refuse_failed_snapshot(self):
        """Снимок со статусом failed может содержать часть точек: ЭК по нему считать нельзя."""
        snapshot_id = self.calculate().json()["id"]
        self.with_demo_portfolio()
        self.set_snapshot_status(snapshot_id, "failed")
        response = self.client.get("/api/v1/results", params={"snapshot_id": snapshot_id})
        self.assertIn(response.status_code, (404, 409))

    def test_scenario_without_shifts_is_rejected(self):
        response = self.client.post("/api/v1/scenarios", json=scenario_payload(shifts=[]))
        self.assertEqual(response.status_code, 422)

    def test_scenario_with_duplicate_tenors_is_rejected(self):
        response = self.client.post(
            "/api/v1/scenarios", json=scenario_payload(shifts=[SHIFT, SHIFT])
        )
        self.assertEqual(response.status_code, 422)   # сейчас 500: нарушение UNIQUE в БД

    def test_scenario_with_non_positive_tenor_is_rejected(self):
        for tenor in (0, -1):
            with self.subTest(tenor=tenor):
                response = self.client.post("/api/v1/scenarios", json=scenario_payload(
                    shifts=[{"tenor_years": tenor, "shift_bp": 10}]))
                self.assertEqual(response.status_code, 422)

    def test_scenario_with_absurd_shift_is_rejected(self):
        """-15000 б.п. даёт отрицательную ставку ниже -100% и ломает NPV."""
        response = self.client.post("/api/v1/scenarios", json=scenario_payload(
            shifts=[{"tenor_years": 1, "shift_bp": -15000}]))
        self.assertEqual(response.status_code, 422)

    def test_scenario_code_and_type_are_validated(self):
        for field, value in (("code", "x" * 51), ("code", ""), ("scenario_type", "что-угодно")):
            with self.subTest(field=field, value=value[:10]):
                response = self.client.post("/api/v1/scenarios", json=scenario_payload(**{field: value}))
                self.assertEqual(response.status_code, 422)

    def test_custom_scenario_cannot_pose_as_regulatory(self):
        """Любой клиент API может пометить свой сценарий регуляторным: нужна авторизация."""
        response = self.client.post("/api/v1/scenarios", json=scenario_payload(is_regulatory=True))
        self.assertIn(response.status_code, (401, 403, 422))


@unittest.skipUnless(HAS_DEPS, "нужны зависимости API")
class InputValidation(ApiTestCase):
    def test_unknown_ids_are_404(self):
        self.calculate()
        for path in ("/curves/999/base", "/curves/999/scenarios/1", "/curves/1/scenarios/999",
                     "/scenarios/999", "/curves/0/base"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get("/api/v1" + path).status_code, 404)

    def test_garbage_ids_are_422(self):
        for path in ("/curves/abc/base", "/scenarios/x", "/curves/1/scenarios/y"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get("/api/v1" + path).status_code, 422)

    def test_garbage_trade_date_is_422(self):
        for value in ("2026-13-45", "вчера", "31.08.2026"):
            with self.subTest(value=value):
                response = self.client.post("/api/v1/curves/calculate", params={"trade_date": value})
                self.assertEqual(response.status_code, 422)

    def test_position_validation(self):
        base = {"name": "x", "amount": 100, "rate": 10, "maturity_months": 12, "repricing_months": 12}
        for changes in ({"rate": -1}, {"maturity_months": 0}, {"repricing_months": 0},
                        {"repricing_months": 13}, {"amount": "много"}, {"name": None}):
            with self.subTest(changes=changes):
                response = self.client.post("/api/v1/portfolio", json={**base, **changes})
                self.assertEqual(response.status_code, 422)

    def test_duplicate_scenario_code_is_409(self):
        self.assertEqual(self.client.post("/api/v1/scenarios", json=scenario_payload()).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/scenarios", json=scenario_payload()).status_code, 409)

    def test_results_without_any_snapshot_is_404(self):
        self.assertEqual(self.client.get("/api/v1/results").status_code, 404)

    def test_exports_for_missing_and_unbuilt_snapshots(self):
        self.assertEqual(self.client.get("/api/v1/exports/curves/999/moex.csv").status_code, 404)
        snapshot_id = self.calculate().json()["id"]
        self.set_snapshot_status(snapshot_id, "pending")
        self.assertEqual(self.client.get(f"/api/v1/exports/curves/{snapshot_id}/moex.csv").status_code, 409)

    def test_demo_export_months_limits(self):
        snapshot_id = self.calculate().json()["id"]
        for months in (0, -1, 361):
            with self.subTest(months=months):
                response = self.client.get(
                    f"/api/v1/exports/curves/{snapshot_id}/calculator-demo.csv", params={"months": months})
                self.assertEqual(response.status_code, 422)


@unittest.skipUnless(HAS_DEPS, "нужны зависимости API")
class EndToEnd(ApiTestCase):
    def test_custom_scenario_appears_after_recalculation(self):
        self.calculate()
        self.with_demo_portfolio()
        self.assertEqual(len(self.client.get("/api/v1/results").json()["scenarios"]), 6)

        self.client.post("/api/v1/scenarios", json=scenario_payload())
        # пока кривая не пересчитана, новый сценарий в результатах отсутствует
        self.assertEqual(len(self.client.get("/api/v1/results").json()["scenarios"]), 6)

        self.calculate()
        results = self.client.get("/api/v1/results").json()
        self.assertEqual(len(results["scenarios"]), 7)
        self.assertIn("custom_1", [item["code"] for item in results["scenarios"]])

    def test_economic_capital_matches_minimum_of_listed_scenarios(self):
        self.calculate()
        self.with_demo_portfolio()
        results = self.client.get("/api/v1/results").json()
        deltas = [item["delta_npv"] for item in results["scenarios"]]
        self.assertEqual(results["economic_capital"]["value"], min(deltas))

    def test_results_are_repeatable(self):
        self.calculate()
        self.with_demo_portfolio()
        first = self.client.get("/api/v1/results").json()
        self.calculate()
        self.assertEqual(self.client.get("/api/v1/results").json(), first)

    def test_moex_csv_has_all_points_and_fractions(self):
        snapshot_id = self.calculate().json()["id"]
        response = self.client.get(f"/api/v1/exports/curves/{snapshot_id}/moex.csv")
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(len(rows), 19 * 7)                       # база + 6 сценариев
        self.assertEqual({r["scenario"] for r in rows} - {"base"}, set(
            s["code"] for s in self.client.get("/api/v1/scenarios").json()))
        for row in rows:
            self.assertLess(abs(float(row["rate"])), 1.0, row)    # доли, а не проценты

    def test_scenarios_list_is_stable_between_calls(self):
        self.calculate()
        first = [s["code"] for s in self.client.get("/api/v1/scenarios").json()]
        second = [s["code"] for s in self.client.get("/api/v1/scenarios").json()]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
