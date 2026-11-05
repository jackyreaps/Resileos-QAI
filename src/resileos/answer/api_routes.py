"""
FastAPI route handlers for workbench, world assets, and guild console.

Mount from app.py after Titanos singleton is available:

    from resileos.answer.api_routes import register_workspace_routes
    register_workspace_routes(app, get_titanos=lambda: titanos_singleton)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from resileos.answer.guild import (
    award_merits,
    complete_work,
    create_guild,
    join_guild,
    member_status,
    post_work,
)
from resileos.answer.hub_train import train_from_file, train_hub
from resileos.answer.workbench import Workbench, parse_fact_line
from resileos.answer.world_assets import AssetIndex, WorldAsset, register_asset


class LearnLinesBody(BaseModel):
    lines: list[str] = Field(default_factory=list)


class WorldRegisterBody(BaseModel):
    world_id: str
    asset_id: str
    kind: str = "image"
    title: str = ""
    path: str = ""
    url: str = ""
    tags: str = ""
    parent_scene: str = ""
    codex_ref: str = ""
    status: str = "draft"


class GuildJoinBody(BaseModel):
    guild_id: str
    user_id: str
    role: str = "member"


class GuildMeritBody(BaseModel):
    guild_id: str
    user_id: str
    amount: int
    reason: str = ""


class GuildWorkBody(BaseModel):
    guild_id: str
    work_id: str
    title: str
    assignee: str = ""


class GuildCompleteBody(BaseModel):
    guild_id: str
    work_id: str
    user_id: str = ""
    merit_award: int = 0


def _wb(get_titanos: Callable[[], Any], backend: str = "structured") -> Workbench:
    return Workbench(titan=get_titanos(), backend_name=backend)


def register_workspace_routes(
    app: Any,
    *,
    get_titanos: Callable[[], Any],
    asset_index_path: str = "artifacts/world_assets.json",
) -> None:
    """Register /api/v1/workbench/*, /api/v1/world/*, /api/v1/guild/*."""

    @app.post("/api/v1/workbench/ingest")
    def workbench_ingest(body: LearnLinesBody):
        wb = _wb(get_titanos)
        n = 0
        batch = []
        for line in body.lines:
            t = parse_fact_line(line)
            if t:
                batch.append(t)
        if batch:
            n = train_hub(wb, batch, require_hub_prefix=False)
        return {"ingested": n}

    @app.post("/api/v1/world/register")
    def world_register(body: WorldRegisterBody):
        wb = _wb(get_titanos)
        index = AssetIndex.load(__import__("pathlib").Path(asset_index_path))
        asset = WorldAsset(
            world_id=body.world_id,
            asset_id=body.asset_id,
            kind=body.kind,  # type: ignore[arg-type]
            title=body.title,
            path=body.path,
            url=body.url,
            tags=body.tags,
            parent_scene=body.parent_scene,
            codex_ref=body.codex_ref,
            status=body.status,
        )
        n = register_asset(wb, asset, index=index)
        return {"registered": n, "subject": asset.subject()}

    @app.post("/api/v1/guild/create")
    def guild_create(guild_id: str, name: str = ""):
        wb = _wb(get_titanos)
        n = create_guild(wb, guild_id, name=name)
        return {"ok": True, "triples": n, "guild_id": guild_id}

    @app.post("/api/v1/guild/join")
    def guild_join(body: GuildJoinBody):
        wb = _wb(get_titanos)
        n = join_guild(wb, body.guild_id, body.user_id, role=body.role)
        st = member_status(wb, body.guild_id, body.user_id)
        return {
            "ok": True,
            "triples": n,
            "role": st.role,
            "merits": st.merits,
            "status": st.status,
        }

    @app.post("/api/v1/guild/merit")
    def guild_merit(body: GuildMeritBody):
        wb = _wb(get_titanos)
        total = award_merits(
            wb, body.guild_id, body.user_id, body.amount, reason=body.reason
        )
        return {"ok": True, "merits": total}

    @app.get("/api/v1/guild/member")
    def guild_member(guild_id: str, user_id: str):
        wb = _wb(get_titanos)
        st = member_status(wb, guild_id, user_id)
        return {
            "guild_id": st.guild_id,
            "user_id": st.user_id,
            "role": st.role,
            "merits": st.merits,
            "status": st.status,
        }

    @app.post("/api/v1/guild/work")
    def guild_work(body: GuildWorkBody):
        wb = _wb(get_titanos)
        n = post_work(
            wb, body.guild_id, body.work_id, body.title, assignee=body.assignee
        )
        return {"ok": True, "triples": n, "work_id": body.work_id}

    @app.post("/api/v1/guild/complete")
    def guild_complete(body: GuildCompleteBody):
        wb = _wb(get_titanos)
        return complete_work(
            wb,
            body.guild_id,
            body.work_id,
            merit_award=body.merit_award,
            user_id=body.user_id,
        )
