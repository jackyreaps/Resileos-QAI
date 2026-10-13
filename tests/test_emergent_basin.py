"""
Tests for emergent basin reorganization in Titanos.

Without the non-conservative operator in the loop, the basin is static:
anisotropy stays at 1.0, thresholds do not move, and keeping quality up
requires external tuning. With it, the geometry reorganizes from
monitors computed during retrieval.

These tests check the observable consequences, not the internal theory.
The scaling sigma_eff = sigma_base / sqrt(anisotropy) is a proposal
(RES-200 §extension); the tests verify the mechanism produces the
expected direction, not a specific magnitude.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from titanos import Titanos, TitanosConfig, Answer


FACTS = [
    ("Uranus", "parent_of", "Cronus"), ("Cronus", "parent_of", "Zeus"),
    ("Cronus", "parent_of", "Poseidon"), ("Cronus", "parent_of", "Hades"),
    ("Zeus", "parent_of", "Ares"), ("Zeus", "parent_of", "Athena"),
    ("Zeus", "domain", "sky"), ("Poseidon", "domain", "sea"),
    ("Hades", "domain", "underworld"), ("Ares", "domain", "war"),
    ("Athena", "domain", "wisdom"), ("Uranus", "is_a", "primordial"),
    ("Cronus", "is_a", "titan"), ("Zeus", "is_a", "olympian"),
    ("Poseidon", "is_a", "olympian"), ("Hades", "is_a", "olympian"),
    ("Ares", "is_a", "olympian"), ("Athena", "is_a", "olympian"),
]

DRIVE = [
    ("Zeus", "parent_of"), ("Cronus", "parent_of"),
    ("Zeus", "domain"), ("Poseidon", "domain"),
    ("Hades", "domain"), ("Zeus", "is_a"),
    ("Cronus", "is_a"), ("Athena", "is_a"),
]


def _build(emergent: bool) -> Titanos:
    cfg = TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=4, seed=42,
        emergent=emergent,
        classical_conf=None, abstention_gate=None,
    )
    t = Titanos(cfg)
    for s, r, o in FACTS:
        t.learn(s, r, o)
    return t


def _drive(t: Titanos, cycles: int = 5) -> None:
    for _ in range(cycles):
        for subj, rel in DRIVE:
            t.ask(subj, rel)


# ── anisotropy and basin evolution ──────────────────────────────────────
def test_conservative_anisotropy_stays_one():
    t = _build(emergent=False)
    _drive(t, cycles=3)
    assert np.isclose(t._current_anisotropy(), 1.0, atol=1e-9)


def test_emergent_anisotropy_grows():
    t = _build(emergent=True)
    a0 = t._current_anisotropy()
    _drive(t, cycles=5)
    a1 = t._current_anisotropy()
    assert a1 > a0 + 1e-3, f"anisotropy did not grow: {a0} -> {a1}"


def test_emergent_sigma_eff_shrinks():
    """sigma_eff = sigma_base / sqrt(anisotropy). Growth of anisotropy
    should shrink the effective noise floor."""
    t = _build(emergent=True)
    rel = "domain"
    s0 = t._noise_sigma_effective(rel)
    _drive(t, cycles=5)
    s1 = t._noise_sigma_effective(rel)
    assert s1 < s0, f"sigma_eff did not fall: {s0} -> {s1}"


# ── noise-aware thresholds ──────────────────────────────────────────────
def test_thresholds_track_effective_sigma():
    """With no explicit overrides, thresholds must be alpha * sigma_eff."""
    t = _build(emergent=True)
    _drive(t, cycles=2)
    classical, abstain, sigma_eff = t._thresholds_for("domain")
    assert np.isclose(classical, t.cfg.conf_alpha_classical * sigma_eff,
                      rtol=1e-9)
    assert np.isclose(abstain, t.cfg.conf_alpha_abstain * sigma_eff,
                      rtol=1e-9)


def test_thresholds_shift_after_drive():
    """Derived thresholds move on their own; no external tuning."""
    t = _build(emergent=True)
    before = t._thresholds_for("domain")
    _drive(t, cycles=8)
    after = t._thresholds_for("domain")
    assert abs(after[0] - before[0]) > 1e-4, (
        f"threshold did not move: {before[0]} -> {after[0]}")


def test_conservative_thresholds_do_not_shift():
    """Without emergent mode, thresholds are pinned to sigma_base."""
    t = _build(emergent=False)
    before = t._thresholds_for("domain")
    _drive(t, cycles=8)
    after = t._thresholds_for("domain")
    assert np.isclose(before[0], after[0], rtol=1e-12)


def test_explicit_overrides_ignore_sigma_eff():
    """When classical_conf is set explicitly, sigma_eff is computed but
    does not affect the threshold."""
    cfg = TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=4, seed=42,
        emergent=True,
        classical_conf=0.09, abstention_gate=0.035,
    )
    t = Titanos(cfg)
    for s, r, o in FACTS:
        t.learn(s, r, o)
    _drive(t, cycles=5)
    classical, abstain, _ = t._thresholds_for("domain")
    assert np.isclose(classical, 0.09, rtol=1e-12)
    assert np.isclose(abstain, 0.035, rtol=1e-12)


# ── CSI tracking ────────────────────────────────────────────────────────
def test_csi_tracked_after_queries():
    t = _build(emergent=True)
    samples_before = t._csi.samples()
    _drive(t, cycles=2)
    samples_after = t._csi.samples()
    assert samples_after > samples_before


def test_csi_in_answer():
    t = _build(emergent=True)
    a = t.ask("Zeus", "domain")
    assert 0.0 <= a.csi <= 1.0


# ── agency integration ──────────────────────────────────────────────────
def test_no_children_dispatch_equals_ask():
    t = _build(emergent=True)
    a1 = t.ask("Zeus", "domain")
    a2 = t.dispatch("Zeus", "domain")
    assert a1.value == a2.value
    assert a1.status == a2.status
    assert a2.child_name is None


def test_register_child_and_dispatch():
    t = _build(emergent=True)

    def child_handler(titan, subject, relation, inverse):
        return titan._ask(subject, relation, inverse=inverse,
                          conf_mode_override="mag")

    t.register_child("mag_child", child_handler, weight=1.0)
    ans = t.dispatch("Zeus", "domain")
    assert ans.value == "sky"
    assert ans.child_name == "mag_child"


def test_dispatch_child_declines_falls_through():
    t = _build(emergent=True)

    def declining(titan, subject, relation, inverse):
        return None

    t.register_child("nope", declining)
    ans = t.dispatch("Zeus", "domain")
    assert ans.value == "sky"
    assert ans.child_name == "nope"


def test_agency_weights_update_after_dispatch():
    t = _build(emergent=True)

    def mag_reader(titan, subject, relation, inverse):
        return titan._ask(subject, relation, inverse=inverse,
                          conf_mode_override="mag")

    def sim_reader(titan, subject, relation, inverse):
        return titan._ask(subject, relation, inverse=inverse,
                          conf_mode_override="sim")

    t.register_child("mag", mag_reader, weight=0.5)
    t.register_child("sim", sim_reader, weight=0.5)

    for _ in range(5):
        for subj, rel in DRIVE:
            t.dispatch(subj, rel)
            t.prune()

    snap = t.agency.snapshot()
    # The weaker child should have lost ground, either by weight or by
    # being eaten. Either outcome is acceptable.
    assert (
        snap["children"]["sim"]["weight"] < snap["children"]["mag"]["weight"]
        or "sim" in snap["eaten"]
    )


def test_stats_includes_agency_snapshot():
    t = _build(emergent=True)
    t.register_child("x", lambda *args: None)
    stats = t.stats()
    assert "agency" in stats
    assert "x" in stats["agency"]["children"]


# ── correctness under evolution ─────────────────────────────────────────
def test_retrieval_still_works_after_evolution():
    t = _build(emergent=True)
    _drive(t, cycles=3)
    # Single-hop queries should still resolve.
    assert t.ask("Zeus", "domain").value == "sky"
    assert t.ask("Poseidon", "domain").value == "sea"
    assert t.ask("Cronus", "is_a").value == "titan"


def test_backward_compat_single_accumulator_save():
    """Legacy save format with 'acc' should load cleanly."""
    cfg = TitanosConfig(dim=2500, m=50, n=50, r=4, n_loops=4, seed=42,
                        emergent=False)
    t = Titanos(cfg)
    for s, r, o in FACTS:
        t.learn(s, r, o)
    # Simulate legacy save: strip bands, put merged acc under "_legacy"
    legacy_state = {
        "cfg": {**t.cfg.__dict__, "seed_list": list(t.cfg.seed_list)},
        "acc": t._merged_acc().tolist(),
        "entities": {k: v.tolist() for k, v in t.entities.items()},
        "relations": {k: v.tolist() for k, v in t.relations.items()},
        "roles": {k: v.tolist() for k, v in t.roles.items()},
        "facts": [list(x) for x in t.facts],
        "perm": t._perm.tolist(),
    }
    import json
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "legacy.json"
        p.write_text(json.dumps(legacy_state))
        t2 = Titanos.load(p)
        assert "_legacy" in t2._bands
        assert len(t2.facts) == len(t.facts)


# ── save/load persistence ───────────────────────────────────────────────
def test_emergent_state_persists_across_save_load(tmp_path):
    t = _build(emergent=True)
    _drive(t, cycles=3)
    a_before = t._current_anisotropy()
    p = tmp_path / "titanos_state.json"
    t.save(p)
    t2 = Titanos.load(p)
    a_after = t2._current_anisotropy()
    assert np.isclose(a_before, a_after, rtol=1e-6)


def test_csi_state_persists(tmp_path):
    t = _build(emergent=True)
    _drive(t, cycles=2)
    csi_before = t._csi.value()
    samples_before = t._csi.samples()
    p = tmp_path / "titanos_state.json"
    t.save(p)
    t2 = Titanos.load(p)
    assert t2._csi.samples() == samples_before
    assert np.isclose(t2._csi.value(), csi_before, rel_tol=1e-9)
