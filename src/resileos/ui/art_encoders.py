"""Custom encoders for music and art.

These write into the Apollo art path. They do not pass the pure-truth
eat gate. A later encoder can replace the body; the interface stays.
"""
from __future__ import annotations

from typing import Any

from resileos.kin.apollo import apollo_cycle
from resileos.ui.scale_address import scale_address


def encode_music(title: str, notes: str, *, world_id: str = "world:music") -> dict[str, Any]:
    """Encode a short piece as an art fact on the scale address."""
    addr = scale_address(subject=world_id)
    facts = [{"subject": world_id, "relation": "music", "obj": f"{title}: {notes[:80]}"}]
    out = apollo_cycle(facts, subject=world_id, art=True)
    return {"kind": "music", "title": title, "address": addr["embed"], "apollo": out}


def encode_art(title: str, description: str, *, world_id: str = "world:art") -> dict[str, Any]:
    """Encode a visual or poetic work as an art fact."""
    addr = scale_address(subject=world_id)
    facts = [{"subject": world_id, "relation": "art", "obj": f"{title}: {description[:80]}"}]
    out = apollo_cycle(facts, subject=world_id, art=True)
    return {"kind": "art", "title": title, "address": addr["embed"], "apollo": out}
