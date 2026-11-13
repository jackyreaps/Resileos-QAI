# middleware/auth.py
"""API-key authentication, monthly quotas, and per-minute rate limiting.

This middleware is one of two auth layers. The other is
``app.verify_api_key``, applied via ``Depends`` on individual routes.
Both use ``middleware.keyring``.

  - No keys configured      -> 503
  - Missing key             -> 401
  - Invalid key             -> 403
  - Revoked key             -> 403
  - RESILEOS_AUTH_BYPASS=1  -> bypass (local development only)

Key sources (merged), digests only:

  1. configs/api_keys.json or API_KEYS_PATH
  2. RESILEOS_API_KEYS
  3. RESILEOS_API_KEY
  4. Cloudflare KV ``key:<sha256>`` when the API token is configured

Anonymous trial requests carry an HMAC from the Pages proxy instead of
a shared key. The allowance is per client IP per UTC day.
"""
from __future__ import annotations

import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from middleware.keyring import (
    AuthError,
    authenticate,
    describe_usage,
)

PUBLIC_PATHS = {
    "/healthz",
    "/api/v1/ready",
    "/api/v1/substrate_stats",
    "/api/v1/lecore/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
}

_USAGE_READ = {"/api/v1/usage"}


def _error(exc: AuthError, headers: dict | None = None) -> JSONResponse:
    body = {"detail": exc.detail}
    body.update(exc.extra)
    return JSONResponse(body, status_code=exc.status, headers=headers or {})


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limit = int(os.getenv("RESILEOS_RATE_LIMIT_PER_MIN", "60"))
        self._windows: dict[str, list[float]] = {}

    def _rate_ok(self, key_id: str) -> tuple[bool, int]:
        now = time.monotonic()
        window = self._windows.setdefault(key_id, [])
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= self.rate_limit:
            return False, 0
        window.append(now)
        return True, self.rate_limit - len(window)

    async def dispatch(self, request: Request, call_next):
        normalized = request.url.path.rstrip("/") or "/"
        if normalized in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        if os.getenv("RESILEOS_AUTH_BYPASS", "0") == "1":
            return await call_next(request)

        if normalized in _USAGE_READ and request.method == "GET":
            raw = request.headers.get("x-api-key", "").strip()
            if not raw:
                auth = request.headers.get("authorization", "").strip()
                if auth.lower().startswith("bearer "):
                    raw = auth[7:].strip()
            if not raw:
                return JSONResponse(
                    {"detail": "missing API key: send X-API-Key or Authorization: Bearer"},
                    status_code=401,
                )
            try:
                info = describe_usage(raw)
            except AuthError as exc:
                return _error(exc)
            if info.get("revoked"):
                return JSONResponse({"detail": "API key revoked"}, status_code=403)
            return JSONResponse(info)

        try:
            decision = authenticate(request.headers, increment=True)
        except AuthError as exc:
            headers = {"Retry-After": "60"} if exc.status == 429 and "rate" in exc.detail else None
            if exc.extra.get("code") == "trial_exhausted":
                headers = {"Retry-After": "86400"}
            return _error(exc, headers)

        ok, remaining = self._rate_ok(decision.key_id)
        if not ok:
            return JSONResponse(
                {"detail": f"rate limit exceeded ({self.rate_limit}/min)"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        request.state.resileos_decision = decision
        response = await call_next(request)
        quota_header = "unlimited" if decision.tier == "enterprise" else str(decision.quota)
        response.headers["X-Usage-Count"] = str(decision.count)
        response.headers["X-Usage-Quota"] = quota_header
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if decision.kind == "trial":
            response.headers["X-Trial-Remaining"] = str(max(decision.quota - decision.count, 0))
        return response
