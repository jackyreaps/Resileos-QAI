"""Tests for the fluid generator."""
import numpy as np

from resileos.ui.fluid_gen import fluid_prompt, generate_still, generate_video_hook


def test_generate_still():
    arr = np.zeros((16, 16, 3), dtype=np.uint8)
    arr[..., 1] = 180
    out = generate_still(arr, belt=1, frame=2, persona="calm")
    assert out["embed"]["belt"] == 1
    assert "calm" in out["prompt"]
    assert out["still_url"].startswith("http")
    assert out["triple"]["relation"] == "residual_address"


def test_video_hook_unconfigured(monkeypatch):
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)
    out = generate_video_hook("test")
    assert out["status"] == "not_configured"
