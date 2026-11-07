"""Tests for the core bridge."""
from resileos.ui.core_bridge import core_step_from_address, search_from_field


def test_core_step_shape():
    embed = {"belt": 1, "frame": 2, "residual_bin": "r10_s1", "mean_luma": 0.6, "edge_density": 0.1}
    out = core_step_from_address(embed)
    assert out["backend"] in {"residual_core", "fallback"}
    assert "packet_hash" in out


def test_search_shape():
    out = search_from_field([0.1, 0.2, 0.3])
    assert out["backend"] in {"oscillator_search", "fallback"}
    assert "budget" in out
