"""Tests for the oscillator-driven local generator."""
import numpy as np

from resileos.ui.local_gen import generate_local


def test_local_uses_field():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 0] = 200
    out = generate_local(arr, belt=1, frame=2)
    assert out["triple"]["relation"] == "residual_address"
    assert out["field"]["n"] == 3
    assert out["backend"] in {"kuramoto", "fallback"}
    assert out["pattern_shape"] == [32, 32, 3]
