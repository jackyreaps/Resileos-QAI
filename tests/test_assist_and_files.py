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
                    {"title": "One", "url": "https://one.example/a", "snippet": "a red fox in the snow " + query},
                    {"title": "Two", "url": "https://two.example/b", "snippet": "more about " + query}]}}

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
    fakes.setdefault("crawl_top", 0)
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
    assert calls["search"] and "red" in calls["search"][0]  # searched for what it saw
    assert any(label.startswith("Searched 2 sources") for label in labels(out))
    assert [s["url"] for s in out["assist"]["sources"]] == ["https://one.example/a", "https://two.example/b"]


def test_attachment_context_reaches_the_chat_history():
    out, calls = run({"message": "what do you think?", "attachments": [{"name": "notes.txt", "kind": "text", "text": "Alice works at Acme."}]})
    assert labels(out)[0] == "Read your file"
    assert any("Alice works at Acme" in str(h.get("content")) for h in calls["history"])
    assert "Alice works at Acme" in out["assist"]["context"]


def test_variation_is_made_from_the_chroma_code():
    out, calls = run({"message": "make a variation of this", "attachments": [{"name": "fox.png", "kind": "image", "matrix": IMG}]})
    assert not calls["forge"], "variations come from the chroma code, not a provider"
    created = out["assist"]["created"]
    assert created["made"] is True and created["url"] is None
    assert len(created["variations"]) == 4
    assert all(len(v) == 6 and len(v[0]) == 8 and len(v[0][0]) == 3 for v in created["variations"])
    assert "Made 4 variations" in labels(out)
    assert calls["chat"] == 0


def test_picture_from_text_only_needs_a_provider():
    out, calls = run({"message": "make a picture of a fox"})
    assert calls["forge"]
    created = out["assist"]["created"]
    assert created["made"] is False and created["unavailable"] is True
    assert "Couldn't make a picture: no generator is connected" in labels(out)
    assert "won't pretend" in out["value"]


def test_clip_from_an_uploaded_clip_returns_its_frames():
    out, calls = run({"message": "make a clip from this", "attachments": [{"name": "c.webm", "kind": "clip", "frames": CLIP}]})
    assert labels(out)[:1] == ["Watched your clip"]
    assert "Made a clip" in labels(out)
    assert len(out["assist"]["created"]["frames"]) == 4
    assert out["assist"]["created"]["check_metrics"]["version"] == "clip-metrics/1"


def test_clip_from_one_picture_uses_phi_motion():
    big = [[[0.9, 0.3, 0.1] if 6 <= y < 18 and 8 <= x < 20 else [0.1, 0.15, 0.25] for x in range(32)] for y in range(24)]
    out, calls = run({"message": "make a clip from this", "attachments": [{"name": "fox.png", "kind": "image", "matrix": big}]})
    created = out["assist"]["created"]
    assert created["made"] and len(created["frames"]) == 12 and not calls["forge"]
    assert created["check_metrics"]["moving_transitions"] > 0


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
    assert body["assist"]["created"]["made"] is True  # variation from the chroma code
    assert body["assist"]["attachments"][0]["address"].startswith("5/5/")
    assert len(bytes.fromhex(body["assist"]["attachments"][0]["code"])) == 23
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


def test_search_reply_is_plain_words():
    async def search_fn(query):
        return {"status": "ACCEPTED", "value": "Unverified web search results:\n- <b>Lean</b>", "search": {"results": [
            {"title": "<b>Lean</b> 4", "url": "https://lean-lang.org/", "snippet": "you&#x27;re using <b>Lean</b>"}]}}

    out, _ = run({"message": "search for lean 4"}, search_fn=search_fn)
    assert "<b>" not in out["value"] and "&#x27;" not in out["value"]
    first = out["assist"]["sources"][0]
    assert {k: first[k] for k in ("title", "url", "snippet")} == {"title": "Lean 4", "url": "https://lean-lang.org/", "snippet": "you're using Lean"}
    assert first["address"].startswith("5/3/")
    assert out["verified"] is False


def test_guarded_fetch_connects_to_the_checked_ip():
    """DNS rebinding: the fetch must use the address that was checked."""
    import httpx

    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("host"), request.extensions.get("sni_hostname")))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://evil.example/next"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>ok</p>")

    answers = {"good.example": "93.184.216.34", "evil.example": None}

    def resolver(url):
        from urllib.parse import urlparse

        return answers[urlparse(url).hostname]

    factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = asyncio.run(A.guarded_fetch("https://good.example/start", client_factory=factory, resolver=resolver))
    # The first hop went to the pinned IP with the real Host and SNI; the
    # redirect to a host that doesn't resolve publicly was refused.
    assert seen == [("https://93.184.216.34/start", "good.example", "good.example")]
    assert out["status"] == "BLOCKED"
    answers["evil.example"] = "2606:4700::1111"
    seen.clear()
    out = asyncio.run(A.guarded_fetch("https://good.example/start", client_factory=factory, resolver=resolver))
    assert out["status"] == "SUCCESS"
    assert seen[1][0] == "https://[2606:4700::1111]/next" and seen[1][1] == "evil.example"


def test_resolve_public_refuses_mixed_answers(monkeypatch):
    monkeypatch.setattr(A.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.0.0.1", 443))])
    assert A.resolve_public("https://mixed.example/") is None
    monkeypatch.setattr(A.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert A.resolve_public("https://ok.example/") == "93.184.216.34"
