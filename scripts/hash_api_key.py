#!/usr/bin/env python3
"""Generate an API key and its SHA-256 hash for configs/api_keys.json."""
import hashlib
import secrets
import sys

key = sys.argv[1] if len(sys.argv) > 1 else secrets.token_urlsafe(32)
print(f"key:  {key}")
print(f"hash: {hashlib.sha256(key.encode()).hexdigest()}")
