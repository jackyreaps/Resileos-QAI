"""Hades checkpointing: file-backed save, fresh restore, bundle integration."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.harness.packet import ControlPacket
from resileos.kin.hades import Checkpoint, Hades, make_hades


@pytest.fixture
def hades(tmp_path):
    """File-backed Hades in a temp dir so tests don't pollute data/."""
    return Hades(store_dir=tmp_path / "hades")


def _verified_packet(**overrides):
    pkt = ControlPacket(id="test-1")
    pkt.guides_loaded = [
        "docs/harness/CONSTRAINTS.md",
        "docs/harness/AGENTS.md",
    ]
    pkt.confidence = 0.93
    pkt.evidence = [
        {"source": "probe", "result": {"matched": 5, "passed": 5}},
    ]
    pkt.verified = True
    pkt.turn = 4
    pkt.history = [{"event": "step", "n": i} for i in range(4)]
    for k, v in overrides.items():
        setattr(pkt, k, v)
    return pkt


# ══════════════════════════════════════════════════════════════════════
# Save
# ══════════════════════════════════════════════════════════════════════


def test_save_creates_file(hades, tmp_path):
    pkt = _verified_packet()
    ckpt = hades.save(pkt)
    assert isinstance(ckpt, Checkpoint)
    assert ckpt.verified is True
    assert ckpt.turn == 4
    # File written
    files = list((tmp_path / "hades").glob("*.json"))
    assert len(files) == 1
    assert files[0].stem == ckpt.id


def test_save_returns_string_lesson(hades):
    ckpt = hades.save(_verified_packet())
    assert isinstance(ckpt.lesson, str)
    assert "turn 4" in ckpt.lesson
    assert "verified=True" in ckpt.lesson


def test_save_accepts_custom_lesson(hades):
    ckpt = hades.save(_verified_packet(), lesson="custom one-liner")
    assert ckpt.lesson == "custom one-liner"


def test_save_accepts_residual_hash(hades):
    ckpt = hades.save(_verified_packet(), residual_packet_hash="abc123")
    assert ckpt.residual_packet_hash == "abc123"


def test_save_unverified_does_not_raise(hades):
    """Hades.save does not gate on verified — the caller does.

    Documented explicitly so a future change that adds a raise must
    update this test and bundle.py in the same commit.
    """
    pkt = ControlPacket(id="test-2")
    pkt.verified = False
    ckpt = hades.save(pkt)
    assert ckpt.verified is False


def test_save_bounds_evidence_gist(hades):
    """evidence_gist keeps only last 5 entries in to_dict()."""
    pkt = _verified_packet()
    pkt.evidence = [
        {"source": "probe", "result": {"i": i}} for i in range(10)
    ]
    ckpt = hades.save(pkt)
    d = ckpt.to_dict()
    assert len(d["evidence_gist"]) == 5
    # The most recent 5 (indices 5..9)
    assert d["evidence_gist"][0]["result"]["i"] == 5
    assert d["evidence_gist"][-1]["result"]["i"] == 9


# ══════════════════════════════════════════════════════════════════════
# Load and roundtrip
# ══════════════════════════════════════════════════════════════════════


def test_load_from_cache(hades):
    ckpt = hades.save(_verified_packet())
    loaded = hades.load(ckpt.id)
    assert loaded is not None
    assert loaded.id == ckpt.id


def test_load_from_disk_after_clear(hades):
    ckpt = hades.save(_verified_packet())
    # Clear cache, force disk read
    hades._cache.clear()
    loaded = hades.load(ckpt.id)
    assert loaded is not None
    assert loaded.id == ckpt.id
    assert loaded.lesson == ckpt.lesson


def test_load_missing_returns_none(hades):
    assert hades.load("nonexistent") is None


def test_latest_returns_most_recent(hades):
    ckpt1 = hades.save(_verified_packet(id="test-1"))
    ckpt2 = hades.save(_verified_packet(id="test-2"))
    latest = hades.latest()
    assert latest is not None
    assert latest.id in (ckpt1.id, ckpt2.id)


def test_latest_empty_returns_none(hades):
    assert hades.latest() is None


# ══════════════════════════════════════════════════════════════════════
# Restore
# ══════════════════════════════════════════════════════════════════════


