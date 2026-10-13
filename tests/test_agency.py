"""Tests for the heuristic agency routing layer (RES-307)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.substrate.agency import AgencyGroup, AgencyChild


# ── AgencyChild unit tests ──────────────────────────────────────────────
def test_child_fitness_update():
    c = AgencyChild(name="a", handler=lambda *a: None)
    c.update_fitness(0.8, 1.0)
    c.update_fitness(0.6, 1.0)
    assert len(c.local_csi) == 2
    assert c.mean_csi == pytest.approx(0.7)
    assert 0.0 < c.contribution <= 1.0


def test_child_window_caps():
    c = AgencyChild(name="a", handler=lambda *a: None, csi_window=3)
    for i in range(5):
        c.update_fitness(i * 0.1, 1.0)
    assert len(c.local_csi) == 3


def test_child_empty_csi_defaults_to_one():
    c = AgencyChild(name="a", handler=lambda *a: None)
    assert c.mean_csi == 1.0


def test_child_accept_rate():
    c = AgencyChild(name="a", handler=lambda *a: None)
    c.query_count = 4
    c.accept_count = 3
    assert c.accept_rate == pytest.approx(0.75)


def test_child_accept_rate_zero_queries():
    c = AgencyChild(name="a", handler=lambda *a: None)
    assert c.accept_rate == 0.0


# ── AgencyGroup registration ────────────────────────────────────────────
def test_group_add_child():
    g = AgencyGroup()
    c = g.add_child("a", lambda *args: None)
    assert c.name == "a"
    assert "a" in g.children


def test_group_rejects_duplicate_name():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None)
    with pytest.raises(ValueError, match="already registered"):
        g.add_child("a", lambda *args: None)


def test_group_rejects_nonpositive_weight():
    g = AgencyGroup()
    with pytest.raises(ValueError, match="weight"):
        g.add_child("a", lambda *args: None, weight=0.0)


def test_group_remove_child():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None)
    g.remove_child("a")
    assert "a" not in g.children
    assert g.select() is None


def test_group_rejects_bad_absorption_rate():
    with pytest.raises(ValueError):
        AgencyGroup(absorption_rate=1.0)
    with pytest.raises(ValueError):
        AgencyGroup(absorption_rate=-0.1)


# ── selection ───────────────────────────────────────────────────────────
def test_group_select_highest_weight():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None, weight=0.3)
    g.add_child("b", lambda *args: None, weight=0.7)
    assert g.select().name == "b"


def test_group_select_returns_none_when_empty():
    g = AgencyGroup()
    assert g.select() is None


def test_group_select_skips_inactive():
    g = AgencyGroup()
    a = g.add_child("a", lambda *args: None, weight=0.9)
    g.add_child("b", lambda *args: None, weight=0.1)
    a.active = False
    assert g.select().name == "b"


def test_group_select_deterministic_on_ties():
    """Equal weights: max() returns the first encountered in dict order."""
    g = AgencyGroup()
    g.add_child("a", lambda *args: None, weight=0.5)
    g.add_child("b", lambda *args: None, weight=0.5)
    first = g.select().name
    for _ in range(5):
        assert g.select().name == first


# ── fitness recording ───────────────────────────────────────────────────
def test_record_updates_counters():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None)
    g.record("a", csi=0.8, accepted=True)
    g.record("a", csi=0.6, accepted=False)
    c = g.children["a"]
    assert c.query_count == 2
    assert c.accept_count == 1
    assert len(c.local_csi) == 2


def test_record_ignores_inactive():
    g = AgencyGroup()
    c = g.add_child("a", lambda *args: None)
    c.active = False
    g.record("a", csi=0.1, accepted=False)
    assert c.query_count == 0


def test_record_ignores_unknown_child():
    g = AgencyGroup()
    g.record("ghost", csi=0.5, accepted=True)  # must not raise


# ── eating ──────────────────────────────────────────────────────────────
def test_eat_requires_min_queries():
    g = AgencyGroup(min_queries_before_eat=5)
    c = g.add_child("weak", lambda *args: None)
    for _ in range(3):
        g.record("weak", csi=0.05, accepted=False)
    assert g.eat("weak") is False
    assert c.active is True


def test_eat_requires_low_csi():
    g = AgencyGroup(min_queries_before_eat=3,
                    eat_threshold_csi=0.35)
    c = g.add_child("good", lambda *args: None)
    for _ in range(10):
        g.record("good", csi=0.9, accepted=True)
    assert g.eat("good") is False
    assert c.active is True


def test_eat_requires_low_contribution():
    g = AgencyGroup(min_queries_before_eat=3,
                    eat_threshold_csi=0.9,
                    eat_threshold_contrib=0.15)
    c = g.add_child("contributor", lambda *args: None)
    for _ in range(10):
        g.record("contributor", csi=0.1, accepted=True)
    # CSI is low, contribution is high — not edible.
    assert g.eat("contributor") is False


def test_eat_reduces_weight():
    g = AgencyGroup(min_queries_before_eat=3, absorption_rate=0.4)
    c = g.add_child("weak", lambda *args: None, weight=1.0)
    for _ in range(20):
        g.record("weak", csi=0.05, accepted=False)
    w0 = c.weight
    assert g.eat("weak") is True
    assert c.weight < w0


def test_eat_deactivates_eventually():
    g = AgencyGroup(min_queries_before_eat=3,
                    eat_threshold_csi=0.35,
                    eat_threshold_contrib=0.15,
                    min_weight=0.05,
                    absorption_rate=0.4)
    c = g.add_child("weak", lambda *args: None)
    for _ in range(20):
        g.record("weak", csi=0.05, accepted=False)
    for _ in range(20):
        g.eat("weak")
        if not c.active:
            break
    assert c.active is False
    assert "weak" in g.eaten


def test_eat_inactive_child_returns_false():
    g = AgencyGroup()
    c = g.add_child("a", lambda *args: None)
    c.active = False
    assert g.eat("a") is False


def test_eat_unknown_child_returns_false():
    g = AgencyGroup()
    assert g.eat("ghost") is False


# ── prune ───────────────────────────────────────────────────────────────
def test_prune_returns_newly_inactive():
    g = AgencyGroup(min_queries_before_eat=3,
                    eat_threshold_csi=0.35,
                    eat_threshold_contrib=0.15,
                    min_weight=0.05,
                    absorption_rate=0.4)
    g.add_child("strong", lambda *args: None)
    g.add_child("weak", lambda *args: None)
    for _ in range(20):
        g.record("strong", csi=0.9, accepted=True)
        g.record("weak", csi=0.05, accepted=False)
    eaten = []
    for _ in range(20):
        eaten = g.evaluate_and_prune()
        if eaten:
            break
    assert "weak" in eaten
    assert "strong" not in eaten


def test_prune_returns_empty_when_nothing_edible():
    g = AgencyGroup(min_queries_before_eat=3)
    g.add_child("a", lambda *args: None)
    for _ in range(10):
        g.record("a", csi=0.9, accepted=True)
    assert g.evaluate_and_prune() == []


# ── snapshot ────────────────────────────────────────────────────────────
def test_snapshot_shape():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None)
    g.record("a", csi=0.7, accepted=True)
    snap = g.snapshot()
    assert "children" in snap
    assert "eaten" in snap
    assert "a" in snap["children"]
    fields = snap["children"]["a"]
    for key in ("weight", "active", "query_count", "accept_count",
                "accept_rate", "mean_csi", "contribution"):
        assert key in fields


def test_snapshot_reflects_eaten_state():
    g = AgencyGroup(min_queries_before_eat=2,
                    eat_threshold_csi=0.35,
                    eat_threshold_contrib=0.15,
                    min_weight=0.05,
                    absorption_rate=0.5)
    g.add_child("w", lambda *args: None)
    for _ in range(20):
        g.record("w", csi=0.01, accepted=False)
    for _ in range(20):
        g.evaluate_and_prune()
        if not g.children["w"].active:
            break
    snap = g.snapshot()
    assert "w" in snap["eaten"]
    assert snap["children"]["w"]["active"] is False


# ── integration with a mock handler ─────────────────────────────────────
def test_weights_normalize_across_active():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None, weight=1.0)
    g.add_child("b", lambda *args: None, weight=3.0)
    total = sum(c.weight for c in g.children.values())
    assert abs(total - 1.0) < 1e-9
    assert g.children["b"].weight > g.children["a"].weight


def test_removing_child_renormalizes():
    g = AgencyGroup()
    g.add_child("a", lambda *args: None, weight=1.0)
    g.add_child("b", lambda *args: None, weight=1.0)
    g.remove_child("a")
    assert abs(g.children["b"].weight - 1.0) < 1e-9
