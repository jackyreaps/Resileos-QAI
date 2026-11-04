from pathlib import Path

from resileos.answer.hub_train import open_hub_workbench
from resileos.answer.world_assets import AssetIndex, WorldAsset, register_asset


def test_register_image_and_game_codex(tmp_path: Path):
    wb = open_hub_workbench(seed=False)
    index = AssetIndex.load(tmp_path / "idx.json")
    img = WorldAsset(
        world_id="demo",
        asset_id="hero_idle",
        kind="image",
        path="assets/demo/hero_idle.png",
        title="Hero idle",
        status="ready",
    )
    codex = WorldAsset(
        world_id="demo",
        asset_id="combat",
        kind="game_codex",
        path="assets/demo/combat.json",
        codex_ref="combat_v1",
        status="draft",
    )
    assert register_asset(wb, img, index=index) >= 1
    assert register_asset(wb, codex, index=index) >= 1
    assert "image" in wb.ask_rows("world:demo:asset:hero_idle", "kind")
    assert "combat_v1" in wb.ask_rows("world:demo:asset:combat", "codex_ref")
    assert img.subject() in index.assets
