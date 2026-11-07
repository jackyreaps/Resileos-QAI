"""
Optional FastAPI routes for eat + kin cycle.

Mount from app.py when ready:

    from resileos.kin.http_routes import register_kin_routes
    register_kin_routes(app, get_titanos=lambda: titanos_singleton, auth_dep=verify_api_key)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.kin.bundle import KinBundle, build_kin_bundle
from resileos.kin.eat import eat_and_learn, eat_filter
from resileos.kin.council import council_query


def register_kin_routes(
    app: Any,
    *,
    get_titanos: Callable[[], Any],
    auth_dep: Optional[Any] = None,
    get_bundle: Optional[Callable[[], KinBundle]] = None,
    get_metrics: Optional[Callable[[], dict]] = None,
    get_agency: Optional[Callable[[], Any]] = None,
) -> None:
    """Register POST /api/v1/eat and POST /api/v1/kin/cycle."""
    try:
        from fastapi import Depends
        from pydantic import BaseModel, Field
    except ImportError as e:
        raise ImportError("fastapi required to register kin routes") from e

    deps = [Depends(auth_dep)] if auth_dep is not None else []

    class EatRequest(BaseModel):
        claim: Any = Field(..., description="Triple string or {subject,relation,obj}")
        user_id: str = ""
        allow_sys: bool = False

    class CycleRequest(BaseModel):
        user_id: str = ""
        apply_policy: bool = True

    bundle_holder: dict[str, KinBundle] = {}

    def _bundle() -> KinBundle:
        if get_bundle:
            return get_bundle()
        if "b" not in bundle_holder:
            bundle_holder["b"] = build_kin_bundle()
        return bundle_holder["b"]

    @app.post("/api/v1/eat", dependencies=deps)
    def api_eat(body: EatRequest) -> dict:
        titan = get_titanos()

        def learn(s: str, r: str, o: str) -> None:
            titan.learn(s, r, o)

        decision = eat_and_learn(
            body.claim,
            learn,
            user_id=body.user_id or "",
            seed_record=bool(body.user_id),
            allow_sys=body.allow_sys,
        )
        return decision.to_dict()

    @app.post("/api/v1/kin/cycle", dependencies=deps)
    def api_kin_cycle(body: CycleRequest) -> dict:
        metrics = get_metrics() if get_metrics else {}
        if body.user_id and not metrics:
            try:
                from resileos.seed.metrics import metrics_for

                metrics = metrics_for(body.user_id)
            except Exception:
                metrics = {}
        agency = get_agency() if get_agency else None
        report, policy = _bundle().cycle(
            metrics=metrics,
            agency_group=agency,
            apply_policy=body.apply_policy,
        )
        return {"report": report.to_dict(), "policy": policy.to_dict()}

    @app.post("/api/v1/eat/preview", dependencies=deps)
    def api_eat_preview(body: EatRequest) -> dict:
        """Filter only — no learn."""
        return eat_filter(body.claim, allow_sys=body.allow_sys).to_dict()

    class CouncilRequest(BaseModel):
        subject: str
        relation: str
        profile: str = "personal"

    @app.post("/api/v1/council/query", dependencies=deps)
    def api_council(body: CouncilRequest) -> dict:
        titan = get_titanos()

        def ask(s: str, r: str):
            ask_list = getattr(titan, "ask_list", None)
            if callable(ask_list):
                rows = ask_list(s, r)
                if not rows:
                    return None
                return rows if len(rows) > 1 else rows[0]
            return titan.ask(s, r)

        return council_query(body.subject, body.relation, ask, profile=body.profile).to_dict()

    class PerceiveRequest(BaseModel):
        caption: str
        subject: str = "image"
        commit: bool = False

    @app.post("/api/v1/perceive", dependencies=deps)
    def api_perceive(body: PerceiveRequest) -> dict:
        from resileos.ui.perceive import perceive
        from resileos.kin.eat import eat_filter

        def eat(claim):
            return eat_filter(claim)

        return perceive(body.caption, subject=body.subject, eat_fn=eat, commit=body.commit)

    class TaskStep(BaseModel):
        subject: str
        relation: str

    class TaskRequest(BaseModel):
        goal: str
        steps: list[TaskStep]

    @app.post("/api/v1/task", dependencies=deps)
    def api_task(body: TaskRequest) -> dict:
        from resileos.ui.task_api import task_from_steps
        titan = get_titanos()

        def ask(s, r):
            fn = getattr(titan, "ask", None)
            return fn(s, r) if callable(fn) else None

        steps = [st.model_dump() if hasattr(st, "model_dump") else st.dict() for st in body.steps]
        return task_from_steps(body.goal, steps, ask)

