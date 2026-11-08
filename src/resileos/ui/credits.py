"""Closed-loop credits for Resileos use.

Guild rules (GS-MTX-005, Compact):
  - Credits are closed-loop. They are not transferable.
  - They are not redeemable for fiat.
  - Use burns them. Work earns them.

Merit is separate. Merit is an attestation. Credit is the usage unit.
"""
from __future__ import annotations

from typing import Any


class CreditLedger:
    def __init__(self) -> None:
        self._bal: dict[str, int] = {}
        self._log: list[dict[str, Any]] = []

    def balance(self, member: str) -> int:
        return int(self._bal.get(member, 0))

    def earn(self, member: str, amount: int, *, reason: str = "") -> dict[str, Any]:
        """Work or contribution earns closed-loop credits."""
        if amount <= 0:
            return {"ok": False, "error": "amount must be positive"}
        self._bal[member] = self.balance(member) + amount
        row = {
            "subject": f"user:{member}",
            "relation": "credit_earn",
            "obj": str(amount),
            "reason": reason,
            "balance": self.balance(member),
            "closed_loop": True,
        }
        self._log.append(row)
        return {"ok": True, **row}

    def spend(self, member: str, amount: int, *, reason: str = "") -> dict[str, Any]:
        """Use burns credits. No transfer."""
        if amount <= 0:
            return {"ok": False, "error": "amount must be positive"}
        if self.balance(member) < amount:
            return {"ok": False, "error": "insufficient", "balance": self.balance(member)}
        self._bal[member] = self.balance(member) - amount
        row = {
            "subject": f"user:{member}",
            "relation": "credit_spend",
            "obj": str(amount),
            "reason": reason,
            "balance": self.balance(member),
            "closed_loop": True,
        }
        self._log.append(row)
        return {"ok": True, **row}

    def transfer(self, src: str, dst: str, amount: int) -> dict[str, Any]:
        """Prohibited. Credits do not move between members."""
        return {"ok": False, "error": "credits are not transferable", "closed_loop": True}

    def log(self, member: str | None = None) -> list[dict[str, Any]]:
        if member is None:
            return list(self._log)
        return [r for r in self._log if r["subject"] == f"user:{member}"]


ledger = CreditLedger()


def earn_for_work(member: str, title: str, *, amount: int = 1) -> dict[str, Any]:
    return ledger.earn(member, amount, reason=f"work:{title}")


def spend_for_use(member: str, units: int, *, what: str = "query") -> dict[str, Any]:
    return ledger.spend(member, units, reason=f"use:{what}")
