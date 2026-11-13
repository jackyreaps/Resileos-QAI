"""Clip check metrics: Kuramoto R over motion phase, Betti counts on residuals."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.studio.clip_metrics import (
    betti_numbers,
    clip_check_metrics,
    order_parameter,
    residual_betti,
)
from resileos.studio.sequence_stage import run_sequence_stage


@pytest.fixture(autouse=True)
def _traces(monkeypatch, tmp_path):
    monkeypatch.setenv("RESILEOS_IRIS_JSONL", str(tmp_path / "iris.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_JSONL", str(tmp_path / "hades.jsonl"))
    monkeypatch.setenv("RESILEOS_HADES_DIR", str(tmp_path / "hades"))
    monkeypatch.delenv("RESILEOS_VIDEO_PROVIDER", raising=False)


def test_order_parameter_bounds():
    assert order_parameter([0.3, 0.3, 0.3]) == pytest.approx(1.0)
    assert order_parameter([0.0, np.pi]) == pytest.approx(0.0, abs=1e-12)
    assert order_parameter([]) is None


def test_betti_counts_components_and_holes():
    ring = np.zeros((7, 7), dtype=bool)
    ring[1:6, 1:6] = True
    ring[2:5, 2:5] = False
    assert betti_numbers(ring) == (1, 1)
    two = np.zeros((6, 6), dtype=bool)
    two[0, 0] = True
    two[4:6, 4:6] = True
    assert betti_numbers(two) == (2, 0)
    # diagonal neighbours are separate under 4-connectivity
    diag = np.array([[1, 0], [0, 1]], dtype=bool)
    assert betti_numbers(diag) == (2, 0)
    assert betti_numbers(np.zeros((3, 3), dtype=bool)) == (0, 0)


def _moving_square(steps, dx=1, dy=0):
    frames = []
    for t in range(steps):
        frame = np.zeros((12, 12))
        x, y = 2 + t * dx, 2 + t * dy
        frame[y:y + 3, x:x + 3] = 1.0
        frames.append(frame)
    return frames


def test_coherent_motion_has_high_R_and_stable_betti():
    out = clip_check_metrics(_moving_square(5))
    assert out["moving_transitions"] == 4
    assert out["motion_phase_coherence"] == pytest.approx(1.0)
    assert out["betti_stable"] is True
    assert out["gating"] is False


def test_back_and_forth_motion_has_low_R():
    base = _moving_square(2)
    frames = [base[0], base[1], base[0], base[1], base[0]]
    out = clip_check_metrics(frames)
    assert out["motion_phase_coherence"] == pytest.approx(0.0, abs=1e-9)


def test_static_clip_has_no_R_and_zero_betti():
    still = [np.full((8, 8), 0.5)] * 3
    out = clip_check_metrics(still)
    assert out["motion_phase_coherence"] is None
    assert residual_betti(still) == [[0, 0], [0, 0]]
    assert out["betti_stable"] is None
    assert clip_check_metrics([still[0]])["betti"] == []


def test_metrics_are_deterministic():
    frames = _moving_square(4, dx=1, dy=1)
    assert clip_check_metrics(frames) == clip_check_metrics([f.copy() for f in frames])


def test_sequence_stage_records_metrics_without_changing_the_gate():
    frames = [f.tolist() for f in _moving_square(3)]
    drafted = run_sequence_stage(stage="draft", prompt="p", frames=frames)
    packet = drafted["video_packet"]
    assert packet["check_metrics"]["version"] == "clip-metrics/1"
    assert packet["check_metrics"]["gating"] is False
    assert drafted["check_metrics"] == packet["check_metrics"]
    assert drafted["url"] is None
    assert drafted["learned"] is False and drafted["scar_matrix_updated"] is False


def test_phase_shift_recovers_translation():
    from resileos.studio.clip_metrics import phase_shift

    frames = _moving_square(2, dx=2, dy=1)
    dy, dx, _ = phase_shift(frames[0], frames[1])
    assert (dy, dx) == (1, 2)
    out = clip_check_metrics(_moving_square(4, dx=0, dy=1))
    assert out["shifts"] == [[1, 0], [1, 0], [1, 0]]
