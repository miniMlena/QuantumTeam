# airflow/Dockerfile
FROM apache/airflow:2.9.3-python3.11

# Зависимости, которые нужны DAG'ам (не всему приложению)
RUN pip install --no-cache-dir \
    "sqlalchemy>=2.0" \
    "psycopg[binary]>=3.1" \
    "httpx>=0.27" \
    "numpy>=1.26"