def test_restore_fresh_drops_history(hades):
    pkt = _verified_packet()
    ckpt = hades.save(pkt)
    fresh = hades.restore_fresh(ckpt.id)

    # New id
    assert fresh.id == f"from-{ckpt.id}"

    # Guides and budget survived
    assert fresh.guides_loaded == pkt.guides_loaded
    assert fresh.confidence == pkt.confidence

    # History reset to just the restore event
    assert len(fresh.history) == 1
    assert fresh.history[0]["event"] == "restored_from_checkpoint"
    assert fresh.history[0]["from"] == ckpt.id

    # No scars, no evidence carry-over
    assert fresh.scars == []
    assert fresh.evidence == []

    # Not verified until re-verified
    assert fresh.verified is False


def test_restore_fresh_missing_returns_empty(hades):
    """Missing checkpoint does not raise; returns a fresh empty packet."""
    fresh = hades.restore_fresh("nonexistent", new_id="custom-id")
    assert fresh.id == "custom-id"
    assert len(fresh.history) == 0


def test_restore_fresh_custom_new_id(hades):
    ckpt = hades.save(_verified_packet())
    fresh = hades.restore_fresh(ckpt.id, new_id="my-restart")
    assert fresh.id == "my-restart"


# ══════════════════════════════════════════════════════════════════════
# make_hades factory
# ══════════════════════════════════════════════════════════════════════


def test_make_hades_creates_dir(tmp_path):
    store = tmp_path / "custom-hades"
    h = make_hades(store_dir=store)
    assert store.exists()
    assert isinstance(h, Hades)


# ══════════════════════════════════════════════════════════════════════
# Bundle integration
# ══════════════════════════════════════════════════════════════════════


def test_bundle_cycle_checkpoints_on_verified(monkeypatch, tmp_path):
    """Verified cycle produces checkpoint; unverified does not."""
    from resileos.kin import bundle as bundle_module

    # Redirect make_hades to a temp dir so no files land in data/
    real_make = bundle_module.make_hades
    def patched_make(*args, **kwargs):
        return real_make(store_dir=tmp_path / "hades")
    monkeypatch.setattr(bundle_module, "make_hades", patched_make)

    b = bundle_module.build_kin_bundle()

    # 1. First cycle: no evidence -> unverified -> no checkpoint
    _, _, h1 = b.cycle(metrics={"hits": 5})
    assert h1["verified"] is False
    assert "checkpoint" not in h1

    # 2. Attach evidence, run again -> verified -> checkpoint
    b.control.evidence = [
        {"source": "probe", "result": {"matched": 5, "passed": 5}}
    ]
    _, _, h2 = b.cycle(metrics={"hits": 5})
    assert h2["verified"] is True
    assert "checkpoint" in h2
    assert "lesson" in h2
    assert isinstance(h2["lesson"], str)


def test_bundle_reuses_hades_instance(monkeypatch, tmp_path):
    from resileos.kin import bundle as bundle_module

    real_make = bundle_module.make_hades
    def patched_make(*args, **kwargs):
        return real_make(store_dir=tmp_path / "hades")
    monkeypatch.setattr(bundle_module, "make_hades", patched_make)

    b = bundle_module.build_kin_bundle()
    b.control.evidence = [
        {"source": "probe", "result": {"matched": 1, "passed": 1}}
    ]
    _, _, _ = b.cycle(metrics={"hits": 1})
    first = b._hades
    assert first is not None

    # Second verified cycle reuses the same instance
    b.control.evidence = [
        {"source": "probe", "result": {"matched": 1, "passed": 1}}
    ]
    _, _, _ = b.cycle(metrics={"hits": 1})
    assert b._hades is first
    # At least one file exists in the temp dir
    files = list((tmp_path / "hades").glob("*.json"))
    assert len(files) >= 1


def test_bundle_checkpoint_failure_does_not_break_cycle(monkeypatch):
    """If Hades creation fails (e.g. read-only fs), cycle still returns."""
    from resileos.kin import bundle as bundle_module

    def broken_make(*args, **kwargs):
        raise OSError("simulated read-only filesystem")
    monkeypatch.setattr(bundle_module, "make_hades", broken_make)

    b = bundle_module.build_kin_bundle()
    b.control.evidence = [
        {"source": "probe", "result": {"matched": 1, "passed": 1}}
    ]
    _, _, h = b.cycle(metrics={"hits": 1})
    # Cycle still completes
    assert h["verified"] is True
    assert "checkpoint_error" in h
    assert "read-only" in h["checkpoint_error"]
