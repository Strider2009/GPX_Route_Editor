"""Weather for a route on a given day, from Open-Meteo (free, no API key).

Wind matters more than temperature on a loaded bike, so the headwind/tailwind
component is worked out against the direction the route is actually heading.
"""

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import date

from . import http_client

BASE = os.environ.get("OPEN_METEO_BASE", "https://api.open-meteo.com/v1/forecast")
# Open-Meteo's free forecast reaches about this far ahead.
FORECAST_DAYS = 16

WEATHER_CODES = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Violent showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def describe(code) -> str:
    try:
        return WEATHER_CODES.get(int(code), f"Code {code}")
    except (TypeError, ValueError):
        return "Unknown"


def bearing(a: dict, b: dict) -> float:
    """Compass bearing in degrees from point a to point b."""
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlon = math.radians(b["lon"] - a["lon"])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(degrees: float) -> str:
    names = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    return names[int((degrees % 360) / 22.5 + 0.5) % 16]


def wind_effect(route_bearing: float, wind_from: float, wind_speed: float) -> dict:
    """Head/tail/cross components for wind blowing *from* `wind_from`."""
    # Wind direction is reported as the direction it comes from; the vector it
    # pushes towards is the opposite.
    blowing_towards = (wind_from + 180) % 360
    delta = math.radians(blowing_towards - route_bearing)
    along = wind_speed * math.cos(delta)  # positive = pushing you along
    across = wind_speed * math.sin(delta)
    if along > 3:
        label = "tailwind"
    elif along < -3:
        label = "headwind"
    else:
        label = "crosswind"
    return {
        "label": label,
        "along_kmh": round(along, 1),
        "across_kmh": round(abs(across), 1),
    }


def fetch(lat: float, lon: float, when: date) -> dict:
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
        "wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,weather_code,sunrise,sunset",
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,weather_code",
        "timezone": "Europe/London",
        "start_date": when.isoformat(),
        "end_date": when.isoformat(),
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = http_client.build_request(url, headers={"User-Agent": "personal-gpx-route-planner/1.0"})
    with http_client.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())
