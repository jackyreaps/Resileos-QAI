from pathlib import Path

from resileos.answer.guild import GuildLedger, join_guild, award_merits
from resileos.answer.guild_classes import (
    RankTable,
    claim_bounty,
    complete_bounty,
    post_bounty,
    standing,
)
from resileos.answer.hub_train import open_hub_workbench


def test_rank_ladder(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    ledger = GuildLedger(tmp_path / "led.json")
    join_guild(wb, "g", "alice", ledger=ledger)
    assert standing(wb, "g", "alice", ledger=ledger).rank == "initiate"
    award_merits(wb, "g", "alice", 12, ledger=ledger)
    assert standing(wb, "g", "alice", ledger=ledger).rank == "member"
    award_merits(wb, "g", "alice", 50, ledger=ledger)
    st = standing(wb, "g", "alice", ledger=ledger)
    assert st.rank == "journeyman"
    assert st.next_rank == "senior"


def test_bounty_flow(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    ledger = GuildLedger(tmp_path / "led.json")
    join_guild(wb, "g", "bob", ledger=ledger)
    post_bounty(
        wb, "g", "q1", "Verify lemma X",
        kind="derivation", circle="formalist",
        bounty_merit=5, bounty_credits=3,
    )
    claim_bounty(wb, "g", "q1", "bob")
    out = complete_bounty(wb, "g", "q1", "bob", ledger=ledger)
    assert out["state"] == "done"
    st = standing(wb, "g", "bob", ledger=ledger)
    assert st.merits == 5 and st.credits == 3
