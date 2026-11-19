"""FastAPI application: API routes, security middleware, static UI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__, advisor, service
from app.airdata import DATA_SOURCE, AirDataError, TTLCache, fetch_air, search_places
from app.config import get_settings
from app.llm import Narrator
from app.ratelimit import SlidingWindowLimiter
from app.schemas import (
    AqiOut,
    AskRequest,
    AskResponse,
    AssistRequest,
    AssistResponse,
    GeocodeResponse,
    PlaceOut,
)

log = logging.getLogger("airwise")
STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY_BYTES = 8 * 1024

API_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.http = httpx.AsyncClient(
        timeout=settings.http_timeout_s, headers={"User-Agent": f"AirWise/{__version__}"}
    )
    app.state.cache = TTLCache(settings.cache_ttl_s)
    app.state.narrator = Narrator(settings)
    app.state.limiters = {
        "general": SlidingWindowLimiter(settings.rate_limit_per_min),
        "ask": SlidingWindowLimiter(settings.ask_rate_limit_per_min),
    }
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="AirWise: Urban Air Quality Assistant",
    version=__version__,
    description="Personalised, low-emission daily plans for severe urban air pollution.",
    lifespan=lifespan,
)


# ---- Middleware --------------------------------------------------------------------
@app.middleware("http")
async def guard_and_secure(request: Request, call_next):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return _error(413, "payload_too_large", "Request body is too large.")
    response = await call_next(request)
    docs = request.url.path.startswith(("/docs", "/redoc"))
    response.headers["Content-Security-Policy"] = DOCS_CSP if docs else API_CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---- Error handling ----------------------------------------------------------------
@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
    return _error(422, "invalid_input", f"Please check these inputs: {', '.join(fields)}.")


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error(exc.status_code, "http_error", "Request could not be completed.")


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", type(exc).__name__)
    return _error(500, "server_error", "Something went wrong on our side. Please try again.")


# ---- Rate limiting -----------------------------------------------------------------
def _client_key(request: Request) -> str:
    if request.app.state.settings.trust_proxy:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        parts = [p for p in parts if p]
        if parts:
            return parts[-1]  # the hop appended by our trusted proxy
    return request.client.host if request.client else "unknown"


def limited(name: str):
    async def dependency(request: Request) -> None:
        if not request.app.state.limiters[name].allow(_client_key(request)):
            raise ApiError(429, "rate_limited", "Too many requests. Please wait a minute.")

    return dependency


# ---- Routes ------------------------------------------------------------------------
async def _report(request: Request, req: AssistRequest) -> service.Report:
    state = request.app.state
    try:
        reading = await fetch_air(state.http, req.location.lat, req.location.lon, state.cache)
        return service.make_report(reading, req.profile, req.location.name)
    except AirDataError as exc:
        log.warning("air data unavailable: %s", exc)
        raise ApiError(
            502, "air_data_unavailable", "Live air data is unavailable right now. Try again shortly."
        ) from exc


@app.get("/api/health")
async def health(request: Request) -> dict:
    narrator = request.app.state.narrator
    return {
        "status": "ok",
        "version": __version__,
        "ai_enabled": narrator.enabled,
        "ai_status": narrator.status,  # ready | no_key | sdk_missing
        "ai_last_error": narrator.last_error,  # error class only, never secrets
    }


@app.get("/api/geocode", response_model=GeocodeResponse, dependencies=[Depends(limited("general"))])
async def geocode(
    request: Request, q: Annotated[str, Query(min_length=2, max_length=80)]
) -> GeocodeResponse:
    try:
        places = await search_places(request.app.state.http, q.strip())
    except AirDataError as exc:
        raise ApiError(502, "geocode_unavailable", "Place search is unavailable right now.") from exc
    return GeocodeResponse(
        places=[PlaceOut(name=p.name, region=p.region, lat=p.lat, lon=p.lon) for p in places]
    )


@app.post("/api/assist", response_model=AssistResponse, dependencies=[Depends(limited("general"))])
async def assist(req: AssistRequest, request: Request) -> AssistResponse:
    report = await _report(request, req)
    note = advisor.fallback_note(report.place, report.aqi, report.outlook, report.actions)
    ai = False
    if req.use_ai:
        generated = await request.app.state.narrator.coach_note(
            service.llm_facts(report, req.profile)
        )
        if generated:
            note, ai = generated, True
    r = report.reading
    return AssistResponse(
        place=report.place,
        aqi=AqiOut(
            index=report.aqi.index,
            category=report.aqi.category,
            level=report.aqi.level,
            dominant=report.aqi.dominant,
            pm25=r.pm25,
            pm10=r.pm10,
            no2=r.no2,
            o3=r.o3,
            observed_at=r.observed_at.isoformat(timespec="minutes"),
        ),
        headline=report.headline,
        outdoor_window=service.window_out(report.outlook),
        actions=report.actions,
        impact=report.impact,
        coach_note=note,
        ai_generated=ai,
        data_source=DATA_SOURCE,
        disclaimer=advisor.DISCLAIMER,
    )


@app.post("/api/ask", response_model=AskResponse, dependencies=[Depends(limited("ask"))])
async def ask(req: AskRequest, request: Request) -> AskResponse:
    report = await _report(request, req)
    generated = None
    if req.use_ai:
        generated = await request.app.state.narrator.answer(
            req.question, service.llm_facts(report, req.profile)
        )
    if generated:
        return AskResponse(answer=generated, ai_generated=True)
    return AskResponse(
        answer=advisor.fallback_answer(req.question, report.actions), ai_generated=False
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
