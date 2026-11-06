"""
Frame / dimensionality categories for gate and answer honesty.

Operational tags only — not a consciousness claim. Aligns verifier,
answer, and council outputs so later atlas / Human Medium work can map
onto stable codes without inventing store content.
"""
from __future__ import annotations

from typing import Any, Optional

# Primary honesty axis (answer + eat)
FRAME_EXACT = "exact"
FRAME_RECONSTRUCTED = "reconstructed"
FRAME_ABSTAINED = "abstained"
FRAME_UNRESOLVED = "unresolved"
FRAME_FILTERED = "filtered"
FRAME_PROVISIONAL = "provisional"

# Higher-dimensional category axis (hub / authority / layer)
# These tag *how* a claim is situated, not whether it is true.
CAT_USER = "dim.user"
CAT_WORLD = "dim.world"
CAT_ORG = "dim.org"
CAT_DEFAULT = "dim.default"
CAT_SYS = "dim.sys"
CAT_SEED = "dim.seed"
CAT_MEDIA = "dim.media"
CAT_POLICY = "dim.policy"
CAT_MULTI = "dim.multi"  # council merge
CAT_CONFLICT = "dim.conflict"

HONESTY_FRAMES = frozenset(
    {
        FRAME_EXACT,
        FRAME_RECONSTRUCTED,
        FRAME_ABSTAINED,
        FRAME_UNRESOLVED,
        FRAME_FILTERED,
        FRAME_PROVISIONAL,
    }
)

DIM_CATEGORIES = frozenset(
    {
        CAT_USER,
        CAT_WORLD,
        CAT_ORG,
        CAT_DEFAULT,
        CAT_SYS,
        CAT_SEED,
        CAT_MEDIA,
        CAT_POLICY,
        CAT_MULTI,
        CAT_CONFLICT,
    }
)


def hub_category(subject: str) -> str:
    s = (subject or "").strip()
    if s.startswith("user:"):
        return CAT_USER
    if s.startswith("world:"):
        return CAT_WORLD
    if s.startswith("org:"):
        return CAT_ORG
    if s.startswith("sys:"):
        return CAT_SYS
    if s.startswith("seed:"):
        return CAT_SEED
    if ":asset:" in s or s.startswith("media:"):
        return CAT_MEDIA
    return CAT_DEFAULT


def classify_decision(
    action: str,
    *,
    subject: str = "",
    has_source: bool = False,
    reconstructed: bool = False,
    conflict: bool = False,
) -> dict[str, str]:
    """Return honesty frame + dim category for API payloads."""
    dim = hub_category(subject)
    if conflict:
        return {"frame": FRAME_FILTERED, "dim": CAT_CONFLICT}
    act = (action or "").lower()
    if act == "accept":
        frame = FRAME_PROVISIONAL if not has_source else FRAME_EXACT
        if reconstructed:
            frame = FRAME_RECONSTRUCTED
        return {"frame": frame, "dim": dim}
    if act == "abstain":
        return {"frame": FRAME_ABSTAINED, "dim": dim}
    if act == "reject":
        return {"frame": FRAME_FILTERED, "dim": dim}
    return {"frame": FRAME_UNRESOLVED, "dim": dim}


def enrich_payload(payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Attach frame + dim if missing."""
    out = dict(payload)
    if "frame" not in out or "dim" not in out:
        c = classify_decision(
            str(out.get("action") or out.get("status") or ""),
            subject=str(out.get("subject") or kwargs.get("subject") or ""),
            has_source=bool(out.get("source") or kwargs.get("has_source")),
            reconstructed=bool(kwargs.get("reconstructed")),
            conflict=bool(kwargs.get("conflict")),
        )
        out.setdefault("frame", c["frame"])
        out.setdefault("dim", c["dim"])
    return out
