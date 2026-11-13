"""Scene legions under the forge.

Daedalus, Helios, and Argus are Hermes tools. Hephaestus is the studio
patron and is not a Kin, so the gate stays Hermes, the same gate as
``forge_video``. Each one writes a scene-description artifact and a
residual hash of that artifact, then a Hades checkpoint.

They are stubs. No Blender executor is configured. The classical core
is shown the residual hash only. The script source stays in the artifact
file and does not enter the control packet, the checkpoint, or a core call.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from resileos.harness.packet import VideoPacket
from resileos.kin.hades import Hades
from resileos.kin.legions import invoke_legion, kin_catalogue, register_legion

SCENE_LEGIONS = ("daedalus", "helios", "argus")

_JOBS = (
    ("daedalus", "geometry", "Daedalus", "the craftsman who built the labyrinth"),
    ("helios", "lighting", "Helios", "the sun, light and materials"),
    ("argus", "camera", "Argus", "the many-eyed watcher of camera and animation"),
)


def core_residual_view(packet_hash: str) -> dict[str, str]:
    """The only object a classical core is given for a scene step."""
    if not isinstance(packet_hash, str) or len(packet_hash) != 64:
        raise ValueError("the classical core sees a residual hash, not a script")
    if any(char not in "0123456789abcdef" for char in packet_hash):
        raise ValueError("the classical core sees a residual hash, not a script")
    return {"packet_hash": packet_hash}


def _artifact_dir(explicit: str | None) -> Path:
    raw = explicit or os.environ.get("RESILEOS_SCENE_DIR", "data/scene")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_dir(explicit: str | None) -> str:
    if explicit:
        return explicit
    return os.environ.get("RESILEOS_HADES_DIR", "data/hades")


def _step(name: str, job: str, god: str, about: str, seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stub. No Blender executor is configured."""
    del seen
    script = kwargs.get("script")
    if not isinstance(script, str):
        script = ""
    script = script[:8000]
    directory = _artifact_dir(kwargs.get("artifact_dir") if isinstance(kwargs.get("artifact_dir"), str) else None)
    body = (
        "executor: stub\n"
        "note: Stub. No Blender executor is configured.\n"
        f"legion: {name}\n"
        f"job: {job}\n"
        f"named_for: {god}. {about}.\n"
        "script:\n"
        f"{script}\n"
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    path = directory / f"{name}.txt"
    path.write_text(body, encoding="utf-8")
    view = core_residual_view(digest)
    holder = VideoPacket(
        id=f"scene-{name}",
        frame_residuals=[digest],
        temporal_delta=0.0,
        keyframe_ids=[],
        provider_stage="draft",
        scene_script_hash=digest,
    )
    holder.evidence = [{"source": "residual_core", "result": dict(view)}]
    holder.history = []
    holder.verified = False
    saved = Hades(_store_dir(kwargs.get("store_dir") if isinstance(kwargs.get("store_dir"), str) else None)).save(
        holder,
        residual_packet_hash=digest,
        lesson=f"{god} stub {job} residual {digest}",
        extra={
            "executor": "stub",
            "legion": name,
            "job": job,
            "scene_script_hash": digest,
            "frame_residuals": [digest],
            "provider_stage": "draft",
            "keyframe_ids": [],
            "temporal_delta": 0.0,
        },
    )
    produced = {
        "executor": "stub",
        "stub": True,
        "legion": name,
        "job": job,
        "named_for": god,
        "scene_script_hash": digest,
        "artifact": path.name,
        "core_view": view,
        "checkpoint_id": saved.id,
        "lesson": saved.lesson,
        "residual_hash": digest,
        "produces_video": False,
        "url": None,
    }
    if script and script in json.dumps(produced):
        raise RuntimeError("scene script leaked into the legion result")
    return produced


def daedalus(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stub. Scene geometry. Named for Daedalus. No Blender executor is configured."""
    return _step("daedalus", "geometry", "Daedalus", _JOBS[0][3], seen, **kwargs)


def helios(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stub. Lighting and materials. Named for Helios. No Blender executor is configured."""
    return _step("helios", "lighting", "Helios", _JOBS[1][3], seen, **kwargs)


def argus(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stub. Camera and animation. Named for Argus. No Blender executor is configured."""
    return _step("argus", "camera", "Argus", _JOBS[2][3], seen, **kwargs)


_TOOLS = {"daedalus": daedalus, "helios": helios, "argus": argus}
_ACTIONS = {
    "daedalus": "scene geometry",
    "helios": "scene lighting",
    "argus": "scene camera",
}


def register_scene_legions() -> list[str]:
    """Register the three forge scene legions on Hermes. Idempotent."""
    present = {row["name"] for row in kin_catalogue("hermes")}
    for name in SCENE_LEGIONS:
        if name in present:
            continue
        register_legion(
            "hermes",
            _TOOLS[name],
            name=name,
            constraints={
                "action": _ACTIONS[name],
                "writes_residual": False,
                "executes": True,
            },
        )
    return list(SCENE_LEGIONS)


def run_scene_workflow(
    script: str,
    *,
    store_dir: str | None = None,
    artifact_dir: str | None = None,
) -> dict[str, Any]:
    """Daedalus, then Helios, then Argus. Each step checkpoints.

    The returned record has hashes and checkpoint ids. It does not include
    the script source.
    """
    register_scene_legions()
    steps: list[dict[str, Any]] = []
    for name in SCENE_LEGIONS:
        host: dict[str, Any] = {
            "id": f"scene-{name}",
            "budget_remaining": {"steps": 8, "cost": 1.0, "tokens": 1000},
            "evidence": [],
            "history": [],
            "scars": [],
            "verified": False,
        }
        result = invoke_legion(
            "hermes",
            name,
            host,
            script=script if isinstance(script, str) else "",
            store_dir=store_dir,
            artifact_dir=artifact_dir,
        )
        steps.append(
            {
                "legion": name,
                "executor": result.get("executor"),
                "stub": True,
                "job": result.get("job"),
                "named_for": result.get("named_for"),
                "scene_script_hash": result.get("scene_script_hash"),
                "artifact": result.get("artifact"),
                "core_view": result.get("core_view"),
                "checkpoint_id": result.get("checkpoint_id"),
                "lesson": result.get("lesson"),
                "residual_hash": result.get("residual_hash"),
                "verified": False,
                "kin": result.get("kin"),
            }
        )
    public = {
        "executor": "stub",
        "stub": True,
        "steps": steps,
        "produces_video": False,
        "url": None,
        "note": "Stub. No Blender executor is configured. The classical core sees the residual hash only.",
    }
    text = script if isinstance(script, str) else ""
    if text and text in json.dumps(public):
        raise RuntimeError("scene script leaked into the workflow result")
    return public


__all__ = [
    "SCENE_LEGIONS",
    "argus",
    "core_residual_view",
    "daedalus",
    "helios",
    "register_scene_legions",
    "run_scene_workflow",
]
