"""Glue: turn raw readings and a profile into a complete report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import advisor
from app.airdata import AirReading
from app.aqi import Aqi, Outlook, build_outlook, compute_aqi, hour_label
from app.schemas import Action, ImpactSummary, Profile, WindowOut

DEFAULT_PLACE = "your area"


@dataclass(frozen=True)
class Report:
    place: str
    reading: AirReading
    aqi: Aqi
    outlook: Outlook | None
    actions: list[Action]
    impact: ImpactSummary
    headline: str


def make_report(reading: AirReading, profile: Profile, place: str | None) -> Report:
    aqi = compute_aqi(reading.pm25, reading.pm10)
    outlook = build_outlook(
        reading.times, reading.pm25_series, reading.pm10_series, reading.observed_at
    )
    actions = advisor.build_actions(profile, aqi, outlook)
    return Report(
        place=place or DEFAULT_PLACE,
        reading=reading,
        aqi=aqi,
        outlook=outlook,
        actions=actions,
        impact=advisor.build_impact(profile, actions),
        headline=advisor.HEADLINES[aqi.level],
    )


def window_out(outlook: Outlook | None) -> WindowOut | None:
    if outlook is None:
        return None
    return WindowOut(
        best_time=hour_label(outlook.best.time),
        best_aqi=outlook.best.aqi,
        worst_time=hour_label(outlook.worst.time),
        worst_aqi=outlook.worst.aqi,
    )


def llm_facts(report: Report, profile: Profile) -> dict[str, Any]:
    """Minimal, non-identifying facts handed to the LLM. No coordinates are sent."""
    window = window_out(report.outlook)
    return {
        "place": report.place,
        "aqi": report.aqi.index,
        "category": report.aqi.category,
        "dominant_pollutant": report.aqi.dominant,
        "cleanest_hour": window.best_time if window else None,
        "dirtiest_hour": window.worst_time if window else None,
        "commute": profile.commute_mode.replace("_", " "),
        "household": {
            "children": profile.has_children,
            "older_adults": profile.has_elderly,
            "breathing_condition": profile.has_respiratory_condition,
            "has_purifier": profile.has_purifier,
            "cooking_fuel": profile.cooking_fuel,
            "outdoor_exercise": profile.exercises_outdoors,
        },
        "plan": [
            {"title": a.title, "impact": a.impact} for a in report.actions[:6]
        ],
        "weekly_commute_co2_kg": report.impact.weekly_commute_co2_kg,
        "best_commute_saving_kg": report.impact.best_option_saving_kg,
    }
