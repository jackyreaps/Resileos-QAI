"""Belt chroma compression: more variations at lower byte and op cost."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.ui.cascade_address import BELT, ORIENTATION_SCALES
from resileos.ui.chroma import (
    BELT_AXES,
    CODE_BYTES,
    HUE_STEPS,
    chroma_code,
    expand_variations,
    measure_variations,
    pack_code,
    unpack_code,
)
from resileos.ui.residual_embed import embed_frame


def test_pack_roundtrip_and_variation_counts():
    code = chroma_code(chroma=[0.2, 0.8, 0.5, 0.1, 0.4], orientation="sun_earth_moon")
    packed = pack_code(code)
    assert len(packed) == CODE_BYTES
    back = unpack_code(packed)
    assert back["belt"] == BELT
    assert back["axes"] == list(BELT_AXES)
    palettes = expand_variations(code)
    assert len(palettes) == BELT * 6 * HUE_STEPS
    assert all("frame" not in item for item in palettes)
    with_scales = expand_variations(code, include_scales=True)
    assert len(with_scales) == len(palettes) * len(ORIENTATION_SCALES)


def test_measure_variations_is_cheaper_than_naive_frames():
    measured = measure_variations(shape=(16, 16), include_scales=False, repeats=8)
    assert measured["variations"] == BELT * 6 * HUE_STEPS
    assert measured["code_bytes"] == CODE_BYTES
    assert measured["code_bytes"] < measured["naive_frame_bytes"]
    assert measured["ops_expand"] < measured["ops_naive_frames"]
    # Wall-clock at a 16x16 tile can go either way; bytes and ops are
    # the cost that this path is built to cut. Timings are recorded.
    print("chroma_measure", measured)


def test_embed_frame_without_scale_is_unchanged():
    import numpy as np

    arr = np.zeros((4, 4), dtype=np.uint8)
    a = embed_frame(arr, belt=1, frame=3)
    b = embed_frame(arr, belt=1, frame=3)
    assert a == b
    assert "scale_level" not in a
    scaled = embed_frame(arr, belt=1, frame=3, scale="orion")
    assert scaled["belt"] == BELT
    assert scaled["frame"] == 9
    assert scaled["scale_level"] == 2
