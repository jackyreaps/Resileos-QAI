"""Tests for audio, video, and language perception."""
import numpy as np

from resileos.ui.perceive_audio import perceive_audio
from resileos.ui.perceive_language import perceive_language
from resileos.ui.perceive_video import perceive_video


def test_audio_has_energy_and_address():
    wave = np.sin(np.linspace(0, 10, 1600)).astype(np.float32)
    out = perceive_audio(wave, subject="tone")
    assert out["subject"] == "tone"
    assert out["energy"] > 0
    assert "address" in out


def test_video_has_motion_and_address():
    frames = np.zeros((4, 8, 8, 3), dtype=np.uint8)
    frames[2] = 255
    out = perceive_video(frames, subject="clip")
    assert out["frames"] == 4
    assert out["motion"] > 0
    assert "address" in out


def test_language_has_tokens_and_address():
    out = perceive_language("hello world", subject="note")
    assert out["tokens"] == 2
    assert "address" in out
    assert out["note"]
