from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["AIRWISE_SKIP_DOTENV"] = "1"
os.environ.pop("GEMINI_API_KEY", None)

from app.config import Settings, get_settings  # noqa: E402
from app.llm import Narrator  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import SlidingWindowLimiter  # noqa: E402


def air_payload(pm25: float = 150.0, pm10: float = 220.0) -> dict:
    """Open-Meteo style payload: 48 hourly points with a clear daily dip."""
    times, a, b = [], [], []
    for day in ("2026-11-18", "2026-11-19"):
        for hour in range(24):
            times.append(f"{day}T{hour:02d}:00")
            factor = 0.5 if 12 <= hour <= 16 else (1.4 if 6 <= hour <= 9 else 1.0)
            a.append(round(pm25 * factor, 1))
            b.append(round(pm10 * factor, 1))
    return {
        "current": {
            "time": "2026-11-18T05:00",
            "pm2_5": pm25,
            "pm10": pm10,
            "nitrogen_dioxide": 40.0,
            "ozone": 30.0,
        },
        "hourly": {"time": times, "pm2_5": a, "pm10": b},
    }


GEOCODE_PAYLOAD = {
    "results": [
        {"name": "Delhi", "latitude": 28.65, "longitude": 77.23, "admin1": "Delhi", "country": "India"}
    ]
}


def make_handler(payload=None, geocode=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in request.url.host:
            return httpx.Response(status, json=geocode or GEOCODE_PAYLOAD)
        return httpx.Response(status, json=payload or air_payload())

    return handler


@pytest.fixture
def make_client():
    clients: list[TestClient] = []

    def factory(handler=None, generate=None, rate: int = 100, ask_rate: int = 100) -> TestClient:
        get_settings.cache_clear()
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        state = client.app.state
        state.http = httpx.AsyncClient(transport=httpx.MockTransport(handler or make_handler()))
        settings: Settings = state.settings
        state.narrator = Narrator(settings, generate=generate)
        state.limiters = {
            "general": SlidingWindowLimiter(rate),
            "ask": SlidingWindowLimiter(ask_rate),
        }
        return client

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


VALID_BODY = {
    "location": {"lat": 28.65, "lon": 77.23, "name": "Delhi"},
    "profile": {
        "commute_mode": "car",
        "commute_km": 12,
        "has_children": True,
        "has_elderly": False,
        "has_respiratory_condition": False,
        "has_purifier": False,
        "cooking_fuel": "lpg",
        "exercises_outdoors": True,
    },
}
