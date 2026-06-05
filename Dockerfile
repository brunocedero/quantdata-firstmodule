# Imagen de Airflow con nuestras dependencias YA instaladas (una sola vez, en build).
FROM apache/airflow:2.10.4-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
USER airflow

RUN mkdir -p /opt/airflow/dbt_artifacts/packages /opt/airflow/dbt_artifacts/target

# psycopg2-binary -> conexión a Postgres desde la ingesta
# dbt-postgres     -> transformación
# requests/pandas/numpy -> cliente de API y análisis
RUN pip install --no-cache-dir \
    "dbt-core==1.8.*" \
    "dbt-postgres==1.8.*" \
    psycopg2-binary \
    requests \
    pandas \
    numpy