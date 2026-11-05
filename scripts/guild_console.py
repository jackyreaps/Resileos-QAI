#!/usr/bin/env python3
"""Guild day-flow CLI: join, merit, credits, work, status."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos.answer.guild import (  # noqa: E402
    GuildLedger,
    award_merits,
    burn_credits,
    complete_work,
    create_guild,
    grant_credits,
    join_guild,
    member_status,
    post_work,
)
from resileos.answer.hub_train import open_hub_workbench  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=[
        "create", "join", "merit", "credit", "burn", "work", "complete", "status",
    ])
    ap.add_argument("--guild", required=True)
    ap.add_argument("--moniker", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--role", default="member")
    ap.add_argument("--circle", default="")
    ap.add_argument("--amount", type=int, default=0)
    ap.add_argument("--reason", default="")
    ap.add_argument("--work-id", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--kind", default="")
    ap.add_argument("--assignee", default="")
    ap.add_argument("--merit-award", type=int, default=0)
    ap.add_argument("--credit-award", type=int, default=0)
    ap.add_argument("--ledger", default="artifacts/guild_ledger.json")
    ap.add_argument("--state", default="artifacts/guild_hub_state.json")
    args = ap.parse_args()

    ledger = GuildLedger(Path(args.ledger))
    state = Path(args.state)
    wb = open_hub_workbench(
        backend="structured",
        state_path=state if state.exists() else None,
        seed=False,
    )

    def save():
        if hasattr(wb.titan, "save"):
            state.parent.mkdir(parents=True, exist_ok=True)
            wb.titan.save(str(state))

    if args.cmd == "create":
        n = create_guild(wb, args.guild, name=args.name)
        save()
        print(json.dumps({"created": n, "guild": args.guild}))
        return 0
    if args.cmd == "join":
        n = join_guild(wb, args.guild, args.moniker, role=args.role, circle=args.circle, ledger=ledger)
        save()
        print(json.dumps({"joined": n, "moniker": args.moniker}))
        return 0
    if args.cmd == "merit":
        v = award_merits(wb, args.guild, args.moniker, args.amount, reason=args.reason, ledger=ledger)
        save()
        print(json.dumps({"merits": v}))
        return 0
    if args.cmd == "credit":
        v = grant_credits(wb, args.guild, args.moniker, args.amount, reason=args.reason, ledger=ledger)
        save()
        print(json.dumps({"credits": v}))
        return 0
    if args.cmd == "burn":
        v = burn_credits(wb, args.guild, args.moniker, args.amount, reason=args.reason, ledger=ledger)
        save()
        print(json.dumps({"credits": v}))
        return 0
    if args.cmd == "work":
        n = post_work(
            wb, args.guild, args.work_id, args.title,
            assignee=args.assignee or args.moniker, kind=args.kind, circle=args.circle,
        )
        save()
        print(json.dumps({"work": args.work_id, "triples": n}))
        return 0
    if args.cmd == "complete":
        out = complete_work(
            wb, args.guild, args.work_id, moniker=args.moniker,
            merit_award=args.merit_award, credit_award=args.credit_award, ledger=ledger,
        )
        save()
        print(json.dumps(out))
        return 0
    if args.cmd == "status":
        st = member_status(wb, args.guild, args.moniker, ledger=ledger)
        print(json.dumps({
            "guild_id": st.guild_id,
            "moniker": st.moniker,
            "role": st.role,
            "merits": st.merits,
            "credits": st.credits,
            "status": st.status,
        }, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
