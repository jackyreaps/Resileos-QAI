"""Smoke test for portable diagnostics."""
import numpy as np

from resileos.ui.diagnostics import diagnose_image, histogram_rows


def test_diagnose_rgb():
    arr = np.zeros((32, 48, 3), dtype=np.uint8)
    arr[..., 0] = 200
    d = diagnose_image(arr)
    assert d["height"] == 32
    assert d["width"] == 48
    assert "histogram" in d
    assert "channel_means" in d
    rows = histogram_rows(d)
    assert len(rows) == 32
    assert sum(r["count"] for r in rows) == 32 * 48
