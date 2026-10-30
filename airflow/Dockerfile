FROM apache/airflow:2.9.3-python3.11

# Airflow 2.9 использует SQLAlchemy 1.x, проект — SQLAlchemy 2.x.
# DAG запускает расчётный скрипт в отдельном окружении.
RUN python -m venv /opt/airflow/project-venv \
    && /opt/airflow/project-venv/bin/pip install --no-cache-dir \
        "sqlalchemy>=2.0" "psycopg[binary]>=3.1" "httpx>=0.27"
