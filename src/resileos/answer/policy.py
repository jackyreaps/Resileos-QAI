"""Sector × gate_state routing policy (Tier A).

Maps (sector, gate_state, confidence) to a preferred child name. Used by
/query after encode_gate. Does not replace recovery abstain.

Two functions:

    prefer_child(...)           -> "zeus" | "parent" | "none"
    gbx_bypass_recurrent(...)   -> bool   (predicate; does not resolve)

The second is a *predicate*, not a resolver. It answers "should this
query skip the recurrent loop?" — nothing more. The caller is
responsible for what "skip" means: in /query that means building a
synthetic Answer from ask_list and bypassing both Zeus and the
recurrent pass. Calling it and then still running ask() defeats the
sector policy; see the gbx fast-path block in app.py.
"""
from __future__ import annotations


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
    """True when single-hop exact band should skip long recurrent loops.

    Predicate only. The caller decides what "skip" means:

      - gbx_like  -> resolve from ask_list when exactly one row exists,
                     build a synthetic Answer (mode="FAST", loops=0,
                     gate_state="LOCKED"), and do not invoke Zeus.
      - anything else -> the normal Zeus-with-fallthrough path.

    Calling this and then running ask() anyway makes the sector policy
    decorative: the recurrent loop runs, the sector annotation is
    accurate, and the promised cost saving never materialises.
    """
    return (sector or "").lower() == "gbx_like"


__all__ = ["prefer_child", "gbx_bypass_recurrent"]
