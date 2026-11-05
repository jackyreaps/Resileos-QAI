"""
Guild operational store (GS-FND-002 surface, not the Compact itself).

Merit and Credits are decoupled (Compact §3 / Article II).
Balances live in a small sidecar JSON so multi-value Titanos history
does not break burn/award; Titanos still records event triples for audit.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from resileos.answer.hub_train import train_hub
from resileos.answer.workbench import Workbench

_ID = re.compile(r"^[a-z0-9_]{1,64}$")
_DEFAULT_LEDGER = Path("artifacts/guild_ledger.json")


def _id(name: str, label: str) -> str:
    n = name.strip().lower()
    if not _ID.match(n):
        raise ValueError(f"invalid {label}: {name!r}")
    return n


def guild_subject(guild_id: str) -> str:
    return f"org:guild:{_id(guild_id, 'guild_id')}"


def member_subject(guild_id: str, moniker: str) -> str:
    return f"org:guild:{_id(guild_id, 'guild_id')}:member:{_id(moniker, 'moniker')}"


def work_subject(guild_id: str, work_id: str) -> str:
    return f"org:guild:{_id(guild_id, 'guild_id')}:work:{_id(work_id, 'work_id')}"


class GuildLedger:
    """Sidecar Merit/Credits balances (authoritative for numbers)."""

    def __init__(self, path: Path = _DEFAULT_LEDGER) -> None:
        self.path = path
        self._data: dict = {"members": {}}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def _key(self, guild_id: str, moniker: str) -> str:
        return f"{_id(guild_id, 'guild_id')}:{_id(moniker, 'moniker')}"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, guild_id: str, moniker: str) -> tuple[int, int]:
        rec = self._data["members"].get(self._key(guild_id, moniker), {})
        return int(rec.get("merits", 0)), int(rec.get("credits", 0))

    def set_merits(self, guild_id: str, moniker: str, value: int) -> int:
        k = self._key(guild_id, moniker)
        rec = self._data["members"].setdefault(k, {"merits": 0, "credits": 0})
        rec["merits"] = max(0, int(value))
        self.save()
        return rec["merits"]

    def set_credits(self, guild_id: str, moniker: str, value: int) -> int:
        k = self._key(guild_id, moniker)
        rec = self._data["members"].setdefault(k, {"merits": 0, "credits": 0})
        rec["credits"] = max(0, int(value))
        self.save()
        return rec["credits"]


@dataclass
class MemberStatus:
    guild_id: str
    moniker: str
    role: str
    merits: int
    credits: int
    status: str


def create_guild(wb: Workbench, guild_id: str, name: str = "") -> int:
    s = guild_subject(guild_id)
    facts = [
        (s, "status", "active"),
        (s, "name", (name or guild_id)[:128]),
        (s, "compact_ref", "GS-FND-002"),
    ]
    return train_hub(wb, facts, require_hub_prefix=True)


def join_guild(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    *,
    role: str = "member",
    circle: str = "",
    ledger: Optional[GuildLedger] = None,
) -> int:
    create_guild(wb, guild_id)
    ledger = ledger or GuildLedger()
    ledger.set_merits(guild_id, moniker, 0)
    ledger.set_credits(guild_id, moniker, 0)
    s = member_subject(guild_id, moniker)
    facts = [
        (s, "status", "active"),
        (s, "role", role[:32]),
        (guild_subject(guild_id), "has_member", _id(moniker, "moniker")),
    ]
    if circle:
        facts.append((s, "circle", circle[:64]))
    return train_hub(wb, facts, require_hub_prefix=True)


def award_merits(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    amount: int,
    *,
    reason: str = "",
    ledger: Optional[GuildLedger] = None,
) -> int:
    if amount < 0:
        raise ValueError("Merit is non-purchasable and not decremented here")
    ledger = ledger or GuildLedger()
    m, _ = ledger.get(guild_id, moniker)
    new = ledger.set_merits(guild_id, moniker, m + int(amount))
    s = member_subject(guild_id, moniker)
    facts = [(s, "merit_event", f"+{amount}:{reason[:64]}" if reason else f"+{amount}")]
    train_hub(wb, facts, require_hub_prefix=True)
    return new


def grant_credits(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    amount: int,
    *,
    reason: str = "",
    ledger: Optional[GuildLedger] = None,
) -> int:
    ledger = ledger or GuildLedger()
    _, c = ledger.get(guild_id, moniker)
    new = ledger.set_credits(guild_id, moniker, c + int(amount))
    s = member_subject(guild_id, moniker)
    train_hub(
        wb,
        [(s, "credit_event", f"{amount:+d}:{reason[:64]}" if reason else f"{amount:+d}")],
        require_hub_prefix=True,
    )
    return new


def burn_credits(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    amount: int,
    *,
    reason: str = "",
    ledger: Optional[GuildLedger] = None,
) -> int:
    if amount < 0:
        raise ValueError("burn amount must be >= 0")
    return grant_credits(
        wb, guild_id, moniker, -amount, reason=reason or "burn", ledger=ledger
    )


def post_work(
    wb: Workbench,
    guild_id: str,
    work_id: str,
    title: str,
    *,
    assignee: str = "",
    kind: str = "",
    circle: str = "",
) -> int:
    s = work_subject(guild_id, work_id)
    facts = [
        (s, "title", title[:256]),
        (s, "state", "open"),
        (guild_subject(guild_id), "has_work", _id(work_id, "work_id")),
    ]
    if assignee:
        facts.append((s, "assignee", _id(assignee, "assignee")))
    if kind:
        facts.append((s, "kind", kind[:64]))
    if circle:
        facts.append((s, "circle", circle[:64]))
    return train_hub(wb, facts, require_hub_prefix=True)


def complete_work(
    wb: Workbench,
    guild_id: str,
    work_id: str,
    *,
    moniker: str = "",
    merit_award: int = 0,
    credit_award: int = 0,
    ledger: Optional[GuildLedger] = None,
) -> dict:
    s = work_subject(guild_id, work_id)
    train_hub(wb, [(s, "state", "done")], require_hub_prefix=True)
    merits = credits = None
    if moniker and merit_award:
        merits = award_merits(
            wb, guild_id, moniker, merit_award, reason=f"work:{work_id}", ledger=ledger
        )
    if moniker and credit_award:
        credits = grant_credits(
            wb, guild_id, moniker, credit_award, reason=f"work:{work_id}", ledger=ledger
        )
    return {"work": work_id, "state": "done", "merits": merits, "credits": credits}


def member_status(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    *,
    ledger: Optional[GuildLedger] = None,
) -> MemberStatus:
    ledger = ledger or GuildLedger()
    m, c = ledger.get(guild_id, moniker)
    s = member_subject(guild_id, moniker)
    roles = wb.ask_rows(s, "role")
    statuses = wb.ask_rows(s, "status")
    return MemberStatus(
        guild_id=_id(guild_id, "guild_id"),
        moniker=_id(moniker, "moniker"),
        role=roles[0] if roles else "",
        merits=m,
        credits=c,
        status=statuses[0] if statuses else "unknown",
    )
