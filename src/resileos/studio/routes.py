"""HTTP wrappers for the studio coding layer.

Each route validates its body, requires the API-key dependency, and calls
the module function it is named for. Codec and sampler routes do not call
``learn``. Graphify calls ``learn`` only for an Eat accept when commit is set.

``render_residual_codec`` is a Streamlit renderer. ``GET /panel`` returns
the data that renderer shows. The gear drawer in ``ui.py`` calls the
renderer itself.

The external sampler route refuses the call unless
``RESILEOS_EXTERNAL_SAMPLER`` is an enabled sampler, and it always runs
``risk_classify``. A deny risk is refused even when the sampler is on.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from resileos.harness.tools import risk_classify
from resileos.studio.candidates import register_candidate
from resileos.studio.codecs import codec_names, open_codec, project_gray
from resileos.studio.external_sampler import SamplerOff, resolve_external_sampler
from resileos.studio.gate import gate_studio_packet
from resileos.studio.service import (
    propose_external,
    round_trip,
    sample_toy_prior,
    study_prior_report,
)
from resileos.ui.query_scale import to_jsonable


class ImageBody(BaseModel):
    image: list[Any]
    m: int = Field(default=8, ge=1, le=64)
    n: int = Field(default=8, ge=1, le=64)


class RoundTripBody(BaseModel):
    image: list[Any]
    codec_name: str = "pca_component"


class CandidateBody(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    path: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=200)
    world_id: str = "studio"
    note: str = ""


class SampleBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: int = Field(ge=0, le=9)
    seed: int = 0
    store_candidate: bool = Field(default=True, alias="register")


class GateBody(BaseModel):
    packet: dict[str, Any]


class ExternalBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    condition: dict[str, Any] | None = None
    store_candidate: bool = Field(default=True, alias="register")


class ForgeBody(BaseModel):
    prompt: str = Field(default="", max_length=2000)
    stage: str = "draft"


class GraphifyBody(BaseModel):
    source: dict[str, Any] | list[Any] | str = ""
    commit: bool = False


class PlanStep(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)


class PlanBody(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[PlanStep] | None = None


class StopBody(BaseModel):
    owner: str = Field(min_length=1, max_length=200)


def _image(data: list[Any]) -> Any:
    import numpy as np

    array = np.asarray(data)
    if array.ndim not in (2, 3) or array.size == 0 or array.size > 1_000_000:
        raise ValueError("image must be a non-empty 2-D or 3-D array up to 1e6 elements")
    return array


def _sampler_enabled() -> bool:
    raw = os.getenv("RESILEOS_EXTERNAL_SAMPLER", "").strip().lower()
    if raw in ("", "off", "none", "disabled"):
        return False
    return bool(resolve_external_sampler().enabled)


def register_studio_routes(
    app: FastAPI,
    auth_dep: Any,
    get_titanos: Any = None,
) -> None:
    deps = [Depends(auth_dep)]

    @app.get("/api/v1/studio/codecs", dependencies=deps)
    def studio_codecs() -> dict[str, Any]:
        return {"codecs": codec_names()}

    @app.post("/api/v1/studio/codecs/project", dependencies=deps)
    def studio_project(body: ImageBody) -> dict[str, Any]:
        try:
            projected = project_gray(_image(body.image), body.m, body.n)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"shape": list(projected.shape), "image": to_jsonable(projected)}

    @app.post("/api/v1/studio/candidates", dependencies=deps)
    def studio_candidates(body: CandidateBody) -> dict[str, Any]:
        return register_candidate(
            kind=body.kind,
            path=body.path,
            title=body.title,
            world_id=body.world_id,
            note=body.note,
        )

    @app.get("/api/v1/studio/service/prior", dependencies=deps)
    def studio_prior() -> dict[str, Any]:
        return study_prior_report()

    @app.post("/api/v1/studio/service/round-trip", dependencies=deps)
    def studio_round_trip(body: RoundTripBody) -> dict[str, Any]:
        if body.codec_name not in codec_names():
            raise HTTPException(400, f"unknown codec {body.codec_name}")
        codec = open_codec(body.codec_name)
        if not getattr(codec, "available", False):
            raise HTTPException(
                409,
                {"codec": body.codec_name, "available": False, "learned": False},
            )
        try:
            result = round_trip(_image(body.image), codec_name=body.codec_name)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return to_jsonable(result)

    @app.post("/api/v1/studio/service/sample", dependencies=deps)
    def studio_sample(body: SampleBody) -> dict[str, Any]:
        try:
            result = sample_toy_prior(
                body.label, seed=body.seed, register=body.store_candidate
            )
        except (ValueError, TypeError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return to_jsonable(result)

    @app.post("/api/v1/studio/gate", dependencies=deps)
    def studio_gate(body: GateBody) -> dict[str, Any]:
        try:
            return to_jsonable(gate_studio_packet(body.packet))
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/v1/studio/panel", dependencies=deps)
    def studio_panel() -> dict[str, Any]:
        sampler = resolve_external_sampler()
        return {
            "codecs": codec_names(),
            "prior": study_prior_report(),
            "sampler": sampler.status(),
            "renderer": "resileos.studio.panel.render_residual_codec",
            "http_invokes_renderer": False,
        }

    @app.get("/api/v1/studio/external-sampler", dependencies=deps)
    def studio_external_status() -> dict[str, Any]:
        sampler = resolve_external_sampler()
        risk = risk_classify("external_sampler status")
        return {
            "refused": not sampler.enabled,
            "risk": risk,
            "sampler": sampler.status(),
        }

    @app.post("/api/v1/studio/external-sampler", dependencies=deps)
    def studio_external(body: ExternalBody) -> dict[str, Any]:
        prompt = ""
        if body.condition:
            prompt = str(body.condition.get("prompt") or "")
        risk = risk_classify(f"external_sampler propose {prompt}".strip())
        if risk["risk_class"] == "deny":
            raise HTTPException(
                403,
                {"refused": True, "reason": risk["reason"], "risk": risk},
            )
        if not _sampler_enabled():
            sampler = resolve_external_sampler()
            raise HTTPException(
                403,
                {
                    "refused": True,
                    "reason": sampler.status().get(
                        "reason", "RESILEOS_EXTERNAL_SAMPLER is unset"
                    ),
                    "risk": risk,
                    "sampler": sampler.status(),
                },
            )
        try:
            result = propose_external(
                condition=body.condition, register=body.store_candidate
            )
        except SamplerOff as exc:
            raise HTTPException(403, {"refused": True, "reason": str(exc), "risk": risk}) from exc
        payload = to_jsonable(result)
        payload["refused"] = False
        payload["risk"] = risk
        return payload

    @app.post("/api/v1/studio/forge/video", dependencies=deps)
    def studio_forge_video(body: ForgeBody) -> dict[str, Any]:
        from resileos.kin.legions import LegionError
        from resileos.kin.studio_tools import run_forge_video

        stage = body.stage if body.stage in {"draft", "verify", "upscale"} else body.stage
        try:
            return to_jsonable(run_forge_video(body.prompt, stage=stage))
        except LegionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/studio/graphify", dependencies=deps)
    def studio_graphify(body: GraphifyBody) -> dict[str, Any]:
        from resileos.kin.legions import LegionError
        from resileos.kin.studio_tools import run_graphify

        learn = None
        if body.commit and get_titanos is not None:
            titan = get_titanos()

            def learn(subject: str, relation: str, obj: str) -> None:
                titan.learn(subject, relation, obj)

        try:
            return to_jsonable(run_graphify(body.source, commit=body.commit, learn_fn=learn))
        except LegionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/studio/plan-test-debug", dependencies=deps)
    def studio_plan_test_debug(body: PlanBody) -> dict[str, Any]:
        from resileos.kin.legions import LegionError
        from resileos.kin.studio_tools import run_plan_loop

        if body.steps is not None and len(body.steps) > 12:
            raise HTTPException(400, "at most 12 steps")
        steps = None if body.steps is None else [step.model_dump() for step in body.steps]
        try:
            return to_jsonable(run_plan_loop(body.goal, steps=steps))
        except LegionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/studio/stop", dependencies=deps)
    def studio_stop(body: StopBody) -> dict[str, Any]:
        from resileos.kin.moirai import stop_owner

        return to_jsonable(stop_owner(body.owner))
