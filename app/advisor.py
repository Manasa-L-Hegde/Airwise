"""Rule-based personalised plan: routines, indoor air hacks, greener alternatives.

Everything here is deterministic and unit-tested. The GenAI layer only narrates
these facts; it never invents numbers or advice.
"""

from __future__ import annotations

import re

from app.aqi import Aqi, Outlook, hour_label
from app.schemas import Action, ImpactSummary, Profile

# Approximate tailpipe/grid emissions in kg CO2e per passenger-km (typical India averages).
EMISSION_KG_PER_KM = {
    "car": 0.17,
    "two_wheeler": 0.04,
    "public_transport": 0.03,
    "walk_cycle": 0.0,
    "work_from_home": 0.0,
}
WORK_DAYS = 5

HEADLINES = {
    0: "Air is good today. Enjoy it and let fresh air into your home.",
    1: "Air is acceptable. Unusually sensitive people may notice effects after long outdoor effort.",
    2: "Moderate pollution. Sensitive people should cut back on long or heavy outdoor activity.",
    3: "Poor air. Limit prolonged outdoor exertion and protect your commute and your home air.",
    4: "Very poor air. Skip outdoor exercise, wear a fitted N95 outdoors and run indoor air cleaning.",
    5: "Severe air. Stay indoors as much as you can and treat every outdoor trip as exposure to manage.",
}

DISCLAIMER = (
    "General wellbeing guidance, not medical advice. If you have symptoms such as "
    "breathlessness or chest tightness, follow your doctor's advice or seek care."
)


def weekly_commute_co2(mode: str, km: float, days: int = WORK_DAYS) -> float:
    """Round-trip commute emissions in kg CO2e for `days` working days."""
    return EMISSION_KG_PER_KM[mode] * km * 2 * days


def _act(
    id_: str,
    category: str,
    priority: int,
    title: str,
    why: str,
    impact: str,
    co2: float | None = None,
) -> Action:
    return Action(
        id=id_,
        category=category,  # type: ignore[arg-type]
        priority=priority,
        title=title,
        why=why,
        impact=impact,
        co2_saved_kg_week=None if co2 is None else round(co2, 1),
    )


