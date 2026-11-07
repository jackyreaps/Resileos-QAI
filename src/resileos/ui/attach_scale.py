"""Shared scale attach for any result dict.

One function so iris, metis, hermes, eat, mouth, and benches
do not each invent an address.
"""
from __future__ import annotations

from typing import Any

from resileos.ui.scale_address import scale_address


def attach_scale(payload: dict[str, Any], subject: str = "") -> dict[str, Any]:
    addr = scale_address(subject=subject or "result")
    payload["scale"] = {"address": addr["embed"], "gate": addr["gate"]}
    return payload
