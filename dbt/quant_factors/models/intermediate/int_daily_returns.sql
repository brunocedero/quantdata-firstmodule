-- Intermediate: calcula retornos diarios por ticker.
-- Esta capa es para lógica reutilizable que todavía no es un "producto final":
-- varios factores van a necesitar retornos, así que los calculamos una sola vez acá.
--
-- Concepto clave: window functions. `lag(close) over (partition by ticker order by date)`
-- toma, para cada fila, el cierre del DÍA ANTERIOR del MISMO ticker. El partition by
-- evita mezclar tickers (que el "anterior" de un AAPL no sea un MSFT) y el order by
-- define qué significa "anterior". Es el patrón base de toda serie temporal financiera.
--
-- Calculamos dos retornos:
--   * simple   = (P_t / P_t-1) - 1   -> intuitivo, para reportar
--   * log      = ln(P_t / P_t-1)     -> se suma en el tiempo, mejor para componer.
--     Preferido en quant porque la suma de log-returns = log-return del período total.

with prices as (
    select * from {{ ref('stg_prices') }}
),

with_lag as (
    select
        ticker,
        date,
        close,
        lag(close) over (partition by ticker order by date) as prev_close
    from prices
)

select
    ticker,
    date,
    close,
    prev_close,
    close / prev_close - 1                as daily_return,
    ln(close / prev_close)                as log_return
from with_lag
where prev_close is not null   -- la primera fila de cada ticker no tiene día previo