def build_actions(profile: Profile, aqi: Aqi, outlook: Outlook | None) -> list[Action]:
    level = aqi.level
    sensitive = profile.has_children or profile.has_elderly or profile.has_respiratory_condition
    commutes_outdoors = profile.commute_mode != "work_from_home"
    acts: list[Action] = []

    best = hour_label(outlook.best.time) if outlook else None
    worst = hour_label(outlook.worst.time) if outlook else None

    # ---- Daily routine -------------------------------------------------------------
    if outlook and level >= 2 and outlook.worst.aqi - outlook.best.aqi >= 15:
        acts.append(_act(
            "outdoor-window", "routine", 1,
            f"Do outdoor errands around {best}, not {worst}",
            "Pollution rises and falls through the day, so timing changes how much you breathe in.",
            f"Modelled air near you is about AQI {outlook.best.aqi} around {best} "
            f"versus {outlook.worst.aqi} around {worst}.",
        ))

    if level >= 3 and commutes_outdoors:
        acts.append(_act(
            "mask", "routine", 1 if (level >= 4 or sensitive) else 2,
            "Wear a fitted N95/FFP2 mask outdoors",
            "Fine particles (PM2.5) reach deep into the lungs; "
            "loose cloth or surgical masks let most through.",
            "A well-fitted N95 blocks at least 95% of fine particles. Fit matters: no gaps at nose or chin.",
        ))

    if profile.exercises_outdoors:
        if level >= 3:
            acts.append(_act(
                "workout-indoors", "routine", 1,
                "Move today's workout indoors",
                "Hard exercise multiplies how much air you breathe, and so how many particles you inhale.",
                "Training indoors removes the highest-exposure activity of your day.",
            ))
        elif level == 2:
            acts.append(_act(
                "workout-ease", "routine", 2,
                "Keep outdoor exercise short and easy, in the cleanest hour",
                "Moderate air is fine for most people, but heavy effort still raises exposure.",
                f"Aim for around {best}." if best else "Choose the hour with the lowest pollution.",
            ))

    if profile.has_children and level >= 2:
        acts.append(_act(
            "kids-play", "routine", 1 if level >= 3 else 2,
            "Swap park time for indoor play" if level >= 3
            else "Keep outdoor play short and away from busy roads",
            "Children breathe faster for their size and their lungs are still developing.",
            "Less time near traffic and during peak hours cuts the dose they inhale.",
        ))
    if profile.has_elderly and level >= 3:
        acts.append(_act(
            "elder-care", "routine", 2,
            "Keep older family members indoors for non-essential trips",
            "Older adults are more likely to feel heart and lung effects of polluted air.",
            "Fewer outdoor hours means fewer high-exposure hours.",
        ))
    if profile.has_respiratory_condition and level >= 2:
        acts.append(_act(
            "action-plan", "routine", 1,
            "Follow your doctor's action plan and keep prescribed medicines within reach",
            "Pollution can trigger flare-ups in asthma and similar conditions.",
            "Being prepared shortens the time to relief if symptoms start.",
        ))
    if level >= 3:
        acts.append(_act(
            "watch-symptoms", "routine", 3,
            "Watch for coughing, throat irritation or breathlessness and rest if they appear",
            "Poor air commonly causes irritation even in healthy people.",
            "Speak to a doctor if symptoms persist or worsen.",
        ))
    if level <= 1:
        acts.append(_act(
            "good-day", "routine", 2,
            "Good day to exercise outdoors and open the windows",
            "Fresh outdoor air dilutes pollutants that build up indoors from cooking and cleaning.",
            "Air this clean is the best time to flush your home.",
        ))

    # ---- Indoor air ----------------------------------------------------------------
    if level >= 3:
        acts.append(_act(
            "ventilation", "indoor", 1,
            f"Keep windows shut around {worst}; air the home around {best}" if outlook
            else "Keep windows mostly closed while outdoor air is poor",
            "Indoor air follows outdoor air, so ventilate when the outside is cleanest.",
            "Closing up at the worst hours keeps indoor particle levels lower.",
        ))
    elif level == 2:
        acts.append(_act(
            "ventilation", "indoor", 2,
            f"Ventilate your home around {best}" if best else "Ventilate in the cleanest hour",
            "Short airing in cleaner hours removes stale indoor air without inviting much pollution.",
            "A 10-15 minute cross-draught is enough.",
        ))
    else:
        acts.append(_act(
            "ventilation", "indoor", 2,
            "Cross-ventilate for 10-15 minutes",
            "Open windows on opposite sides to flush cooking fumes and dust.",
            "Cheap, free and effective when outdoor air is clean.",
        ))

    if level >= 3:
        if profile.has_purifier:
            acts.append(_act(
                "purifier-on", "indoor", 1,
                "Run your purifier on auto in the room you use most, doors and windows closed",
                "A HEPA purifier removes fine particles that get in around closed windows.",
                "Replace or clean filters on schedule; a clogged filter does little.",
            ))
        else:
            acts.append(_act(
                "purifier-get", "indoor", 2,
                "Consider a HEPA purifier sized for your room",
                "Choose a clean air delivery rate (CADR) of roughly two-thirds "
                "of the room's floor area in sq ft.",
                "Until then, a box fan with a MERV-13 filter taped to it is a low-cost option.",
            ))

    if profile.cooking_fuel != "induction" and level >= 2:
        acts.append(_act(
            "cook-vent", "indoor", 2,
            "Use the chimney or exhaust fan while cooking, and for 10 minutes after",
            "Cooking, especially frying, adds fine particles to indoor air.",
            "Venting moves them outside instead of letting them linger.",
        ))
    if level >= 2:
        acts.append(_act(
            "no-smoke", "indoor", 3,
            "Skip incense, mosquito coils and candles for now",
            "They release fine particles into rooms you are trying to keep clean.",
            "Removes a source of indoor PM2.5.",
        ))
    acts.append(_act(
        "wet-clean", "indoor", 3,
        "Wet-mop and wipe with a damp cloth instead of dry sweeping",
        "Dry sweeping lifts settled dust back into the air.",
        "Keeps dust out of the air you breathe.",
    ))
    acts.append(_act(
        "plants-myth", "indoor", 3,
        "Don't rely on houseplants to clean the air",
        "Plants add comfort, but you would need a very large number to affect air quality.",
        "Spend that effort on ventilation timing and filtration instead.",
    ))

    # ---- Greener alternatives ------------------------------------------------------
    km, mode = profile.commute_km, profile.commute_mode
    car_week = weekly_commute_co2("car", km)
    if profile.cooking_fuel == "biomass":
        acts.append(_act(
            "clean-fuel", "alternative", 1,
            "Move from wood or biomass to LPG or induction cooking",
            "Biomass smoke is one of the largest sources of household fine particles.",
            "Cleaner fuel cuts indoor smoke exposure and also reduces local outdoor pollution.",
        ))
    if mode == "car" and km > 0:
        transit = (EMISSION_KG_PER_KM["car"] - EMISSION_KG_PER_KM["public_transport"]) * km * 2 * 3
        acts.append(_act(
            "transit-3days", "alternative", 2,
            "Take the metro or bus 3 days a week",
            "Public transport carries many people per vehicle, so each trip adds far less pollution.",
            f"Saves about {transit:.1f} kg CO2e a week on your {km:g} km commute.",
            transit,
        ))
        wfh = weekly_commute_co2("car", km, days=1)
        acts.append(_act(
            "wfh-day", "alternative", 2,
            "Work from home one day a week, or on the worst-air days",
            "A trip not taken is the cleanest trip, and it keeps you out of traffic fumes.",
            f"Saves about {wfh:.1f} kg CO2e for each day you skip the drive.",
            wfh,
        ))
        pool = car_week * 0.5
        acts.append(_act(
            "carpool", "alternative", 3,
            "Carpool with one colleague",
            "Two people in one car halve the emissions per person.",
            f"Saves about {pool:.1f} kg CO2e a week.",
            pool,
        ))
    elif mode == "two_wheeler":
        if 0 < km <= 5:
            saving = weekly_commute_co2("two_wheeler", km)
            acts.append(_act(
                "walk-short", "alternative", 2,
                "Walk or cycle trips under 5 km",
                "Short trips are where engines run least efficiently.",
                f"Saves about {saving:.1f} kg CO2e a week and builds daily activity.",
                saving,
            ))
        acts.append(_act(
            "puc-service", "alternative", 3,
            "Keep your vehicle serviced and its pollution-under-control certificate current",
            "A poorly tuned engine emits much more per kilometre.",
            "Cuts your own tailpipe contribution to street-level pollution.",
        ))
    elif mode == "public_transport":
        avoided = (EMISSION_KG_PER_KM["car"] - EMISSION_KG_PER_KM["public_transport"]) * km * 2 * WORK_DAYS
        acts.append(_act(
            "keep-transit", "alternative", 3,
            "Keep taking public transport. It is already your biggest win",
            "You share a vehicle with many others, which keeps per-person emissions low.",
            f"Versus driving, your commute avoids about {avoided:.1f} kg CO2e a week.",
        ))
    elif mode == "walk_cycle":
        avoided = car_week
        acts.append(_act(
            "quiet-lanes", "alternative", 2,
            "On poor-air days choose quieter side streets and ease your pace",
            "Roadside air is dirtier, and harder effort means deeper breathing.",
            f"Versus driving, you avoid about {avoided:.1f} kg CO2e a week.",
        ))
    elif mode == "work_from_home":
        acts.append(_act(
            "wfh-win", "alternative", 3,
            "Working from home already removes your commute emissions",
            "No commute means no tailpipe emissions and no traffic exposure.",
            f"Versus driving 10 trips a week, that is about {car_week:.1f} kg CO2e avoided for a "
            f"{km:g} km commute.",
        ))

    if mode in {"car", "two_wheeler"}:
        acts.append(_act(
            "no-idling", "alternative", 3,
            "Switch the engine off at long stops",
            "An idling engine burns fuel and emits pollutants while going nowhere.",
            "Even 1-2 minutes saved per stop adds up across a week of commuting.",
        ))
    acts.append(_act(
        "no-burning", "alternative", 2 if level >= 3 else 3,
        "Don't burn leaves, garbage or wood for warmth; layer up or use an electric heater",
        "Open burning releases large amounts of fine particles right where people live.",
        "One less fire near your home improves the air for the whole street.",
    ))

    # Drop duplicate ids (ventilation variants are mutually exclusive by construction).
    seen: set[str] = set()
    unique = [a for a in acts if not (a.id in seen or seen.add(a.id))]
    return sorted(unique, key=lambda a: (a.priority, a.category, a.id))


