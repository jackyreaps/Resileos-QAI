"""
Tests for emergent basin reorganization in Titanos.
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
    t = _build(emergent=True)
    rel = "domain"
    s0 = t._noise_sigma_effective(rel)
    _drive(t, cycles=5)
    s1 = t._noise_sigma_effective(rel)
    assert s1 < s0, f"sigma_eff did not fall: {s0} -> {s1}"


# ── noise-aware thresholds ──────────────────────────────────────────────
def test_thresholds_track_effective_sigma():
    t = _build(emergent=True)
    _drive(t, cycles=2)
    classical, abstain, sigma_eff = t._thresholds_for("domain")
    assert np.isclose(classical, t.cfg.conf_alpha_classical * sigma_eff,
                      rtol=1e-9)
    assert np.isclose(abstain, t.cfg.conf_alpha_abstain * sigma_eff,
                      rtol=1e-9)


def test_thresholds_shift_after_drive():
    t = _build(emergent=True)
    before = t._thresholds_for("domain")
    _drive(t, cycles=8)
    after = t._thresholds_for("domain")
    assert abs(after[0] - before[0]) > 1e-4, (
        f"threshold did not move: {before[0]} -> {after[0]}")


def test_conservative_thresholds_do_not_shift():
    t = _build(emergent=False)
    before = t._thresholds_for("domain")
    _drive(t, cycles=8)
    after = t._thresholds_for("domain")
    assert np.isclose(before[0], after[0], rtol=1e-12)


def test_explicit_overrides_ignore_sigma_eff():
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


# ── retrieval under evolution ───────────────────────────────────────────
def test_retrieval_still_works_after_evolution():
    t = _build(emergent=True)
    _drive(t, cycles=3)
    assert t.ask("Zeus", "domain").value == "sky"
    assert t.ask("Poseidon", "domain").value == "sea"
    assert t.ask("Cronus", "is_a").value == "titan"


def test_retrieval_fresh_build():
    """Sanity: retrieval is correct on a fresh build (no drive)."""
    t = _build(emergent=True)
    assert t.ask("Zeus", "domain").value == "sky"
    assert t.ask("Poseidon", "domain").value == "sea"


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
                          conf_mode_override="sim")

    t.register_child("sim_child", child_handler, weight=1.0)
    ans = t.dispatch("Zeus", "domain")
    assert ans.value == "sky"
    assert ans.child_name == "sim_child"


def test_dispatch_child_declines_falls_through():
    t = _build(emergent=True)

    def declining(titan, subject, relation, inverse):
        return None

    t.register_child("nope", declining)
    ans = t.dispatch("Zeus", "domain")
    assert ans.value == "sky"
    assert ans.child_name == "nope"


def test_agency_eats_low_contributing_child():
    """
    Direct test of the eat mechanism.

    A child whose handler always abstains accumulates zero
    contribution. With enough queries and the CSI gate relaxed, the
    child is deactivated by prune().

    This replaces an earlier test that relied on mag vs sim children
    diverging on this corpus. After the float64 fix to _score_candidates,
    both modes retrieve correctly on the known corpus, so they do not
    diverge — the mechanism must be tested directly.
    """
    t = _build(emergent=True)
    t.agency.min_queries_before_eat = 3
    t.agency.eat_threshold_contrib = 0.5
    t.agency.eat_threshold_csi = 1.1   # effectively disable CSI gate
    t.agency.min_weight = 0.05
    t.agency.absorption_rate = 0.5

    def always_abstain(titan, subject, relation, inverse):
        return Answer(value=None, confidence=0.0, status="ABSTAINED",
                      mode="ABSTAIN", loops=0, csi=0.9)

    t.register_child("weak", always_abstain, weight=1.0)

    for _ in range(10):
        for subj, rel in DRIVE[:3]:
            t.dispatch(subj, rel)
            t.prune()

    snap = t.agency.snapshot()
    assert snap["children"]["weak"]["active"] is False
    assert "weak" in snap["eaten"]


def test_agency_keeps_high_contributing_child():
    """Mirror of the above: a child that always accepts stays active."""
    t = _build(emergent=True)
    t.agency.min_queries_before_eat = 3
    t.agency.eat_threshold_contrib = 0.5
    t.agency.eat_threshold_csi = 1.1

    def always_accept(titan, subject, relation, inverse):
        return Answer(value="x", confidence=1.0, status="ACCEPTED",
                      mode="CLASSICAL", loops=0, csi=0.9)

    t.register_child("strong", always_accept, weight=1.0)

    for _ in range(10):
        for subj, rel in DRIVE[:3]:
            t.dispatch(subj, rel)
            t.prune()

    snap = t.agency.snapshot()
    assert snap["children"]["strong"]["active"] is True
    assert "strong" not in snap["eaten"]


def test_stats_includes_agency_snapshot():
    t = _build(emergent=True)
    t.register_child("x", lambda *args: None)
    stats = t.stats()
    assert "agency" in stats
    assert "x" in stats["agency"]["children"]


# ── save/load persistence ───────────────────────────────────────────────
def test_backward_compat_single_accumulator_save():
    cfg = TitanosConfig(dim=2500, m=50, n=50, r=4, n_loops=4, seed=42,
                        emergent=False)
    t = Titanos(cfg)
    for s, r, o in FACTS:
        t.learn(s, r, o)
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
    assert np.isclose(t2._csi.value(), csi_before, rtol=1e-9)
