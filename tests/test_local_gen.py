"""Tests for the oscillator-driven local generator."""
import numpy as np

from resileos.ui.local_gen import field_from_embed, generate_local


def test_field_from_embed_steps():
    out = field_from_embed({"mean_luma": 0.2, "edge_density": 0.3, "belt": 1})
    assert out["backend"] == "kuramoto"
    assert out["n"] == 3
    assert len(out["theta"]) == 3


def test_local_uses_field():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 0] = 200
    out = generate_local(arr, belt=1, frame=2)
    assert out["triple"]["relation"] == "residual_address"
    assert len(out["field"]["theta"]) == 3
    assert out["backend"] == "kuramoto"
    assert "gate" in out
    assert out["pattern_shape"] == [32, 32, 3]
