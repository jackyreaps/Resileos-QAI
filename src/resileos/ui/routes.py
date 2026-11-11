"""HTTP wrappers for the portable UI modules.

Perception routes return candidates. They call ``learn`` only when the
caller sets ``commit`` and ``eat_filter`` returns ``accept`` for that
triple.

``agent/task`` wraps ``agent_loop.run_task`` with ``harness_wrap``.
Steps that use a mutating tool are classed with ``verification_required``
and are not executed.

Not mounted, and why:

- ``fluid_gen.generate_video_hook`` — optional external video provider.
  ``POST /generate/fluid`` calls ``generate_still``.
- ``task_loop.run_task`` and ``task_api.task_from_steps`` — store lookup
  loop, not the mutating worker. ``POST /agent/task`` wraps
  ``agent_loop.run_task``.
- ``studio.panel.render_residual_codec`` — Streamlit only. See
  ``resileos.studio.routes``.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from resileos.harness.harness_wrap import harness_wrap
from resileos.harness.tools import verification_required
from resileos.kin.eat import eat_filter
from resileos.ui.agent_loop import run_task
from resileos.ui.art_encoders import encode_art
from resileos.ui.custom_mouth import answer as mouth_answer
from resileos.ui.explain_remember import explain, remember
from resileos.ui.fluid_gen import generate_still
from resileos.ui.frame_codec import codec_summary, encode_frame
from resileos.ui.language_tool import detect_language, translate
from resileos.ui.local_gen import generate_local
from resileos.ui.perceive_image import perceive_image
from resileos.ui.query_scale import to_jsonable

_MUTATING = {"write_file", "apply_diff", "git_commit"}


class ImagePerceiveBody(BaseModel):
    image: list[Any]
    subject: str = "image"
    commit: bool = False


class ArtBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    world_id: str = "world:art"
    commit: bool = False


class FrameBody(BaseModel):
    image: list[Any]
    subject: str = "frame"
    commit: bool = False


class GenerateBody(BaseModel):
    image: list[Any] | None = None
    belt: int = 0
    frame: int = 0
    persona: str = ""
    subject: str = "frame"


class DetectBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class TranslateBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    target: str = "en"
    source: str | None = None


class TaskStep(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)


class TaskBody(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[TaskStep] | None = None


class MouthBody(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    question: str = ""


class ExplainBody(BaseModel):
    query: str = ""
    hub_rows: list[Any] = Field(default_factory=list)


class RememberBody(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    relation: str = Field(min_length=1, max_length=64)
    obj: str = Field(min_length=1, max_length=500)


def _image(data: list[Any]) -> Any:
    import numpy as np

    array = np.asarray(data)
    if array.ndim not in (2, 3) or array.size == 0 or array.size > 1_000_000:
        raise ValueError("image must be a non-empty 2-D or 3-D array up to 1e6 elements")
    return array


def apply_eat(
    triples: list[dict[str, str]],
    *,
    commit: bool,
    learn: Callable[[str, str, str], None] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Run eat_filter. Learn only accepted triples when commit is set."""
    decided: list[dict[str, Any]] = []
    written: list[dict[str, str]] = []
    for triple in triples:
        decision = eat_filter(triple)
        accepted = getattr(decision, "action", "") == "accept"
        eat = decision.to_dict() if hasattr(decision, "to_dict") else {"action": decision.action}
        decided.append({"triple": triple, "accepted": accepted, "eat": eat})
        if commit and accepted and learn is not None:
            learn(triple["subject"], triple["relation"], triple["obj"])
            written.append(triple)
    return decided, written


