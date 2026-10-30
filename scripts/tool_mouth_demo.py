#!/usr/bin/env python3
"""Tool-only mouth demo: frontier-style agent that cannot invent store facts.

Simulates an external LLM that may ONLY call resileos tools. Any claim about
world/user facts must come from tool results. Soft chat is allowed only as
glue language around Oracle rows.

Usage:
  PYTHONPATH=src:scripts:. python scripts/tool_mouth_demo.py
  PYTHONPATH=src:scripts:. python scripts/tool_mouth_demo.py --hub-user demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))


def build_oracle():
    from titanos import Titanos, TitanosConfig

    T = Titanos(TitanosConfig())
    # minimal seed if empty
    try:
        n = int(T.stats().get("facts", 0))
    except Exception:
        n = 0
    if n == 0:
        for s, r, o in [
            ("Zeus", "domain", "sky"),
            ("Poseidon", "domain", "sea"),
            ("Hades", "domain", "underworld"),
        ]:
            T.learn(s, r, o)
    return T


def mouth_reply(tool_result: dict) -> str:
    """Renderer only — no new facts."""
    status = tool_result.get("status")
    frame = tool_result.get("frame")
    instruction = tool_result.get("instruction", "")
    if status in ("NONE_CHANNEL", "ABSTAINED") or frame in ("unresolved", "abstained"):
        return (
            "I don't have a verified fact for that in the store. "
            f"({status}/{frame}) {instruction}"
        )
    rows = tool_result.get("rows") or []
    value = tool_result.get("value")
    if value is not None:
        return f"Store ({frame}): {value}"
    if rows:
        return f"Store ({frame}): " + ", ".join(str(x) for x in rows)
    return f"Store returned no rows ({status}). {instruction}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub-user", default="", help="Optional hub id for user-memory facts")
    args = ap.parse_args()

    from resileos.answer.tool_execute import execute_tool

    T = build_oracle()
    if args.hub_user:
        # Learned user/hub fact — same Oracle path as world facts
        T.learn(args.hub_user, "prefers", "exact_answers")
        T.learn(args.hub_user, "hub", "active")

    plan = [
        ("resileos_ask", {"subject": "Zeus", "relation": "domain"}),
        ("resileos_ask", {"subject": "Nobody", "relation": "domain"}),
        ("resileos_abstain", {"reason": "user asked to speculate beyond store"}),
    ]
    if args.hub_user:
        plan.append(
            ("resileos_ask", {"subject": args.hub_user, "relation": "prefers"})
        )

    transcript = []
    for name, arguments in plan:
        result = execute_tool(name, arguments, titanos=T)
        reply = mouth_reply(result)
        transcript.append(
            {
                "tool": name,
                "arguments": arguments,
                "oracle": {
                    "status": result.get("status"),
                    "frame": result.get("frame"),
                    "rows": result.get("rows"),
                    "value": result.get("value"),
                },
                "mouth": reply,
            }
        )
        print(f"TOOL {name} {arguments}")
        print(f"  oracle: {result.get('status')} / {result.get('frame')} rows={result.get('rows')}")
        print(f"  mouth:  {reply}")
        print()

    out = ROOT / "artifacts" / "report_tool_mouth_demo.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"transcript": transcript}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
