"""Attach the scale address to an existing hub train batch.

Uses the hub_train namespaces (user: / world: / org:).
Does not replace Workbench or Titanos.
"""
from __future__ import annotations

from typing import Any

from resileos.persona.promote import scale_of_subject
from resileos.ui.cascade_address import pin_address
from resileos.ui.scale_address import scale_address


def address_for_hub_subject(subject: str) -> dict[str, Any]:
    """Scale address for a hub subject. Kind from the prefix.

    Also records the pin address for that namespace (user →
    individual, org → local, world → global). This does not promote
    a fact and does not call learn.
    """
    kind = "user"
    if subject.startswith("world:"):
        kind = "world"
    elif subject.startswith("org:"):
        kind = "org"
    addr = scale_address(subject=subject)
    pin = scale_of_subject(subject)
    return {
        "subject": subject,
        "kind": kind,
        "address": addr["embed"],
        "field": addr["field"],
        "pin": pin,
        "pin_address": pin_address(pin) if pin else None,
    }
