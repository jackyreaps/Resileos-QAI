"""HTTP wrappers for the portable UI modules.

Perception routes return candidates. They call ``learn`` only when the
caller sets ``commit`` and ``eat_filter`` returns ``accept`` for that
triple.

``agent/task`` wraps ``agent_loop.run_task`` with ``harness_wrap``.
Steps that use a mutating tool are classed with ``verification_required``
and are not executed.

Mounted beside the worker:

- ``POST /generate/video`` calls ``generate_video_hook``. No provider
  means ``UNAVAILABLE`` and no URL.
- ``POST /task/lookup`` calls ``task_with_scale`` (store lookups).
  ``POST /agent/task`` still wraps ``agent_loop.run_task``. Mutating
  steps stay refused.
- ``POST /perceive/audio``, ``/perceive/video``, and
  ``/perceive/language`` follow the image route: candidates, and
  ``learn`` only when ``commit`` and eat accept.
- ``/perceive/language`` also calls ``perceive_language.into_kin`` so
  Psyche receives the perception. ``into_kin`` does not learn. Eat
  remains the only ingest gate.
- ``studio.panel.render_residual_codec`` stays Streamlit-only. The
  gear drawer in ``ui.py`` calls it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from resileos.harness.harness_wrap import harness_wrap
from resileos.harness.tools import verification_required
from resileos.kin.eat import eat_filter
from resileos.ui.agent_loop import run_task
from resileos.ui.art_encoders import encode_art
from resileos.ui.custom_mouth import answer as mouth_answer
from resileos.ui.explain_remember import explain, remember
from resileos.ui.fluid_gen import generate_still, generate_video_hook
from resileos.ui.frame_codec import codec_summary, encode_frame
from resileos.ui.language_tool import detect_language, translate
from resileos.ui.local_gen import generate_local
from resileos.ui.perceive_audio import perceive_audio
from resileos.ui.perceive_image import perceive_image
from resileos.ui.perceive_language import perceive_language
from resileos.ui.perceive_video import perceive_video
from resileos.ui.query_scale import to_jsonable
from resileos.ui.scale_wire import task_with_scale

_MUTATING = {"write_file", "apply_diff", "git_commit"}

# Process Psyche for the language route. Callers pass this into into_kin.
_language_session: dict[str, Any] = {}


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


class VideoGenerateBody(BaseModel):
    prompt: str = Field(default="", max_length=2000)


class AudioBody(BaseModel):
    wave: list[float]
    subject: str = "audio"
    sample_rate: int = 16000
    commit: bool = False


class VideoPerceiveBody(BaseModel):
    frames: list[Any]
    subject: str = "video"
    fps: float = 12.0
    commit: bool = False


class LanguagePerceiveBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    subject: str = "text"
    commit: bool = False


class LookupStep(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    relation: str = Field(min_length=1, max_length=64)


class LookupBody(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    steps: list[LookupStep] = Field(default_factory=list)
    persona: str = ""
    belt: int = 0


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


def _clip(data: list[Any]) -> Any:
    import numpy as np

    array = np.asarray(data)
    if array.ndim not in (3, 4) or array.size == 0 or array.size > 1_000_000:
        raise ValueError("frames must be a non-empty 3-D or 4-D array up to 1e6 elements")
    return array


def _metric_triples(subject: str, metrics: dict[str, Any]) -> list[dict[str, str]]:
    triples: list[dict[str, str]] = []
    for relation, value in metrics.items():
        if value is None:
            continue
        triples.append({"subject": subject, "relation": relation, "obj": str(value)})
    return triples


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

    @app.post("/api/v1/perceive/audio", dependencies=deps)
    def perceive_audio_route(body: AudioBody) -> dict[str, Any]:
        try:
            import numpy as np

            wave = np.asarray(body.wave, dtype=float)
            if wave.size == 0 or wave.size > 1_000_000:
                raise ValueError("wave must contain 1 to 1e6 samples")
            perceived = perceive_audio(
                wave, subject=body.subject, sample_rate=body.sample_rate
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return _perception(
            _metric_triples(
                body.subject,
                {
                    "energy": perceived.get("energy"),
                    "zero_cross_rate": perceived.get("zero_cross_rate"),
                    "spectral_centroid_hz": perceived.get("spectral_centroid_hz"),
                },
            ),
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"perception": perceived},
        )

    @app.post("/api/v1/perceive/video", dependencies=deps)
    def perceive_video_route(body: VideoPerceiveBody) -> dict[str, Any]:
        try:
            perceived = perceive_video(
                _clip(body.frames), subject=body.subject, fps=body.fps
            )
        except (ValueError, TypeError, IndexError) as exc:
            raise HTTPException(400, str(exc)) from exc
        codec = perceived.get("codec") or {}
        return _perception(
            _metric_triples(
                body.subject,
                {
                    "mean_luma": perceived.get("mean_luma"),
                    "mean_edge": perceived.get("mean_edge"),
                    "motion": perceived.get("motion"),
                    "residual_bin": codec.get("residual_bin"),
                },
            ),
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"perception": perceived},
        )

    @app.post("/api/v1/perceive/language", dependencies=deps)
    def perceive_language_route(body: LanguagePerceiveBody) -> dict[str, Any]:
        from resileos.ui.perceive_language import into_kin
        from resileos.ui.studio_app import hand_perception_to_psyche

        perceived = perceive_language(body.text, subject=body.subject)
        # Observation reaches Psyche. Learn stays on the eat gate below.
        handed = hand_perception_to_psyche(perceived, into_kin, _language_session)
        return _perception(
            _metric_triples(
                body.subject,
                {
                    "chars": perceived.get("chars"),
                    "tokens": perceived.get("tokens"),
                    "latin_share": perceived.get("latin_share"),
                    "other_share": perceived.get("other_share"),
                },
            ),
            commit=body.commit,
            learn=_learn,
            save=save,
            extra={"perception": perceived, "kin": handed["kin"]},
        )

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

    @app.post("/api/v1/generate/video", dependencies=deps)
    def generate_video_route(body: VideoGenerateBody) -> dict[str, Any]:
        return to_jsonable(generate_video_hook(body.prompt))

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

    @app.post("/api/v1/task/lookup", dependencies=deps)
    def task_lookup_route(body: LookupBody) -> dict[str, Any]:
        """Store lookups through task_with_scale. Does not run tools."""
        if len(body.steps) > 12:
            raise HTTPException(400, "at most 12 steps")
        titan = get_titanos()

        def ask(subject: str, relation: str) -> Any:
            ask_list = getattr(titan, "ask_list", None)
            if callable(ask_list):
                rows = ask_list(subject, relation)
                if not rows:
                    return None
                return rows[0] if len(rows) == 1 else rows
            return titan.ask(subject, relation)

        steps = [
            {"subject": step.subject, "relation": step.relation} for step in body.steps
        ]
        return to_jsonable(
            task_with_scale(
                body.goal, steps, ask, persona=body.persona, belt=body.belt
            )
        )

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
