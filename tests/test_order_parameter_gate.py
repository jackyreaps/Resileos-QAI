"""
Tests for the order parameter gate (RES-309).

Unit tests verify the mechanism. Integration tests measure whether the
gate changes the abstention/accuracy tradeoff on the Greek corpus.
The integration tests report the effect rather than asserting it
improves — a null result is a valid outcome.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from titanos import Titanos, TitanosConfig


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

KNOWN = [
    ("Zeus", "domain"), ("Poseidon", "domain"), ("Hades", "domain"),
    ("Cronus", "is_a"), ("Zeus", "is_a"),
    ("Cronus", "parent_of"), ("Zeus", "parent_of"),
]

UNKNOWN = [
    ("Zeus", "capital_of"),
    ("Cronus", "domain"),
    ("Athena", "parent_of"),
]


def _build(use_gate: bool, seed: int = 42) -> Titanos:
    cfg = TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=4, seed=seed,
        emergent=True,
        use_order_parameter_gate=use_gate,
        classical_conf=None, abstention_gate=None,
    )
    t = Titanos(cfg)
    for s, r, o in FACTS:
        t.learn(s, r, o)
    return t


def _drive(t: Titanos, cycles: int = 3) -> None:
    for _ in range(cycles):
        for subj, rel in KNOWN:
            t.ask(subj, rel)


# ── unit tests ──────────────────────────────────────────────────────────
def test_order_parameter_at_init_is_one():
    t = _build(use_gate=True)
    assert np.isclose(t._order_parameter(), 1.0, atol=1e-9)


def test_order_parameter_bounded():
    t = _build(use_gate=True)
    _drive(t, cycles=5)
    R = t._order_parameter()
    assert 0.0 <= R <= 1.0


def test_order_parameter_scale_endpoints():
    t = _build(use_gate=True)
    # R = 1 → scale 1
    assert np.isclose(t._order_parameter_scale(1.0), 1.0)
    # R = 0 → scale = floor
    assert np.isclose(t._order_parameter_scale(0.0),
                      t.cfg.order_parameter_floor)


def test_order_parameter_scale_monotone():
    t = _build(use_gate=True)
    s_lo = t._order_parameter_scale(0.2)
    s_hi = t._order_parameter_scale(0.9)
    assert s_hi > s_lo


def test_gate_off_by_default():
    cfg = TitanosConfig()
    assert cfg.use_order_parameter_gate is False


def test_invalid_floor_raises():
    with pytest.raises(ValueError, match="order_parameter_floor"):
        TitanosConfig(order_parameter_floor=1.5)


# ── integration: gate changes confidence ────────────────────────────────
def test_gate_reduces_confidence_when_applied():
    """When the gate is on and R < 1, confidence should be <= raw."""
    t = _build(use_gate=True)
    _drive(t, cycles=5)
    a = t.ask("Zeus", "domain")
    if a.status == "ACCEPTED":
        assert a.confidence <= a.raw_confidence + 1e-12
        assert a.order_parameter_scale <= 1.0 + 1e-12


def test_gate_off_leaves_confidence_unchanged():
    """With the gate off, raw == gated."""
    t = _build(use_gate=False)
    _drive(t, cycles=5)
    a = t.ask("Zeus", "domain")
    assert np.isclose(a.confidence, a.raw_confidence, atol=1e-12)
    assert np.isclose(a.order_parameter_scale, 1.0, atol=1e-12)


def test_gate_reported_in_stats():
    t = _build(use_gate=True)
    _drive(t, cycles=2)
    stats = t.stats()
    assert "order_parameter" in stats
    assert "use_order_parameter_gate" in stats
    assert stats["use_order_parameter_gate"] is True


# ── effect measurement (report, not assert) ─────────────────────────────
def test_report_gate_effect():
    """
    Measure the effect of the gate on known/unknown separation.
    Prints a table. Does not assert improvement; the assertion is only
    that the gate does *something* when R moves.
    """
    t_off = _build(use_gate=False, seed=42)
    t_on = _build(use_gate=True, seed=42)
    _drive(t_off, cycles=5)
    _drive(t_on, cycles=5)

    def collect(t):
        known_conf, unknown_conf = [], []
        known_acc = 0
        known_tot = 0
        unknown_abstain = 0
        unknown_tot = 0
        for subj, rel in KNOWN:
            a = t.ask(subj, rel)
            known_conf.append(a.confidence)
            known_tot += 1
            if a.status == "ACCEPTED":
                known_acc += 1
        for subj, rel in UNKNOWN:
            a = t.ask(subj, rel)
            unknown_conf.append(a.confidence)
            unknown_tot += 1
            if a.status == "ABSTAINED":
                unknown_abstain += 1
        return {
            "known_mean_conf": float(np.mean(known_conf)),
            "unknown_mean_conf": float(np.mean(unknown_conf)),
            "known_accept_rate": known_acc / known_tot,
            "unknown_abstain_rate": unknown_abstain / unknown_tot,
            "R": t._order_parameter(),
        }

    off = collect(t_off)
    on = collect(t_on)

    print("\n=== Order parameter gate effect ===")
    print(f"                    off        on         delta")
    print(f"known mean conf   {off['known_mean_conf']:.4f}   "
          f"{on['known_mean_conf']:.4f}   "
          f"{on['known_mean_conf'] - off['known_mean_conf']:+.4f}")
    print(f"unknown mean conf {off['unknown_mean_conf']:.4f}   "
          f"{on['unknown_mean_conf']:.4f}   "
          f"{on['unknown_mean_conf'] - off['unknown_mean_conf']:+.4f}")
    print(f"known accept rate {off['known_accept_rate']:.3f}    "
          f"{on['known_accept_rate']:.3f}    "
          f"{on['known_accept_rate'] - off['known_accept_rate']:+.3f}")
    print(f"unknown abstain   {off['unknown_abstain_rate']:.3f}    "
          f"{on['unknown_abstain_rate']:.3f}    "
          f"{on['unknown_abstain_rate'] - off['unknown_abstain_rate']:+.3f}")
    print(f"R at end          {off['R']:.4f}   {on['R']:.4f}")

    # The only assertion: the gate must not silently no-op.
    # If R < 1 and the gate is on, at least one confidence must differ.
    if on["R"] < 0.999:
        assert (abs(on["known_mean_conf"] - off["known_mean_conf"]) > 1e-6
                or abs(on["unknown_mean_conf"] - off["unknown_mean_conf"]) > 1e-6), \
            "gate reported active but no confidence changed"