def _perception(
    triples: list[dict[str, str]],
    *,
    commit: bool,
    learn: Callable[[str, str, str], None] | None,
    save: Callable[[], None] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    candidates, written = apply_eat(triples, commit=commit, learn=learn)
    if written and save is not None:
        save()
    body = {
        "candidates": candidates,
        "written": written,
        "committed": bool(written),
    }
    body.update(extra)
    return to_jsonable(body)


def register_ui_routes(
    app: FastAPI,
    auth_dep: Any,
    *,
    get_titanos: Callable[[], Any],
    save: Callable[[], None] | None = None,
) -> None:
    deps = [Depends(auth_dep)]

    def _learn(s: str, r: str, o: str) -> None:
        get_titanos().learn(s, r, o)

    @app.post("/api/v1/perceive/image", dependencies=deps)
    def perceive_image_route(body: ImagePerceiveBody) -> dict[str, Any]:
        try:
            perceived = perceive_image(_image(body.image), subject=body.subject)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        triples: list[dict[str, str]] = []
        for relation in ("mean_luma", "edge_density"):
            value = perceived.get(relation)
            if value is None:
                continue
            triples.append(
                {"subject": body.subject, "relation": relation, "obj": str(value)}
            )
        codec = perceived.get("codec") or {}
        if codec.get("residual_bin"):
            triples.append(
                {
                    "subject": body.subject,
                    "relation": "residual_bin",
                    "obj": str(codec["residual_bin"]),
                }
            )
        return _perception(
            triples,
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"perception": perceived},
        )

    @app.post("/api/v1/perceive/art", dependencies=deps)
    def perceive_art_route(body: ArtBody) -> dict[str, Any]:
        # encode_art does not call Titanos.learn. The eat gate below is the
        # only path that can write, and only when commit is set.
        encoded = encode_art(body.title, body.description, world_id=body.world_id)
        obj = f"{body.title}: {body.description[:80]}"
        triples = [{"subject": body.world_id, "relation": "art", "obj": obj}]
        return _perception(
            triples,
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"art": encoded},
        )

    @app.post("/api/v1/perceive/frame", dependencies=deps)
    def perceive_frame_route(body: FrameBody) -> dict[str, Any]:
        try:
            encoded = encode_frame(_image(body.image))
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        summary = codec_summary(encoded)
        triples = [
            {
                "subject": body.subject,
                "relation": "residual_bin",
                "obj": str(summary["residual_bin"]),
            }
        ]
        return _perception(
            triples,
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"codec": summary},
        )

    @app.post("/api/v1/generate/fluid", dependencies=deps)
    def generate_fluid_route(body: GenerateBody) -> dict[str, Any]:
        try:
            image = None if body.image is None else _image(body.image)
            result = generate_still(
                image,
                belt=body.belt,
                frame=body.frame,
                persona=body.persona,
                subject=body.subject,
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return to_jsonable(result)

    @app.post("/api/v1/generate/local", dependencies=deps)
    def generate_local_route(body: GenerateBody) -> dict[str, Any]:
        try:
            image = None if body.image is None else _image(body.image)
            result = generate_local(
                image,
                belt=body.belt,
                frame=body.frame,
                subject=body.subject,
                persona=body.persona,
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return to_jsonable(result)

    @app.post("/api/v1/language/detect", dependencies=deps)
    def language_detect_route(body: DetectBody) -> dict[str, Any]:
        return to_jsonable(detect_language(body.text))

    @app.post("/api/v1/language/translate", dependencies=deps)
    def language_translate_route(body: TranslateBody) -> dict[str, Any]:
        return to_jsonable(translate(body.text, target=body.target, source=body.source))

    @app.post("/api/v1/agent/task", dependencies=deps)
    def agent_task_route(body: TaskBody) -> dict[str, Any]:
        steps = None if body.steps is None else [step.model_dump() for step in body.steps]
        if steps is not None and len(steps) > 12:
            raise HTTPException(400, "at most 12 steps")
        mutating = bool(steps) and any(step["tool"] in _MUTATING for step in steps)
        action = "agent_mutate" if mutating else "query"

        def _run(goal: str, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            verdict = verification_required(action)
            if verdict["requires_verification"]:
                return {
                    "goal": goal,
                    "ok": False,
                    "ran": False,
                    "steps": 0,
                    "trace": [],
                    "verification": verdict,
                }
            out = run_task(goal, steps=steps)
            out["ran"] = True
            out["verification"] = verdict
            return out

        wrapped = harness_wrap(_run, action)
        try:
            return to_jsonable(wrapped(body.goal, steps=steps))
        except Exception as exc:
            raise HTTPException(500, str(exc)) from exc

    @app.post("/api/v1/mouth/custom", dependencies=deps)
    def mouth_custom_route(body: MouthBody) -> dict[str, Any]:
        return to_jsonable(mouth_answer(body.rows, body.question))

    @app.post("/api/v1/explain", dependencies=deps)
    def explain_route(body: ExplainBody) -> dict[str, Any]:
        return to_jsonable(explain(body.query, body.hub_rows))

    @app.post("/api/v1/remember", dependencies=deps)
    def remember_route(body: RememberBody) -> dict[str, Any]:
        # Fact line only. The hub write is POST /api/v1/chat class HUB_LEARN.
        return to_jsonable(remember(body.subject, body.relation, body.obj))
