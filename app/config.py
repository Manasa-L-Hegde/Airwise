"""Runtime configuration, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (real env vars win).

    Tiny built-in loader so local runs need no extra dependency. Skipped when
    AIRWISE_SKIP_DOTENV is set (used by the test suite).
    """
    if os.getenv("AIRWISE_SKIP_DOTENV"):
        return
    env_file = path or Path(__file__).resolve().parents[1] / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if key and value:
            os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    llm_timeout_s: float
    http_timeout_s: float
    cache_ttl_s: int
    rate_limit_per_min: int
    ask_rate_limit_per_min: int
    trust_proxy: bool


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    key = (os.getenv("GEMINI_API_KEY") or "").strip() or None
    return Settings(
        gemini_api_key=key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        llm_timeout_s=_env_float("LLM_TIMEOUT_S", 12.0),
        http_timeout_s=_env_float("HTTP_TIMEOUT_S", 8.0),
        cache_ttl_s=_env_int("CACHE_TTL_S", 600),
        rate_limit_per_min=_env_int("RATE_LIMIT_PER_MIN", 30),
        ask_rate_limit_per_min=_env_int("ASK_RATE_LIMIT_PER_MIN", 8),
        trust_proxy=_env_bool("TRUST_PROXY", False),
    )
