"""API key store matching Resileos-QAI configs/api_keys.json format.

Record shape (keyed by SHA-256 hex of the plaintext key):
  { "name": str, "tier": "free"|"pro"|"enterprise", "quota": int,
    "email": str | None, "stripe_customer_id": str | None,
    "plan": str | None, "created_at": str }

Tier mapping from docs/marketing/pricing.md §7:
  Free -> free / 5000
  Builder -> pro / 100000
  Team -> pro / 500000
  Org -> enterprise / 0
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()

TIER_QUOTA = {
    "free": ("free", 5000),
    "builder": ("pro", 100_000),
    "founding_builder": ("pro", 100_000),
    "team": ("pro", 500_000),
    "org": ("enterprise", 0),
}


def keys_path() -> Path:
    return Path(os.getenv("API_KEYS_PATH", "./data/api_keys.json")).resolve()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read() -> dict:
    path = keys_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: dict) -> None:
    path = keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def mint_key(
    *,
    plan: str,
    name: str,
    email: str | None = None,
    stripe_customer_id: str | None = None,
) -> tuple[str, dict]:
    """Create a plaintext key once; store only the hash. Returns (plaintext, record)."""
    if plan not in TIER_QUOTA:
        raise ValueError(f"unknown plan: {plan}")
    tier, quota = TIER_QUOTA[plan]
    plaintext = f"rsk_{secrets.token_urlsafe(32)}"
    record = {
        "name": name,
        "tier": tier,
        "quota": quota,
        "plan": plan,
        "email": email,
        "stripe_customer_id": stripe_customer_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _LOCK:
        data = _read()
        data[_hash(plaintext)] = record
        _write(data)
    return plaintext, record


def upgrade_by_customer(
    stripe_customer_id: str,
    *,
    plan: str,
    email: str | None = None,
) -> dict | None:
    """Upgrade an existing hashed record matched by stripe_customer_id, or None."""
    if plan not in TIER_QUOTA:
        raise ValueError(f"unknown plan: {plan}")
    tier, quota = TIER_QUOTA[plan]
    with _LOCK:
        data = _read()
        for h, rec in data.items():
            if rec.get("stripe_customer_id") == stripe_customer_id:
                rec["tier"] = tier
                rec["quota"] = quota
                rec["plan"] = plan
                if email:
                    rec["email"] = email
                rec["updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                data[h] = rec
                _write(data)
                return rec
    return None


def downgrade_customer_to_free(stripe_customer_id: str) -> bool:
    with _LOCK:
        data = _read()
        changed = False
        for h, rec in data.items():
            if rec.get("stripe_customer_id") == stripe_customer_id:
                rec["tier"] = "free"
                rec["quota"] = 5000
                rec["plan"] = "free"
                rec["updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                data[h] = rec
                changed = True
        if changed:
            _write(data)
        return changed


def count_keys_for_email(email: str) -> int:
    email = email.lower().strip()
    with _LOCK:
        data = _read()
    return sum(
        1
        for rec in data.values()
        if (rec.get("email") or "").lower() == email
    )
