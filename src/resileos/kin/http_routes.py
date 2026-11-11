"""Optional FastAPI routes for eat + kin cycle.

No ``from __future__ import annotations`` here: the request models are
defined inside ``register_kin_routes``, and postponed annotations make
FastAPI read them as query parameters instead of JSON bodies.
"""

from typing import Any, Callable, Optional

from resileos.kin.bundle import KinBundle, build_kin_bundle
from resileos.kin.eat import eat_and_learn, eat_filter
from resileos.kin.council import council_query
from resileos.harness.separated import run_separated


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
        residual_packet_hash: Optional[str] = None

    class SeparatedCycleRequest(BaseModel):
        writer: str = "apollo"
        subject: str = "world:apollo"
        facts: list = []
        art: bool = False
        use_council: bool = True
        use_athena: bool = False
        profile: str = "personal"

    bundle_holder: dict[str, KinBundle] = {}

    def _bundle() -> KinBundle:
        if get_bundle:
            return get_bundle()
        if "b" not in bundle_holder:
            bundle_holder["b"] = build_kin_bundle()
        return bundle_holder["b"]

    def _ask_fn(titan):
        def ask(s: str, r: str):
            ask_list = getattr(titan, "ask_list", None)
            if callable(ask_list):
                rows = ask_list(s, r)
                if not rows:
                    return None
                return rows if len(rows) > 1 else rows[0]
            return titan.ask(s, r)
        return ask

    @app.post("/api/v1/eat", dependencies=deps)
    def api_eat(body: EatRequest) -> dict:
        titan = get_titanos()
        decision = eat_and_learn(
            body.claim,
            lambda s, r, o: titan.learn(s, r, o),
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

    @app.post("/api/v1/kin/separated_cycle", dependencies=deps)
    def api_separated_cycle(body: SeparatedCycleRequest) -> dict:
        """Write → verifiers → council → (athena) → Zeus apply."""
        from resileos.kin.apollo import apollo_cycle

        titan = get_titanos()

        if body.writer == "apollo":
            writer_fn = apollo_cycle
            writer_kwargs = {"subject": body.subject, "art": body.art}
            writer_args = (body.facts,)
        else:
            return {"applied": False, "reason": f"unknown writer: {body.writer}"}

        return run_separated(
            writer_fn,
            writer_name=body.writer,
            action_type="apollo",
            learn_fn=titan.learn,
            ask_fn=_ask_fn(titan),
            use_council=body.use_council,
            use_athena=body.use_athena,
            profile=body.profile,
            writer_args=writer_args,
            writer_kwargs=writer_kwargs,
        )

    @app.post("/api/v1/eat/preview", dependencies=deps)
    def api_eat_preview(body: EatRequest) -> dict:
        return eat_filter(body.claim, allow_sys=body.allow_sys).to_dict()

    class CouncilRequest(BaseModel):
        subject: str
        relation: str
        profile: str = "personal"

    @app.post("/api/v1/council/query", dependencies=deps)
    def api_council(body: CouncilRequest) -> dict:
        titan = get_titanos()
        return council_query(
            body.subject, body.relation, _ask_fn(titan),
            profile=body.profile,
        ).to_dict()
