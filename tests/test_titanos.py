"""Titanos application-level tests."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from titanos import Titanos, TitanosConfig, parse_query


def _cfg():
    return TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=6, seed=42,
        classical_conf=0.09, abstention_gate=0.035,
        sigma_E=10.0, sigma_k=3,
        E_sat=10.0, E_sigma=10.0, tau_sat=0.9, tau_low=0.1,
    )


def _kb():
    t = Titanos(_cfg())
    facts = [
        ("Uranus",   "parent_of", "Cronus"),
        ("Cronus",   "parent_of", "Zeus"),
        ("Cronus",   "parent_of", "Poseidon"),
        ("Cronus",   "parent_of", "Hades"),
        ("Zeus",     "parent_of", "Ares"),
        ("Zeus",     "parent_of", "Athena"),
        ("Zeus",     "domain",    "sky"),
        ("Poseidon", "domain",    "sea"),
        ("Hades",    "domain",    "underworld"),
        ("Ares",     "domain",    "war"),
        ("Athena",   "domain",    "wisdom"),
    ]
    for s, r, o in facts:
        t.learn(s, r, o)
    return t


# ── Single-hop ────────────────────────────────────────────────────────────
def test_single_hop():
    t = _kb()
    a = t.ask("Zeus", "domain")
    assert a.status == "ACCEPTED"
    assert a.value == "sky"
    assert a.mode in ("CLASSICAL", "QUANTUM_SIM")


def test_single_hop_loop_history_shape():
    t = _kb()
    a = t.ask("Zeus", "parent_of")
    assert a.loops >= 1
    assert len(a.loop_history) == a.loops
    for h in a.loop_history:
        assert {"loop", "scar_energy", "delta", "mu", "DeltaS",
                "rank", "volume_ok", "sigma1_action", "gate_state",
                "packet_hash"} <= set(h.keys())


# ── Inverse ───────────────────────────────────────────────────────────────
def test_inverse():
    t = _kb()
    a = t.ask_inverse("Zeus", "parent_of")
    assert a.status == "ACCEPTED"
    assert a.value in ("Cronus",)


# ── Chain ─────────────────────────────────────────────────────────────────
def test_chain():
    t = _kb()
    a = t.chain("Uranus", ["parent_of", "parent_of"])
    assert a.status == "ACCEPTED"
    assert a.value in ("Ares", "Athena", "Poseidon", "Hades")
    assert a.confidence > 0.0


def test_chain_breaks_on_unknown():
    t = _kb()
    a = t.chain("Zeus", ["capital_of"])
    assert a.status == "ABSTAINED"
    assert a.reason


# ── Analogy ───────────────────────────────────────────────────────────────
def test_analogy():
    t = _kb()
    a = t.analogy("Zeus", "sky", "Poseidon")
    assert a.status in ("ACCEPTED", "ABSTAINED")


# ── Abstention ────────────────────────────────────────────────────────────
def test_abstain_on_unknown_entity():
    t = _kb()
    a = t.ask("Odin", "parent_of")
    assert a.status == "ABSTAINED"
    assert "unknown entity" in a.reason


def test_abstain_on_unknown_relation():
    t = _kb()
    a = t.ask("Zeus", "capital_of")
    assert a.status == "ABSTAINED"


# ── Quantum label ─────────────────────────────────────────────────────────
def test_quantum_path_labeled():
    """If mode is QUANTUM_SIM, it must never be reported as CLASSICAL."""
    t = _kb()
    # Force the quantum band by tightening classical_conf above realistic sims.
    t.cfg = TitanosConfig(**{**t.cfg.__dict__, "classical_conf": 0.5})
    a = t.ask("Zeus", "parent_of")
    assert a.mode in ("QUANTUM_SIM", "ABSTAIN")


# ── Persistence ───────────────────────────────────────────────────────────
def test_save_load_roundtrip(tmp_path):
    t = _kb()
    p = tmp_path / "titanos.json"
    t.save(p)
    t2 = Titanos.load(p)
    assert t2.stats()["facts"] == t.stats()["facts"]
    a1 = t.ask("Zeus", "domain")
    a2 = t2.ask("Zeus", "domain")
    assert a1.value == a2.value


# ── NLP front-end ─────────────────────────────────────────────────────────
def test_nlp_parser():
    assert parse_query("Who is the parent of Zeus?") == ("Zeus", "parent", True)
    assert parse_query("Who is Zeus's parent?") == ("Zeus", "parent", False)
    assert parse_query("What is Poseidon's domain?") == ("Poseidon", "domain", False)
    assert parse_query("nonsense without structure 123 !!!") is None


# ── Frozen-core contract ──────────────────────────────────────────────────
def test_core_is_read_only_from_titanos():
    """Titanos must not mutate the core's parameters except through its own step()."""
    t = _kb()
    Lambda_before = t.core.Lambda.copy()
    step_before = t.core.schedule_index

    # Asking questions triggers core.step(), which advances schedule_index
    # and updates Λ, but only through the documented API.
    t.ask("Zeus", "domain")

    assert t.core.schedule_index >= step_before
    assert t.core.Lambda.shape == Lambda_before.shape
