"""Outward promotion of a verified fact, one scale at a time.

The live CascadeRouter sets ``verified``. This module never re-verifies.
Unverified facts are refused and stay put. A verified fact still needs
an explicit opt-in (or a consent token) from the owner; without it the
fact stays put. There is no automatic promotion.

On accept, ``promote`` returns the subject at the next scale only. It
does not call Eat, ``learn``, or the scar matrix. The caller hands that
subject to the existing Eat / learn path. Studio, visual, and persona
paths must not call learn. No scar update beyond the learn at the scale
that accepted it.

Scales are the pin names (individual, local, global), which map onto
the persona-store tiers (individual, hub, latent). One vocabulary is
used; see ``resileos.ui.cascade_address``.

Hub namespaces in ``hub_train.py`` are ``user:``, ``world:``, and
``org:``. A draft mapped individual→user, local→world, global→org.
That pairing is backwards relative to the repo: ``org:`` is the tenant
and guild-hub namespace (``org:guild:...``), and ``world:`` is the
shared project / world-facts namespace. The mapping used here is:

    individual (private / pin individual)  -> user:<ident>
    local      (guild hub / pin local)     -> org:<ident>
    global     (latent     / pin global)   -> world:<ident>

So a one-step walk is ``user:ada`` → ``org:ada`` → ``world:ada``.
The global scale cannot promote further.

Residual learning: the persona store already stores only the residual
against the tier above on ``promote_to_hub`` / ``promote_to_latent``.
This helper does not write. Titanos ``learn`` stores a full fact at the
new subject, not a residual against the tier above. That gap stays with
the learn path; it is not papered over here.
"""
from __future__ import annotations

from typing import Any

from resileos.ui.cascade_address import (
    PIN_TO_TIER,
    PINS,
    TIER_TO_PIN,
    pin_for_tier,
    tier_for_pin,
)

# Pin names, outward. Same sequence as ``resileos.ui.cascade_address.PINS``.
SCALES: tuple[str, ...] = ("individual", "local", "global")

# Corrected hub_train prefixes. Draft had local=world, global=org.
PREFIX: dict[str, str] = {
    "individual": "user",
    "local": "org",
    "global": "world",
}

_PREFIX_TO_SCALE: dict[str, str] = {prefix: scale for scale, prefix in PREFIX.items()}

__all__ = [
    "PREFIX",
    "SCALES",
    "PIN_TO_TIER",
    "TIER_TO_PIN",
    "pin_for_tier",
    "promote",
    "scale_of_subject",
    "subject_at",
    "tier_for_pin",
]


def subject_at(scale: str, ident: str) -> str:
    """Hub subject for a pin scale and an identity, for example ``user:ada``."""
    if scale not in PREFIX:
        raise ValueError(f"unknown scale: {scale!r}")
    token = str(ident).strip()
    if not token:
        raise ValueError("ident is required")
    return f"{PREFIX[scale]}:{token}"


def scale_of_subject(subject: str) -> str | None:
    """Pin scale for a ``user:`` / ``org:`` / ``world:`` subject, if known."""
    raw = (subject or "").strip()
    prefix = raw.split(":", 1)[0] if ":" in raw else ""
    return _PREFIX_TO_SCALE.get(prefix)


def _opted_in(opt_in: Any) -> bool:
    if opt_in is True:
        return True
    if isinstance(opt_in, str) and opt_in.strip():
        return True
    return False


def _current_scale(fact: dict[str, Any]) -> str | None:
    named = fact.get("scale") or fact.get("pin")
    if named in PINS:
        return str(named)
    if named in TIER_TO_PIN:
        return pin_for_tier(str(named))
    return scale_of_subject(str(fact.get("subject") or ""))


def _refuse(reason: str, fact: dict[str, Any], **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "decision": "refuse",
        "reason": reason,
        "fact": dict(fact),
        "writes": False,
        "learned": False,
    }
    out.update(extra)
    return out


def promote(
    fact: dict[str, Any],
    *,
    verified: bool,
    to_scale: str,
    ident: str,
    opt_in: Any = False,
) -> dict[str, Any]:
    """Return the next-scale subject for a verified, opted-in fact.

    One step outward only. Does not re-verify, does not write, and does
    not call learn. ``to_scale`` must be a pin name (individual, local,
    global).
    """
    body = dict(fact or {})
    if to_scale not in PINS:
        raise ValueError(f"unknown scale: {to_scale!r}")
    if not verified:
        return _refuse("unverified; stays at current scale", body)

    if not _opted_in(opt_in):
        return _refuse(
            "opt-in required; stays at current scale",
            body,
        )

    current = _current_scale(body)
    if current is None:
        return _refuse("current scale is unknown; stays put", body)

    here = SCALES.index(current)
    if current == "global" or here >= len(SCALES) - 1:
        return _refuse("already at global; cannot promote further", body, scale=current)

    nxt = SCALES[here + 1]
    if to_scale != nxt:
        return _refuse(
            "to_scale must be the next scale outward; cannot skip a scale",
            body,
            scale=current,
        )

    relation = body.get("relation")
    obj = body.get("obj")
    subject = subject_at(to_scale, ident)
    return {
        "ok": True,
        "decision": "accept",
        "scale": to_scale,
        "tier": PIN_TO_TIER[to_scale],
        "from_scale": current,
        "subject": subject,
        "relation": relation,
        "obj": obj,
        "note": (
            "one step outward; write through Eat/learn; "
            "no scar update beyond the learn at the scale that accepted it"
        ),
        "writes": False,
        "learned": False,
    }
