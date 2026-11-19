# AirWise: Urban Air Quality Assistant

> Winter smog is outside the window. AirWise turns **live air quality** into a **personal plan**: low-emission daily routines, indoor air hacks and greener alternatives, each with its **direct impact explained**.

Built for PromptWars Challenge 06. Python, FastAPI, Google Gemini, Open-Meteo.

## What it does

1. You pick a city (or use device location) and describe your day: commute, cooking fuel, household (children, older adults, breathing conditions), purifier, outdoor exercise.
2. It fetches live PM2.5, PM10, NO2 and ozone, and an hourly outlook, then computes the **Indian CPCB AQI**.
3. It returns a prioritised plan in three groups, matching the brief:
   - **Daily routine**: best hour for outdoor errands, when a mask helps, move workouts indoors, protect children and older adults.
   - **Indoor air**: when to ventilate, purifier use or sizing, cooking exhaust, wet cleaning.
   - **Greener alternatives**: metro or bus days, carpooling, work-from-home days, clean cooking fuel, no open burning.
4. Every action explains **why** and its **impact** in numbers, for example "saves 10.1 kg CO2e a week on your 12 km commute" or "AQI 78 around 2 PM versus 195 around 8 AM".
5. A **Gemini coach note** and a **follow-up Q&A** make the plan conversational.

## How GenAI is used (and why it is trustworthy)

The plan is built by **deterministic, unit-tested code**. Gemini only *narrates* those verified facts:

| Concern | Approach |
|---|---|
| Hallucinated numbers | The model receives a small JSON of computed facts and is told to use nothing else |
| Prompt injection | User questions are sanitised, length-limited and fenced as untrusted data; the system prompt refuses off-topic requests and forbids revealing rules |
| Privacy | No coordinates, no names of people and no storage. Only the place label and lifestyle flags reach the model |
| Outages and cost | 12 s timeout; any failure falls back to rule-based text, so the app works with **no API key at all** |
| Medical safety | No diagnosis; health answers end with a "see a doctor" reminder; a disclaimer is always shown |

## Architecture

```
app/
  aqi.py        CPCB AQI maths + hourly best/worst window
  advisor.py    rules -> prioritised actions with quantified impact
  airdata.py    Open-Meteo clients, validation, TTL cache
  llm.py        Gemini narrator, prompt-injection defences, graceful fallback
  service.py    glue: reading + profile -> report
  schemas.py    pydantic models, strict validation (extra=forbid)
  main.py       FastAPI routes, security headers, rate limiting, error handling
  static/       accessible UI (HTML, CSS, JS, no inline scripts)
tests/          84 tests: AQI maths, advisor rules, LLM guards, API behaviour
```

## Security

- Strict validation on every input (ranges, enums, lengths, unknown fields rejected)
- Control characters and angle brackets stripped from free text; UI renders with `textContent` only (no `innerHTML`)
- Content-Security-Policy with no inline script or style on app pages; `nosniff`, `DENY` framing, `no-referrer`
- Per-client sliding-window rate limits (stricter on the LLM endpoint); body-size cap
- Generic error messages: upstream or internal details never reach the client
- Secrets only via environment variables; non-root container

## Accessibility

Skip link, semantic landmarks and headings, labelled controls, keyboard-operable ARIA tabs (arrow keys, Home, End), live regions for status and results, focus moved to results, visible focus rings, colour is never the only signal (category text is always shown), `prefers-color-scheme` dark mode, responsive down to small phones.

## Efficiency

Async I/O with a shared HTTP client, 10-minute TTL cache keyed by ~1 km grid cell, bounded cache and limiter memory, one upstream call per report.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env        # Windows: copy .env.example .env
# edit .env and paste your key:  GEMINI_API_KEY=your-key   (no quotes, no spaces)
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

`.env` is loaded automatically. Check it worked: open `http://127.0.0.1:8000/api/health` and look for `"ai_enabled": true`. The page also shows a notice when no key is configured.

## Test

```bash
pytest        # 84 tests, offline (network and LLM are mocked)
ruff check .
```

## Deploy (Google Cloud Run)

```bash
gcloud run deploy airwise --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your-key
```

## Data and limits

Air data: Open-Meteo Air Quality API (CAMS model data), modelled rather than ground-sensor readings, so it can differ from a nearby monitoring station. The AQI uses the PM2.5 and PM10 sub-indices with CPCB breakpoints. CO2 figures use typical per-km averages and are estimates. Guidance is general wellbeing advice, not medical advice.
