"""Ежедневный запуск того же пайплайна, что используется для ручной проверки."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="daily_curve_pipeline",
    description="Ежедневная загрузка MOEX и построение кривых",
    schedule="0 6 * * 1-5",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "quantum_team", "retries": 3,
                  "retry_delay": timedelta(minutes=5)},
    tags=["irrbb", "market_data"],
) as dag:
    calculate = BashOperator(
        task_id="fetch_build_and_apply",
        bash_command="/opt/airflow/project-venv/bin/python -m scripts.demo_pipeline",
    )