def build_impact(profile: Profile, actions: list[Action]) -> ImpactSummary:
    weekly = weekly_commute_co2(profile.commute_mode, profile.commute_km)
    savings = [a.co2_saved_kg_week for a in actions if a.co2_saved_kg_week]
    best = max(savings, default=0.0)
    pct = round(best / weekly * 100) if weekly > 0 else 0
    return ImpactSummary(
        weekly_commute_co2_kg=round(weekly, 1),
        best_option_saving_kg=round(best, 1),
        best_option_saving_pct=min(pct, 100),
    )


def fallback_note(place: str, aqi: Aqi, outlook: Outlook | None, actions: list[Action]) -> str:
    """Deterministic summary used whenever the LLM is unavailable."""
    parts = [
        f"{place} is at AQI {aqi.index} ({aqi.category}), driven mainly by {aqi.dominant}.",
        HEADLINES[aqi.level],
    ]
    if actions:
        parts.append(f"Your best first step: {actions[0].title}. {actions[0].impact}")
    return " ".join(parts)


_WORD = re.compile(r"[a-z0-9]+")


def fallback_answer(question: str, actions: list[Action]) -> str:
    """Keyword-match a question against the plan when the LLM is unavailable."""
    q = set(_WORD.findall(question.lower()))
    scored = []
    for action in actions:
        words = set(_WORD.findall(f"{action.title} {action.why}".lower()))
        overlap = len(q & words - {"the", "a", "to", "and", "of", "in", "my", "i", "do", "is"})
        if overlap:
            scored.append((overlap, action))
    scored.sort(key=lambda s: -s[0])
    if not scored:
        return (
            "The AI assistant is offline, so I can only share your plan. "
            "Try asking about masks, windows, purifiers, exercise, children or commuting."
        )
    top = scored[:2]
    return "The AI assistant is offline, but your plan covers this: " + " ".join(
        f"{a.title}. {a.why}" for _, a in top
    )
