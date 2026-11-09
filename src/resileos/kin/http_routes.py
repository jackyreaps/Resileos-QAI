"""Optional FastAPI routes for eat + kin cycle.

Mount from app.py when ready:

    from resileos.kin.http_routes import register_kin_routes
    register_kin_routes(app, get_titanos=lambda: titanos_singleton,
                        auth_dep=verify_api_key)
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
        claim: Any = Field(
            ..., description="Triple string or {subject,relation,obj}"
        )
        user_id: str = ""
        allow_sys: bool = False

    class CycleRequest(BaseModel):
        user_id: str = ""
        apply_policy: bool = True
        residual_packet_hash: Optional[str] = None

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

        residual_packet = None
        if body.residual_packet_hash:
            residual_packet = type(
                "Stub", (), {"packet_hash": body.residual_packet_hash}
            )()

        report, policy, harness = _bundle().cycle(
            metrics=metrics,
            agency_group=agency,
            apply_policy=body.apply_policy,
            residual_packet=residual_packet,
        )
        return {
            "report": report.to_dict(),
            "policy": policy.to_dict(),
            "harness": harness,
        }

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

        return council_query(
            body.subject, body.relation, ask, profile=body.profile
        ).to_dict()

    class PerceiveRequest(BaseModel):
        caption: str
        subject: str = "image"
        commit: bool = False

    @app.post("/api/v1/perceive", dependencies=deps)
    def api_perceive(body: PerceiveRequest) -> dict:
        from resileos.ui.perceive import perceive

        def eat(claim):
            return eat_filter(claim)

        return perceive(
            body.caption,
            subject=body.subject,
            eat_fn=eat,
            commit=body.commit,
        )

    class TaskStep(BaseModel):
        subject: str
        relation: str

    class TaskRequest(BaseModel):
        goal: str
        steps: list[TaskStep]

    @app.post("/api/v1/task", dependencies=deps)
    def api_task(body: TaskRequest) -> dict:
        from resileos.ui.scale_wire import task_with_scale

        titan = get_titanos()

        def ask(s, r):
            fn = getattr(titan, "ask", None)
            return fn(s, r) if callable(fn) else None

        steps = [
            st.model_dump() if hasattr(st, "model_dump") else st.dict()
            for st in body.steps
        ]
        return task_with_scale(body.goal, steps, ask)

    class PerceiveImageRequest(BaseModel):
        features: Optional[dict] = None
        subject: str = "image"

    @app.post("/api/v1/perceive/image", dependencies=deps)
    def api_perceive_image(body: PerceiveImageRequest) -> dict:
        from resileos.ui.framework_gate import gate_candidate
        from resileos.ui.image_encoder import features_to_triples

        features = body.features or {}
        triples = (
            features_to_triples(features, subject=body.subject)
            if features
            else []
        )
        gated = [
            gate_candidate(t, stored=[], eat_accepted=False) for t in triples
        ]
        return {
            "features": features,
            "candidates": gated,
            "note": "Not facts until eat accepts and learn is called.",
        }

    class WorkbenchRequest(BaseModel):
        text: str
        subject: str = "work"
        persona: str = ""

    @app.post("/api/v1/workbench", dependencies=deps)
    def api_workbench(body: WorkbenchRequest) -> dict:
        from resileos.ui.workbench import formalize

        titan = get_titanos()

        def eat(claim):
            return eat_filter(claim)

        def learn(s, r, o):
            fn = getattr(titan, "learn", None)
            if callable(fn):
                fn(s, r, o)

        return formalize(
            body.text,
            subject=body.subject,
            persona=body.persona,
            eat_fn=eat,
            learn_fn=learn,
        )

    class QdterIngestRequest(BaseModel):
        track: str
        payload_id: str
        belt: int = 0
        frame: int = 0
        persona: str = ""

    @app.post("/api/v1/qdter/ingest", dependencies=deps)
    def api_qdter(body: QdterIngestRequest) -> dict:
        from resileos.ui.qdter_interface import ingest

        claim = f"{body.track} payload {body.payload_id}"
        decision = eat_filter(claim)
        return ingest(
            body.track,
            body.payload_id,
            belt=body.belt,
            frame=body.frame,
            persona=body.persona,
            eat_accepted=bool(getattr(decision, "accepted", False)),
        )

    _HUBS: dict = {}

    class HubLearnRequest(BaseModel):
        hub_id: str
        subject: str
        relation: str
        obj: str
        kind: str = "user"

    @app.post("/api/v1/hub/learn", dependencies=deps)
    def api_hub_learn(body: HubLearnRequest) -> dict:
        from resileos.ui.hub import Hub

        h = _HUBS.get(body.hub_id)
        if h is None:
            h = Hub(body.hub_id, kind=body.kind)
            _HUBS[body.hub_id] = h

        def eat(claim):
            return eat_filter(claim)

        event = h.learn(
            body.subject, body.relation, body.obj, eat_fn=eat
        )
        return {"event": event, "observe": h.observe()}

    @app.get("/api/v1/hub/{hub_id}", dependencies=deps)
    def api_hub_get(hub_id: str) -> dict:
        h = _HUBS.get(hub_id)
        if h is None:
            return {"hub_id": hub_id, "n_facts": 0, "n_events": 0}
        return h.observe()

    class ApolloRequest(BaseModel):
        subject: str = "world:apollo"
        facts: list = []
        art: bool = False

    @app.post("/api/v1/apollo", dependencies=deps)
    def api_apollo(body: ApolloRequest) -> dict:
        from resileos.kin.apollo import apollo_cycle

        return apollo_cycle(
            body.facts,
            subject=body.subject,
            eat_fn=eat_filter,
            art=body.art,
        )
