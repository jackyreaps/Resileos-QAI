"""Spend gate for use.

Free tier is allowed. Above the free allowance, credit is required.
"""
from __future__ import annotations

from typing import Any

from resileos.ui.credits import spend_for_use

FREE_UNITS = 20


def allow_use(member: str, units: int = 1, *, used_free: int = 0, what: str = "query") -> dict[str, Any]:
    """Free tier first. Then credits. Never invents a charge."""
    if used_free < FREE_UNITS:
        return {"ok": True, "source": "free", "remaining_free": FREE_UNITS - used_free - units}
    spent = spend_for_use(member, units, what=what)
    if not spent.get("ok"):
        return {"ok": False, "source": "credit", "error": spent.get("error"), "balance": spent.get("balance")}
    return {"ok": True, "source": "credit", "balance": spent.get("balance")}
