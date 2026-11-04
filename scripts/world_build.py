#!/usr/bin/env python3
"""World-building CLI: register image/video/game assets into Titanos hubs.

  python scripts/world_build.py register \\
    --world demo --id hero_idle --kind image \\
    --path assets/demo/hero_idle.png --title "Hero idle"

  python scripts/world_build.py register \\
    --world demo --id combat_codex --kind game_codex \\
    --codex-ref combat_v1 --path assets/demo/combat.json

  python scripts/world_build.py ask world:demo:asset:hero_idle kind
  python scripts/world_build.py list --index artifacts/world_assets.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from resileos.answer.hub_train import open_hub_workbench  # noqa: E402
from resileos.answer.world_assets import (  # noqa: E402
    AssetIndex,
    WorldAsset,
    register_asset,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="World-building asset registry")
    ap.add_argument("cmd", choices=["register", "ask", "list"])
    ap.add_argument("--world", default="demo")
    ap.add_argument("--id", default="")
    ap.add_argument("--kind", default="image",
                    choices=["image", "video", "audio", "game_codex", "scene", "prop", "other"])
    ap.add_argument("--path", default="")
    ap.add_argument("--url", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--parent-scene", default="")
    ap.add_argument("--codex-ref", default="")
    ap.add_argument("--status", default="draft")
    ap.add_argument("--state", default="artifacts/world_hub_state.json")
    ap.add_argument("--index", default="artifacts/world_assets.json")
    ap.add_argument("ask_args", nargs="*")
    args = ap.parse_args()

    state = Path(args.state)
    index = AssetIndex.load(Path(args.index))
    wb = open_hub_workbench(backend="structured", state_path=state if state.exists() else None, seed=False)

    if args.cmd == "register":
        if not args.id:
            print("--id required", file=sys.stderr)
            return 2
        asset = WorldAsset(
            world_id=args.world,
            asset_id=args.id,
            kind=args.kind,  # type: ignore[arg-type]
            title=args.title,
            path=args.path,
            url=args.url,
            tags=args.tags,
            parent_scene=args.parent_scene,
            codex_ref=args.codex_ref,
            status=args.status,
        )
        n = register_asset(wb, asset, index=index)
        if hasattr(wb.titan, "save"):
            state.parent.mkdir(parents=True, exist_ok=True)
            wb.titan.save(str(state))
        print(json.dumps({"registered": n, "subject": asset.subject(), "index": str(index.path)}))
        return 0

    if args.cmd == "list":
        print(json.dumps({"assets": index.assets}, indent=2))
        return 0

    if args.cmd == "ask":
        if len(args.ask_args) < 2:
            print("usage: ask <subject> <relation>", file=sys.stderr)
            return 2
        sub, rel = args.ask_args[0], args.ask_args[1]
        result = wb.answer(sub, rel)
        print(json.dumps({
            "subject": sub,
            "relation": rel,
            "rows": list(result.rows),
            "answer_text": result.answer_text,
            "empty": result.empty,
        }, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
