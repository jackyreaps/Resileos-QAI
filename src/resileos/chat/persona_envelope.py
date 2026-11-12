"""Persona envelope: style, tools, hub scope, and metric weights.

An envelope is not a license to assert unstored facts. Evolution is the
version plus probe and lesson history. Frame tags label a finished atlas
entry. An unfinished tag does not open another runtime path, and a label
does not become a Titanos relation.

Honesty stays strictly above fluency and charm.
"""
from __future__ import annotations

from typing import Any

from resileos.answer.user_profile import PERSONA_PACKS

# Atlas documents in this tree are still proposed. Nothing here is finished,
# so a frame tag cannot select a second mouth path until a caller passes a
# finished catalog (tests, or a future finished atlas).
FINISHED_FRAME_TAGS: frozenset[str] = frozenset()

# Labels only. They never become relations.
_FRAME_LABELS = frozenset({"stewardship", "diagnostic"})

_ALLOWED_TOOLS = ("resileos_ask",)

# Fluency and charm are capped below honesty inside ``_weights``.
_BASE_WEIGHTS = {
    "tool_adherence": 0.90,
    "invent_rate_penalty": 0.95,
    "hub_consistency": 0.75,
    "unneeded_tool_calls": 0.45,
    "soft_chat_leak_penalty": 0.90,
    "context_layer_utility": 0.40,
    "honesty": 1.0,
    "fluency": 0.25,
    "charm": 0.15,
}

# Finished tags may retune an honesty-side weight. They do not raise charm.
_FRAME_TEMPLATES = {
    "stewardship": {"hub_consistency": 0.85},
    "diagnostic": {"tool_adherence": 0.95},
}


def _pack(persona: str) -> tuple[str, dict[str, str]]:
    name = persona if persona in PERSONA_PACKS else "honest"
    return name, dict(PERSONA_PACKS[name])


def _weights(frame_tag: str | None) -> dict[str, float]:
    weights = dict(_BASE_WEIGHTS)
    if frame_tag and frame_tag in _FRAME_TEMPLATES:
        weights.update(_FRAME_TEMPLATES[frame_tag])
    ceiling = float(weights["honesty"]) - 0.05
    weights["fluency"] = min(float(weights["fluency"]), ceiling)
    weights["charm"] = min(float(weights["charm"]), ceiling)
    return weights


def build_envelope(
    persona: str,
    *,
    hub_scope: str,
    hermes_depth: int | None = None,
    frame_tag: str | None = None,
    finished_frames: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Return one envelope. Unfinished tags are dropped, not branched."""
    name, pack = _pack(persona)
    catalog = FINISHED_FRAME_TAGS if finished_frames is None else frozenset(finished_frames)
    requested = (frame_tag or "").strip().lower()
    label = None
    if requested and requested in _FRAME_LABELS and requested in catalog:
        from resileos.kin.athena import load_frame

        loaded = load_frame(requested)
        label = str(loaded.get("label") or requested)
    weights = _weights(label)
    return {
        "version": "v1",
        "persona": name,
        "style": pack,
        "allowed_tools": list(_ALLOWED_TOOLS),
        "hub_scope": hub_scope,
        "weights": weights,
        "hermes_depth": hermes_depth,
        "frame_tag": label,
        "branched": False,
        "writes_residual": False,
    }
