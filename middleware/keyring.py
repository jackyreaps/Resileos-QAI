"""Shared API-key directory.

The Pages project mints keys into Cloudflare KV (`key:<sha256>`). This
module is what the API host reads, merged with the file and env sources
that already work:

  1. configs/api_keys.json or API_KEYS_PATH, keyed by SHA-256 hex
  2. RESILEOS_API_KEYS, plaintext or SHA-256 hex
  3. RESILEOS_API_KEY, one legacy plaintext key
  4. Cloudflare KV, when CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID,
     and CLOUDFLARE_KV_NAMESPACE_ID are set

Only the digest is stored. A record with ``revoked: true`` is rejected.
Quota and tier come from the merged record. Monthly counters stay in
USAGE_PATH and reset on the calendar month, using the host's local
clock, the same way the file-backed counter always has.

Anonymous chat is not a shared key. The Pages proxy proves the caller
IP with HMAC (RESILEOS_PROXY_SECRET). Each IP gets
RESILEOS_TRIAL_DAILY_LIMIT requests per UTC day (default 20).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
_USAGE_LOCK = threading.Lock()
_READER_LOCK = threading.Lock()
_reader_override = None
_env_reader = None
_env_signature: tuple | None = None

_TRIAL_SKEW_SEC = 300


class AuthError(Exception):
    def __init__(self, status: int, detail: str, extra: dict | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.extra = dict(extra or {})


class KvUnavailable(Exception):
    pass


class Decision:
    def __init__(self, kind: str, key_id: str, tier: str, quota: int, count: int, plan: str):
        self.kind = kind
        self.key_id = key_id
        self.tier = tier
        self.quota = quota
        self.count = count
        self.plan = plan


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def usage_path() -> Path:
    explicit = os.getenv("USAGE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    return _REPO_ROOT / "data" / "usage.json"


def keys_path() -> Path:
    explicit = os.getenv("API_KEYS_PATH", "").strip()
    if explicit:
        return Path(explicit)
    return _REPO_ROOT / "configs" / "api_keys.json"


def load_static_keys() -> dict[str, dict]:
    """File and env keys. KV is not included."""
    merged: dict[str, dict] = {}
    raw_env = os.getenv("RESILEOS_API_KEYS", "").strip()
    if raw_env:
        try:
            parsed = json.loads(raw_env)
            if isinstance(parsed, dict):
                for key, record in parsed.items():
                    if not isinstance(record, dict):
                        continue
                    is_hex = len(key) == 64 and all(
                        c in "0123456789abcdef" for c in key.lower()
                    )
                    merged[key if is_hex else sha256_hex(key)] = record
        except Exception:
            pass

    path = keys_path()
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                for key, record in parsed.items():
                    if isinstance(record, dict):
                        merged[str(key)] = record
        except Exception:
            pass

    legacy = os.getenv("RESILEOS_API_KEY", "").strip()
    if legacy:
        merged.setdefault(
            sha256_hex(legacy),
            {"name": "legacy", "tier": "enterprise", "quota": 0},
        )
    return merged


def _load_usage() -> dict:
    path = usage_path()
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_usage(usage: dict) -> None:
    path = usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(usage, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def _header(headers: Mapping[str, str], name: str) -> str:
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    raw = getter(name) if getter else None
    if raw is None and getter:
        raw = getter(name.lower())
    if raw is None:
        return ""
    return str(raw).strip()


def _extract_key(headers: Mapping[str, str]) -> str:
    key = _header(headers, "x-api-key")
    if key:
        return key
    auth = _header(headers, "authorization")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _scrub(record: dict) -> dict:
    cleaned = dict(record)
    for banned in ("api_key", "key", "secret", "plaintext", "seal", "password"):
        cleaned.pop(banned, None)
    return cleaned


def _quota_of(record: dict) -> tuple[str, int, str]:
    tier = str(record.get("tier") or "free")
    plan = str(record.get("plan") or "")
    try:
        quota = int(record.get("quota", 1000))
    except (TypeError, ValueError):
        quota = 1000
    return tier, quota, plan


class CloudflareKvReader:
    """Read ``key:<digest>`` through the Cloudflare API. Short TTL cache.

    The token needs Account → Workers KV Storage → Read. Seal values and
    session records are never requested.
    """

    def __init__(self, account_id: str, namespace_id: str, token: str, ttl: float):
        self.account_id = account_id
        self.namespace_id = namespace_id
        self._token = token
        self.ttl = ttl if ttl > 0 else 30.0
        self._cache: dict[str, tuple[float, dict | None]] = {}
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return True

    def get_record(self, digest: str) -> dict | None:
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(digest)
            if hit is not None and hit[0] > now:
                return hit[1]
        record = self._fetch(digest)
        with self._lock:
            self._cache[digest] = (time.monotonic() + self.ttl, record)
        return record

    def _fetch(self, digest: str) -> dict | None:
        from urllib.parse import quote

        key_name = quote("key:" + digest, safe="")
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/storage/kv/namespaces/{self.namespace_id}/values/{key_name}"
        )
        req = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer " + self._token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise KvUnavailable(f"HTTP {exc.code}") from exc
        except Exception as exc:
            raise KvUnavailable("lookup failed") from exc
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise KvUnavailable("record was not JSON") from exc
        if not isinstance(parsed, dict):
            return None
        if parsed.get("success") is False:
            raise KvUnavailable("lookup rejected")
        return _scrub(parsed)


class MapKv:
    """In-memory directory for tests."""

    def __init__(self, records: dict[str, dict] | None = None, fail: bool = False):
        self.records = records or {}
        self.fail = fail

    def configured(self) -> bool:
        return True

    def get_record(self, digest: str) -> dict | None:
        if self.fail:
            raise KvUnavailable("down")
        record = self.records.get(digest)
        if record is None:
            return None
        return _scrub(dict(record))


def set_kv_reader(reader) -> None:
    global _reader_override
    with _READER_LOCK:
        _reader_override = reader


def kv_reader():
    global _env_reader, _env_signature
    with _READER_LOCK:
        if _reader_override is not None:
            return _reader_override
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    namespace = os.getenv("CLOUDFLARE_KV_NAMESPACE_ID", "").strip()
    ttl_raw = os.getenv("RESILEOS_KV_CACHE_TTL", "30").strip() or "30"
    signature = (token, account, namespace, ttl_raw)
    with _READER_LOCK:
        global _env_reader, _env_signature
        if signature != _env_signature:
            _env_signature = signature
            if token and account and namespace:
                try:
                    ttl = float(ttl_raw)
                except ValueError:
                    ttl = 30.0
                _env_reader = CloudflareKvReader(account, namespace, token, ttl)
            else:
                _env_reader = None
        return _env_reader


def kv_configured() -> bool:
    reader = kv_reader()
    return reader is not None and reader.configured()


def lookup_record(raw_key: str) -> dict | None:
    """Return the merged record, or None if the key is unknown.

    Raises KvUnavailable when the key is not local and KV cannot be read.
    """
    digest = sha256_hex(raw_key)
    static = load_static_keys().get(digest)
    reader = kv_reader()
    kv_record = None
    kv_failed = False
    if reader is not None and reader.configured():
        try:
            kv_record = reader.get_record(digest)
        except KvUnavailable:
            kv_failed = True
    if kv_record is not None and not isinstance(kv_record, dict):
        kv_record = None
    if static is None and kv_record is None:
        if kv_failed:
            raise KvUnavailable("lookup failed")
        return None
    if static is None:
        record = _scrub(kv_record)
    elif kv_record is None:
        record = _scrub(static)
    else:
        record = _scrub(static)
        overlay = _scrub(kv_record)
        record.update(overlay)
        if static.get("revoked") or kv_record.get("revoked"):
            record["revoked"] = True
    record["_digest"] = digest
    return record


def trial_limit() -> int:
    raw = os.getenv("RESILEOS_TRIAL_DAILY_LIMIT", "20").strip() or "20"
    try:
        limit = int(raw)
    except ValueError:
        return 20
    return limit if limit > 0 else 20


def _trial_ip(headers: Mapping[str, str], now: float) -> str | None:
    if _header(headers, "x-resileos-trial") != "1":
        return None
    secret = os.getenv("RESILEOS_PROXY_SECRET", "").strip()
    if not secret:
        return None
    ip = _header(headers, "x-resileos-client-ip")
    ts = _header(headers, "x-resileos-trial-ts")
    proof = _header(headers, "x-resileos-trial-proof").lower()
    if not ip or not ts or not proof or len(ip) > 128:
        return None
    if any(ch in ip for ch in "\r\n\x00"):
        return None
    try:
        ts_i = int(ts)
    except ValueError:
        return None
    if abs(int(now) - ts_i) > _TRIAL_SKEW_SEC:
        return None
    mac = hmac.new(secret.encode("utf-8"), f"{ip}\n{ts}".encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, proof):
        return None
    return ip


def trial_key_id(headers: Mapping[str, str], now: float | None = None) -> str | None:
    """Stable per-IP id when the proxy proof is valid. Does not meter."""
    moment = time.time() if now is None else now
    ip = _trial_ip(headers, moment)
    if not ip:
        return None
    return "trial:" + sha256_hex(ip)


def _no_directory() -> bool:
    return not load_static_keys() and not kv_configured() and not os.getenv("RESILEOS_PROXY_SECRET", "").strip()


def _unconfigured_detail() -> str:
    return (
        "No API keys configured. Set API_KEYS_PATH, "
        "RESILEOS_API_KEYS, or RESILEOS_API_KEY. "
        "Local dev only: RESILEOS_AUTH_BYPASS=1."
    )


def describe_usage(raw_key: str, now: float | None = None) -> dict:
    """Usage snapshot. Does not increment. Over quota still returns 200 data."""
    if not raw_key:
        raise AuthError(401, "missing API key: send X-API-Key or Authorization: Bearer")
    try:
        record = lookup_record(raw_key)
    except KvUnavailable as exc:
        raise AuthError(503, "Key directory is unavailable.") from exc
    if record is None:
        raise AuthError(403, "invalid API key")
    moment = time.time() if now is None else now
    month = time.strftime("%Y-%m", time.localtime(moment))
    digest = record.get("_digest") or sha256_hex(raw_key)
    tier, quota, plan = _quota_of(record)
    with _USAGE_LOCK:
        usage = _load_usage()
        count = int(usage.get(digest, {}).get(month, {}).get("count", 0) or 0)
    return {
        "count": count,
        "quota": quota if tier != "enterprise" else 0,
        "unlimited": tier == "enterprise",
        "tier": tier,
        "plan": plan or None,
        "month": month,
        "prefix": str(record.get("prefix") or ""),
        "revoked": bool(record.get("revoked")),
    }


def authenticate(headers: Mapping[str, str], *, increment: bool, now: float | None = None) -> Decision:
    """Validate a key or a per-IP trial proof.

    ``increment`` meters a successful check. The usage read is a separate
    path and does not call this with increment.
    """
    moment = time.time() if now is None else now
    raw = _extract_key(headers)
    if raw:
        return _authenticate_key(raw, increment=increment, now=moment)
    ip = _trial_ip(headers, moment)
    if ip:
        return _authenticate_trial(ip, increment=increment, now=moment)
    if _no_directory():
        raise AuthError(503, _unconfigured_detail())
    raise AuthError(
        401,
        "missing API key: send X-API-Key or Authorization: Bearer",
    )


def _authenticate_key(raw: str, *, increment: bool, now: float) -> Decision:
    try:
        record = lookup_record(raw)
    except KvUnavailable as exc:
        raise AuthError(503, "Key directory is unavailable.") from exc
    if record is None:
        raise AuthError(403, "invalid API key")
    if record.get("revoked"):
        raise AuthError(403, "API key revoked")
    tier, quota, plan = _quota_of(record)
    digest = str(record["_digest"])
    month = time.strftime("%Y-%m", time.localtime(now))
    with _USAGE_LOCK:
        usage = _load_usage()
        bucket = usage.setdefault(digest, {}).setdefault(month, {"count": 0})
        try:
            count = int(bucket.get("count", 0) or 0)
        except (TypeError, ValueError):
            count = 0
        bucket["count"] = count
        if tier != "enterprise" and count >= quota:
            raise AuthError(
                429,
                f"monthly quota exceeded ({count}/{quota})",
                {"tier": tier},
            )
        if increment:
            bucket["count"] = count + 1
            _save_usage(usage)
            count = bucket["count"]
    return Decision("key", digest, tier, quota, count, plan)


def _authenticate_trial(ip: str, *, increment: bool, now: float) -> Decision:
    limit = trial_limit()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    key_id = "trial:" + sha256_hex(ip)
    with _USAGE_LOCK:
        usage = _load_usage()
        bucket = usage.setdefault(key_id, {}).setdefault(day, {"count": 0})
        try:
            count = int(bucket.get("count", 0) or 0)
        except (TypeError, ValueError):
            count = 0
        bucket["count"] = count
        if count >= limit:
            raise AuthError(
                429,
                f"Daily trial exceeded ({count}/{limit}). Sign in to continue.",
                {"code": "trial_exhausted", "tier": "trial"},
            )
        if increment:
            bucket["count"] = count + 1
            _save_usage(usage)
            count = bucket["count"]
    return Decision("trial", key_id, "trial", limit, count, "trial")
