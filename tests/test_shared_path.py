"""Tests for shared search and phasor."""
from resileos.ui.shared_state import init_shared, phasor_shared, search_shared, step_shared


def test_step_search_phasor():
    init_shared()
    s = step_shared()
    q = search_shared()
    p = phasor_shared(0.3)
    assert s["backend"] in {"residual_core", "fallback"}
    assert q["backend"] in {"oscillator_search", "fallback"}
    assert p["backend"] in {"phasor", "fallback"}
