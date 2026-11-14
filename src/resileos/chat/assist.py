"""One chat turn that chains the existing tools.

The composer sends a message plus any attachments. This module:

1. perceives each attachment with the existing perceivers (image, clip,
   text). Perception here never learns: no Eat commit, no Titanos write.
2. checks Lean proofs with ``resileos.verify.lean_check`` when a .lean file
   is attached or a proof is pasted.
3. reads pages linked in the message (Hermes ``crawl_envelope``) through a
   fetcher that refuses private and local addresses.
4. searches the web (the chat search path) when asked or when the message
   wants sources.
5. answers with the normal chat agent (``run_agent_chat``), so Eat stays the
   only writer and every chat gate is unchanged.
6. makes a picture or clip with ``run_forge_video`` when asked. With no
   provider it reports UNAVAILABLE and returns no media.

Every step is listed in ``trail`` in plain words, with sources linked.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin, urlparse

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

MAX_ATTACHMENTS = 6
MAX_TEXT = 20_000
MAX_URLS = 2
CONTEXT_CHARS = 1_200

_URL = re.compile(r"https?://[^\s<>\"')\]]+")
_SEARCH = re.compile(r"^/search\s+|\b(search|look (?:it |this )?up|find sources|sources? (?:for|on|about)|latest|news|related|similar)\b", re.I)
_CREATE = re.compile(
    r"\b(make|create|draw|generate|turn|render|produce)\b[^.?!]*\b(image|picture|photo|variation|clip|video|animation|gif)\b",
    re.I,
)
_CLIP_WORDS = re.compile(r"\b(clip|video|animation|gif)\b", re.I)


class Attachment(BaseModel):
    name: str = Field(default="file", max_length=200)
    type: str = Field(default="", max_length=120)
    kind: str = Field(default="file", max_length=16)  # image | clip | text | lean | file
    size: int | None = None
    file_id: str | None = Field(default=None, max_length=64)
    matrix: list[Any] | None = None
    frames: list[Any] | None = None
    text: str | None = Field(default=None, max_length=MAX_TEXT)


class Hints(BaseModel):
    search: bool = False
    create: str | None = None  # "image" | "clip"


class AssistBody(BaseModel):
    message: str = Field(default="", max_length=8000)
    history: list = []
    hub_id: str = "anon"
    persona: str = "honest"
    prose: bool = True
    last_tool_empty: bool = False
    attachments: list[Attachment] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)
    hints: Hints = Field(default_factory=Hints)


class LeanBody(BaseModel):
    source: str = Field(default="", max_length=2_000_000)
    filename: str = Field(default="Proof.lean", max_length=200)


# ---------------------------------------------------------------- perception

def _array(data: Any, ndims: tuple[int, ...]) -> Any:
    import numpy as np

    array = np.asarray(data, dtype=float)
    if array.ndim not in ndims or array.size == 0 or array.size > 250_000:
        raise ValueError("attachment pixels have the wrong shape")
    if array.max() > 1.0:
        array = array / 255.0
    return array


def _level(value: float, words: tuple[str, str, str], cuts: tuple[float, float] = (0.33, 0.66)) -> str:
    if value < cuts[0]:
        return words[0]
    if value < cuts[1]:
        return words[1]
    return words[2]


def _dominant(means: dict[str, float]) -> str:
    if not means:
        return ""
    r, g, b = (float(means.get(k, 0)) for k in ("r", "g", "b"))
    if max(r, g, b) - min(r, g, b) < 0.06:
        return "mostly neutral tones"
    return "mostly " + {r: "warm red/orange", g: "green", b: "blue"}[max(r, g, b)] + " tones"


def perceive_attachment(att: Attachment) -> dict[str, Any]:
    """Look at one attachment. Returns plain words plus the raw perception."""
    from resileos.ui.query_scale import to_jsonable

    subject = f"upload:{att.name}"[:120]
    if att.kind == "image" and att.matrix is not None:
        from resileos.ui.perceive_image import perceive_image

        image = _array(att.matrix, (2, 3))
        raw = to_jsonable(perceive_image(image, subject=subject))
        diag = raw.get("diagnostics") or {}
        luma = float(raw.get("mean_luma") or 0)
        edges = float(raw.get("edge_density") or 0)
        bits = [
            _level(luma, ("dark", "medium brightness", "bright")),
            _level(edges, ("smooth", "some detail", "lots of detail")),
        ]
        color = _dominant(diag.get("channel_means") or {})
        if color:
            bits.append(color)
        if diag.get("width") and diag.get("height"):
            bits.append("wide" if diag["width"] > diag["height"] * 1.2 else "tall" if diag["height"] > diag["width"] * 1.2 else "square-ish")
        return {"kind": "image", "label": "Looked at your image", "summary": ", ".join(bits), "raw": raw}
    if att.kind == "clip" and att.frames is not None:
        from resileos.ui.perceive_video import perceive_video

        frames = _array(att.frames, (3, 4))
        if frames.ndim == 3:
            frames = frames[..., None].repeat(3, axis=-1)
        raw = to_jsonable(perceive_video(frames, subject=subject, fps=3.0))
        motion = float(raw.get("motion") or 0)
        bits = [
            f"{int(raw.get('frames') or len(frames))} frames",
            _level(motion, ("almost still", "gentle motion", "lots of motion"), (0.08, 0.25)),
            _level(float(raw.get("mean_luma") or 0), ("dark", "medium brightness", "bright")),
        ]
        return {"kind": "clip", "label": "Watched your clip", "summary": ", ".join(bits), "raw": raw}
    if att.kind in {"text", "lean"} and att.text:
        from resileos.ui.perceive_language import perceive_language

        raw = to_jsonable(perceive_language(att.text[:8000], subject=subject))
        words = len(att.text.split())
        lines = att.text.count("\n") + 1
        return {
            "kind": att.kind,
            "label": "Read your file",
            "summary": f"{words} words, {lines} lines",
            "raw": raw,
            "excerpt": " ".join(att.text.split())[:CONTEXT_CHARS],
        }
    return {"kind": "file", "label": "Got your file", "summary": "Saved as an attachment. I can't read inside this type yet.", "raw": {}}


# ---------------------------------------------------------------- crawling

def public_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.port not in (None, 80, 443):
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return False
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if not addr.is_global or addr.is_multicast:
            return False
    return bool(infos)


async def guarded_fetch(url: str, *, client_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Fetch one public page. Redirects are followed by hand and re-checked."""
    import httpx

    factory = client_factory or (lambda: httpx.AsyncClient(timeout=8.0, follow_redirects=False))
    current = url
    async with factory() as client:
        for _ in range(4):
            if not public_url(current):
                return {"status": "BLOCKED", "content": ""}
            resp = await client.get(current, headers={"User-Agent": "ResileosBot/1.0 (+https://resileosai.fun)"})
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            if resp.status_code >= 400:
                return {"status": "ERROR", "content": ""}
            kind = resp.headers.get("content-type", "")
            if "html" not in kind and "text" not in kind:
                return {"status": "ERROR", "content": ""}
            return {"status": "SUCCESS", "content": resp.text[:400_000], "url": current}
    return {"status": "ERROR", "content": ""}


