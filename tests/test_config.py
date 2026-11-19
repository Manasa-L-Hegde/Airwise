from __future__ import annotations

import os

from app import config


def test_dotenv_loads_keys_without_overriding_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nGEMINI_API_KEY="abc123"\nexport GEMINI_MODEL=m1\nEMPTY=\nKEEP=file\n')
    monkeypatch.delenv("AIRWISE_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("KEEP", "real")
    config.load_dotenv(env)
    try:
        assert os.environ["GEMINI_API_KEY"] == "abc123"
        assert os.environ["GEMINI_MODEL"] == "m1"
        assert os.environ["KEEP"] == "real"
        assert "EMPTY" not in os.environ
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GEMINI_MODEL", None)


def test_dotenv_missing_file_is_fine(tmp_path, monkeypatch):
    monkeypatch.delenv("AIRWISE_SKIP_DOTENV", raising=False)
    config.load_dotenv(tmp_path / "nope.env")
