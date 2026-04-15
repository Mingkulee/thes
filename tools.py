"""External tools the agents can call."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


async def geocode_location(
    location: str,
) -> tuple[float, float, str, str] | None:
    """Resolve a place name to (latitude, longitude, display_name, country).

    Returns None if no match was found.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _GEOCODE_URL,
            params={"name": location, "count": 1, "language": "ko"},
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results") or []
    if not results:
        return None

    r = results[0]
    return (
        float(r["latitude"]),
        float(r["longitude"]),
        r.get("name", location),
        r.get("country", ""),
    )


async def fetch_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch current weather and a 3-day forecast from Open-Meteo."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "weather_code",
                "wind_speed_10m",
                "precipitation",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "precipitation_sum",
            ]
        ),
        "timezone": "auto",
        "forecast_days": 3,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_FORECAST_URL, params=params)
        resp.raise_for_status()
        return resp.json()


# Open-Meteo WMO weather codes → 한국어 설명 (간략 매핑)
WEATHER_CODE_KO: dict[int, str] = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분적으로 흐림",
    3: "흐림",
    45: "안개",
    48: "서리 안개",
    51: "약한 이슬비",
    53: "보통 이슬비",
    55: "강한 이슬비",
    56: "약한 어는 이슬비",
    57: "강한 어는 이슬비",
    61: "약한 비",
    63: "보통 비",
    65: "강한 비",
    66: "약한 어는 비",
    67: "강한 어는 비",
    71: "약한 눈",
    73: "보통 눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "보통 소나기",
    82: "강한 소나기",
    85: "약한 눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "약한 우박을 동반한 뇌우",
    99: "강한 우박을 동반한 뇌우",
}


def describe_weather_code(code: int) -> str:
    return WEATHER_CODE_KO.get(code, f"날씨 코드 {code}")
