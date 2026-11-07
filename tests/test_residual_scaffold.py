"""Tests for residual embedding and cascade address scaffolds."""
import numpy as np

from resileos.ui.cascade_address import cascade_address, is_valid_address
from resileos.ui.residual_embed import address_triple, embed_frame


def test_embed_and_triple():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 0] = 200
    e = embed_frame(arr, belt=1, frame=3)
    assert e["belt"] == 1
    assert e["frame"] == 3
    assert e["residual_bin"] in {"high_high", "high_low", "low_high", "low_low"}
    t = address_triple(e, subject="clip")
    assert t["relation"] == "residual_address"
    assert "belt1_frame3" in t["obj"]


def test_cascade_address():
    a = cascade_address(2, 5, "low_high")
    assert is_valid_address(a)
    assert a["path"] == "2/5/low_high"
