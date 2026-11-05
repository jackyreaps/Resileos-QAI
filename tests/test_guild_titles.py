from pathlib import Path

from resileos.answer.guild import GuildLedger, join_guild, award_merits
from resileos.answer.guild_titles import (
    award_title,
    define_title,
    list_titles,
    portfolio,
    record_valor,
)
from resileos.answer.hub_train import open_hub_workbench


def test_titles_and_valor(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    ledger = GuildLedger(tmp_path / "led.json")
    join_guild(wb, "g", "alice", circle="forge", ledger=ledger)
    award_merits(wb, "g", "alice", 12, ledger=ledger)
    define_title(wb, "g", "lean_contributor", "Lean Contributor")
    award_title(wb, "g", "alice", "lean_contributor", evidence_ref="world:g:proof1")
    record_valor(
        wb, "g", "alice", "cost_borne",
        status="accomplished", evidence_ref="world:g:incident1",
    )
    titles = list_titles(wb, "g", "alice")
    assert "lean_contributor" in titles
    port = portfolio(wb, "g", "alice", ledger=ledger)
    assert port.rank == "member"
    assert "lean_contributor" in port.titles
    assert any("cost_borne:accomplished" in v for v in port.valor_events)
