"""ASGI entrypoint for Resileos-QAI.

Wraps `app:app` with API-key auth, CORS, and a /healthz probe.
Run with: uvicorn asgi:app --host 127.0.0.1 --port 8000 --workers 1

CORS allows https://resileosai.fun and https://www.resileosai.fun unless
RESILEOS_CORS_ORIGINS replaces that list.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import app as _app
from app import configured_cors_origins
from middleware.auth import APIKeyMiddleware

app: FastAPI = _app

# Order matters: auth is added first (inner), CORS second (outermost),
# so preflight OPTIONS is handled before auth.
app.add_middleware(APIKeyMiddleware)

_origins = configured_cors_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Usage-Count", "X-Usage-Quota", "X-RateLimit-Remaining"],
    )


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Unauthenticated liveness probe. Used by Docker healthcheck."""
    return {"ok": True}
