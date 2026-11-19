from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.llm import SYSTEM_PROMPT, Narrator, _clean

SETTINGS = Settings(
    gemini_api_key=None,
    gemini_model="m",
    llm_timeout_s=0.2,
    http_timeout_s=1,
    cache_ttl_s=1,
    rate_limit_per_min=10,
    ask_rate_limit_per_min=10,
    trust_proxy=False,
)
FACTS = {"aqi": 180}


def run(coro):
    return asyncio.run(coro)


def test_disabled_without_key():
    narrator = Narrator(SETTINGS)
    assert not narrator.enabled
    assert run(narrator.coach_note(FACTS)) is None


def test_returns_cleaned_text():
    async def gen(system, prompt):
        return "**Wear** a `mask`. # Stay safe"

    assert run(Narrator(SETTINGS, gen).coach_note(FACTS)) == "Wear a mask. Stay safe"


def test_question_is_fenced_and_rules_sent():
    seen = {}

    async def gen(system, prompt):
        seen.update(system=system, prompt=prompt)
        return "ok"

    run(Narrator(SETTINGS, gen).answer("is it safe?", FACTS))
    assert seen["system"] == SYSTEM_PROMPT
    assert "<user_question>is it safe?</user_question>" in seen["prompt"]
    assert "untrusted" in SYSTEM_PROMPT


def test_errors_degrade_to_none():
    async def boom(system, prompt):
        raise RuntimeError("api down")

    assert run(Narrator(SETTINGS, boom).coach_note(FACTS)) is None


def test_timeout_degrades_to_none():
    async def slow(system, prompt):
        await asyncio.sleep(5)
        return "late"

    assert run(Narrator(SETTINGS, slow).coach_note(FACTS)) is None


@pytest.mark.parametrize("raw", ["", "   ", None, "***"])
def test_empty_output_is_none(raw):
    async def gen(system, prompt):
        return raw

    assert run(Narrator(SETTINGS, gen).coach_note(FACTS)) is None


def test_long_output_is_truncated_on_sentence():
    text = "This is a sentence. " * 100
    cleaned = _clean(text)
    assert cleaned is not None and len(cleaned) <= 900 and cleaned.endswith(".")
