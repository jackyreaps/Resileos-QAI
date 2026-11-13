"""Scene legions: geometry, light, and camera stubs under Hermes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from resileos.core import ResidualCore
from resileos.kin.hades import Hades
from resileos.kin.legions import kin_catalogue
from resileos.kin.scene_legions import core_residual_view, register_scene_legions, run_scene_workflow


SENTINEL = "UNIQUE_SCENE_SENTINEL the labyrinth is lit from the left"


def test_core_view_is_only_a_hash():
    with pytest.raises(ValueError):
        core_residual_view(SENTINEL)
    view = core_residual_view("a" * 64)
    assert view == {"packet_hash": "a" * 64}
    assert SENTINEL not in json.dumps(view)


def test_scene_steps_hash_artifacts_and_restore_without_the_script(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("scene legion called ResidualCore")

    monkeypatch.setattr(ResidualCore, "step", boom)
    monkeypatch.setattr(ResidualCore, "_scar_update", boom)
    store = tmp_path / "hades"
    artifacts = tmp_path / "scene"
    monkeypatch.setenv("RESILEOS_HADES_DIR", str(store))
    monkeypatch.setenv("RESILEOS_SCENE_DIR", str(artifacts))

    register_scene_legions()
    names = {row["name"] for row in kin_catalogue("hermes")}
    assert {"daedalus", "helios", "argus"} <= names

    result = run_scene_workflow(SENTINEL, store_dir=str(store), artifact_dir=str(artifacts))
    assert result["executor"] == "stub"
    assert result["url"] is None
    assert result["produces_video"] is False
    assert [step["legion"] for step in result["steps"]] == ["daedalus", "helios", "argus"]
    dumped = json.dumps(result)
    assert SENTINEL not in dumped
    hashes = [step["scene_script_hash"] for step in result["steps"]]
    assert len(set(hashes)) == 3
    for step in result["steps"]:
        assert step["stub"] is True
        assert step["core_view"] == {"packet_hash": step["scene_script_hash"]}
        assert step["checkpoint_id"]
        text = (artifacts / f"{step['legion']}.txt").read_text(encoding="utf-8")
        assert "Stub. No Blender executor is configured." in text
        assert SENTINEL in text

    hades = Hades(store)
    for step in result["steps"]:
        ckpt = hades.load(step["checkpoint_id"])
        assert ckpt is not None
        blob = json.dumps(ckpt.to_dict())
        assert SENTINEL not in blob
        assert step["scene_script_hash"] in blob
        fresh = hades.restore_fresh(step["checkpoint_id"])
        assert fresh.verified is False
        assert fresh.scars == []
        fresh_blob = json.dumps(
            {
                "history": fresh.history,
                "evidence": fresh.evidence,
                "scars": fresh.scars,
            }
        )
        assert SENTINEL not in fresh_blob
        assert any(isinstance(item, dict) and item.get("lesson") for item in fresh.history)
    assert len(list(Path(store).glob("*.json"))) == 3
