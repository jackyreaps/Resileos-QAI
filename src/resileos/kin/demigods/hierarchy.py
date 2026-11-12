"""Rank guards for a summoned Demi-god.

A Demi-god serves under Kin. It cannot call learn, take ownership of the
residual core, summon another Demi-god, or carry durable state other than
the Hades lesson and the residual packet hash.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_active: ContextVar[str | None] = ContextVar("resileos_demigod_duty", default=None)

_DURABLE_KEYS = frozenset({"lesson", "residual_packet_hash", "residual_hash"})


class DemigodError(Exception):
    """Fail-closed roster, name, or packet error."""


class DemigodHierarchyError(DemigodError):
    """A Demi-god tried to act above its rank."""


def active_demigod() -> str | None:
    return _active.get()


@contextmanager
def demigod_duty(name: str) -> Iterator[str]:
    """Mark one Demi-god as the active duty. Nesting is refused."""
    current = _active.get()
    if current is not None:
        raise DemigodHierarchyError(
            f"demigod {current} cannot summon or enter another duty ({name})"
        )
    token = _active.set(name)
    try:
        yield name
    finally:
        _active.reset(token)


def promote_temporary(*_args: Any, **_kwargs: Any) -> None:
    """A temporary swarm member cannot become a permanent legion."""
    raise DemigodHierarchyError(
        "a demigod cannot promote a temporary legion to permanent status"
    )


def refuse_learn(*_args: Any, **_kwargs: Any) -> None:
    """The learn entry a Demi-god can see. It always refuses."""
    raise DemigodHierarchyError("a demigod cannot call learn")


def refuse_residual_ownership(_core: Any = None) -> None:
    """Refuse to retain a residual core. Hash reads go through residual_hash_only."""
    raise DemigodHierarchyError("a demigod cannot own the residual core")


def residual_hash_only(residual_packet: Any) -> str | None:
    """Copy the packet hash and drop the core object."""
    if residual_packet is None:
        return None
    if isinstance(residual_packet, dict):
        digest = residual_packet.get("packet_hash")
    else:
        digest = getattr(residual_packet, "packet_hash", None)
    if not isinstance(digest, str) or digest == "":
        return None
    return digest


def durable_cross_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the Hades lesson and the residual hash.

    Any other key is a rank violation, not something to quietly drop.
    """
    if not isinstance(payload, dict):
        raise DemigodHierarchyError("durable state must be a dict")
    extra = set(payload) - _DURABLE_KEYS
    if extra:
        names = ", ".join(sorted(extra))
        raise DemigodHierarchyError(
            "a demigod cannot persist "
            f"{names}; only the Hades lesson and residual hash cross attempts"
        )
    out: dict[str, Any] = {}
    if "lesson" in payload:
        out["lesson"] = payload["lesson"]
    if "residual_packet_hash" in payload:
        out["residual_packet_hash"] = payload["residual_packet_hash"]
    elif "residual_hash" in payload:
        out["residual_packet_hash"] = payload["residual_hash"]
    return out
