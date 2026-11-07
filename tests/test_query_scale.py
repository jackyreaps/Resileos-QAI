"""Tests for shared state and query scale attachment."""
from resileos.ui.query_scale import with_scale
from resileos.ui.shared_state import get_shared, init_shared


def test_shared_init():
    s = init_shared()
    assert "core" in s and "field" in s
    assert s["ready"] is True


def test_with_scale():
    resp = {"value": "sky", "status": "ACCEPTED"}
    out = with_scale(resp, "Zeus", "domain")
    assert "scale" in out
    assert out["scale"]["gate"]["frame"] in {"exact", "reconstructed", "abstained"}
    assert "shared_core" in out["scale"]
