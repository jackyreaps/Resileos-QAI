"""Attach the scale address to an existing hub train batch.

Uses the hub_train namespaces (user: / world: / org:).
Does not replace Workbench or Titanos.
"""
from __future__ import annotations

from typing import Any

from resileos.ui.scale_address import scale_address


def address_for_hub_subject(subject: str) -> dict[str, Any]:
    """Scale address for a hub subject. Kind from the prefix."""
    kind = "user"
    if subject.startswith("world:"):
        kind = "world"
    elif subject.startswith("org:"):
        kind = "org"
    addr = scale_address(subject=subject)
    return {"subject": subject, "kind": kind, "address": addr["embed"], "field": addr["field"]}
