"""
Titles and valor records for guild members.

Portfolio layer over Merit/rank: named achievements and valor events
that charters / GS-CHR-012 may treat as eligibility evidence.

Does not grant network authority (Convocation, Senate, Sovereign).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from resileos.answer.guild import GuildLedger, member_subject
from resileos.answer.hub_train import train_hub as th
from resileos.answer.workbench import Workbench

_ID = re.compile(r"^[a-z0-9_]{1,64}$")
_VALOR_KINDS = frozenset({
    "cost_borne",
    "coherence_under_load",
    "belief_line",
    "judgment_accepted",
})


def _id(name: str, label: str) -> str:
    n = name.strip().lower()
    if not _ID.match(n):
        raise ValueError(f"invalid {label}: {name!r}")
    return n


def title_def_subject(guild_id: str, slug: str) -> str:
    return f"org:guild:{_id(guild_id, 'guild_id')}:title:{_id(slug, 'slug')}"


def define_title(
    wb: Workbench,
    guild_id: str,
    slug: str,
    name: str,
    *,
    description: str = "",
) -> int:
    s = title_def_subject(guild_id, slug)
    facts = [
        (s, "name", (name or slug)[:128]),
        (s, "status", "active"),
    ]
    if description:
        facts.append((s, "description", description[:512]))
    return th(wb, facts, require_hub_prefix=True)


def award_title(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    slug: str,
    *,
    evidence_ref: str = "",
    reason: str = "",
) -> int:
    """Attach a title slug to a member. Non-purchasable."""
    s = member_subject(guild_id, moniker)
    slug = _id(slug, "slug")
    facts = [(s, "title", slug)]
    if evidence_ref:
        facts.append((s, "title_evidence", f"{slug}:{evidence_ref[:200]}"))
    if reason:
        facts.append((s, "title_reason", f"{slug}:{reason[:128]}"))
    return th(wb, facts, require_hub_prefix=True)


def list_titles(wb: Workbench, guild_id: str, moniker: str) -> list[str]:
    rows = wb.ask_rows(member_subject(guild_id, moniker), "title")
    # preserve order, unique
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        t = str(r).strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def record_valor(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    kind: str,
    *,
    status: str = "pending",
    evidence_ref: str = "",
    note: str = "",
) -> int:
    """
    Record a valor event. status: pending | accomplished.
    Accomplished should follow attestation / audit outside this call.
    """
    kind = kind.strip().lower()
    if kind not in _VALOR_KINDS:
        raise ValueError(
            f"valor kind must be one of {sorted(_VALOR_KINDS)}, got {kind!r}"
        )
    status = status.strip().lower()
    if status not in ("pending", "accomplished"):
        raise ValueError("status must be pending|accomplished")
    payload = f"{kind}:{status}"
    if evidence_ref:
        payload += f":{evidence_ref[:160]}"
    if note:
        payload += f":{note[:80]}"
    s = member_subject(guild_id, moniker)
    return th(wb, [(s, "valor_event", payload)], require_hub_prefix=True)


def list_valor(wb: Workbench, guild_id: str, moniker: str) -> list[str]:
    return [str(r) for r in wb.ask_rows(member_subject(guild_id, moniker), "valor_event")]


@dataclass
class Portfolio:
    guild_id: str
    moniker: str
    merits: int
    credits: int
    rank: str
    titles: list[str] = field(default_factory=list)
    valor_events: list[str] = field(default_factory=list)
    circle: str = ""


def portfolio(
    wb: Workbench,
    guild_id: str,
    moniker: str,
    *,
    ledger: Optional[GuildLedger] = None,
) -> Portfolio:
    from resileos.answer.guild_classes import standing

    st = standing(wb, guild_id, moniker, ledger=ledger)
    return Portfolio(
        guild_id=st.guild_id,
        moniker=st.moniker,
        merits=st.merits,
        credits=st.credits,
        rank=st.rank,
        titles=list_titles(wb, guild_id, moniker),
        valor_events=list_valor(wb, guild_id, moniker),
        circle=st.circle,
    )
