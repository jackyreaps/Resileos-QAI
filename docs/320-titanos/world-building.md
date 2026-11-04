---
doc: RES-329-world
title: World-Building Assets — Image, Video, Game Codex
status: implemented
depends_on: [RES-328-hub-ns, RES-328-workbench]
---

# World-Building Assets

Titanos stores world objects as hub facts. An on-disk asset index stores paths and URLs for renderers and tools.

| Kind | Use |
|------|-----|
| `image` | Still art, sprites, maps |
| `video` | Clips, cutscenes |
| `audio` | SFX, voice |
| `game_codex` | Rules / animation / interaction packs |
| `scene` | Scene graph anchor |
| `prop` | Placeable object |

## Subject form

`world:<world_id>:asset:<asset_id>`

## Relations

`kind`, `path`, `url`, `title`, `tags`, `parent_scene`, `codex_ref`, `status`

## CLI

```bash
python scripts/world_build.py register --world demo --id hero_idle --kind image \
  --path assets/demo/hero_idle.png --title "Hero idle" --status ready

python scripts/world_build.py register --world demo --id combat --kind game_codex \
  --path assets/demo/combat.json --codex-ref combat_v1

python scripts/world_build.py ask world:demo:asset:hero_idle path
python scripts/world_build.py list --index artifacts/world_assets.json
```

## Code

| Path | Role |
|------|------|
| `src/resileos/answer/world_assets.py` | Registry + Titanos learn |
| `scripts/world_build.py` | CLI |
