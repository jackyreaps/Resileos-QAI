"""Streaming chat turns: typed parts over SSE, resumable, cancellable.

Our own layer, no outside SDK. One turn runs the normal ``run_assist``
path (Kin, harness, Eat gates, mouth policy) and emits typed parts as it
goes. Every part has ``{"v": 1, "seq": n, "type": ...}``; ``PART_SCHEMA``
lists each type's fields and is mirrored by ``assets/stream-parts.js``
(chat, Studio, and Admin share it).

Mouth policy: reply prose is streamed token by token only when the
reply is verified **and** ``should_render_prose`` (Metis + verified
cycle) allows it. Otherwise the reply arrives as one part marked
``verified: false`` and the UI labels it "Not verified".

Resume: parts are buffered per stream (``StreamHub``) for ``TTL`` seconds;
``GET /chat/stream/{id}?after=n`` (or ``Last-Event-ID``) replays from
``n`` and then follows live. Cancel: ``POST /chat/stream/{id}/cancel``
stops the producer task. Streams belong to the caller's key/account.
"""

import asyncio
import json
import re
import time
import uuid
from typing import Any, AsyncIterator, Callable, Optional

SCHEMA_VERSION = 1
PART_SCHEMA: dict[str, tuple[str, ...]] = {
    "start": ("stream_id", "run_id"),
    "step": ("step", "status", "label", "detail"),
    "token": ("content", "verified"),
    "harness": ("confidence", "risk", "verified", "route", "budget"),
    "cycle": ("stage", "label"),
    "checkpoint": ("id", "verified"),
    "evidence": ("sources", "attachments", "packet_hash"),
    "eat": ("accepted", "abstained", "rejected"),
    "address": ("name", "path", "code", "dominant"),
    "abstain": ("status", "label"),
    "separated": ("proposal", "reviewers", "applied", "blind"),
    "final": ("answer", "apollo", "verified", "status", "assist"),
    "error": ("label",),
    "cancelled": ("label",),
    "done": (),
}
TTL = 600
MAX_STREAMS = 256
_TOKEN = re.compile(r"\S+\s*")


def part(kind: str, **fields: Any) -> dict[str, Any]:
    if kind not in PART_SCHEMA:
        raise ValueError(f"unknown part type: {kind}")
    allowed = PART_SCHEMA[kind]
    return {"v": SCHEMA_VERSION, "type": kind, **{k: v for k, v in fields.items() if k in allowed}}


def sse(event: dict[str, Any]) -> str:
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


