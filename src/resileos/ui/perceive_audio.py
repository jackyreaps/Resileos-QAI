"""Audio perception.

Simple honest figures from a 1-D waveform plus the scale address
so a perceived sound can enter the hub and the Apollo path.
"""
from __future__ import annotations

from typing import Any, Optional

from typing import Any

import numpy as np

from resileos.ui.scale_address import scale_address


def perceive_audio(
    wave: np.ndarray,
    *,
    subject: str = "audio",
    sample_rate: int = 16000,
) -> dict[str, Any]:
    """Perceive a waveform: energy, zero-cross rate, and scale address."""
    w = np.asarray(wave, dtype=np.float32).ravel()
    if w.size == 0:
        w = np.zeros(1, dtype=np.float32)
    energy = float(np.mean(w ** 2))
    if w.size < 2:
        zcr = 0.0
    else:
        zcr = float(np.mean(np.diff(np.signbit(w)).astype(np.float32)))
    # crude spectral centroid via FFT magnitude
    spec = np.abs(np.fft.rfft(w))
    freqs = np.fft.rfftfreq(w.size, d=1.0 / max(1, sample_rate))
    centroid = float(np.sum(freqs * spec) / (np.sum(spec) + 1e-8))
    # pad to a 2-D frame with both axes long enough for np.gradient
    frame = w.reshape(-1, 1)
    if frame.shape[0] < 8:
        frame = np.resize(frame, (8, 1))
    frame = np.hstack([frame, frame])
    addr = scale_address(frame, subject=subject, step_core=False)
    return {
        "subject": subject,
        "sample_rate": int(sample_rate),
        "duration_s": round(float(w.size) / max(1, sample_rate), 4),
        "energy": round(energy, 6),
        "zero_cross_rate": round(zcr, 4),
        "spectral_centroid_hz": round(centroid, 1),
        "address": addr["embed"],
        "gate": addr["gate"],
    }

def into_kin(perceived: dict, psyche=None):
    """Send this perception into Psyche and Athena."""
    from resileos.kin.psyche import Psyche
    from resileos.kin.wire_perception import wire_perception
    return wire_perception(psyche or Psyche(), perceived)
