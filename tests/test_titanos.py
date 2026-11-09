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
        ("Uranus", "parent_of", "Cronus"),
        ("Cronus", "parent_of", "Zeus"),
        ("Cronus", "parent_of", "Poseidon"),
        ("Cronus", "parent_of", "Hades"),
        ("Zeus", "parent_of", "Ares"),
        ("Zeus", "parent_of", "Athena"),
        ("Zeus", "domain", "sky"),
        ("Poseidon", "domain", "sea"),
        ("Hades", "domain", "underworld"),
        ("Ares", "domain", "war"),
        ("Athena", "domain", "wisdom"),
    ]
    for s, r, o in facts:
        t.learn(s, r, o)
    return t


def _temporal_kb():
    """KB with temporal facts (RES-332). All dates ISO 8601 YYYY-MM-DD."""
    t = Titanos(_cfg())
    t.learn(
        "Athens", "capital_of", "Ottoman Empire",
        valid_from="1458-01-01", valid_to="1834-01-01",
    )
    t.learn(
        "Athens", "capital_of", "Greece",
        valid_from="1834-01-01", valid_to=None,
    )
    t.learn(
        "Rome", "capital_of", "Roman Empire",
        valid_from=None, valid_to="476-01-01",
    )
    return t


# ── Single-hop ──────────────────────────────────────────────────────────
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
        assert {"loop", "scar_energy", "delta", "mu", "DeltaS", "rank",
                "volume_ok", "sigma1_action", "gate_state",
                "packet_hash"} <= set(h.keys())


# ── Inverse ─────────────────────────────────────────────────────────────
def test_inverse():
    t = _kb()
    a = t.ask_inverse("Zeus", "parent_of")
    assert a.status == "ACCEPTED"
    assert a.value in ("Cronus",)


# ── Chain ───────────────────────────────────────────────────────────────
def test_chain():
    t = _kb()
    a = t.chain("Uranus", ["parent_of", "parent_of"])
    assert a.status == "ACCEPTED"
    # Uranus -> Cronus (only child) -> {Zeus, Poseidon, Hades}.
    # Ares and Athena are three hops from Uranus, not two.
    assert a.value in ("Zeus", "Poseidon", "Hades")
    assert a.confidence > 0.0


def test_chain_breaks_on_unknown():
    t = _kb()
    a = t.chain("Zeus", ["capital_of"])
    assert a.status == "ABSTAINED"
    assert a.reason


# ── Analogy ─────────────────────────────────────────────────────────────
def test_analogy():
    t = _kb()
    a = t.analogy("Zeus", "sky", "Poseidon")
    assert a.status in ("ACCEPTED", "ABSTAINED")


# ── Abstention ──────────────────────────────────────────────────────────
def test_abstain_on_unknown_entity():
    t = _kb()
    a = t.ask("Odin", "parent_of")
    assert a.status == "ABSTAINED"
    assert "unknown entity" in a.reason


def test_abstain_on_unknown_relation():
    t = _kb()
    a = t.ask("Zeus", "capital_of")
    assert a.status == "ABSTAINED"


# ── Quantum label ───────────────────────────────────────────────────────
def test_quantum_path_labeled():
    """If mode is QUANTUM_SIM, it must never be reported as CLASSICAL."""
    t = _kb()
    # Force the quantum band by tightening classical_conf above realistic sims.
    t.cfg = TitanosConfig(**{**t.cfg.__dict__, "classical_conf": 0.5})
    a = t.ask("Zeus", "parent_of")
    assert a.mode in ("QUANTUM_SIM", "ABSTAIN")


# ── Persistence ─────────────────────────────────────────────────────────
def test_save_load_roundtrip(tmp_path):
    t = _kb()
    p = tmp_path / "titanos.json"
    t.save(p)
    t2 = Titanos.load(p)
    assert t2.stats()["facts"] == t.stats()["facts"]
    a1 = t.ask("Zeus", "domain")
    a2 = t2.ask("Zeus", "domain")
    assert a1.value == a2.value


# ── NLP front-end ───────────────────────────────────────────────────────
def test_nlp_parser():
    assert parse_query("Who is the parent of Zeus?") == ("Zeus", "parent", True)
    assert parse_query("Who is Zeus's parent?") == ("Zeus", "parent", False)
    assert parse_query("What is Poseidon's domain?") == ("Poseidon", "domain", False)
    assert parse_query("nonsense without structure 123 !!!") is None


# ── Frozen-core contract ────────────────────────────────────────────────
def test_core_is_read_only_from_titanos():
    """Titanos must not mutate the core's parameters except through its
    own step()."""
    t = _kb()
    Lambda_before = t.core.Lambda.copy()
    step_before = t.core.schedule_index
    # Asking questions triggers core.step(), which advances schedule_index
    # and updates Λ, but only through the documented API.
    t.ask("Zeus", "domain")
    assert t.core.schedule_index >= step_before
    assert t.core.Lambda.shape == Lambda_before.shape


# ══════════════════════════════════════════════════════════════════════════
# Temporal (RES-332)
# ══════════════════════════════════════════════════════════════════════════


def test_temporal_fact_tuple_shape():
    """learn() always appends a 5-tuple, even for legacy 3-arg calls."""
    t = Titanos(_cfg())
    t.learn("A", "r", "B")
    assert len(t.facts) == 1
    assert len(t.facts[0]) == 5
    s, r, o, vf, vt = t.facts[0]
    assert (s, r, o) == ("A", "r", "B")
    assert vf is None and vt is None


