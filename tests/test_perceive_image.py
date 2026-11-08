"""Tests for real perceive_image."""
import numpy as np

from resileos.ui.perceive_image import perceive_image


def test_perceive_has_diagnostics_and_address():
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    out = perceive_image(arr, subject="photo")
    assert out["subject"] == "photo"
    assert "diagnostics" in out
    assert "address" in out
    assert out["mean_luma"] == 0.0
    assert "edge_density" in out
