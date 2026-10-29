"""Sector × gate_state routing policy (Tier A).

Maps (sector, gate_state, confidence) to a preferred child name.
Used by /query after encode_gate. Does not replace recovery abstain.
"""
from __future__ import annotations

from typing import Optional


def prefer_child(
    *,
    sector: str,
    gate_state: str = "",
    confidence: float = 1.0,
    abstain_threshold: float = 0.03,
) -> str:
    """Return preferred child key: ``zeus`` | ``parent`` | ``none``.

    - ``none`` — caller should abstain / NONE_CHANNEL behaviour
    - ``zeus`` — always allowed to run; may still decline
    - ``parent`` — exact Titanos ask path
    """
    sec = (sector or "").lower()
    gs = (gate_state or "").upper()
    if confidence < abstain_threshold and gs in {"REPULSE", "UNLOCKED", ""}:
        if gs == "REPULSE" and confidence <= 0.0:
            return "none"
    # Dual-sector default: both may run Zeus first; gbx prefers parent
    # after Zeus declines. Policy name is the *first* preference.
    if sec == "gbx_like":
        return "parent"
    if sec == "otx_like":
        return "zeus"
    return "zeus"  # unset → try Zeus, fall through parent


def gbx_bypass_recurrent(sector: str) -> bool:
    """True when single-hop exact band should skip long recurrent loops."""
    return (sector or "").lower() == "gbx_like"
