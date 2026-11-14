"""One composer turn chains the existing tools; Files are per account.

Fakes stand in for the network (search, page fetch) and for the generator,
so these run offline. Nothing in a turn learns from attachments.
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from resileos.chat import assist as A

ROOT = Path(__file__).resolve().parents[1]
IMG = [[[0.9, 0.2, 0.1] for _ in range(8)] for _ in range(6)]
CLIP = [[[[0.1 * t, 0.1, 0.1] for _ in range(8)] for _ in range(6)] for t in range(4)]


def run(body, **fakes):
    calls = {"chat": 0, "search": [], "forge": [], "lean": []}

    async def chat_fn(titanos, message, history, **kw):
        calls["chat"] += 1
        calls["history"] = history
        return {"status": "ACCEPTED", "value": "answer: " + message, "reply_text": "answer: " + message}

    async def search_fn(query):
        calls["search"].append(query)
        return {"status": "ACCEPTED", "value": "Unverified web search results", "verified": False,
                "search": {"query": query, "results": [
                    {"title": "One", "url": "https://one.example/a", "snippet": "x"},
                    {"title": "Two", "url": "https://two.example/b", "snippet": "y"}]}}

    def forge_fn(prompt, **kw):
        calls["forge"].append((prompt, kw))
        if kw.get("clip") and kw.get("frames"):
            return {"status": "drafted", "url": None, "preview": kw["frames"], "produces_video": False}
        if kw.get("matrix") is not None:
            return {"status": "inconclusive", "url": None, "produces_video": False}
        return {"status": "UNAVAILABLE", "detail": "No video generator is configured on this host.", "url": None}

    def lean_fn(source):
        calls["lean"].append(source)
        return {"status": "FAILED", "line": 2, "summary": "Fails at line 2: rfl failed", "raw": "Proof.lean:2:2: error: rfl failed"}

    fakes.setdefault("chat_fn", chat_fn)
    fakes.setdefault("search_fn", search_fn)
    fakes.setdefault("forge_fn", forge_fn)
    fakes.setdefault("lean_fn", lean_fn)
    out = asyncio.run(A.run_assist(A.AssistBody(**body), titanos=None, **fakes))
    return out, calls


def labels(out):
    return [step["label"] for step in out["assist"]["trail"]]


def test_plain_question_goes_to_the_normal_chat_path():
    out, calls = run({"message": "What is the domain of Zeus?"})
    assert calls["chat"] == 1 and not calls["search"] and not calls["forge"]
    assert out["value"].startswith("answer:")
    assert out["assist"]["learned"] is False


def test_image_is_perceived_then_searched_then_answered_with_sources():
    out, calls = run({"message": "find sources about this", "attachments": [{"name": "fox.png", "kind": "image", "matrix": IMG}]})
    assert labels(out)[0] == "Looked at your image"
    assert "red/orange" in out["assist"]["attachments"][0]["summary"]
    assert calls["search"] and "Searched 2 sources" in labels(out)
    assert [s["url"] for s in out["assist"]["sources"]] == ["https://one.example/a", "https://two.example/b"]


def test_attachment_context_reaches_the_chat_history():
    out, calls = run({"message": "what do you think?", "attachments": [{"name": "notes.txt", "kind": "text", "text": "Alice works at Acme."}]})
    assert labels(out)[0] == "Read your file"
    assert any("Alice works at Acme" in str(h.get("content")) for h in calls["history"])
    assert "Alice works at Acme" in out["assist"]["context"]


def test_variation_request_without_a_generator_is_honest():
    out, calls = run({"message": "make a variation of this", "attachments": [{"name": "fox.png", "kind": "image", "matrix": IMG}]})
    assert calls["forge"] and calls["forge"][0][1]["matrix"] is not None
    created = out["assist"]["created"]
    assert created["made"] is False and created["url"] is None and created["preview"] is None
    assert "Couldn't make a variation: no generator is connected" in labels(out)
    assert "won't pretend" in out["value"]
    assert calls["chat"] == 0


def test_clip_from_an_uploaded_clip_returns_its_frames():
    out, calls = run({"message": "make a clip from this", "attachments": [{"name": "c.webm", "kind": "clip", "frames": CLIP}]})
    assert labels(out)[:1] == ["Watched your clip"]
    assert "Made a clip" in labels(out)
    assert len(out["assist"]["created"]["preview"]) == 4


def test_clip_from_text_only_is_unavailable():
    out, _ = run({"message": "", "hints": {"create": "clip"}, "attachments": [{"name": "n.txt", "kind": "text", "text": "waves"}]})
    assert out["assist"]["created"]["made"] is False
    assert out["assist"]["created"]["unavailable"] is True


def test_lean_attachment_and_pasted_proof_are_checked():
    out, calls = run({"message": "", "attachments": [{"name": "P.lean", "kind": "lean", "text": "theorem t : 1 = 2 := by\n  rfl\n"}]})
    assert calls["lean"] and out["assist"]["lean"]["line"] == 2
    assert "Fails at line 2" in out["value"]
    assert "Checked your proof: it fails" in labels(out)
    out2, calls2 = run({"message": "```lean\ntheorem t : 1 = 1 := rfl\n```"})
    assert calls2["lean"] == ["theorem t : 1 = 1 := rfl\n"]
    assert calls2["chat"] == 0


def test_links_are_read_through_the_guarded_fetcher(monkeypatch):
    monkeypatch.setattr(A, "public_url", lambda url: True)

    async def fetch(url):
        return {"status": "SUCCESS", "content": "<p>Page text about Zeus</p>"}

    out, _ = run({"message": "summarize https://example.org/zeus"}, fetch_fn=fetch)
    assert "Read 1 page" in labels(out)
    assert out["assist"]["sources"][0]["url"] == "https://example.org/zeus"


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/x", "http://localhost:8000/", "file:///etc/passwd", "http://169.254.169.254/latest", "https://example.org:8443/"])
def test_private_and_odd_urls_are_refused(url):
    assert A.public_url(url) is False


def test_hint_search_without_keywords():
    out, calls = run({"message": "zeus temples", "hints": {"search": True}})
    assert calls["search"] == ["zeus temples"]


# ------------------------------------------------------------- HTTP routes

@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RESILEOS_FILES_DIR", str(tmp_path / "files"))
    return tmp_path / "files"


def _keys(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", False)
    monkeypatch.setenv(
        "RESILEOS_API_KEYS",
        '{"ada-key":{"name":"ada","tier":"free","quota":500},"bob-key":{"name":"bob","tier":"free","quota":500}}',
    )


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_files_crud_is_per_account(client, monkeypatch, files_dir):
    _keys(monkeypatch)
    ada = {"X-API-Key": "ada-key"}
    bob = {"X-API-Key": "bob-key"}
    assert client.get("/api/v1/files").status_code == 401
    up = client.post("/api/v1/files", headers=ada, files={"file": ("pic.png", io.BytesIO(PNG), "image/png")})
    assert up.status_code == 200, up.text
    fid = up.json()["id"]
    assert up.json()["kind"] == "image"
    lean = client.post("/api/v1/files", headers=ada, files={"file": ("P.lean", io.BytesIO(b"theorem t : 1 = 1 := rfl\n"), "text/plain")})
    assert lean.json()["kind"] == "lean"
    listed = client.get("/api/v1/files", headers=ada).json()
    assert {f["name"] for f in listed["files"]} == {"pic.png", "P.lean"}
    assert client.get("/api/v1/files", headers=bob).json()["files"] == []
    assert client.get(f"/api/v1/files/{fid}", headers=bob).status_code == 404
    got = client.get(f"/api/v1/files/{fid}", headers=ada)
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-disposition"].startswith("attachment;")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert client.delete(f"/api/v1/files/{fid}", headers=bob).status_code == 404
    assert client.delete(f"/api/v1/files/{fid}", headers=ada).json()["deleted"] is True
    assert client.get(f"/api/v1/files/{fid}", headers=ada).status_code == 404
    assert client.get("/api/v1/files/../../etc", headers=ada).status_code == 404


def test_files_limits_and_types(client, monkeypatch, files_dir):
    _keys(monkeypatch)
    ada = {"X-API-Key": "ada-key"}
    bad_type = client.post("/api/v1/files", headers=ada, files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
    assert bad_type.status_code == 415
    fake_png = client.post("/api/v1/files", headers=ada, files={"file": ("x.png", io.BytesIO(b"<svg/>"), "image/png")})
    assert fake_png.status_code == 415
    monkeypatch.setenv("RESILEOS_FILE_MAX_BYTES", "100")
    big = client.post("/api/v1/files", headers=ada, files={"file": ("a.txt", io.BytesIO(b"x" * 101), "text/plain")})
    assert big.status_code == 413
    monkeypatch.setenv("RESILEOS_FILES_MAX_COUNT", "1")
    assert client.post("/api/v1/files", headers=ada, files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")}).status_code == 200
    assert client.post("/api/v1/files", headers=ada, files={"file": ("b.txt", io.BytesIO(b"hi"), "text/plain")}).status_code == 413


def test_files_need_an_account_not_a_trial(client, monkeypatch, files_dir):
    from resileos.chat import files as F

    with pytest.raises(Exception) as err:
        F._require_account("trial:abc")
    assert getattr(err.value, "status_code", None) == 401


def test_files_never_learn():
    text = (ROOT / "src" / "resileos" / "chat" / "files.py").read_text(encoding="utf-8")
    assert ".learn(" not in text and "eat_filter" not in text and "promote" not in text


def test_assist_route(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    empty = client.post("/api/v1/assist", json={"message": ""})
    assert empty.status_code == 400
    res = client.post("/api/v1/assist", json={"message": "", "attachments": [{"name": "fox.png", "kind": "image", "matrix": IMG}], "hints": {"create": "image"}})
    assert res.status_code == 200, res.text
    body = res.json()
    trail = [s["label"] for s in body["assist"]["trail"]]
    assert trail[0] == "Looked at your image"
    assert body["assist"]["created"]["made"] is False  # no generator configured in tests
    assert body["assist"]["learned"] is False


def test_assist_does_not_learn_from_attachments(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    calls = []
    monkeypatch.setattr(app_module.titanos_singleton, "learn", lambda *a, **k: calls.append(a))
    res = client.post("/api/v1/assist", json={"message": "", "attachments": [{"name": "n.txt", "kind": "text", "text": "Zeus rules the sky."}]})
    assert res.status_code == 200
    assert calls == []


def test_verify_lean_route_is_honest_without_lean(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "_AUTH_BYPASS", True)
    monkeypatch.setenv("RESILEOS_LEAN_BIN", "/nonexistent/lean")
    res = client.post("/api/v1/verify/lean", json={"source": "theorem t : 1 = 1 := rfl"})
    assert res.status_code == 200
    assert res.json()["status"] == "UNAVAILABLE"
