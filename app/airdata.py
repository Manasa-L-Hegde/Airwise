"""Open-Meteo clients: place search and air quality (free, no API key)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
DATA_SOURCE = "Open-Meteo Air Quality API (CAMS model data)"


class AirDataError(RuntimeError):
    """Raised when upstream data is unreachable or unusable."""


@dataclass(frozen=True)
class Place:
    name: str
    region: str
    lat: float
    lon: float


@dataclass(frozen=True)
class AirReading:
    observed_at: datetime
    pm25: float | None
    pm10: float | None
    no2: float | None
    o3: float | None
    times: tuple[str, ...] = ()
    pm25_series: tuple[float | None, ...] = ()
    pm10_series: tuple[float | None, ...] = ()


class TTLCache:
    """Tiny in-memory cache with expiry and a size cap."""

    def __init__(self, ttl_s: float, max_items: int = 512) -> None:
        self._ttl = ttl_s
        self._max = max_items
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        hit = self._data.get(key)
        if hit is None:
            return None
        expires, value = hit
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            self._data.pop(oldest, None)
        self._data[key] = (time.monotonic() + self._ttl, value)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _series(values: Any) -> tuple[float | None, ...]:
    return tuple(_num(v) for v in values) if isinstance(values, list) else ()


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AirDataError(f"upstream request failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise AirDataError("unexpected upstream payload")
    return payload


async def search_places(client: httpx.AsyncClient, query: str, count: int = 5) -> list[Place]:
    payload = await _get_json(
        client, GEOCODE_URL, {"name": query, "count": count, "language": "en", "format": "json"}
    )
    places: list[Place] = []
    for item in payload.get("results") or []:
        try:
            lat, lon = float(item["latitude"]), float(item["longitude"])
            name = str(item["name"])[:80]
        except (KeyError, TypeError, ValueError):
            continue
        region = ", ".join(str(item[k]) for k in ("admin1", "country") if item.get(k))
        places.append(Place(name=name, region=region[:80], lat=lat, lon=lon))
    return places


async def fetch_air(
    client: httpx.AsyncClient, lat: float, lon: float, cache: TTLCache | None = None
) -> AirReading:
    key = (round(lat, 2), round(lon, 2))
    if cache is not None:
        cached = cache.get(key)
        if isinstance(cached, AirReading):
            return cached

    payload = await _get_json(
        client,
        AIR_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "current": "pm10,pm2_5,nitrogen_dioxide,ozone",
            "hourly": "pm2_5,pm10",
            "forecast_days": 2,
            "timezone": "auto",
        },
    )
    current = payload.get("current")
    if not isinstance(current, dict):
        raise AirDataError("no current air data for this location")
    pm25, pm10 = _num(current.get("pm2_5")), _num(current.get("pm10"))
    if pm25 is None and pm10 is None:
        raise AirDataError("no particulate data for this location")
    try:
        observed = datetime.fromisoformat(str(current["time"]))
    except (KeyError, ValueError) as exc:
        raise AirDataError("missing observation time") from exc

    raw_hourly = payload.get("hourly")
    hourly: dict[str, Any] = raw_hourly if isinstance(raw_hourly, dict) else {}
    times = hourly.get("time")
    reading = AirReading(
        observed_at=observed,
        pm25=pm25,
        pm10=pm10,
        no2=_num(current.get("nitrogen_dioxide")),
        o3=_num(current.get("ozone")),
        times=tuple(str(t) for t in times) if isinstance(times, list) else (),
        pm25_series=_series(hourly.get("pm2_5")),
        pm10_series=_series(hourly.get("pm10")),
    )
    if cache is not None:
        cache.set(key, reading)
    return reading