class Stream:
    def __init__(self, owner: str):
        self.id = uuid.uuid4().hex
        self.owner = owner
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.created = time.time()
        self.task: Optional[asyncio.Task] = None
        self._cond = asyncio.Condition()

    async def push(self, event: dict[str, Any]) -> None:
        async with self._cond:
            event = {**event, "seq": len(self.events) + 1}
            self.events.append(event)
            if event["type"] == "done":
                self.done = True
            self._cond.notify_all()

    async def follow(self, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        index = max(0, int(after))
        while True:
            async with self._cond:
                while index >= len(self.events) and not self.done:
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                batch = self.events[index:]
                finished = self.done
            if not batch and not finished:
                yield {"type": "_ping"}
                continue
            for event in batch:
                index += 1
                yield event
            if finished and index >= len(self.events):
                return


class StreamHub:
    def __init__(self) -> None:
        self.streams: dict[str, Stream] = {}

    def create(self, owner: str) -> Stream:
        self.sweep()
        if len(self.streams) >= MAX_STREAMS:
            oldest = min(self.streams.values(), key=lambda s: s.created)
            self.streams.pop(oldest.id, None)
        stream = Stream(owner)
        self.streams[stream.id] = stream
        return stream

    def get(self, stream_id: str, owner: str) -> Optional[Stream]:
        stream = self.streams.get(stream_id)
        return stream if stream is not None and stream.owner == owner else None

    def sweep(self) -> None:
        now = time.time()
        for sid in [s.id for s in self.streams.values() if now - s.created > TTL]:
            self.streams.pop(sid, None)


HUB = StreamHub()


def _harness(reply: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    risk = next((r.get("risk_class") for r in reversed(rows) if r.get("kind") == "risk"), None)
    route = next((r.get("route") for r in reversed(rows) if r.get("kind") == "route"), None)
    budget = next((r.get("ok") for r in reversed(rows) if r.get("kind") == "budget"), None)
    return part("harness", confidence=reply.get("confidence"), risk=risk or "allow", verified=bool(reply.get("verified") is True),
                route=route or ("residual" if reply.get("source") in ("memory", "residual", "kin") else "answer"),
                budget=budget)


async def produce(stream: Stream, body: Any, *, run: Callable[..., Any], prose_allowed: Callable[[bool], bool]) -> None:
    """Run one turn and push its parts. Never invents a part."""
    loop = asyncio.get_running_loop()
    queue: list[dict[str, Any]] = []

    def on_event(event: dict[str, Any]) -> None:
        kind = event.get("type", "step")
        try:
            queue.append(part(kind, **{k: v for k, v in event.items() if k != "type"}))
        except ValueError:
            return
        loop.call_soon_threadsafe(lambda: None)

    async def flush() -> None:
        while queue:
            await stream.push(queue.pop(0))

    from resileos import run_trace

    try:
        await stream.push(part("start", stream_id=stream.id))
        await stream.push(part("cycle", stage="iris", label="Reading your message"))
        turn = asyncio.ensure_future(run(body, on_event=on_event))
        while not turn.done():
            await flush()
            await asyncio.sleep(0.02)
        await flush()
        reply = turn.result()
        assist = reply.get("assist") or {}
        rows = run_trace.read_run(assist.get("run_id") or "") if assist.get("run_id") else []
        await stream.push(_harness(reply, rows))
        if any(s.get("step") == "search" for s in assist.get("trail") or []):
            await stream.push(part("cycle", stage="hermes", label="Searched"))
        for att in assist.get("attachments") or []:
            if att.get("address") or att.get("code"):
                await stream.push(part("address", name=att.get("name"), path=att.get("address"), code=att.get("code"), dominant=att.get("dominant")))
        eats = [r for r in rows if r.get("kind") == "eat"]
        if eats:
            await stream.push(part("eat", accepted=sum(r.get("action") == "accept" for r in eats),
                                   abstained=sum(r.get("action") == "abstain" for r in eats),
                                   rejected=sum(r.get("action") == "reject" for r in eats)))
        for r in rows:
            if r.get("kind") == "review":
                await stream.push(part("separated", proposal="writer", reviewers=r.get("reviewers"), applied=r.get("applied"), blind=True))
            if r.get("kind") == "checkpoint":
                await stream.push(part("checkpoint", id=r.get("checkpoint_id"), verified=r.get("verified")))
        if assist.get("sources") or assist.get("attachments"):
            await stream.push(part("evidence", sources=[{"title": s.get("title"), "url": s.get("url")} for s in assist.get("sources") or []][:10],
                                   attachments=[a.get("name") for a in assist.get("attachments") or []]))
        verified = reply.get("verified") is True
        mouth = verified and prose_allowed(bool(getattr(body, "prose", True)))
        await stream.push(part("cycle", stage="metis", label="Answer allowed" if mouth else "Answer shown as not verified"))
        text = str(reply.get("reply_text") or reply.get("value") or "")
        status = str(reply.get("status") or "").upper()
        if status in {"NO_ROWS", "ABSTAINED", "ABSTAIN", "MOUTH_CLOSED"}:
            await stream.push(part("abstain", status=status.lower(), label="Doesn't know" if status != "NO_ROWS" else "Nothing saved about that"))
        if mouth:
            for piece in _TOKEN.findall(text):
                await stream.push(part("token", content=piece, verified=True))
                await asyncio.sleep(0)
        elif text:
            await stream.push(part("token", content=text, verified=False))
        await stream.push(part("final", answer=text, apollo=verified, verified=verified, status=status.lower(), assist=assist))
    except asyncio.CancelledError:
        await stream.push(part("cancelled", label="Stopped"))
        await stream.push(part("done"))
        raise
    except Exception:
        await stream.push(part("error", label="Couldn't finish. Try again."))
    await stream.push(part("done"))


def register_stream_routes(app: Any, auth_dep: Any, *, owner_dep: Any, get_titanos: Callable[[], Any]) -> None:
    from fastapi import Depends, HTTPException, Request
    from fastapi.responses import StreamingResponse

    from resileos.chat import assist as assist_mod
    from resileos.chat.assist import AssistBody

    deps = [Depends(auth_dep)]

    def prose_allowed(requested: bool) -> bool:
        try:
            from resileos.kin.mouth_policy import should_render_prose

            return bool(should_render_prose(requested))
        except Exception:
            return False

    async def emit(stream: Stream, after: int, request: Request) -> AsyncIterator[str]:
        yield "retry: 2000\n\n"
        async for event in stream.follow(after):
            if await request.is_disconnected():
                return
            if event.get("type") == "_ping":
                yield ": ping\n\n"
                continue
            yield sse(event)

    headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}

    @app.post("/api/v1/chat/stream", dependencies=deps)
    async def chat_stream(body: AssistBody, request: Request, owner: str = Depends(owner_dep)) -> StreamingResponse:
        if not (body.message or "").strip() and not body.attachments:
            raise HTTPException(400, "Type a message or attach something.")
        from resileos.chat.cascade_tools import FactorPool

        titan = get_titanos()
        stream = HUB.create(owner)

        async def run(b: Any, on_event: Callable) -> dict:
            return await assist_mod.run_assist(b, titanos=titan, factor_pool=FactorPool(), on_event=on_event)

        stream.task = asyncio.ensure_future(produce(stream, body, run=run, prose_allowed=prose_allowed))
        return StreamingResponse(emit(stream, 0, request), media_type="text/event-stream",
                                 headers={**headers, "X-Stream-Id": stream.id})

    @app.get("/api/v1/chat/stream/{stream_id}", dependencies=deps)
    async def chat_stream_resume(stream_id: str, request: Request, after: int = 0, owner: str = Depends(owner_dep)) -> StreamingResponse:
        stream = HUB.get(stream_id, owner)
        if stream is None:
            raise HTTPException(404, "That reply is no longer available. Send it again.")
        last = request.headers.get("last-event-id")
        start = int(last) if last and last.isdigit() else after
        return StreamingResponse(emit(stream, start, request), media_type="text/event-stream",
                                 headers={**headers, "X-Stream-Id": stream.id})

    @app.post("/api/v1/chat/stream/{stream_id}/cancel", dependencies=deps)
    async def chat_stream_cancel(stream_id: str, owner: str = Depends(owner_dep)) -> dict:
        stream = HUB.get(stream_id, owner)
        if stream is None:
            raise HTTPException(404, "Not found.")
        if stream.task is not None and not stream.task.done():
            stream.task.cancel()
            return {"cancelled": True}
        return {"cancelled": False, "reason": "already finished"}


__all__ = ["HUB", "PART_SCHEMA", "SCHEMA_VERSION", "Stream", "StreamHub", "part", "produce", "register_stream_routes", "sse"]
