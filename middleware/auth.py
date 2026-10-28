# middleware/auth.py
"""API-key authentication, monthly quotas, and per-minute rate limiting."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

USAGE_PATH = Path(os.getenv("USAGE_PATH", "/app/data/usage.json"))
KEYS_PATH = Path(os.getenv("API_KEYS_PATH", "/app/configs/api_keys.json"))

PUBLIC_PATHS = {
    "/healthz",
    "/api/v1/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_keys() -> dict[str, dict]:
    """Merge env bootstrap keys with the on-disk key file.

    Env format (RESILEOS_API_KEYS):
      {"plaintext-key": {"name": "...", "tier": "pro", "quota": 100000}}

    File format (configs/api_keys.json):
      {"<sha256-hex>": {"name": "...", "tier": "pro", "quota": 100000}}

    Plaintext keys are hashed on load. A 64-char hex string is treated as
    already-hashed.
    """
    merged: dict[str, dict] = {}

    raw_env = os.getenv("RESILEOS_API_KEYS", "").strip()
    if raw_env:
        try:
            for key, record in json.loads(raw_env).items():
                hashed = key if len(key) == 64 and all(c in "0123456789abcdef" for c in key.lower()) else _sha256(key)
                merged[hashed] = record
        except Exception:
            pass

    if KEYS_PATH.exists():
        try:
            merged.update(json.loads(KEYS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass

    return merged


def _load_usage() -> dict:
    if not USAGE_PATH.exists():
        return {}
    try:
        return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_usage(usage: dict) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = USAGE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(usage, indent=2), encoding="utf-8")
    tmp.replace(USAGE_PATH)


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
        if request.url.path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        raw_key = _extract_key(request)
        if not raw_key:
            return JSONResponse(
                {"detail": "missing API key: send X-API-Key or Authorization: Bearer"},
                status_code=401,
            )

        keys = _load_keys()
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
