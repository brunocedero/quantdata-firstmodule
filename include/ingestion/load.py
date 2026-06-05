"""Carga de precios a la capa `raw` del warehouse.

Punto clave: la carga es IDEMPOTENTE. Usamos `insert ... on conflict do update`
(un "upsert") con clave primaria (ticker, date). Eso significa que correr la misma
tarea dos veces no duplica datos: la segunda vez simplemente sobreescribe. Es lo que
permite re-ejecutar un día fallido o hacer backfill sin miedo a ensuciar la tabla.
"""
import os

import psycopg2
from psycopg2.extras import execute_values

# La capa raw guarda los datos del proveedor casi tal cual, sin transformar.
# La limpieza y el tipado fino se hacen después en dbt (staging).
DDL = """
create schema if not exists raw;

create table if not exists raw.prices (
    ticker        text   not null,
    date          date   not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    volume        bigint,
    adj_open      double precision,
    adj_high      double precision,
    adj_low       double precision,
    adj_close     double precision,
    adj_volume    bigint,
    div_cash      double precision,
    split_factor  double precision,
    loaded_at     timestamptz default now(),
    primary key (ticker, date)
);
"""


def get_conn():
    """Conexión al warehouse (postgres-dw). Lee las credenciales del entorno."""
    return psycopg2.connect(
        host=os.environ["WAREHOUSE_HOST"],
        dbname=os.environ["WAREHOUSE_DB"],
        user=os.environ["WAREHOUSE_USER"],
        password=os.environ["WAREHOUSE_PASSWORD"],
    )


def ensure_schema() -> None:
    """Crea el schema raw y la tabla si no existen. Idempotente."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(DDL)


def upsert_prices(ticker: str, rows: list[dict]) -> int:
    """Inserta/actualiza los precios de un ticker. Devuelve cuántas filas tocó."""
    if not rows:
        return 0

    records = [
        (
            ticker,
            r["date"][:10],  # Tiingo devuelve datetime ISO; nos quedamos con la fecha
            r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"),
            r.get("adjOpen"), r.get("adjHigh"), r.get("adjLow"), r.get("adjClose"),
            r.get("adjVolume"), r.get("divCash"), r.get("splitFactor"),
        )
        for r in rows
    ]

    sql = """
        insert into raw.prices (
            ticker, date, open, high, low, close, volume,
            adj_open, adj_high, adj_low, adj_close, adj_volume, div_cash, split_factor
        ) values %s
        on conflict (ticker, date) do update set
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            adj_open = excluded.adj_open,
            adj_high = excluded.adj_high,
            adj_low = excluded.adj_low,
            adj_close = excluded.adj_close,
            adj_volume = excluded.adj_volume,
            div_cash = excluded.div_cash,
            split_factor = excluded.split_factor,
            loaded_at = now();
    """

    with get_conn() as conn, conn.cursor() as cur:
        execute_values(cur, sql, records)
    return len(records)