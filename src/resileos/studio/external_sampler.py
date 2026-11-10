"""External samplers. Off unless RESILEOS_EXTERNAL_SAMPLER is set.

The only object that crosses this boundary is a studio-codec/1 packet.
A sampler does not decode, does not learn, and does not touch the scar
matrix. Unknown names stay off. This module does not download weights.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Protocol

import numpy as np

from studio.codec import logical_bits


class SamplerOff(RuntimeError):
    """propose() was called while the external sampler is disabled."""


class ExternalSampler(Protocol):
    """Propose a residual packet, or refuse because the sampler is off."""

    name: str
    enabled: bool

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return one studio-codec/1 packet with per-component scales."""


class DisabledExternalSampler:
    name = "off"
    enabled = False

    def __init__(self, reason: str = "RESILEOS_EXTERNAL_SAMPLER is unset") -> None:
        self.reason = reason

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        del condition
        raise SamplerOff(self.reason)

    def status(self) -> dict[str, Any]:
        return {"enabled": False, "name": self.name, "reason": self.reason}


class FakeExternalSampler:
    """In-repo stand-in. Deterministic ±1 factors, no weights, no network."""

    name = "fake"
    enabled = True
    reason = "in-repo fake sampler; not a generative model"

    def propose(self, *, condition: dict[str, Any] | None = None) -> dict[str, Any]:
        seed = 0
        if condition and condition.get("seed") is not None:
            seed = int(condition["seed"])
        rng = np.random.default_rng(seed)
        rank = 2
        m = n = 8
        layers = []
        for _ in range(1):
            ub = np.sign(rng.standard_normal((m, rank))).astype(np.float32)
            vb = np.sign(rng.standard_normal((rank, n))).astype(np.float32)
            ub[ub == 0] = 1.0
            vb[vb == 0] = 1.0
            scales = [float(x) for x in rng.normal(0.0, 0.05, size=rank)]
            layers.append({"Ub": ub, "Vb": vb, "scale": scales})
        return {
            "version": "studio-codec/1",
            "shape": [m, n],
            "rank": rank,
            "n_layers": 1,
            "scale_mode": "component",
            "basis": "external-fake",
            "layers": layers,
            "logical_bits": logical_bits(m, n, rank, 1, "component"),
        }

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "name": self.name, "reason": self.reason}


def resolve_external_sampler(
    env: Mapping[str, str] | None = None,
) -> DisabledExternalSampler | FakeExternalSampler:
    """Off by default. ``fake`` is the only in-repo implementation."""
    source = os.environ if env is None else env
    raw = str(source.get("RESILEOS_EXTERNAL_SAMPLER", "")).strip().lower()
    if raw in ("", "off", "none", "disabled"):
        return DisabledExternalSampler()
    if raw == "fake":
        return FakeExternalSampler()
    return DisabledExternalSampler(
        reason=f"unknown external sampler {raw!r} was not loaded; weights are not vendored"
    )
