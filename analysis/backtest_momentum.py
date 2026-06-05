"""
Backtest didáctico del factor momentum (3 tickers).

OBJETIVO Y LÍMITES (importante, leer antes de sacar conclusiones):
Con solo 3 acciones NO se puede hacer un momentum cross-sectional serio
(comprar ganadores / vender perdedores rankeando el universo): la muestra es
demasiado chica y el resultado lo domina el azar de qué 3 tickers elegimos.
Este script implementa la MECÁNICA completa de un backtest —que es lo
transferible— sobre una estrategia simple y honesta:

  Estrategia: long-only ponderada por la señal de momentum. Cada mes asignamos
  más peso a las acciones con mayor momentum y nada a las de momentum negativo.
  Benchmark: equal-weight buy & hold (tener las 3 acciones por igual, sin tocar).

  Pregunta que responde: ¿inclinar la cartera hacia el momentum aporta algo
  sobre simplemente mantener las acciones? Medible incluso con 3 nombres,
  sin pretender que es la estrategia de un fondo.

Cuando amplíes el universo (30-50 tickers), este mismo código corre igual y
recién ahí los resultados tienen peso estadístico.

Decisiones de diseño que evitan trampas clásicas de backtesting:
  * Rebalanceo MENSUAL: tomamos la señal a fin de mes y la aplicamos al mes
    SIGUIENTE. Nunca usamos el momentum de hoy para "operar" hoy (eso sería
    lookahead bias: usar información que en la práctica no tendrías aún).
  * Los pesos se deciden con datos hasta t, los retornos se cobran en t+1.
  * Costos de transacción: incluimos un costo simple por rebalanceo para no
    inflar el resultado (un backtest sin costos siempre parece genial).
"""

import os
import numpy as np
import pandas as pd
import psycopg2
import matplotlib.pyplot as plt

# --- Parámetros ---------------------------------------------------------------
COST_PER_TURNOVER = 0.001   # 10 bps por unidad de rotación de cartera (costo de operar)
TRADING_DAYS = 252          # ruedas hábiles por año, para anualizar métricas


# --- 1. Leer datos del warehouse ---------------------------------------------
def load_data():
    """Trae precios (stg_prices) y el factor (fct_momentum) desde Postgres."""
    conn = psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "localhost"),
        port=os.environ.get("WAREHOUSE_PORT", "5433"),  # 5433 si corrés desde el host
        dbname=os.environ.get("WAREHOUSE_DB", "quant"),
        user=os.environ.get("WAREHOUSE_USER", "quant"),
        password=os.environ.get("WAREHOUSE_PASSWORD", "quant"),
    )
    prices = pd.read_sql(
        "select ticker, date, close from analytics.stg_prices order by date", conn
    )
    momentum = pd.read_sql(
        "select ticker, date, momentum_12_1 from analytics.fct_momentum order by date",
        conn,
    )
    conn.close()
    prices["date"] = pd.to_datetime(prices["date"])
    momentum["date"] = pd.to_datetime(momentum["date"])
    return prices, momentum


# --- 2. Preparar retornos diarios y señal mensual ----------------------------
def build_panels(prices, momentum):
    """Pivotea a formato ancho (fecha x ticker) y arma retornos y señal."""
    # precios en formato ancho: filas=fechas, columnas=tickers
    px = prices.pivot(index="date", columns="ticker", values="close").sort_index()
    daily_ret = px.pct_change()  # retorno diario simple por acción

    # señal de momentum en formato ancho
    sig = momentum.pivot(index="date", columns="ticker", values="momentum_12_1")
    sig = sig.reindex(px.index).sort_index()  # alinear al calendario de precios

    return daily_ret, sig


