"""Sector × gate_state × status frame system and routing policy.

The four-axis epistemic system (sector, gate_state, status, capacity)
selects what *kind of truth claim* an answer is making. The LLM, when
used at all, only renders; it does not determine the frame.

GPU finding (RAG bridge): structured mouth at 100% store fidelity vs
small decoder RAG ~0.4 — failure mode is the model overriding retrieved
rows. Explicit frames make that division of labor citable and enforceable.
"""
from __future__ import annotations

from typing import Optional

# Truth-frame labels (derived; not Human-Medium prose frames)
FRAME_EXACT = "exact"                 # gbx + answered, field coherent
FRAME_RECONSTRUCTED = "reconstructed"  # otx / path / multi-row
FRAME_ABSTAINED = "abstained"          # recovery / field veto
FRAME_UNRESOLVED = "unresolved"        # none-channel


def derive_frame(
    *,
    sector: str = "",
    gate_state: str = "",
    status: str = "",
    n_rows: int = 0,
) -> str:
    """Map axis values to a single truth-frame label.

    | Condition | Frame |
    |---|---|
    | status NONE_CHANNEL | unresolved |
    | status ABSTAINED | abstained |
    | gbx_like + ANSWERED (+ optional LOCKED) | exact |
    | otx_like or multi-row / path | reconstructed |
    | else ANSWERED | exact if single row else reconstructed |
    """
    st = (status or "").upper()
    sec = (sector or "").lower()
    gs = (gate_state or "").upper()

    if st == "NONE_CHANNEL":
        return FRAME_UNRESOLVED
    if st == "ABSTAINED":
        return FRAME_ABSTAINED
    if st in {"ANSWERED", "NO_ROWS", "ACCEPTED", ""}:
        if st == "NO_ROWS":
            return FRAME_UNRESOLVED if not sec else (
                FRAME_EXACT if sec == "gbx_like" else FRAME_RECONSTRUCTED
            )
        if sec == "otx_like" or n_rows > 1:
            return FRAME_RECONSTRUCTED
        if sec == "gbx_like" or n_rows == 1:
            # REPULSE still allowed as exact if store returned a row;
            # confidence is separate from frame type.
            return FRAME_EXACT
        if n_rows > 1:
            return FRAME_RECONSTRUCTED
        return FRAME_EXACT if n_rows == 1 else FRAME_UNRESOLVED
    return FRAME_UNRESOLVED


def prefer_child(
    *,
    sector: str,
    gate_state: str = "",
    confidence: float = 1.0,
    abstain_threshold: float = 0.03,
    gate_capacity_bits: float = 0.0,
    capacity_floor: float = 1.0,
) -> str:
    """Return preferred child key: ``zeus`` | ``parent`` | ``none``.

    - ``none`` — abstain path
    - ``zeus`` — flexible / otx
    - ``parent`` — exact Titanos ask

    If ``gate_capacity_bits`` is positive and below ``capacity_floor``,
    prefer parent (low-capacity gate → do not trust flexible path or HF).
    """
    sec = (sector or "").lower()
    gs = (gate_state or "").upper()
    if confidence < abstain_threshold and gs in {"REPULSE", "UNLOCKED"}:
        if confidence <= 0.0:
            return "none"
    if gate_capacity_bits > 0.0 and gate_capacity_bits < capacity_floor:
        return "parent"
    if sec == "gbx_like":
        return "parent"
    if sec == "otx_like":
        return "zeus"
    return "zeus"


def gbx_bypass_recurrent(sector: str) -> bool:
    """True when single-hop exact band should skip long recurrent loops."""
    return (sector or "").lower() == "gbx_like"


def frame_to_tool_tag(frame: str) -> str:
    """Map truth-frame → Human-Medium / tools_schema tag when useful."""
    return {
        FRAME_EXACT: "operational",
        FRAME_RECONSTRUCTED: "gnosis",
        FRAME_ABSTAINED: "abstain",
        FRAME_UNRESOLVED: "abstain",
    }.get(frame, "operational")
