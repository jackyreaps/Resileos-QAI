#!/usr/bin/env python3
"""Train / query Titanos hubs.

  python scripts/train_hubs.py seed --state artifacts/hub_state.json
  python scripts/train_hubs.py train facts.txt --state artifacts/hub_state.json
  python scripts/train_hubs.py ask world:materials status --state artifacts/hub_state.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos.answer.hub_train import (  # noqa: E402
    open_hub_workbench,
    seed_default_hubs,
    train_from_file,
)



def _print_addresses(wb) -> None:
    addrs = getattr(wb, "last_hub_addresses", None)
    if addrs:
        print(json.dumps({"addresses": addrs}, indent=2))
    apollo = getattr(wb, "last_apollo", None)
    if apollo:
        print(json.dumps({"apollo": {"kept": apollo.get("kept"), "lifts": apollo.get("lifts")}}, indent=2))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seed", "train", "ask"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--state", default="artifacts/hub_state.json")
    ap.add_argument("--backend", default="structured")
    args = ap.parse_args()
    state = Path(args.state)

    wb = open_hub_workbench(
        backend=args.backend,
        state_path=state if state.exists() else None,
        seed=False,
    )

    if args.cmd == "seed":
        n = seed_default_hubs(wb)
        _print_addresses(wb)
        if hasattr(wb.titan, "save"):
            state.parent.mkdir(parents=True, exist_ok=True)
            wb.titan.save(str(state))
        print(json.dumps({"seeded": n, "state": str(state)}))
        return 0

    if args.cmd == "train":
        if not args.args:
            print("usage: train <facts.txt>", file=sys.stderr)
            return 2
        n = train_from_file(wb, Path(args.args[0]))
        _print_addresses(wb)
        if hasattr(wb.titan, "save"):
            state.parent.mkdir(parents=True, exist_ok=True)
            wb.titan.save(str(state))
        print(json.dumps({"trained": n, "state": str(state)}))
        return 0

    if args.cmd == "ask":
        if len(args.args) < 2:
            print("usage: ask <subject> <relation>", file=sys.stderr)
            return 2
        sub, rel = args.args[0], args.args[1]
        result = wb.answer(sub, rel)
        print(json.dumps({
            "subject": sub,
            "relation": rel,
            "rows": list(result.rows),
            "answer_text": result.answer_text,
            "empty": result.empty,
            "backend": result.backend,
        }, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
