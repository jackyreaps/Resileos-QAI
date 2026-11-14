"""Every API endpoint the public pages call exists and answers (fake-free,
offline). Pairs with landing/functions/_wiring.test.js, which checks the
Pages proxy side of the same list."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMG = [[[0.5, 0.5, 0.5] for _ in range(4)] for _ in range(4)]

CALLS = [
    ("GET", "/api/v1/ready", None),
    ("GET", "/api/v1/usage", None),
    ("POST", "/api/v1/chat", {"message": "What is the domain of Zeus?"}),
    ("POST", "/api/v1/assist", {"message": "What is the domain of Zeus?"}),
    ("POST", "/api/v1/assist", {"message": "", "attachments": [{"name": "p.png", "kind": "image", "matrix": IMG}]}),
    ("POST", "/api/v1/verify/lean", {"source": "theorem t : 1 = 1 := rfl"}),
    ("GET", "/api/v1/conversations", None),
    ("POST", "/api/v1/studio/forge/video", {"prompt": "a fox", "stage": "draft"}),
    ("POST", "/api/v1/studio/video", {"prompt": "waves", "stage": "draft", "frames": [[[0.1, 0.2], [0.3, 0.4]], [[0.2, 0.3], [0.4, 0.5]]]}),
    ("GET", "/api/v1/aphrodite/anon/state", None),
]


@pytest.mark.parametrize("method,path,body", CALLS, ids=[f"{m} {p}" for m, p, _ in CALLS])
def test_public_endpoint_answers(client, monkeypatch, tmp_path, method, path, body):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.setenv("RESILEOS_CONVERSATIONS_PATH", str(tmp_path / "c.json"))
    monkeypatch.setenv("RESILEOS_LEAN_BIN", "/nonexistent/lean")
    res = client.request(method, path, json=body)
    assert res.status_code not in (404, 405), res.text
    assert res.status_code < 500, res.text


def test_files_endpoints_exist(client, monkeypatch, tmp_path):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv("RESILEOS_API_KEYS", '{"k":{"name":"k","tier":"free","quota":50}}')
    monkeypatch.setenv("RESILEOS_FILES_DIR", str(tmp_path))
    h = {"X-API-Key": "k"}
    assert client.get("/api/v1/files", headers=h).status_code == 200
    assert client.get("/api/v1/files/" + "a" * 32, headers=h).status_code == 404
    assert client.delete("/api/v1/files/" + "a" * 32, headers=h).status_code == 404


def test_proxy_allowlist_matches_registered_routes():
    """Each public path in the Pages allowlist maps to a real FastAPI route."""
    import app as app_module

    text = (ROOT / "landing" / "functions" / "_admin.js").read_text(encoding="utf-8")
    block = text.split("const PUBLIC_API = [", 1)[1].split("];", 1)[0]
    entries = re.findall(r'\["(\w+)", \[([^\]]*)\]\]', block)
    routes = []
    for r in app_module.app.routes:
        for m in getattr(r, "methods", None) or []:
            routes.append((m, r.path))
    for method, parts in entries:
        pieces = [p.strip().strip('"') for p in parts.split(",")]
        pattern = "^/api/v1/" + "/".join("\\{[^/]+\\}" if p == "*" else re.escape(p) for p in pieces) + "$"
        assert any(m == method and re.match(pattern, p) for m, p in routes), (method, pieces)
