#!/usr/bin/env python3
"""Run the advance loop. This is the overnight step.

  python scripts/ops/advance.py --steps 5
"""
from __future__ import annotations

import argparse
import json

from resileos.ui.worker_tools import advance


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=5)
    args = ap.parse_args()
    out = advance(steps=args.steps)
    print(json.dumps({"ran": len(out), "results": out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
