"""ASGI entrypoint for Resileos-QAI.

Wraps `app:app` with API-key auth, optional CORS, and a /healthz probe.
Run with: uvicorn asgi:app --host 127.0.0.1 --port 8000 --workers 1
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import app as _app
from middleware.auth import APIKeyMiddleware

app: FastAPI = _app

# Order matters: auth is added first (inner), CORS second (outermost),
# so preflight OPTIONS is handled before auth.
app.add_middleware(APIKeyMiddleware)

_origins = [
    o.strip()
    for o in os.getenv("RESILEOS_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Usage-Count", "X-Usage-Quota", "X-RateLimit-Remaining"],
    )


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Unauthenticated liveness probe. Used by Docker healthcheck."""
    return {"ok": True}
