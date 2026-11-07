"""Tests for the image encoder."""
import numpy as np

from resileos.ui.image_encoder import encode_image, features_to_triples


def test_encode_red_wide():
    arr = np.zeros((32, 64, 3), dtype=np.uint8)
    arr[..., 0] = 220
    f = encode_image(arr)
    assert f["aspect_class"] == "wide"
    assert f["dominant_channel"] == "red"
    assert f["height"] == 32


def test_triples_from_features():
    f = {"aspect_class": "square", "dominant_channel": "blue", "edge_density": 0.2}
    t = features_to_triples(f, subject="photo")
    rels = {x["relation"] for x in t}
    assert "aspect_class" in rels
    assert "dominant_channel" in rels
