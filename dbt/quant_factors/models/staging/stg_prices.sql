-- Staging: una vista delgada sobre raw.prices.
-- Reglas de esta capa (convención del modern data stack):
--   * 1 modelo de staging por tabla de origen
--   * solo limpieza/renombrado/casteo, NADA de lógica de negocio
--   * sin joins ni agregaciones (eso va más adelante)
--
-- Para factor research usamos SIEMPRE los precios ajustados (adj_*), porque
-- corrigen splits y dividendos. Usar el close sin ajustar metería saltos
-- artificiales en los retornos el día de un split: un error clásico.

with source as (
    select * from {{ source('raw', 'prices') }}
)

select
    ticker,
    date,
    -- nos quedamos con los ajustados como precios "oficiales" para análisis
    adj_open   as open,
    adj_high   as high,
    adj_low    as low,
    adj_close  as close,
    adj_volume as volume,
    div_cash,
    split_factor
from source
where adj_close is not null   -- descartamos días sin precio (feriados mal cargados, etc.)