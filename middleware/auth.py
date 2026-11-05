# middleware/auth.py
"""API-key authentication, monthly quotas, and per-minute rate limiting.

This middleware is one of two auth layers. The other is
``app.verify_api_key``, applied via ``Depends`` on individual routes.
Both implement the same policy, so behavior is identical regardless of
entrypoint:

  - No keys configured      -> 503 (refuse to serve openly)
  - Missing key             -> 401
  - Invalid key             -> 403
  - RESILEOS_AUTH_BYPASS=1  -> bypass (local development only)

Key sources, merged on load:

  1. ``configs/api_keys.json``   {"<sha256-hex>": {...}}   primary
  2. ``RESILEOS_API_KEYS``       {"<plaintext>": {...}}    bootstrap map
  3. ``RESILEOS_API_KEY``        "<plaintext>"             legacy single key

Public paths are shared with ``app.py``'s auth-exempt set so the two
layers cannot disagree about what is open. ``/healthz`` is added here
because ``asgi.py`` exposes it statically; ``/docs``, ``/openapi.json``,
``/redoc``, and ``/favicon.ico`` are FastAPI built-ins.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# _REPO_ROOT is /app in the container and the checkout root in a venv,
# because __file__ resolves the same way relative to the package layout.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_usage_path() -> Path:
    explicit = os.getenv("USAGE_PATH")
    if explicit:
        return Path(explicit)
    return _REPO_ROOT / "data" / "usage.json"


def _resolve_keys_path() -> Path:
    explicit = os.getenv("API_KEYS_PATH")
    if explicit:
        return Path(explicit)
    return _REPO_ROOT / "configs" / "api_keys.json"


USAGE_PATH = _resolve_usage_path()
KEYS_PATH = _resolve_keys_path()

# Public paths mirror app.py's auth-exempt set exactly, plus /healthz
# (asgi.py's static liveness) and FastAPI's built-in docs routes.
# Adding a new auth-exempt route in app.py means adding it here too,
# and vice versa. That is the discipline that keeps the two layers
# from silently diverging.
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


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_keys() -> dict[str, dict]:
    """Merge key file, RESILEOS_API_KEYS, and legacy RESILEOS_API_KEY.

    Every returned mapping key is a SHA-256 hex digest. Plaintext keys
    are hashed on load; a 64-char hex string is treated as already-hashed.
    """
    merged: dict[str, dict] = {}

    raw_env = os.getenv("RESILEOS_API_KEYS", "").strip()
    if raw_env:
        try:
            for key, record in json.loads(raw_env).items():
                is_hex = len(key) == 64 and all(
                    c in "0123456789abcdef" for c in key.lower()
                )
                merged[key if is_hex else _sha256(key)] = record
        except Exception:
            pass

    if KEYS_PATH.exists():
        try:
            merged.update(json.loads(KEYS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass

    legacy = os.getenv("RESILEOS_API_KEY", "").strip()
    if legacy:
        merged.setdefault(
            _sha256(legacy),
            {"name": "legacy", "tier": "enterprise", "quota": 0},
        )

    return merged


def _load_usage() -> dict:
    if not USAGE_PATH.exists():
        return {}
    try:
        return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_usage(usage: dict) -> None:
    try:
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = USAGE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(usage, indent=2), encoding="utf-8")
        tmp.replace(USAGE_PATH)
    except Exception:
        # Usage tracking is best-effort. Losing a usage record is
        # preferable to failing the request. Real enforcement uses
        # Stripe's monthly reset, not this file's integrity.
        pass


def _extract_key(request: Request) -> str:
    key = request.headers.get("x-api-key", "").strip()
    if key:
        return key
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limit = int(os.getenv("RESILEOS_RATE_LIMIT_PER_MIN", "60"))
        self._windows: dict[str, list[float]] = {}

    def _rate_ok(self, key_hash: str) -> tuple[bool, int]:
        now = time.monotonic()
        window = self._windows.setdefault(key_hash, [])
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= self.rate_limit:
            return False, 0
        window.append(now)
        return True, self.rate_limit - len(window)

    async def dispatch(self, request: Request, call_next):
        # Public paths: strip a trailing slash so /api/v1/ready/ matches
        # /api/v1/ready. CORS preflight passes through unconditionally.
        normalized = request.url.path.rstrip("/") or "/"
        if normalized in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        # Local development bypass. Production must never set this.
        if os.getenv("RESILEOS_AUTH_BYPASS", "0") == "1":
            return await call_next(request)

        # Fail closed: refuse to serve protected routes when no keys are
        # configured. Matches app.verify_api_key.
        keys = _load_keys()
        if not keys:
            return JSONResponse(
                {
                    "detail": (
                        "No API keys configured. Set API_KEYS_PATH, "
                        "RESILEOS_API_KEYS, or RESILEOS_API_KEY. "
                        "Local dev only: RESILEOS_AUTH_BYPASS=1."
                    )
                },
                status_code=503,
            )

        raw_key = _extract_key(request)
        if not raw_key:
            return JSONResponse(
                {"detail": "missing API key: send X-API-Key or Authorization: Bearer"},
                status_code=401,
            )

        key_hash = _sha256(raw_key)
        record = keys.get(key_hash)
        if record is None:
            return JSONResponse({"detail": "invalid API key"}, status_code=403)

        tier = str(record.get("tier", "free"))
        quota = int(record.get("quota", 1000))

        # Monthly quota
        usage = _load_usage()
        month = time.strftime("%Y-%m")
        bucket = usage.setdefault(key_hash, {}).setdefault(month, {"count": 0})
        if tier != "enterprise" and bucket["count"] >= quota:
            return JSONResponse(
                {
                    "detail": f"monthly quota exceeded ({bucket['count']}/{quota})",
                    "tier": tier,
                },
                status_code=429,
            )

        # Per-minute rate limit
        ok, remaining = self._rate_ok(key_hash)
        if not ok:
            return JSONResponse(
                {"detail": f"rate limit exceeded ({self.rate_limit}/min)"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        bucket["count"] += 1
        _save_usage(usage)

        response = await call_next(request)
        response.headers["X-Usage-Count"] = str(bucket["count"])
        response.headers["X-Usage-Quota"] = (
            str(quota) if tier != "enterprise" else "unlimited"
        )
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
