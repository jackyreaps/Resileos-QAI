from pathlib import Path

from resileos.answer.guild import (
    GuildLedger,
    award_merits,
    burn_credits,
    complete_work,
    grant_credits,
    join_guild,
    member_status,
    post_work,
)
from resileos.answer.hub_train import open_hub_workbench


def test_merit_credits_decoupled(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    ledger = GuildLedger(tmp_path / "ledger.json")
    join_guild(wb, "builders", "alice", role="member", circle="forge", ledger=ledger)
    st = member_status(wb, "builders", "alice", ledger=ledger)
    assert st.merits == 0 and st.credits == 0
    assert award_merits(wb, "builders", "alice", 10, reason="proof", ledger=ledger) == 10
    assert grant_credits(wb, "builders", "alice", 20, reason="compute", ledger=ledger) == 20
    assert burn_credits(wb, "builders", "alice", 5, reason="tool_use", ledger=ledger) == 15
    st = member_status(wb, "builders", "alice", ledger=ledger)
    assert st.merits == 10
    assert st.credits == 15


def test_work_complete_merit(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    ledger = GuildLedger(tmp_path / "ledger.json")
    join_guild(wb, "builders", "bob", ledger=ledger)
    post_work(
        wb, "builders", "task1", "Formalize claim review",
        assignee="bob", kind="claim_review", circle="formalist",
    )
    out = complete_work(
        wb, "builders", "task1", moniker="bob",
        merit_award=5, credit_award=2, ledger=ledger,
    )
    assert out["state"] == "done"
    st = member_status(wb, "builders", "bob", ledger=ledger)
    assert st.merits == 5 and st.credits == 2
