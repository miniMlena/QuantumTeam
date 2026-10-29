from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from db.engine import SessionLocal
from db.repositories import scenario_repo, curve_repo
from domain.moex.client import fetch_curve_from_moex
from domain.curve.builder import build_base_curve
from domain.curve.shifts import apply_shift


default_args = {
    "owner": "quantum_team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def _fetch(**ctx):
    params = fetch_curve_from_moex()
    with SessionLocal() as session:
        trade_date = params.pop("trade_date", None)
        snap = curve_repo.create_snapshot(
            session, trade_date=trade_date, params=params
        )
    ctx["ti"].xcom_push(key="snapshot_id", value=snap.id)
    return snap.id


def _build_base(**ctx):
    snapshot_id = ctx["ti"].xcom_pull(key="snapshot_id")
    with SessionLocal() as session:
        snap = curve_repo.get_snapshot(session, snapshot_id)
        params = {
            "b1": snap.b1, "b2": snap.b2, "b3": snap.b3, "t1": snap.t1,
            **{f"g{i}": getattr(snap, f"g{i}") for i in range(1, 10)},
        }
        points = build_base_curve(params)
        curve_repo.save_base_points(session, snapshot_id, points)
        curve_repo.mark_snapshot_status(session, snapshot_id, "built")
    return len(points)


def _apply_scenarios(**ctx):
    snapshot_id = ctx["ti"].xcom_pull(key="snapshot_id")
    with SessionLocal() as session:
        base = [
            {"tenor_months": p.tenor_months, "rate": float(p.rate),
             "point_type": p.point_type}
            for p in curve_repo.get_base_points(session, snapshot_id)
        ]
        for sc in scenario_repo.list_scenarios(session, only_active=True):
            shift_map = scenario_repo.get_shift_map(session, sc.id)
            shifted = apply_shift(base, shift_map)
            curve_repo.save_shifted_points(session, snapshot_id, sc.id, shifted)
    return snapshot_id


with DAG(
    dag_id="daily_curve_pipeline",
    description="Ежедневная загрузка MOEX и построение кривых",
    schedule="0 6 * * 1-5", # рабочие дни в 6:00
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["irrbb", "market_data"],
) as dag:
    fetch = PythonOperator(task_id="fetch_moex", python_callable=_fetch)
    build = PythonOperator(task_id="build_base_curve", python_callable=_build_base)
    apply = PythonOperator(task_id="apply_scenarios", python_callable=_apply_scenarios)

    fetch >> build >> apply