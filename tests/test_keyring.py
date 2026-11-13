"""Pages-minted keys, revocation, monthly quota, and the per-IP trial."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import APIKeyMiddleware
from middleware.keyring import (
    AuthError,
    MapKv,
    authenticate,
    describe_usage,
    set_kv_reader,
    sha256_hex,
)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("USAGE_PATH", str(tmp_path / "usage.json"))
    monkeypatch.setenv("API_KEYS_PATH", str(tmp_path / "api_keys.json"))
    monkeypatch.delenv("RESILEOS_API_KEYS", raising=False)
    monkeypatch.delenv("RESILEOS_API_KEY", raising=False)
    monkeypatch.delenv("RESILEOS_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("RESILEOS_PROXY_SECRET", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_KV_NAMESPACE_ID", raising=False)
    set_kv_reader(None)


def _client():
    app = FastAPI()

    @app.post("/api/v1/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(APIKeyMiddleware)
    return TestClient(app)


def _proof(secret: str, ip: str, ts: str) -> str:
    return hmac.new(secret.encode(), f"{ip}\n{ts}".encode(), hashlib.sha256).hexdigest()


def _trial_headers(secret: str, ip: str) -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        "X-Resileos-Trial": "1",
        "X-Resileos-Client-Ip": ip,
        "X-Resileos-Trial-Ts": ts,
        "X-Resileos-Trial-Proof": _proof(secret, ip, ts),
    }


def test_file_env_and_legacy_keys_still_work(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    digest = sha256_hex("file-key")
    (tmp_path / "api_keys.json").write_text(
        json.dumps({digest: {"name": "file", "tier": "free", "quota": 3, "plan": "free"}}),
        encoding="utf-8",
    )
    file_ok = authenticate({"x-api-key": "file-key"}, increment=True)
    assert file_ok.kind == "key"
    assert file_ok.plan == "free"

    monkeypatch.setenv(
        "RESILEOS_API_KEYS",
        json.dumps({"env-key": {"name": "env", "tier": "pro", "quota": 9, "plan": "builder"}}),
    )
    env_ok = authenticate({"authorization": "Bearer env-key"}, increment=False)
    assert env_ok.tier == "pro"
    assert env_ok.quota == 9

    monkeypatch.setenv("RESILEOS_API_KEY", "legacy-key")
    legacy = authenticate({"x-api-key": "legacy-key"}, increment=False)
    assert legacy.tier == "enterprise"


def test_kv_record_sets_quota_and_revocation(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    secret = "pages-minted-key"
    digest = sha256_hex(secret)
    set_kv_reader(MapKv({
        digest: {
            "name": "free",
            "tier": "free",
            "quota": 2,
            "plan": "free",
            "prefix": "rsk_example",
            "revoked": False,
        }
    }))
    try:
        client = _client()
        headers = {"X-API-Key": secret}
        assert client.post("/api/v1/ping", headers=headers).status_code == 200
        assert client.post("/api/v1/ping", headers=headers).status_code == 200
        blocked = client.post("/api/v1/ping", headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "monthly quota exceeded (2/2)"
        stored = json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))
        assert secret not in json.dumps(stored)
        assert digest in stored

        usage = client.get("/api/v1/usage", headers=headers)
        assert usage.status_code == 200
        assert usage.json()["count"] == 2
        assert usage.json()["prefix"] == "rsk_example"
        again = describe_usage(secret)
        assert again["count"] == 2

        set_kv_reader(MapKv({
            digest: {"tier": "free", "quota": 2, "plan": "free", "revoked": True}
        }))
        revoked = client.post("/api/v1/ping", headers=headers)
        assert revoked.status_code == 403
        assert revoked.json()["detail"] == "API key revoked"
    finally:
        set_kv_reader(None)


def test_kv_outage_keeps_file_keys_and_fails_closed_for_unknown(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    digest = sha256_hex("local-key")
    (tmp_path / "api_keys.json").write_text(
        json.dumps({digest: {"name": "local", "tier": "pro", "quota": 10, "plan": "builder"}}),
        encoding="utf-8",
    )
    set_kv_reader(MapKv({}, fail=True))
    try:
        ok = authenticate({"x-api-key": "local-key"}, increment=False)
        assert ok.plan == "builder"
        with pytest.raises(AuthError) as caught:
            authenticate({"x-api-key": "missing-key"}, increment=False)
        assert caught.value.status == 503
    finally:
        set_kv_reader(None)


def test_monthly_bucket_resets_on_the_next_month(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    digest = sha256_hex("month-key")
    (tmp_path / "api_keys.json").write_text(
        json.dumps({digest: {"name": "m", "tier": "free", "quota": 1, "plan": "free"}}),
        encoding="utf-8",
    )
    start = time.time()
    authenticate({"x-api-key": "month-key"}, increment=True, now=start)
    with pytest.raises(AuthError) as caught:
        authenticate({"x-api-key": "month-key"}, increment=True, now=start)
    assert caught.value.status == 429
    later = authenticate({"x-api-key": "month-key"}, increment=True, now=start + 40 * 86400)
    assert later.count == 1


def test_trial_is_per_ip_per_utc_day(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("RESILEOS_PROXY_SECRET", "proxy-secret-value")
    monkeypatch.setenv("RESILEOS_TRIAL_DAILY_LIMIT", "2")
    client = _client()
    first = _trial_headers("proxy-secret-value", "203.0.113.10")
    assert client.post("/api/v1/ping", headers=first).status_code == 200
    assert client.post("/api/v1/ping", headers=first).status_code == 200
    blocked = client.post("/api/v1/ping", headers=first)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "trial_exhausted"
    other = client.post("/api/v1/ping", headers=_trial_headers("proxy-secret-value", "203.0.113.11"))
    assert other.status_code == 200
    bad = dict(first)
    bad["X-Resileos-Trial-Proof"] = "0" * 64
    assert client.post("/api/v1/ping", headers=bad).status_code == 401
    stored = (tmp_path / "usage.json").read_text(encoding="utf-8")
    assert "203.0.113.10" not in stored


def test_usage_route_accepts_a_kv_key_without_spending_quota(client, monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    secret = "route-kv-key"
    set_kv_reader(MapKv({
        sha256_hex(secret): {"tier": "free", "quota": 4, "plan": "free", "prefix": "rsk_route"}
    }))
    try:
        missing = client.get("/api/v1/usage")
        assert missing.status_code == 401
        ok = client.get("/api/v1/usage", headers={"X-API-Key": secret})
        assert ok.status_code == 200, ok.text
        assert ok.json()["plan"] == "free"
        assert ok.json()["count"] == 0
        assert ok.json()["prefix"] == "rsk_route"
        unknown = client.get("/api/v1/usage", headers={"X-API-Key": "nope"})
        assert unknown.status_code == 403
    finally:
        set_kv_reader(None)
