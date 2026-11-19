from __future__ import annotations

from datetime import datetime

import pytest

from app import advisor
from app.aqi import build_outlook, compute_aqi
from app.schemas import Profile


def outlook_for(pm25: float):
    times = [f"2026-11-18T{h:02d}:00" for h in range(24)]
    series = [pm25 * (0.4 if 13 <= h <= 15 else 1.2 if 7 <= h <= 9 else 1.0) for h in range(24)]
    return build_outlook(times, series, [None] * 24, datetime(2026, 11, 18, 0))


def plan(profile: Profile, pm25: float):
    aqi = compute_aqi(pm25, None)
    return aqi, advisor.build_actions(profile, aqi, outlook_for(pm25))


def ids(actions):
    return {a.id for a in actions}


def test_commute_emissions_math():
    assert advisor.weekly_commute_co2("car", 10) == pytest.approx(0.17 * 10 * 2 * 5)
    assert advisor.weekly_commute_co2("walk_cycle", 10) == 0
    assert advisor.weekly_commute_co2("work_from_home", 50) == 0


def test_severe_air_triggers_protective_actions():
    _, actions = plan(Profile(exercises_outdoors=True, commute_mode="car"), 300)
    assert {"mask", "workout-indoors", "ventilation", "purifier-get"} <= ids(actions)


def test_good_air_encourages_outdoors():
    _, actions = plan(Profile(), 10)
    assert "good-day" in ids(actions)
    assert "mask" not in ids(actions)
    assert "purifier-get" not in ids(actions)


def test_purifier_owner_is_told_to_run_it():
    _, actions = plan(Profile(has_purifier=True), 200)
    assert "purifier-on" in ids(actions)
    assert "purifier-get" not in ids(actions)


def test_household_specific_actions():
    _, actions = plan(Profile(has_children=True, has_elderly=True, has_respiratory_condition=True), 200)
    assert {"kids-play", "elder-care", "action-plan"} <= ids(actions)


def test_induction_cooks_skip_chimney_tip():
    _, actions = plan(Profile(cooking_fuel="induction"), 200)
    assert "cook-vent" not in ids(actions)


def test_biomass_gets_clean_fuel_advice_first_tier():
    _, actions = plan(Profile(cooking_fuel="biomass"), 200)
    clean = next(a for a in actions if a.id == "clean-fuel")
    assert clean.priority == 1


def test_driver_gets_quantified_alternatives():
    _, actions = plan(Profile(commute_mode="car", commute_km=10), 200)
    transit = next(a for a in actions if a.id == "transit-3days")
    assert transit.co2_saved_kg_week == pytest.approx((0.17 - 0.03) * 10 * 2 * 3, abs=0.05)
    assert "kg CO2e" in transit.impact


def test_work_from_home_has_no_mask_advice():
    _, actions = plan(Profile(commute_mode="work_from_home"), 300)
    assert "mask" not in ids(actions)


def test_actions_sorted_and_unique():
    _, actions = plan(Profile(commute_mode="car", has_children=True, exercises_outdoors=True), 250)
    priorities = [a.priority for a in actions]
    assert priorities == sorted(priorities)
    assert len(ids(actions)) == len(actions)
    assert all(1 <= p <= 3 for p in priorities)


def test_every_action_explains_why_and_impact():
    for pm in (10, 50, 100, 200, 300):
        _, actions = plan(Profile(commute_mode="car", has_children=True, exercises_outdoors=True), pm)
        assert actions
        for a in actions:
            assert a.title and a.why and a.impact


def test_outdoor_window_action_cites_numbers():
    _, actions = plan(Profile(), 150)
    window = next(a for a in actions if a.id == "outdoor-window")
    assert "AQI" in window.impact


def test_impact_summary():
    profile = Profile(commute_mode="car", commute_km=10)
    _, actions = plan(profile, 200)
    impact = advisor.build_impact(profile, actions)
    assert impact.weekly_commute_co2_kg == pytest.approx(17.0)
    assert 0 < impact.best_option_saving_kg <= impact.weekly_commute_co2_kg
    assert 0 < impact.best_option_saving_pct <= 100


def test_impact_zero_for_walkers():
    profile = Profile(commute_mode="walk_cycle")
    _, actions = plan(profile, 100)
    impact = advisor.build_impact(profile, actions)
    assert impact.weekly_commute_co2_kg == 0
    assert impact.best_option_saving_pct == 0


def test_fallback_note_mentions_aqi_and_first_step():
    aqi, actions = plan(Profile(), 200)
    note = advisor.fallback_note("Delhi", aqi, None, actions)
    assert "Delhi" in note and str(aqi.index) in note and actions[0].title in note


def test_fallback_answer_matches_keywords():
    _, actions = plan(Profile(), 250)
    answer = advisor.fallback_answer("should I wear a mask outside", actions)
    assert "N95" in answer


def test_fallback_answer_handles_unknown_topics():
    _, actions = plan(Profile(), 250)
    assert "offline" in advisor.fallback_answer("zzzz qqqq", actions)
