"""Diagnostic script for AirWise Gemini AI integration.

Checks:
1. .env file existence and formatting (ensures no .env.txt, quotes, spaces).
2. GEMINI_API_KEY presence and format (never prints the key).
3. google-genai package installation and version.
4. Model configuration and live test call to Gemini API.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("AirWise AI Diagnostic Check")
    print("=" * 60)

    # 1. Check .env file
    env_path = ROOT / ".env"
    env_txt_path = ROOT / ".env.txt"

    if env_txt_path.exists():
        print(f"[WARNING] Found '{env_txt_path.name}'! Rename it to '.env'.")

    if not env_path.exists():
        print(f"[FAIL] .env file not found at {env_path}")
        print("Please copy .env.example to .env and set GEMINI_API_KEY.")
        return 1
    print(f"[OK] .env file found at {env_path}")

    # Inspect .env syntax without revealing secret
    raw_lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    key_line = None
    for line in raw_lines:
        s = line.strip()
        if s.startswith("GEMINI_API_KEY="):
            key_line = s
            break

    if not key_line:
        print("[FAIL] GEMINI_API_KEY line not found in .env")
        return 1

    _, _, raw_val = key_line.partition("=")
    if not raw_val:
        print("[FAIL] GEMINI_API_KEY is empty in .env.")
        return 1

    if raw_val != raw_val.strip():
        print("[WARNING] GEMINI_API_KEY has leading or trailing spaces.")
    if raw_val.startswith(('"', "'")) or raw_val.endswith(('"', "'")):
        print("[WARNING] GEMINI_API_KEY contains quotes. Remove quotes around the key.")

    # 2. Check settings load
    get_settings.cache_clear()
    settings = get_settings()

    if not settings.gemini_api_key:
        print("[FAIL] GEMINI_API_KEY could not be loaded into runtime settings.")
        return 1

    key_len = len(settings.gemini_api_key)
    print(f"[OK] GEMINI_API_KEY loaded successfully (length: {key_len} chars).")

    # 3. Check google-genai dependency
    try:
        import google.genai as genai_pkg

        version = getattr(genai_pkg, "__version__", "unknown")
        print(f"[OK] google-genai installed (version: {version}).")
    except ImportError as exc:
        print(f"[FAIL] google-genai is not installed: {exc}")
        print("Run: pip install -r requirements.txt")
        return 1

    # 4. Check model configuration & connectivity
    model = settings.gemini_model
    print(f"[INFO] Configured GEMINI_MODEL: '{model}'")

    from google import genai
    from google.genai import errors

    client = genai.Client(api_key=settings.gemini_api_key)

    candidate_models = [model]
    if model != "gemini-3.5-flash-lite":
        candidate_models.append("gemini-3.5-flash-lite")
    if model != "gemini-2.5-flash-lite" and "gemini-2.5-flash-lite" not in candidate_models:
        candidate_models.append("gemini-2.5-flash-lite")

    tested_model = None
    success = False
    for candidate in candidate_models:
        print(f"Testing live API call with model '{candidate}'...")
        try:
            response = client.models.generate_content(
                model=candidate,
                contents="Reply with 'AirWise AI is online' in 5 words or fewer.",
            )
            reply = (response.text or "").strip()
            print(f"[OK] Gemini API responded successfully using '{candidate}'!")
            print(f"     Response: \"{reply}\"")
            tested_model = candidate
            success = True
            break
        except errors.APIError as exc:
            msg = str(exc)
            if "NOT_FOUND" in msg or "404" in msg or "no longer available" in msg:
                err_detail = exc.message if hasattr(exc, "message") else msg
                print(f"[WARNING] Model '{candidate}' is not available: {err_detail}")
            elif "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                print(f"[FAIL] Quota exceeded on '{candidate}': {msg}")
                return 1
            elif "API_KEY_INVALID" in msg or "400" in msg or "403" in msg:
                print(f"[FAIL] Invalid API key: {msg}")
                return 1
            else:
                print(f"[WARNING] Call failed on '{candidate}': {msg}")
        except Exception as exc:
            print(f"[WARNING] Call error on '{candidate}': {type(exc).__name__}: {exc}")

    if not success:
        print("\n[FAIL] Could not connect to any candidate Gemini model.")
        print("Please verify your GEMINI_API_KEY and check available models.")
        return 1

    if tested_model != model:
        print(
            f"\n[NOTE] Configured model '{model}' was unavailable; "
            f"'{tested_model}' succeeded."
        )
        print(f"Recommendation: Update GEMINI_MODEL={tested_model} in .env.")

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED: The AI assistant is ready and online.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