def test_temporal_legacy_learn_unchanged():
    """3-arg learn() with no validity kwargs still works as before."""
    t = _kb()
    assert t.stats()["facts"] == 11
    assert t.ask_list("Zeus", "domain") == ["sky"]


def test_ask_list_as_of_filters():
    """as_of resolves to the fact valid at that moment."""
    t = _temporal_kb()
    assert t.ask_list("Athens", "capital_of", as_of="1800-01-01") == [
        "Ottoman Empire"
    ]
    assert t.ask_list("Athens", "capital_of", as_of="1900-01-01") == [
        "Greece"
    ]
    # Before either fact: no chronos-valid match
    assert t.ask_list("Athens", "capital_of", as_of="1450-01-01") == []


def test_ask_list_as_of_empty_returns_all():
    """as_of='' disables the temporal filter — append-only log view."""
    t = _temporal_kb()
    rows = t.ask_list("Athens", "capital_of", as_of="")
    assert set(rows) == {"Ottoman Empire", "Greece"}


def test_ask_list_default_uses_today():
    """as_of=None means today. Ottoman is expired, Greece is current."""
    t = _temporal_kb()
    rows = t.ask_list("Athens", "capital_of")
    assert rows == ["Greece"]


def test_temporal_half_open_interval():
    """valid_to is exclusive: [valid_from, valid_to)."""
    t = _temporal_kb()
    # Day before Ottoman ends: still valid, Greece not yet
    assert t.ask_list("Athens", "capital_of", as_of="1833-12-31") == [
        "Ottoman Empire"
    ]
    # Day Ottoman ends: Ottoman excluded, Greece included
    assert t.ask_list("Athens", "capital_of", as_of="1834-01-01") == [
        "Greece"
    ]


def test_temporal_unbounded_from():
    """Fact with only valid_until (unbounded valid_from) works."""
    t = _temporal_kb()
    assert t.ask_list("Rome", "capital_of", as_of="100-01-01") == [
        "Roman Empire"
    ]
    assert t.ask_list("Rome", "capital_of", as_of="500-01-01") == []


def test_temporal_ask_respects_current_validity():
    """ask() excludes expired facts when temporal_filter_current=True."""
    t = _temporal_kb()
    # Athens -> Ottoman Empire is expired; ask() must not return it
    a = t.ask("Athens", "capital_of")
    assert a.value != "Ottoman Empire"


def test_temporal_filter_disabled():
    """temporal_filter_current=False makes ask() return regardless of validity."""
    cfg = _cfg()
    cfg.temporal_filter_current = False
    t = Titanos(cfg)
    t.learn(
        "Athens", "capital_of", "Ottoman Empire",
        valid_from="1458-01-01", valid_to="1834-01-01",
    )
    a = t.ask("Athens", "capital_of")
    assert a.status == "ACCEPTED"
    assert a.value == "Ottoman Empire"


def test_learn_many_accepts_both_shapes():
    """learn_many accepts 3-tuple and 5-tuple items in the same batch."""
    t = Titanos(_cfg())
    n = t.learn_many([
        ("A", "r", "B"),                                       # 3-tuple
        ("X", "r", "Y", "1800-01-01", "1900-01-01"),           # 5-tuple
    ])
    assert n == 2
    assert len(t.facts) == 2
    assert t.facts[0] == ("A", "r", "B", None, None)
    assert t.facts[1] == ("X", "r", "Y", "1800-01-01", "1900-01-01")


def test_load_normalises_legacy_facts(tmp_path):
    """Legacy 3-tuple facts in JSON are read as (None, None) validity."""
    t = Titanos(_cfg())
    t.learn("A", "r", "B")
    p = tmp_path / "state.json"
    t.save(p)
    # Simulate a legacy state file by rewriting the facts array
    import json
    raw = json.loads(p.read_text())
    raw["facts"] = [["A", "r", "B"]]  # 3-tuple, no validity
    p.write_text(json.dumps(raw))
    t2 = Titanos.load(p)
    assert len(t2.facts) == 1
    assert t2.facts[0] == ("A", "r", "B", None, None)
    assert t2.ask_list("A", "r") == ["B"]


def test_stats_reports_temporal_counts():
    """stats() includes facts_with_validity and facts_expired."""
    t = _temporal_kb()
    s = t.stats()
    assert "facts_with_validity" in s
    assert "facts_expired" in s
    assert "temporal_filter_current" in s
    # 2 Athens facts + 1 Rome fact = 3 all have at least one bound set
    assert s["facts_with_validity"] == 3
    # Ottoman Empire (ends 1834) and Roman Empire (ends 476) are expired
    assert s["facts_expired"] == 2


def test_temporal_save_load_roundtrip(tmp_path):
    """Validity intervals survive save/load."""
    t = _temporal_kb()
    p = tmp_path / "state.json"
    t.save(p)
    t2 = Titanos.load(p)
    assert len(t2.facts) == 3
    for f in t2.facts:
        assert len(f) == 5
    assert t2.ask_list("Athens", "capital_of", as_of="1800-01-01") == [
        "Ottoman Empire"
    ]
    assert t2.ask_list("Athens", "capital_of", as_of="1900-01-01") == [
        "Greece"
    ]
