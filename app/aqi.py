"""PM-based Indian National AQI (CPCB breakpoints) and an hourly outlook.

The official CPCB index needs several pollutants. We use the particulate
sub-indices (PM2.5 and PM10), which dominate winter smog, and take the worst
one as the headline value, exactly as the CPCB method does.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

# (upper concentration in ug/m3, upper index) per CPCB band.
_PM25 = ((30, 50), (60, 100), (90, 200), (120, 300), (250, 400), (380, 500))
_PM10 = ((50, 50), (100, 100), (250, 200), (350, 300), (430, 400), (510, 500))

_BAND_LIMITS = (50, 100, 200, 300, 400, 500)
CATEGORIES = ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe")


@dataclass(frozen=True)
class Aqi:
    index: int
    category: str
    level: int  # 0 (Good) .. 5 (Severe)
    dominant: str


def _sub_index(conc: float, table: Sequence[tuple[int, int]]) -> float:
    """Piecewise-linear sub-index for one pollutant."""
    if not math.isfinite(conc) or conc < 0:
        raise ValueError("concentration must be a non-negative, finite number")
    prev_c, prev_i = 0.0, 0.0
    for hi_c, hi_i in table:
        if conc <= hi_c:
            return prev_i + (conc - prev_c) * (hi_i - prev_i) / (hi_c - prev_c)
        prev_c, prev_i = float(hi_c), float(hi_i)
    return 500.0


def compute_aqi(pm25: float | None, pm10: float | None) -> Aqi:
    """Return the AQI from whichever particulate readings are available."""
    subs: dict[str, float] = {}
    if pm25 is not None:
        subs["PM2.5"] = _sub_index(pm25, _PM25)
    if pm10 is not None:
        subs["PM10"] = _sub_index(pm10, _PM10)
    if not subs:
        raise ValueError("at least one of pm25 or pm10 is required")
    dominant = max(subs, key=lambda k: subs[k])
    index = min(500, round(subs[dominant]))
    level = min(bisect_left(_BAND_LIMITS, index), len(CATEGORIES) - 1)
    return Aqi(index=index, category=CATEGORIES[level], level=level, dominant=dominant)


@dataclass(frozen=True)
class HourPoint:
    time: datetime
    aqi: int


@dataclass(frozen=True)
class Outlook:
    best: HourPoint
    worst: HourPoint


def hour_label(moment: datetime) -> str:
    """12-hour clock label such as '7 AM' (portable, no strftime flags)."""
    hour12 = moment.hour % 12 or 12
    return f"{hour12} {'AM' if moment.hour < 12 else 'PM'}"


def build_outlook(
    times: Sequence[str],
    pm25: Sequence[float | None],
    pm10: Sequence[float | None],
    now: datetime,
    horizon: int = 24,
    min_points: int = 6,
) -> Outlook | None:
    """Find the cleanest and dirtiest hours in the next `horizon` hours."""
    start = now.replace(minute=0, second=0, microsecond=0)
    points: list[HourPoint] = []
    for i, raw in enumerate(times):
        if len(points) >= horizon:
            break
        try:
            moment = datetime.fromisoformat(raw)
            a = pm25[i] if i < len(pm25) else None
            b = pm10[i] if i < len(pm10) else None
            if moment < start or (a is None and b is None):
                continue
            points.append(HourPoint(moment, compute_aqi(a, b).index))
        except (ValueError, TypeError):
            continue
    if len(points) < min_points:
        return None
    best = min(points, key=lambda p: (p.aqi, p.time))
    worst = max(points, key=lambda p: (p.aqi, -p.time.timestamp()))
    return Outlook(best=best, worst=worst)
