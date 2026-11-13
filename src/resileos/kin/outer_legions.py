"""Outer-layer legions: Hermes search and crawl, Iris trace, Hades notes.

Everything here is a legion registered on an existing Kin through
``register_legion``, so it inherits that Kin's gate (risk_classify,
budget guard, evidence_attach, no learn_fn outside Eat). Nothing is
registered unless ``register_outer_legions(enable=True)`` is called.

Hermes (messenger, crosses the boundary to the outside):
    search_envelope   web search results -> untrusted candidate envelopes
    crawl_envelope    one fetched page   -> one untrusted candidate envelope
    sandbox_request   refused or UNAVAILABLE; never runs code (opt-in)

Hermes never writes residual state and never learns. An envelope carries
the source URL, the title, and the snippet exactly as the search backend
returned them (tags stripped). It carries no claim: Hermes does not turn
web prose into triples. ``eat_envelope.eat_commit_envelopes`` is the only
path from an envelope to Titanos, and a claim-less envelope abstains
there as unstructured prose.

Iris:  trace_sensor   read-only summary of the residual JSONL trace
Hades: lesson_note    append one lesson line to the notes sidecar

The search and fetch functions are injectable. Tests pass fakes; the
defaults reuse ``harness.legions.search.web_search`` and ``scrape_url``.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import html
import inspect
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from resileos.kin.legions import LegionError, register_legion

ENVELOPE_PRODUCER_VERSION = "hermes-envelope/1"
_TAG = re.compile(r"<[^>]+>")
_SNIPPET_CAP = 600
_PAGE_CAP = 4000


def _resolve(value: Any) -> Any:
    """Run a coroutine to completion, inside or outside a running loop."""
    if not inspect.isawaitable(value):
        return value

    async def _await() -> Any:
        return await value

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _await()).result()


def _plain(text: Any, cap: int) -> str:
    raw = html.unescape(_TAG.sub(" ", str(text or "")))
    return " ".join(raw.split())[:cap]


def _now(now: Optional[datetime]) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_search() -> Callable[..., Any]:
    from resileos.harness.legions.search import web_search

    return web_search


def _default_fetch() -> Callable[..., Any]:
    from resileos.harness.legions.search import scrape_url

    return scrape_url


def search_envelopes(
    query: str,
    *,
    search_fn: Optional[Callable[..., Any]] = None,
    max_results: int = 3,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Search results as untrusted envelopes. Never invents text."""
    query = str(query or "").strip()
    if not query:
        return {"status": "UNAVAILABLE", "reason": "empty query", "envelopes": []}
    fn = search_fn or _default_search()
    try:
        raw = _resolve(fn(query, max_results=max(1, int(max_results))))
    except Exception as exc:  # backend down or blocked
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "envelopes": []}
    if not isinstance(raw, dict) or raw.get("status") != "SUCCESS":
        reason = "search backend returned no results"
        if isinstance(raw, dict) and raw.get("error"):
            reason = "search backend error"
        return {"status": "UNAVAILABLE", "reason": reason, "envelopes": []}
    stamp = _now(now)
    envelopes = []
    for item in list(raw.get("results") or [])[: max(1, int(max_results))]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        envelopes.append(
            {
                "version": ENVELOPE_PRODUCER_VERSION,
                "producer": "hermes.search_envelope",
                "trust": "untrusted",
                "query": query,
                "source": url,
                "title": _plain(item.get("title"), 200),
                "snippet": _plain(item.get("snippet"), _SNIPPET_CAP),
                "retrieved_at": stamp,
                "claim": None,
            }
        )
    return {"status": "OK" if envelopes else "EMPTY", "envelopes": envelopes}


