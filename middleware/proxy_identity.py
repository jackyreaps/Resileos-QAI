"""Identity the Pages proxy asserts, and the API-side admin gate.

The proxy signs two assertions with RESILEOS_PROXY_SECRET (HMAC-SHA256),
next to the account's own key:

- ``X-Resileos-Account`` (+ ``-Ts``, ``-Legacy``, ``-Proof``): a stable
  account id, so Files and conversations survive a key rotation. Legacy
  lists the key digests the account has used, for a one-time move of
  records that were keyed by key hash.
- ``X-Resileos-Admin`` (+ ``-Ts``, ``-Proof``): only for ADMIN_EMAILS
  sessions, bound to the method and path of this request.

Admin-only endpoints are everything under /api/v1 that is not in
``PUBLIC_API`` (the same list as ``landing/functions/_admin.js``). A
plain user key calling one directly gets 403. Operators can mark a key
record ``"admin": true`` to call them without the proxy.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Mapping

SKEW_SEC = 300
_HEX64 = re.compile(r"^[a-f0-9]{64}$")

# (method, path pattern under /api/v1); "*" is one path segment.
PUBLIC_API: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("GET", ("ready",)),
    ("GET", ("usage",)),
    ("POST", ("chat",)),
    ("POST", ("assist",)),
    ("POST", ("verify", "lean")),
    ("GET", ("files",)),
    ("POST", ("files",)),
    ("GET", ("files", "*")),
    ("DELETE", ("files", "*")),
    ("GET", ("conversations",)),
    ("POST", ("conversations",)),
    ("GET", ("conversations", "*")),
    ("PUT", ("conversations", "*")),
    ("POST", ("studio", "forge", "video")),
    ("POST", ("studio", "video")),
    ("POST", ("studio", "variations")),
    ("POST", ("studio", "clip-from-picture")),
    ("POST", ("generate", "video")),
    ("GET", ("aphrodite", "*", "state")),
    ("POST", ("aphrodite", "*", "state")),
)
# Open probes that never need an identity.
OPEN_PATHS = {"/api/v1/ready", "/api/v1/substrate_stats", "/api/v1/lecore/health"}
_SEGMENT = re.compile(r"^[A-Za-z0-9_.@:-]{1,128}$")


def _secret() -> str:
    return os.getenv("RESILEOS_PROXY_SECRET", "").strip()


def _header(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower(), "")
    return str(value or "").strip()


def _mac(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _fresh(ts: str, now: float) -> bool:
    try:
        return abs(int(now) - int(ts)) <= SKEW_SEC
    except ValueError:
        return False


def api_subpath(path: str) -> str | None:
    """'/api/v1/kin/cycle' -> '/kin/cycle'; None outside /api/v1."""
    if path == "/api/v1" or not path.startswith("/api/v1/"):
        return None
    return path[len("/api/v1"):].rstrip("/") or "/"


def is_public(method: str, path: str) -> bool:
    method = method.upper()
    if method == "HEAD":
        method = "GET"
    if path.rstrip("/") in OPEN_PATHS:
        return True
    sub = api_subpath(path)
    if sub is None:
        return True  # not an API route (healthz, docs)
    parts = [p for p in sub.split("/") if p]
    for want, pattern in PUBLIC_API:
        if want != method or len(pattern) != len(parts):
            continue
        if all((piece == "*" and bool(_SEGMENT.match(part))) or piece == part for piece, part in zip(pattern, parts)):
            return True
    return False


def account_assertion(headers: Mapping[str, str], now: float | None = None) -> dict | None:
    """{'id', 'legacy': [digests]} when the proxy's account proof is valid."""
    secret = _secret()
    if len(secret) < 16:
        return None
    acct = _header(headers, "x-resileos-account").lower()
    ts = _header(headers, "x-resileos-account-ts")
    legacy = _header(headers, "x-resileos-account-legacy").lower()
    proof = _header(headers, "x-resileos-account-proof").lower()
    if not (_HEX64.match(acct) and ts and proof):
        return None
    if not _fresh(ts, time.time() if now is None else now):
        return None
    if not hmac.compare_digest(_mac(secret, f"account\n{acct}\n{ts}\n{legacy}"), proof):
        return None
    digests = [d for d in legacy.split(",") if _HEX64.match(d)][:10]
    return {"id": acct, "legacy": digests}


def admin_assertion(headers: Mapping[str, str], method: str, path: str, now: float | None = None) -> str | None:
    """Account id when the proxy's admin proof for this method+path is valid."""
    secret = _secret()
    if len(secret) < 16:
        return None
    acct = _header(headers, "x-resileos-admin").lower()
    ts = _header(headers, "x-resileos-admin-ts")
    proof = _header(headers, "x-resileos-admin-proof").lower()
    sub = api_subpath(path)
    if not (_HEX64.match(acct) and ts and proof and sub):
        return None
    if not _fresh(ts, time.time() if now is None else now):
        return None
    message = f"admin\n{acct}\n{ts}\n{method.upper()}\n{sub}"
    if not hmac.compare_digest(_mac(secret, message), proof):
        return None
    return acct


def _raw_key(headers: Mapping[str, str]) -> str:
    raw = _header(headers, "x-api-key")
    if not raw:
        auth = _header(headers, "authorization")
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
    return raw


def key_is_admin(headers: Mapping[str, str]) -> bool:
    raw = _raw_key(headers)
    if not raw:
        return False
    try:
        from middleware.keyring import lookup_record

        record = lookup_record(raw) or {}
    except Exception:
        return False
    return bool(record.get("admin") is True and not record.get("revoked"))


def admin_gate(method: str, path: str, headers: Mapping[str, str]) -> tuple[int, str] | None:
    """None to let the request through, else (status, detail)."""
    if method.upper() == "OPTIONS" or is_public(method, path):
        return None
    if admin_assertion(headers, method, path):
        return None
    if key_is_admin(headers):
        return None
    has_identity = bool(_raw_key(headers) or _header(headers, "x-resileos-trial"))
    if not has_identity:
        return None  # the key check answers (401, or 503 when no keys exist)
    return 403, "This endpoint is for site admins."


def account_owner(assertion: dict) -> str:
    return "acct:" + assertion["id"]
