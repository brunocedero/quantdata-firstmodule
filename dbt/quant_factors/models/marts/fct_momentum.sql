with returns as (
    select * from {{ ref('int_daily_returns') }}
),
momentum as (
    select
        ticker,
        date,
        sum(log_return) over (
            partition by ticker order by date
            rows between 252 preceding and 21 preceding
        ) as momentum_12_1_log,
        count(*) over (
            partition by ticker order by date
            rows between 252 preceding and 21 preceding
        ) as obs_in_window
    from returns
)
select
    ticker,
    date,
    momentum_12_1_log,
    exp(momentum_12_1_log) - 1 as momentum_12_1
from momentum
where obs_in_window >= 200
