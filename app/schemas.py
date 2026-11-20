"""Request and response models. All user input is validated here."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CommuteMode = Literal["car", "two_wheeler", "public_transport", "walk_cycle", "work_from_home"]
CookingFuel = Literal["lpg", "induction", "biomass"]
Category = Literal["routine", "indoor", "alternative"]

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f<>]")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", _CONTROL_CHARS.sub(" ", value)).strip()


class Profile(BaseModel):
    """Lifestyle inputs. Used for this request only and never stored."""

    model_config = ConfigDict(extra="forbid")

    commute_mode: CommuteMode = "public_transport"
    commute_km: float = Field(default=8.0, ge=0, le=150, description="One-way distance in km")
    has_children: bool = False
    has_elderly: bool = False
    has_respiratory_condition: bool = False
    has_purifier: bool = False
    cooking_fuel: CookingFuel = "lpg"
    exercises_outdoors: bool = False


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def _tidy_name(cls, value: str | None) -> str | None:
        return (_clean_text(value) or None) if value else None


class AssistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: Location
    profile: Profile = Field(default_factory=Profile)
    use_ai: bool = True


class AskRequest(AssistRequest):
    question: str = Field(min_length=3, max_length=300)

    @field_validator("question")
    @classmethod
    def _tidy_question(cls, value: str) -> str:
        cleaned = _clean_text(value)
        if len(cleaned) < 3:
            raise ValueError("question is too short")
        return cleaned


class Action(BaseModel):
    id: str
    category: Category
    priority: int = Field(ge=1, le=3, description="1 = do this first")
    title: str
    why: str
    impact: str
    co2_saved_kg_week: float | None = None


class AqiOut(BaseModel):
    index: int
    category: str
    level: int
    dominant: str
    pm25: float | None
    pm10: float | None
    no2: float | None
    o3: float | None
    observed_at: str


class WindowOut(BaseModel):
    best_time: str
    best_aqi: int
    worst_time: str
    worst_aqi: int


class ImpactSummary(BaseModel):
    weekly_commute_co2_kg: float
    best_option_saving_kg: float
    best_option_saving_pct: int


class AssistResponse(BaseModel):
    place: str
    aqi: AqiOut
    headline: str
    outdoor_window: WindowOut | None
    actions: list[Action]
    impact: ImpactSummary
    coach_note: str
    ai_generated: bool
    data_source: str
    disclaimer: str


class AskResponse(BaseModel):
    answer: str
    ai_generated: bool


class PlaceOut(BaseModel):
    name: str
    region: str
    lat: float
    lon: float


class GeocodeResponse(BaseModel):
    places: list[PlaceOut]
