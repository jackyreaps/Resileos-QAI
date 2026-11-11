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
        from fastapi import Depends, HTTPException
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
        topics: list[str] = []

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
        if body.residual_packet_hash or body.topics:
            residual_packet = type(
                "Stub",
                (),
                {
                    "packet_hash": body.residual_packet_hash,
                    "topics": list(body.topics),
                },
            )()

        aphrodite_state = None
        hub = body.user_id or "anon"
        store = None
        try:
            from resileos.kin.aphrodite import get_store

            store = get_store()
            aphrodite_state = store.get(hub)
        except ValueError:
            aphrodite_state = None

        report, policy, harness = _bundle().cycle(
            metrics=metrics,
            agency_group=agency,
            apply_policy=body.apply_policy,
            residual_packet=residual_packet,
            aphrodite_state=aphrodite_state,
        )
        if store is not None and aphrodite_state is not None and harness.get("verified"):
            try:
                store.save(hub)
            except ValueError:
                pass
        payload = {
            "report": report.to_dict(),
            "policy": policy.to_dict(),
            "harness": harness,
        }
        if harness.get("verified") and harness.get("tutorial_fragment"):
            payload["tutorial_fragment"] = harness["tutorial_fragment"]
        return payload

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

    from resileos.kin.legions import LegionError, invoke_legion, list_legions

    @app.get("/api/v1/kin/legions", dependencies=deps)
    def api_list_legions() -> dict:
        catalog = list_legions()
        return {"kins": list(catalog), "legions": catalog}

    @app.post("/api/v1/kin/legions/{kin}/{name}", dependencies=deps)
    def api_invoke_legion(kin: str, name: str, payload: dict | None = None) -> dict:
        raw = dict(payload or {})
        packet = raw.pop("packet", {}) or {}
        extra = raw.pop("kwargs", None)
        kwargs = dict(extra) if isinstance(extra, dict) else raw
        try:
            return invoke_legion(kin, name, packet, **kwargs)
        except LegionError as exc:
            raise HTTPException(400, str(exc)) from exc

    from resileos.chat.ledger import normalize_hub_id
    from resileos.kin.aphrodite import get_store, record_preference

    class AphroditeStateBody(BaseModel):
        human_signals: Optional[dict] = None
        step: Optional[str] = None
        verified: bool = False

    class AphroditePreference(BaseModel):
        topic: str
        like: bool = True
        care: int = 1

    def _hub(hub: str) -> str:
        try:
            return normalize_hub_id(hub)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/v1/aphrodite/{hub}/state", dependencies=deps)
    def api_aphrodite_state(hub: str) -> dict:
        return get_store().get(_hub(hub)).to_dict()

    @app.post("/api/v1/aphrodite/{hub}/state", dependencies=deps)
    def api_aphrodite_state_post(hub: str, body: AphroditeStateBody) -> dict:
        hub_id = _hub(hub)
        state = get_store().get(hub_id)
        state.fold_signals(body.human_signals)
        fragment = state.advance(body.step, verified=bool(body.verified)) if body.step else None
        get_store().save(hub_id)
        out = state.to_dict()
        out["tutorial_fragment"] = fragment if body.verified else None
        return out

    @app.post("/api/v1/aphrodite/{hub}/preference", dependencies=deps)
    def api_aphrodite_preference(hub: str, body: AphroditePreference) -> dict:
        hub_id = _hub(hub)
        try:
            state, fragment = record_preference(
                hub_id, body.topic, like=body.like, care=body.care
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        out = state.to_dict()
        out["tutorial_fragment"] = fragment
        return out

    @app.post("/api/v1/aphrodite/{hub}/reset", dependencies=deps)
    def api_aphrodite_reset(hub: str) -> dict:
        return get_store().reset(_hub(hub)).to_dict()
