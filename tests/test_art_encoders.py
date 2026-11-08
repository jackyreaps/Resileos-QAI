"""Tests for art and music encoders."""
from resileos.ui.art_encoders import encode_art, encode_music


def test_music_encoder():
    out = encode_music("dawn", "C E G")
    assert out["kind"] == "music"
    assert out["apollo"]["art"] is True
    assert out["address"]["belt"] == 0


def test_art_encoder():
    out = encode_art("red field", "a field at dusk")
    assert out["kind"] == "art"
    assert out["apollo"]["kept"] == 1
