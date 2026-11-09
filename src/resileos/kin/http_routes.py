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
from resileos.harness.separated import SeparatedCycle, zeus_head


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

    class SeparatedCycleRequest(BaseModel):
        writer: str = "apollo"
        subject: str = "world:apollo"
        facts: list = []
        art: bool = False
        residual_packet_hash: Optional[str] = None

    bundle_holder: dict[str, KinBundle] = {}
    _sep = SeparatedCycle(id_prefix="kin")

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

    @app.post("/api/v1/kin/separated_cycle", dependencies=deps)
    def api_separated_cycle(body: SeparatedCycleRequest) -> dict:
        """Write → review → apply. Zeus is head; Athena reviews."""
        from resileos.kin.apollo import apollo_cycle
        from resileos.kin.athena import judge as athena_judge

        titan = get_titanos()

        def _writer():
            if body.writer == "apollo":
                return lambda **kw: apollo_cycle(
                    body.facts, subject=body.subject, art=body.art, **kw
                )
            raise ValueError(f"unknown writer: {body.writer}")

        proposal = _sep.propose(
            body.writer,
            _writer(),
            action_type="apollo",
        )

        def athena_review(p):
            out = athena_judge(
                perceptions=[{"subject": body.subject,
                              "address": {"residual_bin": "low_low"}}],
                frames=[{"label": "review", "depth": 1}],
            )
            return (
                bool(out.get("ok", False)),
                out.get("reading", "athena judgment"),
                [{"reviewer": "athena", "ok": out.get("ok"),
                  "frame": out.get("gate", {}).get("frame")}],
            )

        def verifier_review(p):
            if not p.claims:
                return (False, "no claims to verify", [{"matched": 0}])
            return (
                True,
                f"{len(p.claims)} claims captured",
                [{"matched": len(p.claims), "passed": len(p.claims)}],
            )

        result = zeus_head(
            proposal,
            reviewers=[
                ("athena", athena_review),
                ("verifier", verifier_review),
            ],
            learn_fn=titan.learn,
            cycle=_sep,
        )
        return result

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
