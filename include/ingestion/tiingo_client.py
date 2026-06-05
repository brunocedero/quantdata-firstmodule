"""Cliente mínimo de la API de Tiingo (precios EOD).

Una sola responsabilidad: pedirle a Tiingo los precios de un ticker en un rango
de fechas y devolver la lista de dicts tal cual viene. No toca la base de datos
ni transforma nada: eso es trabajo de otras capas (separación de responsabilidades).
"""
import os
import requests

BASE_URL = "https://api.tiingo.com/tiingo/daily"


def fetch_eod_prices(ticker: str, start_date: str, end_date: str) -> list[dict]:
    """Devuelve los precios diarios (end-of-day) de un ticker entre dos fechas.

    Fechas en formato 'YYYY-MM-DD'. Cada elemento de la lista trae open/high/low/
    close/volume y sus versiones ajustadas (adjClose, etc.), más dividendos y splits.
    """
    token = os.environ["TIINGO_API_KEY"]
    url = f"{BASE_URL}/{ticker}/prices"
    params = {
        "startDate": start_date,
        "endDate": end_date,
        "token": token,
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()  # lanza excepción si la API responde error -> Airflow reintenta
    return resp.json()