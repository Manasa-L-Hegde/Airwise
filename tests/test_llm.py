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


def test_status_and_last_error_reporting():
    assert Narrator(SETTINGS).status == "no_key"

    async def boom(system, prompt):
        raise RuntimeError("x")

    narrator = Narrator(SETTINGS, boom)
    assert narrator.status == "ready" and narrator.last_error is None
    run(narrator.coach_note(FACTS))
    assert narrator.last_error == "RuntimeError"


def test_empty_response_is_reported():
    async def empty(system, prompt):
        return ""

    narrator = Narrator(SETTINGS, empty)
    assert run(narrator.coach_note(FACTS)) is None
    assert narrator.last_error == "EmptyResponse"


def test_config_disables_thinking_only_for_flash_25():
    from google.genai import types

    from app.llm import _config

    assert _config(types, "gemini-2.5-flash", "s").thinking_config.thinking_budget == 0
    assert _config(types, "gemini-2.5-pro", "s").thinking_config is None
    assert _config(types, "gemini-2.0-flash", "s").thinking_config is None


class _HttpError(Exception):
    def __init__(self, code):
        super().__init__("err")
        self.code = code


def test_retries_once_on_transient_error(monkeypatch):
    monkeypatch.setattr("app.llm.RETRY_DELAY_S", 0)
    calls = []

    async def flaky(system, prompt):
        calls.append(1)
        if len(calls) == 1:
            raise _HttpError(503)
        return "Recovered answer."

    assert run(Narrator(SETTINGS, flaky).coach_note(FACTS)) == "Recovered answer."
    assert len(calls) == 2


def test_no_retry_on_client_error(monkeypatch):
    monkeypatch.setattr("app.llm.RETRY_DELAY_S", 0)
    calls = []

    async def bad_key(system, prompt):
        calls.append(1)
        raise _HttpError(400)

    narrator = Narrator(SETTINGS, bad_key)
    assert run(narrator.coach_note(FACTS)) is None
    assert len(calls) == 1 and "400" in narrator.last_error


def test_gives_up_after_one_retry(monkeypatch):
    monkeypatch.setattr("app.llm.RETRY_DELAY_S", 0)
    calls = []

    async def always(system, prompt):
        calls.append(1)
        raise _HttpError(429)

    assert run(Narrator(SETTINGS, always).coach_note(FACTS)) is None
    assert len(calls) == 2