# --- 3. Construir pesos de la cartera a partir de la señal --------------------
def compute_weights(sig):
    """
    Pesos long-only proporcionales al momentum positivo, rebalanceo mensual.
    - tomamos la señal del ÚLTIMO día de cada mes (lo que sabrías a fin de mes)
    - momentum negativo -> peso 0 (no shorteamos en esta versión simple)
    - normalizamos para que los pesos sumen 1 (cartera totalmente invertida)
    - si en un mes ninguna acción tiene momentum positivo, quedamos en cash (pesos 0)
    """
    monthly_sig = sig.resample("ME").last()      # señal a fin de mes
    positive = monthly_sig.clip(lower=0)         # recorta negativos a 0
    row_sums = positive.sum(axis=1)
    weights = positive.div(row_sums, axis=0).fillna(0.0)  # normaliza; cash si todo es 0
    return weights


# --- 4. Correr el backtest ----------------------------------------------------
def run_backtest(daily_ret, weights):
    """
    Aplica los pesos de fin de mes al MES SIGUIENTE (evita lookahead) y descuenta
    costos por rotación. Devuelve retornos diarios de la estrategia y del benchmark.
    """
    # expandimos los pesos mensuales a frecuencia diaria, desplazados 1 período:
    # la señal de fin de mes M gobierna los retornos del mes M+1.
    w_daily = weights.reindex(daily_ret.index, method="ffill").shift(1).fillna(0.0)

    # retorno bruto de la estrategia = suma ponderada de retornos por acción
    gross = (w_daily * daily_ret).sum(axis=1)

    # costo de transacción: proporcional a cuánto cambian los pesos al rebalancear
    turnover = w_daily.diff().abs().sum(axis=1).fillna(0.0)
    cost = turnover * COST_PER_TURNOVER
    strat = gross - cost

    # benchmark: equal-weight buy & hold (1/N en cada acción, fijo)
    n = daily_ret.shape[1]
    bench = daily_ret.mean(axis=1)  # promedio simple = equal weight

    return strat.fillna(0.0), bench.fillna(0.0)


# --- 5. Métricas --------------------------------------------------------------
def metrics(returns, name):
    """Calcula métricas anualizadas estándar de un stream de retornos diarios."""
    cum = (1 + returns).prod() - 1
    ann_ret = (1 + returns).prod() ** (TRADING_DAYS / len(returns)) - 1
    ann_vol = returns.std() * np.sqrt(TRADING_DAYS)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    # max drawdown: peor caída desde un pico de la curva de equity
    equity = (1 + returns).cumprod()
    drawdown = (equity / equity.cummax() - 1).min()
    return {
        "estrategia": name,
        "retorno_total": f"{cum:.1%}",
        "retorno_anual": f"{ann_ret:.1%}",
        "volatilidad_anual": f"{ann_vol:.1%}",
        "sharpe": f"{sharpe:.2f}",
        "max_drawdown": f"{drawdown:.1%}",
    }


# --- 6. Main ------------------------------------------------------------------
def main():
    prices, momentum = load_data()
    daily_ret, sig = build_panels(prices, momentum)
    weights = compute_weights(sig)
    strat, bench = run_backtest(daily_ret, weights)

    # alinear ambos al período donde la estrategia ya tiene señal (post warm-up)
    valid = strat.index[strat.ne(0).cumsum() > 0]
    strat, bench = strat.loc[valid], bench.loc[valid]

    # tabla de métricas comparativa
    table = pd.DataFrame([
        metrics(strat, "Momentum (long-only)"),
        metrics(bench, "Benchmark (equal-weight)"),
    ])
    print("\n=== Métricas del backtest (3 tickers, didáctico) ===")
    print(table.to_string(index=False))

    # gráfico: curva de equity (cómo crece $1 invertido en cada una)
    eq_strat = (1 + strat).cumprod()
    eq_bench = (1 + bench).cumprod()
    plt.figure(figsize=(11, 6))
    plt.plot(eq_strat.index, eq_strat, label="Momentum (long-only)", linewidth=1.8)
    plt.plot(eq_bench.index, eq_bench, label="Benchmark (equal-weight)",
             linewidth=1.8, alpha=0.8)
    plt.title("Curva de equity: $1 invertido (3 tickers, backtest didáctico)")
    plt.ylabel("Valor de $1")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("backtest_equity.png", dpi=130)
    print("\nGráfico guardado en backtest_equity.png")


if __name__ == "__main__":
    main()