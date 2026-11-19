from __future__ import annotations

from datetime import datetime

import pytest

from app.aqi import build_outlook, compute_aqi, hour_label


@pytest.mark.parametrize(
    ("pm25", "expected_index", "category"),
    [
        (0, 0, "Good"),
        (30, 50, "Good"),
        (45, 75, "Satisfactory"),
        (60, 100, "Satisfactory"),
        (90, 200, "Moderate"),
        (105, 250, "Poor"),
        (120, 300, "Poor"),
        (185, 350, "Very Poor"),
        (250, 400, "Very Poor"),
        (380, 500, "Severe"),
        (900, 500, "Severe"),
    ],
)
def test_pm25_breakpoints(pm25, expected_index, category):
    result = compute_aqi(pm25, None)
    assert result.index == expected_index
    assert result.category == category
    assert result.dominant == "PM2.5"


def test_worst_pollutant_dominates():
    result = compute_aqi(pm25=20, pm10=300)
    assert result.dominant == "PM10"
    assert result.index == 250


def test_pm10_only_is_accepted():
    assert compute_aqi(None, 100).index == 100


def test_requires_a_reading():
    with pytest.raises(ValueError):
        compute_aqi(None, None)


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_rejects_invalid_concentrations(bad):
    with pytest.raises(ValueError):
        compute_aqi(bad, None)


def test_levels_are_monotonic():
    levels = [compute_aqi(c, None).level for c in range(0, 400, 5)]
    assert levels == sorted(levels)


def test_hour_label_is_portable():
    assert hour_label(datetime(2026, 1, 1, 0)) == "12 AM"
    assert hour_label(datetime(2026, 1, 1, 7)) == "7 AM"
    assert hour_label(datetime(2026, 1, 1, 12)) == "12 PM"
    assert hour_label(datetime(2026, 1, 1, 15)) == "3 PM"


def _series(hours):
    times = [f"2026-11-18T{h:02d}:00" for h in range(hours)]
    return times


def test_outlook_picks_best_and_worst():
    times = _series(24)
    pm = [100.0] * 24
    pm[14], pm[7] = 30.0, 200.0
    outlook = build_outlook(times, pm, [None] * 24, datetime(2026, 11, 18, 0, 20))
    assert outlook is not None
    assert outlook.best.time.hour == 14
    assert outlook.worst.time.hour == 7
    assert outlook.best.aqi < outlook.worst.aqi


def test_outlook_ignores_past_hours_and_gaps():
    times = _series(24)
    pm = [None if h % 2 else 80.0 for h in range(24)]
    pm[2] = 10.0  # in the past relative to "now"
    outlook = build_outlook(times, pm, [None] * 24, datetime(2026, 11, 18, 5, 0))
    assert outlook is not None
    assert outlook.best.time.hour >= 5


def test_outlook_needs_enough_points():
    assert build_outlook(_series(3), [50.0] * 3, [None] * 3, datetime(2026, 11, 18, 0)) is None


def test_outlook_survives_malformed_times():
    times = ["garbage"] * 10
    assert build_outlook(times, [50.0] * 10, [None] * 10, datetime(2026, 11, 18, 0)) is None
