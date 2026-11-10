"""Candidate registration for Studio media.

A candidate is a library record. It is not a fact. This function does not
call learn, learn_batch, or world register. World register writes hub
triples through train_hub, so a candidate must not use it.
"""
from __future__ import annotations

import uuid
from typing import Any


def register_candidate(
    *,
    kind: str,
    path: str,
    title: str,
    world_id: str = "studio",
    note: str = "",
    learn: Any = None,
    learn_batch: Any = None,
    world_register: Any = None,
) -> dict[str, Any]:
    """Record a candidate. The learn callables are accepted and never used.

    They are in the signature so a caller that still has them cannot pass
    them by accident into a positional slot, and so tests can hand in spies.
    """
    del learn, learn_batch, world_register
    asset_id = f"a_{uuid.uuid4().hex[:10]}"
    return {
        "ok": True,
        "asset_id": asset_id,
        "kind": kind,
        "path": path[:2000],
        "title": (title or asset_id)[:200],
        "world_id": world_id or "studio",
        "note": note[:200],
        "status": "candidate",
        "learned": False,
        "learn_called": False,
    }
