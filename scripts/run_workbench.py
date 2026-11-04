#!/usr/bin/env python3
"""CLI for the advanced-project workbench (store + mouth).

Examples:
  python scripts/run_workbench.py ingest facts.txt
  python scripts/run_workbench.py ask eps equals
  python scripts/run_workbench.py ask eps equals --backend structured

Optional RAG mouth (needs transformers + model download):
  RESILEOS_ANSWER_BACKEND=local_hf python scripts/run_workbench.py ask ... --backend local_hf
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos.answer.workbench import open_workbench  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Resileos advanced workbench")
    ap.add_argument("cmd", choices=["ingest", "ask", "snapshot"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--backend", default="structured")
    ap.add_argument("--state", default="artifacts/workbench_state.json")
    args = ap.parse_args()

    state = Path(args.state)
    wb = open_workbench(backend=args.backend)
    if state.exists() and hasattr(wb.titan, "load"):
        try:
            wb.titan = type(wb.titan).load(str(state))
            wb._backend = __import__(
                "resileos.answer.backends", fromlist=["select_backend"]
            ).select_backend(args.backend)
        except Exception:
            pass

    if args.cmd == "ingest":
        if not args.args:
            print("usage: ingest <file>", file=sys.stderr)
            return 2
        n = wb.ingest_file(Path(args.args[0]))
        if hasattr(wb.titan, "save"):
            state.parent.mkdir(parents=True, exist_ok=True)
            wb.titan.save(str(state))
        print(json.dumps({"ingested": n, "state": str(state)}))
        return 0

    if args.cmd == "ask":
        if len(args.args) < 2:
            print("usage: ask <subject> <relation> [question...]", file=sys.stderr)
            return 2
        subject, relation, *rest = args.args
        question = " ".join(rest)
        result = wb.answer(subject, relation, question=question)
        print(json.dumps({
            "subject": result.subject,
            "relation": result.relation,
            "rows": list(result.rows),
            "answer_text": result.answer_text,
            "backend": result.backend,
            "empty": result.empty,
        }, indent=2))
        return 0

    print(json.dumps(wb.session_snapshot(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