def crawl_pages(urls: list[str], fetch_fn: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    from resileos.kin.outer_legions import crawl_envelope

    pages = []
    for url in urls[:MAX_URLS]:
        out = crawl_envelope(url, fetch_fn=fetch_fn or guarded_fetch)
        env = (out.get("envelopes") or [None])[0]
        pages.append({"url": url, "status": out.get("status"), "text": (env or {}).get("text", "")})
    return pages


# ---------------------------------------------------------------- the turn

def _intent_create(body: AssistBody) -> str | None:
    hint = (body.hints.create or "").lower()
    if hint in {"image", "clip"}:
        return hint
    match = _CREATE.search(body.message or "")
    if not match:
        return None
    return "clip" if _CLIP_WORDS.search(match.group(0)) else "image"


def _gray(frames: Any) -> list[list[list[float]]]:
    import numpy as np

    arr = np.asarray(frames, dtype=float)
    if arr.max() > 1.0:
        arr = arr / 255.0
    if arr.ndim == 4:
        arr = arr[..., :3] @ np.array([0.299, 0.587, 0.114])
    return [[[round(float(v), 3) for v in row] for row in frame] for frame in arr]


async def run_assist(
    body: AssistBody,
    *,
    titanos: Any,
    chat_fn: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    search_fn: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
    fetch_fn: Callable[..., Any] | None = None,
    forge_fn: Callable[..., dict[str, Any]] | None = None,
    lean_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from resileos.answer.agent_loop import _maybe_search, run_agent_chat
    from resileos.answer.user_profile import PERSONA_PACKS
    from resileos.kin.studio_tools import run_forge_video
    from resileos.ui.query_scale import to_jsonable
    from resileos.verify.lean_check import check_lean, extract_lean, looks_like_lean

    chat_fn = chat_fn or run_agent_chat
    search_fn = search_fn or _maybe_search
    forge_fn = forge_fn or run_forge_video
    lean_fn = lean_fn or check_lean
    persona = body.persona if body.persona in PERSONA_PACKS else "honest"
    message = (body.message or "").strip()
    trail: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    context_lines: list[str] = []
    seen: list[dict[str, Any]] = []

    # 1. perceive attachments
    for att in body.attachments:
        try:
            looked = perceive_attachment(att)
        except (ValueError, TypeError, IndexError) as exc:
            trail.append({"step": "perceive", "label": f"Couldn't read {att.name}", "status": "error", "detail": str(exc)[:200]})
            continue
        looked["name"] = att.name
        seen.append(looked)
        trail.append({"step": "perceive", "label": looked["label"], "status": "done", "detail": f"{att.name}: {looked['summary']}"})
        line = f"Attachment {att.name} ({looked['kind']}): {looked['summary']}."
        if looked.get("excerpt"):
            line += " Excerpt: " + looked["excerpt"]
        context_lines.append(line)

    # 2. Lean proofs
    lean_result = None
    lean_source = next((a.text for a in body.attachments if (a.kind == "lean" or a.name.endswith(".lean")) and a.text), None)
    if lean_source is None and looks_like_lean(message):
        lean_source = extract_lean(message)
    if lean_source:
        lean_result = lean_fn(lean_source)
        status = lean_result.get("status")
        label = {
            "CHECKED": "Checked your proof: it checks",
            "INCOMPLETE": "Checked your proof: not finished",
            "FAILED": "Checked your proof: it fails",
            "DECLINED": "Didn't run your proof",
            "TIMEOUT": "Proof check timed out",
        }.get(status, "Proof checking isn't available")
        trail.append({"step": "lean", "label": label, "status": "done" if status in {"CHECKED", "INCOMPLETE", "FAILED"} else "unavailable", "detail": lean_result.get("summary", "")})

    # 3. read linked pages
    urls = list(dict.fromkeys(_URL.findall(message)))[:MAX_URLS]
    if urls:
        pages = crawl_pages(urls, fetch_fn)
        read = [p for p in pages if p["status"] == "OK"]
        for page in read:
            sources.append({"title": page["text"][:80] or page["url"], "url": page["url"]})
            context_lines.append(f"Page {page['url']}: {page['text'][:CONTEXT_CHARS]}")
        trail.append({
            "step": "crawl",
            "label": f"Read {len(read)} page{'s' if len(read) != 1 else ''}" if read else "Couldn't open the link",
            "status": "done" if read else "error",
            "detail": ", ".join(urls),
        })

    # 4. search
    search_body = None
    wants_search = body.hints.search or bool(_SEARCH.search(message))
    create = _intent_create(body)
    if wants_search:
        query = _URL.sub("", re.sub(r"^/search\s+", "", message, flags=re.I)).strip()
        if not query and seen:
            query = " ".join((seen[0].get("excerpt") or seen[0]["summary"]).split()[:12])
        if query:
            search_body = await search_fn(query)
            results = ((search_body or {}).get("search") or {}).get("results") or []
            for row in results:
                if row.get("url"):
                    sources.append({"title": str(row.get("title") or row["url"])[:160], "url": str(row["url"])})
            trail.append({
                "step": "search",
                "label": f"Searched {len(results)} source{'s' if len(results) != 1 else ''}" if results else "Searched the web: nothing found",
                "status": "done",
                "detail": query,
            })

    # 5. answer
    history = list(body.history or [])[-10:]
    if context_lines:
        history.append({"role": "assistant", "content": "Context for this turn: " + " ".join(context_lines)[:4000]})
    pasted_lean = bool(lean_source) and looks_like_lean(message)
    pure_create = bool(create) and bool(_CREATE.search(message)) and not wants_search
    reply: dict[str, Any]
    if search_body is not None:
        reply = dict(search_body)
    elif message and not pasted_lean and not pure_create:
        reply = await chat_fn(
            titanos,
            message,
            history,
            hub_id=body.hub_id,
            last_tool_empty=body.last_tool_empty,
            persona=persona,
            prose=bool(body.prose),
        )
        trail.append({"step": "answer", "label": "Checked what's saved", "status": "done", "detail": ""})
    else:
        reply = {"status": "ACCEPTED", "value": "", "verified": False}

    # 6. create
    created = None
    if create:
        image_src = next((s for s, a in zip(seen, body.attachments) if s["kind"] == "image" and a.matrix is not None), None)
        clip_att = next((a for a in body.attachments if a.kind == "clip" and a.frames is not None), None)
        image_atts = [a for a in body.attachments if a.kind == "image" and a.matrix is not None]
        prompt = _URL.sub("", message).strip() or (seen[0]["summary"] if seen else "")
        try:
            if create == "clip":
                frames = None
                if clip_att is not None:
                    frames = _gray(clip_att.frames)
                elif len(image_atts) >= 2:
                    shapes = {len(a.matrix) for a in image_atts}
                    if len(shapes) == 1:
                        frames = _gray([a.matrix for a in image_atts])
                out = to_jsonable(forge_fn(prompt[:2000], stage="draft", frames=frames, clip=True))
            else:
                matrix = None
                if image_src is not None:
                    matrix = _gray([image_atts[0].matrix])[0]
                out = to_jsonable(forge_fn(prompt[:2000], stage="draft", matrix=matrix))
        except Exception as exc:  # the trail reports it; nothing is faked
            out = {"status": "ERROR", "detail": type(exc).__name__, "url": None}
        url = out.get("url") if isinstance(out.get("url"), str) and str(out.get("url")).startswith("http") else None
        preview = out.get("preview") if create == "clip" and out.get("preview") else None
        made = bool(url or preview)
        noun = "clip" if create == "clip" else ("variation" if image_src is not None else "picture")
        created = {
            "kind": create,
            "made": made,
            "status": out.get("status"),
            "url": url,
            "preview": preview,
            "detail": out.get("detail") or out.get("note") or "",
            "check_metrics": out.get("check_metrics"),
        }
        created["unavailable"] = not made and (str(out.get("status") or "").upper() == "UNAVAILABLE" or out.get("produces_video") is False)
        if made:
            trail.append({"step": "create", "label": f"Made a {noun}", "status": "done", "detail": ""})
        else:
            unavailable = str(out.get("status") or "").upper() == "UNAVAILABLE" or out.get("produces_video") is False
            trail.append({
                "step": "create",
                "label": f"Couldn't make a {noun}" + (": no generator is connected" if unavailable else ""),
                "status": "unavailable" if unavailable else "error",
                "detail": created["detail"],
            })

    # compose the visible reply
    parts = []
    base_text = str(reply.get("reply_text") or reply.get("value") or "").strip()
    if base_text:
        parts.append(base_text)
    if lean_result:
        parts.append(lean_result.get("summary", ""))
    if seen and not base_text:
        parts.append("Here's what I see: " + "; ".join(f"{s['name']}: {s['summary']}" for s in seen) + ".")
    if created and not created["made"]:
        parts.append(
            "I didn't make anything: no picture or video generator is connected yet, so I won't pretend."
            if created.get("unavailable")
            else "I couldn't make that this time."
        )
    elif created and created["made"]:
        parts.append("Here it is." if created["url"] else "Here's a clip made from your frames (black and white).")
    text = "\n\n".join(p for p in parts if p) or "Done."
    reply = dict(reply)
    reply["value"] = text
    reply["reply_text"] = text
    reply.setdefault("status", "ACCEPTED")
    reply["assist"] = {
        "trail": trail,
        "sources": sources[:10],
        "attachments": [{"name": s["name"], "kind": s["kind"], "summary": s["summary"]} for s in seen],
        "perception": [{"name": s["name"], "raw": s["raw"]} for s in seen],
        "lean": lean_result,
        "created": created,
        "context": " ".join(context_lines)[:4000],
        "learned": False,
    }
    return to_jsonable(reply)


def register_assist_routes(app: FastAPI, auth_dep: Any, *, get_titanos: Callable[[], Any], save: Callable[[], None] | None = None) -> None:
    deps = [Depends(auth_dep)]

    @app.post("/api/v1/assist", dependencies=deps)
    async def assist_route(body: AssistBody) -> dict[str, Any]:
        if not (body.message or "").strip() and not body.attachments:
            raise HTTPException(400, "Type a message or attach something.")
        titan = get_titanos()
        result = await run_assist(body, titanos=titan)
        if (result.get("action_taken") or {}).get("wrote") and save is not None:
            try:
                save()
            except Exception:  # pragma: no cover - same policy as /chat
                pass
        return result

    @app.post("/api/v1/verify/lean", dependencies=deps)
    def verify_lean_route(body: LeanBody) -> dict[str, Any]:
        from resileos.verify.lean_check import check_lean

        return check_lean(body.source)

