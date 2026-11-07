#!/usr/bin/env python3
"""Issue one free-tier API key for onboarding.

Prints the plaintext key once. Store the hash in RESILEOS_API_KEYS
or configs/api_keys.json. Does not require Stripe.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sys


def main() -> int:
    key = secrets.token_urlsafe(24)
    digest = hashlib.sha256(key.encode()).hexdigest()
    record = {digest: {"name": "free", "tier": "free", "quota": 0}}
    print("key:", key)
    print("sha256:", digest)
    print("RESILEOS_API_KEYS=" + json.dumps({key: record[digest]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
