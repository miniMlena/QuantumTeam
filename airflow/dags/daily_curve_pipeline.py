from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import pendulum

from db.engine import SessionLocal
from db.repositories import curve_repo
from services.curve_pipeline import build_curves, load_curve


default_args = {
    "owner": "quantum_team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def _fetch(**ctx):
    with SessionLocal() as session:
        snap = load_curve(session)
        ctx["ti"].xcom_push(key="snapshot_id", value=snap.id)
        return snap.id


def _build(**ctx):
    snapshot_id = ctx["ti"].xcom_pull(key="snapshot_id")
    with SessionLocal() as session:
        snap = curve_repo.get_snapshot(session, snapshot_id)
        if snap.status != "pending":
            snap = curve_repo.copy_snapshot(session, snap)
        build_curves(session, snap)
        return snap.id


with DAG(
    dag_id="daily_curve_pipeline",
    description="Ежедневная загрузка MOEX и построение кривых",
    schedule="0 6 * * 1-5", # рабочие дни в 6:00 Europe/Moscow
    start_date=pendulum.datetime(2026, 1, 1, tz="Europe/Moscow"),
    catchup=False,
    default_args=default_args,
    tags=["irrbb", "market_data"],
) as dag:
    fetch = PythonOperator(task_id="fetch_moex", python_callable=_fetch)
    build = PythonOperator(task_id="build_curves", python_callable=_build)

    fetch >> build
