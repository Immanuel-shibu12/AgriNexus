"""
Weather integration using Open-Meteo (https://open-meteo.com) — free,
no API key needed, good fit for a student MVP. Swap BASE_URL/GEOCODE_URL
for IMD or a paid provider later if you need India-specific accuracy.
"""

import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def geocode_location(place_name: str):
    """Turn a free-text location (e.g. 'Avadi, Tamil Nadu') into lat/lon."""
    try:
        resp = requests.get(GEOCODE_URL, params={"name": place_name, "count": 1}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results")
        if not results:
            return None
        top = results[0]
        return {
            "latitude": top["latitude"],
            "longitude": top["longitude"],
            "resolved_name": f"{top.get('name')}, {top.get('admin1', '')}".strip(", "),
        }
    except requests.RequestException:
        return None


def get_forecast(latitude: float, longitude: float, days: int = 7):
    """Daily precipitation sum + max windspeed for the next `days` days."""
    try:
        resp = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "precipitation_sum,windspeed_10m_max,temperature_2m_max,temperature_2m_min",
                "forecast_days": days,
                "timezone": "auto",
            },
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get("daily")
    except requests.RequestException:
        return None


def get_today_flags(daily_forecast):
    """
    Interpret the first day of a daily forecast into simple advisory flags.
    Thresholds are reasonable defaults for demo purposes:
      - rain_today: precipitation_sum > 2mm
      - high_wind_today: max windspeed > 25 km/h
    """
    if not daily_forecast:
        return {"rain_today": False, "high_wind_today": False, "available": False}

    precip = daily_forecast["precipitation_sum"][0]
    wind = daily_forecast["windspeed_10m_max"][0]

    return {
        "available": True,
        "rain_today": precip is not None and precip > 2.0,
        "high_wind_today": wind is not None and wind > 25.0,
        "precip_mm": precip,
        "wind_kmh": wind,
    }
