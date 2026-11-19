"""Check that Gemini works with your key: python scripts/check_ai.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402


async def main() -> int:
    s = get_settings()
    print(f"key found : {'yes' if s.gemini_api_key else 'NO (check .env in project root)'}")
    print(f"model     : {s.gemini_model}")
    if not s.gemini_api_key:
        return 1
    try:
        from google import genai
    except ImportError:
        print("google-genai missing -> run: pip install -r requirements.txt")
        return 1
    client = genai.Client(api_key=s.gemini_api_key)
    try:
        r = await client.aio.models.generate_content(model=s.gemini_model, contents="Reply with the word OK.")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED    : {type(exc).__name__}: {str(exc)[:300].replace(s.gemini_api_key, '***')}")
        return 1
    print(f"SUCCESS   : {r.text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
