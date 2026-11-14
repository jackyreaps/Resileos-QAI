"""HTTP routes for Studio projects (per account, individual tier).

``/api/v1/studio-projects`` lists and creates; ``/{id}`` reads, saves and
deletes; ``/{id}/op/{name}`` runs one Studio operation; ``/{id}/stream/{name}``
runs it on the shared stream layer (typed parts, resumable and
cancellable through ``/api/v1/chat/stream/{stream_id}``).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from resileos.studio import projects as store
from resileos.studio import studio_ops as ops

_LOCK = threading.Lock()


def _merge_assets(stored: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """The client may rename, annotate, reorder or remove assets, but
    picture data only ever comes from the server's own copy."""
    have = {a["id"]: a for a in stored.get("assets") or []}
    out = []
    for row in incoming.get("assets") or []:
        if isinstance(row, dict) and row.get("id") in have:
            keep = dict(have[row["id"]])
            keep["name"] = str(row.get("name") or keep.get("name") or "")[:120]
            keep["note"] = str(row.get("note") or "")[:500]
            out.append(keep)
    return {**incoming, "assets": out, "picks": incoming.get("picks", stored.get("picks", [])),
            "created_at": stored.get("created_at")}


def _run(owner: str, pid: str, name: str, body: dict[str, Any], *, titanos: Any = None,
         on_step: Callable[[str, str], None] = lambda l, s: None) -> dict[str, Any]:
    with _LOCK:
        project = store.get_project(owner, pid)
        if name in ops.OPS:
            project, result = ops.OPS[name](project, body, on_step=on_step)
        elif name == "pick":
            project, result = ops.pick(project, body)
        elif name == "levels":
            project, result = ops.level_preview(project, body)
        elif name == "check":
            project, result = ops.world_check(project, body)
        elif name == "world_level":
            project, result = ops.world_level(project, body)
        elif name == "lean":
            project, result = ops.game_lean(project, body)
        elif name == "dream":
            project, result = ops.dream(project, body)
        elif name == "promote":
            project, result = ops.promote_preview(project, body, titanos=titanos)
        else:
            raise KeyError(name)
        saved = store.save_project(owner, project) if name in ops.OPS or name == "pick" else project
    return {"result": result, "project": saved}


def register_project_routes(app: FastAPI, owner_dep: Any, *, get_titanos: Callable[[], Any] = lambda: None) -> None:
    def owner_of(owner: str = Depends(owner_dep)) -> str:
        try:
            store.require_account(owner)
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from None
        return owner

    def fail(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(404, "That project isn't here.")
        return HTTPException(400, str(exc))

    @app.get("/api/v1/studio-projects")
    def list_projects(owner: str = Depends(owner_of)) -> dict[str, Any]:
        return {"projects": store.list_projects(owner), "limit": store.MAX_PROJECTS,
                "video_provider": _video_provider()}

    @app.post("/api/v1/studio-projects")
    def create_project(body: dict[str, Any] = Body(default_factory=dict), owner: str = Depends(owner_of)) -> dict[str, Any]:
        try:
            project = store.save_project(owner, {"name": body.get("name"), "summary": body.get("summary")})
            handed = body.get("from_chat")
            if isinstance(handed, dict):
                # Chat's "make from this": the attachment lands on the asset board.
                handed = {**handed, "from_chat": True}
                project = _run(owner, project["id"], "add_asset", handed)["project"]
            return project
        except (ValueError, KeyError) as exc:
            raise fail(exc) from None

    @app.get("/api/v1/studio-projects/{pid}")
    def get_project(pid: str, owner: str = Depends(owner_of)) -> dict[str, Any]:
        try:
            return store.get_project(owner, pid)
        except KeyError as exc:
            raise fail(exc) from None

    @app.put("/api/v1/studio-projects/{pid}")
    def put_project(pid: str, body: dict[str, Any] = Body(...), owner: str = Depends(owner_of)) -> dict[str, Any]:
        try:
            with _LOCK:
                stored = store.get_project(owner, pid)
                return store.save_project(owner, {**_merge_assets(stored, body), "id": pid})
        except (ValueError, KeyError) as exc:
            raise fail(exc) from None

    @app.delete("/api/v1/studio-projects/{pid}")
    def delete_project(pid: str, owner: str = Depends(owner_of)) -> dict[str, Any]:
        try:
            return {"deleted": store.delete_project(owner, pid)}
        except KeyError as exc:
            raise fail(exc) from None

    @app.post("/api/v1/studio-projects/{pid}/op/{name}")
    def run_op(pid: str, name: str, body: dict[str, Any] = Body(default_factory=dict), owner: str = Depends(owner_of)) -> dict[str, Any]:
        try:
            return _run(owner, pid, name, body, titanos=get_titanos())
        except (ValueError, KeyError) as exc:
            raise fail(exc) from None

    @app.post("/api/v1/studio-projects/{pid}/stream/{name}")
    async def stream_op(pid: str, name: str, request: Request, body: dict[str, Any] = Body(default_factory=dict),
                        owner: str = Depends(owner_of)) -> StreamingResponse:
        from resileos.chat.stream import HUB, part, sse

        if name not in ops.OPS:
            raise HTTPException(404, "That can't be streamed.")
        try:
            store.get_project(owner, pid)
        except KeyError as exc:
            raise fail(exc) from None
        stream = HUB.create(owner)
        loop = asyncio.get_running_loop()

        def on_step(label: str, status: str) -> None:
            asyncio.run_coroutine_threadsafe(stream.push(part("step", step=name, status=status, label=label, detail="")), loop)

        async def produce() -> None:
            await stream.push(part("start", stream_id=stream.id))
            await stream.push(part("cycle", stage="morpheus" if name != "text_to_video" else "hermes", label="Making"))
            try:
                out = await asyncio.to_thread(_run, owner, pid, name, body, on_step=on_step)
                result = out["result"]
                status = result.get("status") or "MADE"
                for asset in result.get("made") or []:
                    await stream.push(part("address", name=asset.get("name"), path=(asset.get("address") or {}).get("path"),
                                           code=asset.get("code")))
                if status == "UNAVAILABLE":
                    await stream.push(part("abstain", status="UNAVAILABLE", label=result.get("detail") or "Not available"))
                await stream.push(part("final", answer="", apollo=None, verified=False, status=status,
                                       assist={"result": {k: v for k, v in result.items() if k != "made"},
                                               "made": [a["id"] for a in result.get("made") or []]}))
            except (ValueError, KeyError) as exc:
                await stream.push(part("error", label=str(exc) if isinstance(exc, ValueError) else "That project isn't here."))
            except asyncio.CancelledError:
                await stream.push(part("cancelled", label="Stopped"))
            await stream.push(part("done"))

        stream.task = asyncio.ensure_future(produce())

        async def emit() -> Any:
            yield "retry: 2000\n\n"
            async for event in stream.follow(0):
                if await request.is_disconnected():
                    return
                if event.get("type") == "_ping":
                    yield ": ping\n\n"
                    continue
                yield sse(event)

        return StreamingResponse(emit(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
                                          "X-Stream-Id": stream.id})


def _video_provider() -> dict[str, Any]:
    import os

    configured = bool(os.getenv("RESILEOS_VIDEO_PROVIDER", "").strip())
    return {"configured": configured, "status": "READY" if configured else "UNAVAILABLE"}
