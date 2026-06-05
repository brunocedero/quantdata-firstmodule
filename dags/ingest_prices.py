"""DAG de ingesta de precios EOD desde Tiingo hacia raw.prices.

Decisiones de diseño que vale la pena explicar en el blog:

1) schedule="@monthly" + catchup=True
   Cada "corrida" (DAG run) cubre UN MES. Como start_date es 2010, al despausar
   el DAG Airflow genera automáticamente una corrida por cada mes desde entonces
   hasta hoy: eso es el BACKFILL. No escribimos un script aparte para el histórico;
   el histórico es simplemente "ponerse al día" (catchup) con todos los meses
   pasados. Elegimos mes (y no día) para no disparar miles de llamadas a la API y
   respetar el rate limit del tier gratuito.

2) data_interval_start / data_interval_end
   Airflow le pasa a cada corrida la "ventana de tiempo" que le toca procesar.
   Para la corrida de, digamos, marzo 2015, esos valores son 2015-03-01 y
   2015-04-01. Usamos esa ventana como rango de fechas para pedirle a la API.
   Así cada corrida es autosuficiente y sabe exactamente qué datos le corresponden.

3) .expand(ticker=UNIVERSE) -> dynamic task mapping
   En vez de escribir una tarea por ticker a mano, Airflow crea una instancia de la
   tarea por cada elemento de la lista. Agregar un cuarto ticker = una línea, sin
   tocar la estructura del DAG. Las instancias corren en paralelo (limitado abajo).

4) retries + max_active_runs
   Las llamadas a APIs fallan a veces (timeouts, 429). Con retries Airflow reintenta
   solo. max_active_runs=1 evita que 190 meses golpeen la API a la vez durante el
   backfill; subilo si tu plan de Tiingo lo permite.
"""
from datetime import datetime, timedelta

from airflow.decorators import dag, task

# Universo inicial: tres sectores distintos para que el factor research tenga variedad.
# Agregar tickers = sumar strings a esta lista.
UNIVERSE = ["AAPL", "MSFT", "JPM"]


@dag(
    dag_id="ingest_prices",
    description="Ingesta mensual de precios EOD desde Tiingo a raw.prices",
    schedule="@monthly",
    start_date=datetime(2010, 1, 1),
    catchup=True,            # <- esto habilita el backfill automático
    max_active_runs=1,       # un mes por vez, para no saturar la API gratuita
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["ingestion", "quant"],
)
def ingest_prices():
    @task
    def setup() -> None:
        """Crea schema y tabla raw si no existen. Corre antes de cargar nada."""
        from ingestion.load import ensure_schema
        ensure_schema()

    @task
    def ingest_ticker(ticker: str, **context) -> int:
        """Trae un mes de precios de un ticker y los upsertea en raw.prices."""
        from ingestion.tiingo_client import fetch_eod_prices
        from ingestion.load import upsert_prices

        # La ventana de tiempo que Airflow asignó a esta corrida.
        start = context["data_interval_start"].strftime("%Y-%m-%d")
        end = context["data_interval_end"].strftime("%Y-%m-%d")

        rows = fetch_eod_prices(ticker, start, end)
        n = upsert_prices(ticker, rows)
        print(f"{ticker}: {n} filas cargadas para {start}..{end}")
        return n

    # Orden: primero asegurar el esquema, después cargar (en paralelo) cada ticker.
    setup() >> ingest_ticker.expand(ticker=UNIVERSE)


ingest_prices()