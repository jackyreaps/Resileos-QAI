"""API-side admin enforcement and account-keyed Files/conversations."""
from __future__ import annotations

import hashlib
import hmac
import io
import re
import time
from pathlib import Path

import pytest

from middleware import proxy_identity as P

ROOT = Path(__file__).resolve().parents[1]
SECRET = "proxy-secret-value"
ADA = hashlib.sha256(b"account:ada@example.com").hexdigest()
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _mac(msg: str) -> str:
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def admin_headers(method: str, sub: str, acct: str = ADA, ts: int | None = None) -> dict:
    ts = int(time.time()) if ts is None else ts
    return {"X-Resileos-Admin": acct, "X-Resileos-Admin-Ts": str(ts), "X-Resileos-Admin-Proof": _mac(f"admin\n{acct}\n{ts}\n{method}\n{sub}")}


def account_headers(acct: str = ADA, legacy: list[str] = (), ts: int | None = None) -> dict:
    ts = int(time.time()) if ts is None else ts
    joined = ",".join(legacy)
    return {"X-Resileos-Account": acct, "X-Resileos-Account-Ts": str(ts), "X-Resileos-Account-Legacy": joined,
            "X-Resileos-Account-Proof": _mac(f"account\n{acct}\n{ts}\n{joined}")}


@pytest.fixture
def keys(monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv("RESILEOS_PROXY_SECRET", SECRET)
    monkeypatch.setenv("RESILEOS_API_KEYS", '{"user-key":{"name":"ada","tier":"free","quota":500},'
                       '"user-key-2":{"name":"ada","tier":"free","quota":500},'
                       '"ops-key":{"name":"ops","tier":"enterprise","quota":500,"admin":true}}')
    monkeypatch.setenv("RESILEOS_CONVERSATIONS_PATH", str(tmp_path / "conv.json"))
    app_module._MIGRATED.clear()


def test_public_list_matches_the_pages_proxy():
    text = (ROOT / "landing" / "functions" / "_admin.js").read_text(encoding="utf-8")
    block = text.split("const PUBLIC_API = [", 1)[1].split("];", 1)[0]
    js = {(m, tuple(p.strip().strip('"') for p in parts.split(","))) for m, parts in re.findall(r'\["(\w+)", \[([^\]]*)\]\]', block)}
    assert js == set(P.PUBLIC_API)


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1/eat/preview", {"claim": {"subject": "a", "relation": "b", "obj": "c"}}),
    ("POST", "/api/v1/kin/cycle", {}),
    ("GET", "/api/v1/tools", None),
    ("POST", "/api/v1/studio/graphify", {"source": "Alice works at Acme."}),
    ("GET", "/api/v1/factors/hub", None),
])
def test_plain_user_key_gets_403_on_admin_endpoints(client, keys, method, path, body):
    res = client.request(method, path, json=body, headers={"X-API-Key": "user-key"})
    assert res.status_code == 403, res.text
    assert "admins" in res.json()["detail"]
    # Trial visitors too.
    trial = client.request(method, path, json=body, headers={"X-Resileos-Trial": "1"})
    assert trial.status_code == 403


def test_admin_assertion_or_admin_key_passes(client, keys):
    ok = client.get("/api/v1/tools", headers={"X-API-Key": "user-key", **admin_headers("GET", "/tools")})
    assert ok.status_code == 200, ok.text
    ops = client.get("/api/v1/tools", headers={"X-API-Key": "ops-key"})
    assert ops.status_code == 200


def test_admin_assertion_is_bound_to_path_time_and_secret(client, keys):
    other_path = client.get("/api/v1/tools", headers={"X-API-Key": "user-key", **admin_headers("GET", "/kin/legions")})
    assert other_path.status_code == 403
    stale = client.get("/api/v1/tools", headers={"X-API-Key": "user-key", **admin_headers("GET", "/tools", ts=int(time.time()) - 3600)})
    assert stale.status_code == 403
    forged = admin_headers("GET", "/tools")
    forged["X-Resileos-Admin-Proof"] = "0" * 64
    assert client.get("/api/v1/tools", headers={"X-API-Key": "user-key", **forged}).status_code == 403


def test_public_endpoints_still_work_for_plain_keys(client, keys):
    assert client.get("/api/v1/ready").status_code == 200
    assert client.get("/api/v1/conversations", params={"username": "ada"}, headers={"X-API-Key": "user-key"}).status_code == 200


def test_gate_unit():
    assert P.is_public("GET", "/api/v1/files/" + "a" * 32)
    assert not P.is_public("GET", "/api/v1/files/../tools")
    assert not P.is_public("DELETE", "/api/v1/conversations/x")
    assert P.admin_gate("POST", "/api/v1/kin/cycle", {}) is None  # no identity: the key check answers


def test_files_and_conversations_follow_the_account_across_rotation(client, keys, tmp_path, monkeypatch):
    monkeypatch.setenv("RESILEOS_FILES_DIR", str(tmp_path / "files"))
    old = hashlib.sha256(b"user-key").hexdigest()
    # Before this change: records were keyed by the key hash (no account header).
    up = client.post("/api/v1/files", headers={"X-API-Key": "user-key"}, files={"file": ("p.png", io.BytesIO(PNG), "image/png")})
    assert up.status_code == 200
    conv = client.post("/api/v1/conversations", headers={"X-API-Key": "user-key"},
                       json={"username": "ada", "hub_id": "anon", "messages": [{"role": "user", "text": "hello"}]})
    assert conv.status_code == 200
    # First request through the site with the account assertion moves them once.
    signed = {"X-API-Key": "user-key", **account_headers(legacy=[old])}
    assert [f["name"] for f in client.get("/api/v1/files", headers=signed).json()["files"]] == ["p.png"]
    # The old key-hash view is now empty: the records moved, not copied.
    assert client.get("/api/v1/files", headers={"X-API-Key": "user-key"}).json()["files"] == []
    # After rotating to a new key, the account still sees them.
    rotated = {"X-API-Key": "user-key-2", **account_headers(legacy=[hashlib.sha256(b"user-key-2").hexdigest(), old])}
    files = client.get("/api/v1/files", headers=rotated).json()["files"]
    assert [f["name"] for f in files] == ["p.png"]
    got = client.get("/api/v1/files/" + files[0]["id"], headers=rotated)
    assert got.status_code == 200 and got.content == PNG
    threads = client.get("/api/v1/conversations", params={"username": "ada"}, headers=rotated).json()["conversations"]
    assert [t["title"] for t in threads] == ["hello"]


def test_forged_account_header_is_ignored(client, keys, tmp_path, monkeypatch):
    monkeypatch.setenv("RESILEOS_FILES_DIR", str(tmp_path / "files"))
    victim = hashlib.sha256(b"account:victim@example.com").hexdigest()
    client.post("/api/v1/files", headers={"X-API-Key": "user-key-2", **account_headers(acct=victim)},
                files={"file": ("secret.png", io.BytesIO(PNG), "image/png")})
    forged = account_headers(acct=victim)
    forged["X-Resileos-Account-Proof"] = "f" * 64
    listed = client.get("/api/v1/files", headers={"X-API-Key": "user-key", **forged}).json()["files"]
    assert listed == []


def test_migration_is_idempotent(tmp_path, monkeypatch):
    from resileos.chat import conversations as C, files as F

    monkeypatch.setenv("RESILEOS_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("RESILEOS_CONVERSATIONS_PATH", str(tmp_path / "c.json"))
    assert F.migrate_owner(["k"], "acct:x") == 0
    assert C.migrate_owner(["k"], "acct:x") == 0
