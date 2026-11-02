"""Capacity contract constants and helpers (RES-330).

Residual ledger stays full. Denoise prior and speech channel are bounded.
HF_CAP is a multiple of RESIDUAL_BLOCK (64), not an arbitrary host accident.
"""
from __future__ import annotations

from dataclasses import dataclass


RESIDUAL_BLOCK: int = 64


@dataclass(frozen=True)
class CapacityConfig:
    """Process-wide capacity policy.

    residual_block
        Base quanta (64). Aligns residual-grid / 6-bit capacity language.
    hf_cap_blocks
        Hopfield rebuild budget = residual_block * hf_cap_blocks.
        Default 16 → 1024. Raise only with scale-report proof.
    pattern_dtype
        Storage dtype for attractor pattern list ("float32" recommended).
    require_learn_many_above
        Bulk writes at or above this N should use learn_many.
    min_probe_hit_rate
        Scale admission floor on store probes.
    """

    residual_block: int = RESIDUAL_BLOCK
    hf_cap_blocks: int = 16
    pattern_dtype: str = "float32"
    require_learn_many_above: int = 256
    max_concurrent_titanos: int = 1
    min_probe_hit_rate: float = 1.0

    def __post_init__(self) -> None:
        if self.residual_block < 1:
            raise ValueError("residual_block must be >= 1")
        if self.hf_cap_blocks < 1:
            raise ValueError("hf_cap_blocks must be >= 1")
        if self.require_learn_many_above < 1:
            raise ValueError("require_learn_many_above must be >= 1")
        if not (0.0 <= self.min_probe_hit_rate <= 1.0):
            raise ValueError("min_probe_hit_rate must be in [0, 1]")

    @property
    def hf_cap(self) -> int:
        return int(self.residual_block) * int(self.hf_cap_blocks)


# Process default — override in tests or ops via replace / new instance.
DEFAULT_CAPACITY = CapacityConfig()


def hopfield_cap(cfg: CapacityConfig | None = None) -> int:
    """Hopfield rebuild row cap (C1)."""
    return (cfg or DEFAULT_CAPACITY).hf_cap


def should_use_learn_many(n_triples: int, cfg: CapacityConfig | None = None) -> bool:
    """Bulk write policy (C2)."""
    c = cfg or DEFAULT_CAPACITY
    return int(n_triples) >= int(c.require_learn_many_above)


def admit_scale(hit_rate: float, cfg: CapacityConfig | None = None) -> bool:
    """Scale-up admission on probe hit rate (C8)."""
    c = cfg or DEFAULT_CAPACITY
    return float(hit_rate) >= float(c.min_probe_hit_rate)


__all__ = [
    "RESIDUAL_BLOCK",
    "CapacityConfig",
    "DEFAULT_CAPACITY",
    "hopfield_cap",
    "should_use_learn_many",
    "admit_scale",
]
