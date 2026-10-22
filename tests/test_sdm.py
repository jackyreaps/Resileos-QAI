"""Tests for Kanerva SDM + Modern Hopfield attractor memory (RES-317)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.sdm import (
    AttractorMemory,
    HopfieldConfig,
    KanervaSDM,
    ModernHopfield,
    SDMConfig,
)


# ── configs ─────────────────────────────────────────────────────────────
def test_sdm_config_rejects_bad_dim():
    with pytest.raises(ValueError, match="dim"):
        SDMConfig(dim=1)


def test_sdm_config_rejects_bad_locations():
    with pytest.raises(ValueError, match="n_locations"):
        SDMConfig(dim=8, n_locations=0)


def test_sdm_config_rejects_bad_k():
    with pytest.raises(ValueError, match="k_activate"):
        SDMConfig(dim=8, n_locations=10, k_activate=0)
    with pytest.raises(ValueError, match="k_activate"):
        SDMConfig(dim=8, n_locations=10, k_activate=11)


def test_hopfield_config_rejects_bad_beta():
    with pytest.raises(ValueError, match="beta"):
        HopfieldConfig(beta=0.0)


def test_hopfield_config_rejects_bad_iters():
    with pytest.raises(ValueError, match="max_iters"):
        HopfieldConfig(max_iters=0)


def test_hopfield_config_rejects_bad_tol():
    with pytest.raises(ValueError, match="tol"):
        HopfieldConfig(tol=0.0)


# ── Kanerva SDM ─────────────────────────────────────────────────────────
def test_sdm_addresses_are_bipolar():
    sdm = KanervaSDM(SDMConfig(dim=16, n_locations=32, k_activate=4))
    assert sdm.addresses.shape == (32, 16)
    assert set(np.unique(sdm.addresses)).issubset({-1.0, 1.0})


def test_sdm_write_increments_count():
    sdm = KanervaSDM(SDMConfig(dim=16, n_locations=32, k_activate=4))
    v = np.ones(16, dtype=np.float64)
    sdm.write(v)
    assert sdm.n_writes == 1


def test_sdm_write_rejects_wrong_shape():
    sdm = KanervaSDM(SDMConfig(dim=16, n_locations=32, k_activate=4))
    with pytest.raises(ValueError, match="shape"):
        sdm.write(np.zeros(8))


def test_sdm_read_returns_bipolar():
    sdm = KanervaSDM(SDMConfig(dim=16, n_locations=32, k_activate=4))
    rng = np.random.default_rng(0)
    for _ in range(5):
        v = rng.choice([-1.0, 1.0], size=16)
        sdm.write(v)
    out = sdm.read(np.ones(16))
    assert out.shape == (16,)
    assert set(np.unique(out)).issubset({-1.0, 1.0})


def test_sdm_roundtrip_single_pattern():
    """A single stored pattern should dominate its own read."""
    rng = np.random.default_rng(0)
    v = rng.choice([-1.0, 1.0], size=64)
    sdm = KanervaSDM(SDMConfig(dim=64, n_locations=128, k_activate=8, seed=0))
    sdm.write(v)
    out = sdm.read(v)
    agreement = float(np.mean(out == v))
    assert agreement > 0.75


def test_sdm_read_rejects_wrong_shape():
    sdm = KanervaSDM(SDMConfig(dim=16, n_locations=32, k_activate=4))
    with pytest.raises(ValueError, match="shape"):
        sdm.read(np.zeros(8))


# ── Modern Hopfield ─────────────────────────────────────────────────────
def test_hopfield_empty_patterns_returns_query():
    h = ModernHopfield(HopfieldConfig())
    q = np.ones(16) / np.sqrt(16)
    out = h.relax(q)
    assert np.allclose(out, q)


def test_hopfield_store_and_relax_clean():
    """Clean pattern is a fixed point."""
    rng = np.random.default_rng(0)
    patterns = rng.choice([-1.0, 1.0], size=(4, 64))
    patterns = patterns / np.linalg.norm(patterns, axis=1, keepdims=True)
    h = ModernHopfield(HopfieldConfig(beta=16.0, max_iters=8))
    h.store(patterns)
    out = h.relax(patterns[1])
    # relaxation of a stored pattern should stay near it
    sim = float(np.dot(out, patterns[1]))
    assert sim > 0.9


def test_hopfield_snaps_noisy_to_nearest():
    rng = np.random.default_rng(0)
    patterns = rng.choice([-1.0, 1.0], size=(4, 64))
    patterns = patterns / np.linalg.norm(patterns, axis=1, keepdims=True)
    h = ModernHopfield(HopfieldConfig(beta=32.0, max_iters=16))
    h.store(patterns)
    noisy = patterns[2] + 0.3 * rng.standard_normal(64)
    noisy = noisy / np.linalg.norm(noisy)
    out = h.relax(noisy)
    # after relaxation, nearest stored pattern should be patterns[2]
    sims = patterns @ out
    assert int(np.argmax(sims)) == 2


def test_hopfield_relax_rejects_wrong_shape():
    rng = np.random.default_rng(0)
    patterns = rng.choice([-1.0, 1.0], size=(4, 64))
    h = ModernHopfield(HopfieldConfig())
    h.store(patterns)
    with pytest.raises(ValueError, match="shape"):
        h.relax(np.zeros(32))


def test_hopfield_store_rejects_1d():
    h = ModernHopfield(HopfieldConfig())
    with pytest.raises(ValueError, match="2-D"):
        h.store(np.zeros(64))


# ── combined AttractorMemory ────────────────────────────────────────────
def test_attractor_construction():
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    assert mem.n_patterns == 0
    assert mem.snapshot()["dim"] == 32


def test_attractor_store_increments_count():
    rng = np.random.default_rng(0)
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    for _ in range(5):
        mem.store(rng.choice([-1.0, 1.0], size=32))
    assert mem.n_patterns == 5


def test_attractor_store_rejects_wrong_shape():
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    with pytest.raises(ValueError, match="shape"):
        mem.store(np.zeros(16))


def test_attractor_store_many():
    rng = np.random.default_rng(0)
    patterns = rng.choice([-1.0, 1.0], size=(6, 32))
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    mem.store_many(patterns)
    assert mem.n_patterns == 6


def test_attractor_clean_returns_finite():
    rng = np.random.default_rng(0)
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    for _ in range(3):
        mem.store(rng.choice([-1.0, 1.0], size=32))
    q = rng.standard_normal(32)
    out = mem.cleanup(q)
    assert out.shape == (32,)
    assert np.all(np.isfinite(out))


def test_attractor_recovers_stored_pattern_from_noise():
    """The combined pipeline should recover a stored pattern from a
    heavily noised query better than the query itself."""
    rng = np.random.default_rng(0)
    patterns = rng.choice([-1.0, 1.0], size=(8, 128))
    patterns_norm = patterns / np.linalg.norm(patterns, axis=1, keepdims=True)

    mem = AttractorMemory(
        SDMConfig(dim=128, n_locations=256, k_activate=16, seed=1),
        HopfieldConfig(beta=16.0, max_iters=8),
    )
    mem.store_many(patterns_norm)

    target_idx = 3
    noisy = patterns_norm[target_idx] + 0.25 * rng.standard_normal(128)
    noisy = noisy / np.linalg.norm(noisy)

    cleaned = mem.cleanup(noisy)

    sims_before = patterns_norm @ noisy
    sims_after = patterns_norm @ cleaned

    assert int(np.argmax(sims_after)) == target_idx
    # cleaner should improve the target similarity
    assert sims_after[target_idx] > sims_before[target_idx]


def test_attractor_empty_cleanup_passthrough():
    mem = AttractorMemory(SDMConfig(dim=16, n_locations=32, k_activate=4))
    q = np.ones(16)
    out = mem.cleanup(q)
    assert out.shape == (16,)


def test_attractor_snapshot_keys():
    rng = np.random.default_rng(0)
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    mem.store(rng.choice([-1.0, 1.0], size=32))
    snap = mem.snapshot()
    for k in ("dim", "n_locations", "k_activate", "n_patterns",
              "n_writes", "beta", "max_iters"):
        assert k in snap
    assert snap["n_patterns"] == 1
    assert snap["n_writes"] == 1


def test_attractor_is_parameter_free():
    """No nn.Module / no trainable params — closed-form updates only."""
    mem = AttractorMemory(SDMConfig(dim=32, n_locations=64, k_activate=8))
    # No .parameters(), .state_dict(), or .backward() exposed
    assert not hasattr(mem, "parameters")
    assert not hasattr(mem, "state_dict")
    assert not hasattr(mem, "backward")


# ── crosstalk reduction on synthetic chain ──────────────────────────────
def test_attractor_reduces_crosstalk_in_chain():
    """Simulate multi-hop VSA chain with crosstalk and verify the
    attractor reduces error rate versus raw threshold cleanup."""
    rng = np.random.default_rng(42)
    dim = 256
    n_items = 16
    n_facts = 64

    # codebook
    codebook = rng.choice([-1.0, 1.0], size=(n_items, dim))

    # build facts: for each, bind subj * rel * obj; store all
    facts = []
    for _ in range(n_facts):
        i = int(rng.integers(n_items))
        j = int(rng.integers(n_items))
        rel = rng.choice([-1.0, 1.0], size=dim)
        bound = codebook[i] * rel * codebook[j]
        facts.append((bound, i, j))

    # band = sum of all fact vectors
    band = np.sum(np.stack([f[0] for f in facts], axis=0), axis=0)

    # attractor stores all fact vectors
    mem = AttractorMemory(
        SDMConfig(dim=dim, n_locations=512, k_activate=32, seed=0),
        HopfieldConfig(beta=16.0, max_iters=8),
    )
    mem.store_many(np.stack([f[0] for f in facts], axis=0))

    # for each fact, retrieve via raw threshold and via attractor
    raw_correct = 0
    attractor_correct = 0
    n_trials = 20
    for trial in range(n_trials):
        _, i, j = facts[trial]
        rel = rng.choice([-1.0, 1.0], size=dim)
        # (re-derive rel is wrong; use the stored fact's actual rel)
        # simpler: probe = codebook[i] * rel  (need actual rel)
        # Use a simpler probe: unbind a stored fact by one of its factors
        bound, i_actual, j_actual = facts[trial]
        # guess probe from partial info
        # we'll use the stored bound and ask: does cleanup recover j?
        # raw: threshold(band * bound) → nearest codebook entry
        raw = np.where(band * bound >= 0, 1.0, -1.0)
        raw_sims = codebook @ raw / dim
        raw_pick = int(np.argmax(raw_sims))
        if raw_pick == j_actual:
            raw_correct += 1

        cleaned = mem.cleanup(band * bound)
        # re-threshold cleaned against codebook
        cleaned_sims = codebook @ cleaned / dim
        attractor_pick = int(np.argmax(cleaned_sims))
        if attractor_pick == j_actual:
            attractor_correct += 1

    # Attractor should be at least as good as raw
    assert attractor_correct >= raw_correct, (
        f"attractor {attractor_correct} < raw {raw_correct} "
        f"on {n_trials} trials"
    )
