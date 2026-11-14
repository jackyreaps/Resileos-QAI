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
import html
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
    # Content-free use factors (residual_factors) are on by default; this
    # opts the turn out. Files never contribute either way.
    factors_opt_out: bool = False


class CascadeMakeBody(BaseModel):
    matrix: list[Any] | None = None
    frames: list[Any] | None = Field(default=None, max_length=24)
    code: str | None = Field(default=None, max_length=64)
    n: int = Field(default=4, ge=1, le=6)
    frames_out: int = Field(default=12, ge=2, le=24)


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

def resolve_public(url: str) -> str | None:
    """The address to connect to, or None.

    Only http(s) on ports 80/443, and only when every address the host
    resolves to is global (no private, loopback, link-local, reserved,
    or multicast). The caller connects to this exact address, so a second
    DNS answer can't swap in a private one (DNS rebinding).
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.port not in (None, 80, 443):
        return None
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    addrs = []
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if not addr.is_global or addr.is_multicast:
            return None
        addrs.append(addr)
    return str(addrs[0]) if addrs else None


def public_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves to public addresses."""
    return resolve_public(url) is not None


def pinned_request(url: str, ip: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    """(URL with the host replaced by ``ip``, headers, httpx extensions).

    Host stays the real name for the server, and TLS uses it for SNI and
    certificate checks, so pinning doesn't weaken HTTPS.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    literal = f"[{ip}]" if ":" in ip else ip
    netloc = literal + (f":{parsed.port}" if parsed.port else "")
    target = parsed._replace(netloc=netloc).geturl()
    host_header = host + (f":{parsed.port}" if parsed.port else "")
    headers = {"Host": host_header, "User-Agent": "ResileosBot/1.0 (+https://resileosai.fun)"}
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return target, headers, extensions


async def guarded_fetch(
    url: str,
    *,
    client_factory: Callable[[], Any] | None = None,
    resolver: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Fetch one public page, connecting to the checked IP.

    Each hop (including redirects, followed by hand) is resolved once,
    checked, and then fetched from that exact address.
    """
    import httpx

    factory = client_factory or (lambda: httpx.AsyncClient(timeout=8.0, follow_redirects=False, trust_env=False))
    resolve = resolver or resolve_public
    current = url
    async with factory() as client:
        for _ in range(4):
            ip = resolve(current)
            if not ip:
                return {"status": "BLOCKED", "content": ""}
            target, headers, extensions = pinned_request(current, ip)
            resp = await client.get(target, headers=headers, extensions=extensions)
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


def _guarded_sync(url: str) -> dict[str, Any]:
    from resileos.kin.outer_legions import _resolve

    return _resolve(guarded_fetch(url))


async def native_chat_search(query: str) -> dict[str, Any]:
    """Search our own index. The third-party fallback runs only when
    ``RESILEOS_SEARCH_FALLBACK`` turns it on, and its rows say so."""
    from resileos.kin import hermes_crawl

    found = hermes_crawl.native_search(
        query, index=hermes_crawl.shared_index(), fallback=hermes_crawl.fallback_from_env(), max_results=6
    )
    rows = [
        {"title": p["title"] or p["url"], "url": p["url"], "snippet": p["snippet"], "origin": p["origin_label"],
         "domain": p["domain"], "retrieved_at": p["retrieved_at"]}
        for p in found["packets"]
    ]
    text = ("Search results (not checked against saved facts):\n" + "\n".join(f"- {r['title']} ({r['url']})" for r in rows)
            if rows else "Our search index has nothing on that yet. That is not a stored fact.")
    return {
        "status": "ACCEPTED" if rows else "NO_ROWS",
        "value": text,
        "reply_text": text,
        "verified": False,
        "source": "web_search",
        "message_kind": "search",
        "search": {"query": query, "status": "SUCCESS" if rows else "EMPTY", "results": rows,
                   "fallback_used": found.get("fallback_used")},
    }


def crawl_pages(urls: list[str], fetch_fn: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    from resileos.kin.outer_legions import crawl_envelope

    pages = []
    for url in urls[:MAX_URLS]:
        out = crawl_envelope(url, fetch_fn=fetch_fn or guarded_fetch)
        env = (out.get("envelopes") or [None])[0]
        pages.append({"url": url, "status": out.get("status"), "text": (env or {}).get("text", "")})
    return pages


# ---------------------------------------------------------------- the turn

def _best_sentence(text: str, query: str) -> str:
    """The page sentence that shares the most words with the query."""
    want = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    best, score = "", 0
    for sentence in re.split(r"(?<=[.!?])\s+", text[:20000]):
        sentence = " ".join(sentence.split())
        if not 30 <= len(sentence) <= 400:
            continue
        have = set(re.findall(r"[a-z0-9]+", sentence.lower()))
        hit = len(want & have)
        if hit > score:
            best, score = sentence, hit
    return best


def _clean(text: Any) -> str:
    """Search providers return HTML bits (<b>, &#x27;). Show plain words."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).split())


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
    factor_pool: Any | None = None,
    crawl_top: int = 2,
) -> dict[str, Any]:
    from resileos.answer.agent_loop import run_agent_chat
    from resileos.answer.user_profile import PERSONA_PACKS
    from resileos.kin.studio_tools import run_forge_video
    from resileos.ui.query_scale import to_jsonable
    from resileos.verify.lean_check import check_lean, extract_lean, looks_like_lean
    from resileos.chat import cascade_tools as cascade

    chat_fn = chat_fn or run_agent_chat
    search_fn = search_fn or native_chat_search
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
        try:
            looked["cascade"] = cascade.address_upload(looked["kind"], looked.get("raw"), matrix=att.matrix, frames=att.frames, text=att.text)
        except (ValueError, TypeError, IndexError):
            looked["cascade"] = None
        looked["from_files"] = bool(att.file_id)
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
        if seen and not cascade._tokens(query):
            # "find sources about this": search for what was perceived.
            looked = seen[0].get("excerpt") or seen[0]["summary"]
            dominant = ((seen[0].get("cascade") or {}).get("chroma_code") or {}).get("dominant") or ""
            query = " ".join((f"{dominant} {looked}" if dominant else looked).split()[:12])
        if query:
            search_body = await search_fn(query)
            results = ((search_body or {}).get("search") or {}).get("results") or []
            cleaned = [
                {"title": _clean(row.get("title") or row.get("url"))[:160], "url": str(row.get("url") or ""), "snippet": _clean(row.get("snippet") or "")[:300]}
                for row in results if isinstance(row, dict)
            ]
            colors = [str((s.get("cascade") or {}).get("chroma_code", {}).get("dominant") or "") for s in seen if s.get("cascade") and s["cascade"].get("chroma_code")]
            ranked = cascade.rank_sources(cleaned, query, extra_terms=colors if not cascade._tokens(query) else ())
            for env in ranked["envelopes"]:
                sources.append({"title": env["title"], "url": env["source"], "snippet": env["snippet"], "address": env["address"]["path"], "score": env["score"]})
            kept = len(ranked["envelopes"])
            label = f"Searched {len(results)} source{'s' if len(results) != 1 else ''}" if results else "Searched our index: nothing found"
            if results and kept < len(results):
                label += f", kept {kept}"
            search_step = {"step": "search", "label": label, "status": "done", "detail": query}
            trail.append(search_step)
            # Follow the best-ranked results to their pages (guarded fetch,
            # pinned IP), then check what they say. Chat never saves facts.
            if crawl_top and ranked["envelopes"]:
                from resileos.kin import hermes_crawl

                targets = [env["source"] for env in ranked["envelopes"][:crawl_top] if env["source"] not in urls]
                fan = hermes_crawl.ichnaea_fanout(
                    [{"url": t} for t in targets], max_follow=len(targets), fetch_fn=fetch_fn or _guarded_sync
                ) if targets else {"pages": [], "candidates": []}
                read = fan["pages"]
                for page in read:
                    best = _best_sentence(page["text"], query)
                    for src in sources:
                        if src["url"] == page["url"]:
                            src["read"] = True
                            if best:
                                src["excerpt"] = best
                    context_lines.append(f"Page {page['url']}: {page['text'][:CONTEXT_CHARS]}")
                checked = hermes_crawl.eat_bridge(fan["candidates"])
                facts = [r for r in checked["results"] if r.get("action") == "accept"]
                if read:
                    n = len(facts)
                    search_step["label"] = (
                        f"Searched {len(results)} source{'s' if len(results) != 1 else ''}, "
                        f"followed {len(read)} to the original page{'s' if len(read) != 1 else ''}, "
                        f"kept {n} fact{'s' if n != 1 else ''}"
                    )
                    lines = [f"{f['subject']} · {f['relation']} · {f['obj']}"
                             + (f" ({f.get('valid_from') or '…'} to {f.get('valid_to') or '…'})" if f.get("valid_from") or f.get("valid_to") else "")
                             + f" — {f.get('source')}" for f in facts[:6]]
                    held = checked["held_back"]
                    search_step["detail"] = "; ".join(
                        [query] + lines + ([f"held back {held} (not clear facts)"] if held else [])
                        + ["not saved: chat doesn't write memory"]
                    )
                    search_step["facts"] = [
                        {k: f.get(k) for k in ("subject", "relation", "obj", "valid_from", "valid_to", "source", "as_of")}
                        for f in facts[:6]
                    ]
                elif targets:
                    trail.append({"step": "crawl", "label": "Couldn't open the top results", "status": "error",
                                  "detail": ", ".join(targets)})

    # 5. answer
    history = list(body.history or [])[-10:]
    if context_lines:
        history.append({"role": "assistant", "content": "Context for this turn: " + " ".join(context_lines)[:4000]})
    pasted_lean = bool(lean_source) and looks_like_lean(message)
    pure_create = bool(create) and bool(_CREATE.search(message)) and not wants_search
    reply: dict[str, Any]
    if search_body is not None:
        reply = dict(search_body)
        found = [src for src in sources if src.get("snippet") is not None]
        if found:
            lines = ["Here's what I found. I haven't checked these against what's saved:"]
            for row in found[:5]:
                lines.append(f"- {row['title']}: {row.get('excerpt') or row['snippet']}".rstrip(": "))
            reply["value"] = reply["reply_text"] = "\n".join(lines)
            reply["verified"] = False
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
        made_here = None
        try:
            if create == "clip":
                frames = None
                if clip_att is not None:
                    made_here = cascade.recolor_clip(clip_att.frames)
                elif len(image_atts) >= 2 and len({(len(a.matrix), len(a.matrix[0]) if a.matrix else 0) for a in image_atts}) == 1:
                    made_here = cascade.recolor_clip([a.matrix for a in image_atts], variant=0)
                elif len(image_atts) == 1:
                    made_here = cascade.clip_from_code(image_atts[0].matrix)
                if made_here is None:
                    out = to_jsonable(forge_fn(prompt[:2000], stage="draft", frames=frames, clip=True))
            else:
                if image_src is not None:
                    made_here = cascade.variations_from_code(image_atts[0].matrix, n=4)
                else:
                    out = to_jsonable(forge_fn(prompt[:2000], stage="draft", matrix=None))
        except Exception as exc:  # the trail reports it; nothing is faked
            made_here = None
            out = {"status": "ERROR", "detail": type(exc).__name__, "url": None}
        if made_here is not None:
            out = {"status": "MADE", "url": None, "detail": made_here["method"], "check_metrics": made_here.get("check_metrics")}
        url = out.get("url") if isinstance(out.get("url"), str) and str(out.get("url")).startswith("http") else None
        preview = out.get("preview") if create == "clip" and out.get("preview") else None
        made = bool(url or preview or made_here)
        noun = "clip" if create == "clip" else ("variation" if image_src is not None else "picture")
        created = {
            "kind": create,
            "made": made,
            "status": out.get("status"),
            "url": url,
            "preview": preview,
            "detail": out.get("detail") or out.get("note") or "",
            "check_metrics": out.get("check_metrics"),
            "variations": [v["matrix"] for v in made_here["variations"]] if made_here and made_here.get("variations") else None,
            "frames": made_here.get("frames") if made_here else None,
            "fps": made_here.get("fps") if made_here else None,
            "code": made_here.get("code") if made_here else None,
        }
        created["unavailable"] = not made and (str(out.get("status") or "").upper() == "UNAVAILABLE" or out.get("produces_video") is False)
        if made:
            many = created["variations"] and len(created["variations"]) > 1
            label = f"Made {len(created['variations'])} variations" if many else f"Made a {noun}"
            trail.append({"step": "create", "label": label, "status": "done", "detail": created["detail"]})
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
        if created["url"]:
            parts.append("Here it is.")
        elif created.get("variations"):
            parts.append("Here are a few color variations, made from your picture's color code.")
        elif created.get("frames"):
            parts.append("Here's a short clip made from your picture's color code.")
        else:
            parts.append("Here's a clip made from your frames (black and white).")
    text = "\n\n".join(p for p in parts if p) or "Done."
    reply = dict(reply)
    reply["value"] = text
    reply["reply_text"] = text
    reply.setdefault("status", "ACCEPTED")
    # Content-free use factors for the local hub. Only a checked turn counts
    # (a Lean proof that checks, or a reply marked verified), and the factor
    # is built from the turn's step outcomes only: no attachment, pasted
    # text, or perception value goes into it.
    counted = 0
    if factor_pool is not None and not body.factors_opt_out:
        gate = "lean" if (lean_result or {}).get("status") == "CHECKED" else ("verified" if reply.get("verified") is True else "")
        if gate:
            done = sum(1 for step in trail if step.get("status") == "done")
            record = cascade.turn_factor(gate, steps_done=done, steps_total=len(trail))
            counted += int(factor_pool.add(record))
    reply["assist"] = {
        "trail": trail,
        "sources": sources[:10],
        "attachments": [
            {
                "name": s["name"],
                "kind": s["kind"],
                "summary": s["summary"],
                "address": ((s.get("cascade") or {}).get("address") or {}).get("path"),
                "code": (s.get("cascade") or {}).get("code"),
                "dominant": ((s.get("cascade") or {}).get("chroma_code") or {}).get("dominant"),
            }
            for s in seen
        ],
        "factors_counted": counted,
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
        from resileos.chat.cascade_tools import FactorPool

        titan = get_titanos()
        result = await run_assist(body, titanos=titan, factor_pool=FactorPool())
        if (result.get("action_taken") or {}).get("wrote") and save is not None:
            try:
                save()
            except Exception:  # pragma: no cover - same policy as /chat
                pass
        return result

    @app.post("/api/v1/studio/variations", dependencies=deps)
    def studio_variations(body: CascadeMakeBody) -> dict[str, Any]:
        """Picture variations from a photo's chroma belt code (no provider)."""
        from resileos.chat import cascade_tools as cascade

        try:
            if body.frames:
                return cascade.recolor_clip(body.frames, code=body.code, variant=max(1, body.n))
            if body.matrix is None:
                raise HTTPException(400, "Add a photo to make variations from.")
            return cascade.variations_from_code(body.matrix, n=body.n, code=body.code)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/v1/studio/clip-from-picture", dependencies=deps)
    def studio_clip_from_picture(body: CascadeMakeBody) -> dict[str, Any]:
        """A short clip from one photo: φ hue steps + the motion phase step."""
        from resileos.chat import cascade_tools as cascade

        if body.matrix is None:
            raise HTTPException(400, "Add a photo to make a clip from.")
        try:
            return cascade.clip_from_code(body.matrix, frames=body.frames_out, code=body.code)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/v1/factors/hub", dependencies=deps)
    def factors_hub() -> dict[str, Any]:
        """Content-free use factors aggregated for the local hub, plus
        Morpheus dream candidates. Read-only; Eat stays the only writer.
        The Pages proxy keeps this admin-only."""
        from resileos.chat.cascade_tools import FactorPool

        return FactorPool().hub_aggregate()

    @app.post("/api/v1/verify/lean", dependencies=deps)
    def verify_lean_route(body: LeanBody) -> dict[str, Any]:
        from resileos.verify.lean_check import check_lean

        return check_lean(body.source)