def crawl_envelope(
    url: str,
    *,
    fetch_fn: Optional[Callable[..., Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """One fetched page as one untrusted envelope. Text is the page's own."""
    url = str(url or "").strip()
    if not re.match(r"^https?://", url):
        return {"status": "UNAVAILABLE", "reason": "url must be http or https", "envelopes": []}
    fn = fetch_fn or _default_fetch()
    try:
        raw = _resolve(fn(url))
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "envelopes": []}
    if not isinstance(raw, dict) or raw.get("status") != "SUCCESS":
        return {"status": "UNAVAILABLE", "reason": "fetch failed", "envelopes": []}
    text = _plain(raw.get("content"), _PAGE_CAP)
    if not text:
        return {"status": "EMPTY", "envelopes": []}
    return {
        "status": "OK",
        "envelopes": [
            {
                "version": ENVELOPE_PRODUCER_VERSION,
                "producer": "hermes.crawl_envelope",
                "trust": "untrusted",
                "source": url,
                "text": text,
                "retrieved_at": _now(now),
                "claim": None,
            }
        ],
    }


def review_proof_verified(review: Any) -> bool:
    """True only for a zeus_head result where every reviewer approved and
    verify_on_stop passed."""
    if not isinstance(review, dict) or not review.get("applied"):
        return False
    verdicts = review.get("verdicts") or []
    if not verdicts or not all(isinstance(v, dict) and v.get("approved") for v in verdicts):
        return False
    verification = review.get("verification") or {}
    return bool(isinstance(verification, dict) and verification.get("verified"))


def sandbox_request(*, risk_class: Any = None, review: Any = None) -> dict[str, Any]:
    """Gate for a future sandbox. There is no sandbox runtime, so a request
    that clears the gate is UNAVAILABLE. Nothing is executed."""
    base = {"executed": False, "output": None, "url": None}
    if risk_class != "allow":
        return {**base, "status": "REFUSED", "reason": "risk_class must be allow"}
    if not review_proof_verified(review):
        return {**base, "status": "REFUSED", "reason": "reviewer proof is not verified"}
    return {**base, "status": "UNAVAILABLE", "reason": "no sandbox runtime is configured"}


def register_outer_legions(
    *,
    enable: bool = False,
    search_fn: Optional[Callable[..., Any]] = None,
    fetch_fn: Optional[Callable[..., Any]] = None,
    trace_path: Optional[str] = None,
    notes_path: Optional[str] = None,
    enable_sandbox: bool = False,
) -> list[str]:
    """Register the outer-layer legions. Off unless ``enable`` is true.

    The sandbox gate needs ``enable_sandbox`` as well.
    """
    if not enable:
        return []
    registered: list[str] = []

    def search_envelope(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Web search results as untrusted candidate envelopes."""
        return search_envelopes(
            str(kwargs.get("query") or ""),
            search_fn=search_fn or kwargs.get("search_fn"),
            max_results=int(kwargs.get("max_results") or 3),
        )

    def crawl(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """One fetched page as an untrusted candidate envelope."""
        return crawl_envelope(
            str(kwargs.get("url") or ""),
            fetch_fn=fetch_fn or kwargs.get("fetch_fn"),
        )

    for name, fn, action in (
        ("search_envelope", search_envelope, "web search"),
        ("crawl_envelope", crawl, "fetch page"),
    ):
        registered.append(
            register_legion(
                "hermes",
                fn,
                name=name,
                constraints={
                    "action": action,
                    "writes_residual": False,
                    "executes": True,
                    "escalate_only": True,
                },
            )
        )

    if enable_sandbox:

        def sandbox(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            """Sandbox gate. Refused or UNAVAILABLE. Never runs code."""
            return sandbox_request(
                risk_class=kwargs.get("risk_class"),
                review=kwargs.get("review"),
            )

        registered.append(
            register_legion(
                "hermes",
                sandbox,
                name="sandbox_request",
                constraints={
                    "action": "sandbox request",
                    "writes_residual": False,
                    "executes": True,
                },
            )
        )

    def trace_sensor(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Read-only summary of the residual JSONL trace."""
        from resileos.kin.iris_trace import observe_trace

        return observe_trace(trace_path or kwargs.get("trace_path"), limit=int(kwargs.get("limit") or 500))

    registered.append(
        register_legion(
            "iris",
            trace_sensor,
            name="trace_sensor",
            constraints={"action": "read trace", "writes_residual": False, "executes": True},
        )
    )

    def lesson_note(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Append one lesson line and summary numbers. No history."""
        from resileos.kin.hades_notes import HadesNotes

        path = notes_path or kwargs.get("notes_path")
        if not path:
            raise LegionError("lesson notes need a path")
        return HadesNotes(path).append(
            lesson=kwargs.get("lesson") or seen.get("lesson"),
            verified=bool(kwargs.get("verified", False)),
            outcome=str(kwargs.get("outcome") or "inconclusive"),
            metrics=kwargs.get("metrics"),
            checkpoint_id=kwargs.get("checkpoint_id"),
            packet_hash=kwargs.get("packet_hash"),
        )

    registered.append(
        register_legion(
            "hades",
            lesson_note,
            name="lesson_note",
            constraints={"action": "append lesson", "writes_residual": False, "executes": True},
        )
    )
    return registered


__all__ = [
    "ENVELOPE_PRODUCER_VERSION",
    "crawl_envelope",
    "register_outer_legions",
    "review_proof_verified",
    "sandbox_request",
    "search_envelopes",
]
