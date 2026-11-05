"""
Guild class / rank layer (hierarchical structure without central authority).

Ranks are *local guild policy* derived from Merit thresholds (GS-CHR-002
calibration lives in the Local Charter). Resileos only evaluates thresholds
against the ledger; it does not invent political authority.

Default ladder (override per guild via RankTable):
  initiate → member → journeyman → senior → steward

Circles remain orthogonal (formalist / empirical / forge / distribution).
Large populations scale by: many guilds (polycentric) + ranks inside each
guild + work board sharding by circle/kind — not one global rank.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from resileos.answer.guild import GuildLedger, member_status
from resileos.answer.workbench import Workbench

# Default thresholds: minimum Merit to hold the rank (inclusive)
DEFAULT_RANKS: tuple[tuple[str, int], ...] = (
    ("initiate", 0),
    ("member", 10),
    ("journeyman", 50),
    ("senior", 150),
    ("steward", 400),
)


@dataclass
class RankTable:
    """Per-guild rank ladder; publish in Local Charter (GS-CHR-010)."""

    ranks: tuple[tuple[str, int], ...] = DEFAULT_RANKS

    def rank_for_merits(self, merits: int) -> str:
        current = self.ranks[0][0]
        for name, need in self.ranks:
            if merits >= need:
                current = name
        return current

    def next_rank(self, merits: int) -> Optional[tuple[str, int]]:
        for name, need in self.ranks:
            if merits < need:
                return name, need
        return None


@dataclass
class ClassStanding:
    guild_id: str
    moniker: str
    merits: int
    credits: int
    role: str
    rank: str
    circle: str
    next_rank: Optional[str]
    next_need: Optional[int]


def standing(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    *,
    ledger: Optional[GuildLedger] = None,
    table: Optional[RankTable] = None,
) -> ClassStanding:
    ledger = ledger or GuildLedger()
    table = table or RankTable()
    st = member_status(wb, guild_id, moniker, ledger=ledger)
    ranks = table.rank_for_merits(st.merits)
    nxt = table.next_rank(st.merits)
    circles = wb.ask_rows(
        f"org:guild:{guild_id}:member:{moniker}", "circle"
    )
    return ClassStanding(
        guild_id=st.guild_id,
        moniker=st.moniker,
        merits=st.merits,
        credits=st.credits,
        role=st.role,
        rank=ranks,
        circle=circles[0] if circles else "",
        next_rank=nxt[0] if nxt else None,
        next_need=nxt[1] if nxt else None,
    )


# ── Work / bounty board (quest-style surface over org:guild work subjects) ──


@dataclass
class BoardItem:
    guild_id: str
    work_id: str
    title: str
    state: str  # open | claimed | done
    kind: str
    circle: str
    assignee: str
    bounty_merit: int = 0
    bounty_credits: int = 0


def post_bounty(
    wb: Workbench,
    guild_id: str,
    work_id: str,
    title: str,
    *,
    kind: str = "",
    circle: str = "",
    bounty_merit: int = 0,
    bounty_credits: int = 0,
) -> int:
    from resileos.answer.guild import post_work, work_subject
    from resileos.answer.hub_train import train_hub

    n = post_work(
        wb, guild_id, work_id, title, kind=kind, circle=circle
    )
    s = work_subject(guild_id, work_id)
    extra = [(s, "board", "bounty")]
    if bounty_merit:
        extra.append((s, "bounty_merit", str(int(bounty_merit))))
    if bounty_credits:
        extra.append((s, "bounty_credits", str(int(bounty_credits))))
    n += train_hub(wb, extra, require_hub_prefix=True)
    return n


def claim_bounty(
    wb: Workbench,
    guild_id: str,
    work_id: str,
    moniker: str,
) -> int:
    from resileos.answer.guild import work_subject
    from resileos.answer.hub_train import train_hub

    s = work_subject(guild_id, work_id)
    return train_hub(
        wb,
        [
            (s, "state", "claimed"),
            (s, "assignee", moniker.lower()),
        ],
        require_hub_prefix=True,
    )


def complete_bounty(
    wb: Workbench,
    guild_id: str,
    work_id: str,
    moniker: str,
    *,
    ledger: Optional[GuildLedger] = None,
    bounty_merit: int = 0,
    bounty_credits: int = 0,
) -> dict:
    from resileos.answer.guild import complete_work

    # Prefer explicit awards; else read stored bounty_* if present
    if not bounty_merit:
        rows = wb.ask_rows(
            f"org:guild:{guild_id}:work:{work_id}", "bounty_merit"
        )
        if rows:
            try:
                bounty_merit = int(str(rows[-1]))
            except ValueError:
                pass
    if not bounty_credits:
        rows = wb.ask_rows(
            f"org:guild:{guild_id}:work:{work_id}", "bounty_credits"
        )
        if rows:
            try:
                bounty_credits = int(str(rows[-1]))
            except ValueError:
                pass
    return complete_work(
        wb,
        guild_id,
        work_id,
        moniker=moniker,
        merit_award=bounty_merit,
        credit_award=bounty_credits,
        ledger=ledger,
    )
