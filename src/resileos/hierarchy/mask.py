"""Layered mask stack (RES-312).

A constructive multi-resolution partition over the substrate's feature set.
At small scale, a mask is a binary selection over optional feature bits and
the partition boundary is a curve. At large scale, with layered masks, the
boundary saturates and becomes a membrane — the mask-to-sheath transition.

This module produces the layered structure. It does not measure the sheath
regime; that is RES-304's `sheath_metrics`. `is_saturated()` on the stack
accepts a pre-computed sheath measurement or exposes the criterion for an
external caller to supply.

Spec: docs/310-hierarchy/mask-stack.md

Off states (explicit):
    learned structure   off. Masks are supplied by the caller. The stack
                        does not search for optimal masks.
    compression claim   off. The stack is a re-encoding, not a reduction.
                        Information content is preserved, with crosstalk.
    semantic claim      off. Layer indices are depth-ordered, not
                        semantically ordered.
    capacity guarantee  off. The stack's capacity is bounded by RES-313.
    sheath as failure   off. The sheath is a regime, not a failure. Whether
                        it is desirable is a RES-315 decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from ..codex import PHI, _SEED_MULT, _SEED_MOD


# ── feature bit names (RES-312 §1) ──────────────────────────────────────
FEATURE_BITS: tuple[str, ...] = (
    "csi",
    "order_parameter",
    "direction",
)
K_MIN: int = len(FEATURE_BITS)
DEFAULT_K: int = 4
BIT_SALT_BASE: int = 911


# ── carrier generation ──────────────────────────────────────────────────
def bit_carrier(bit_index: int, dim: int) -> np.ndarray:
    """φ-seeded band carrier for a single feature bit.

    Constant-magnitude complex vector, unit norm. Deterministic per
    (bit_index, dim). Distinct bits get incommensurate phase patterns.
    """
    if dim < 2:
        raise ValueError("dim must be >= 2")
    if bit_index < 0:
        raise ValueError("bit_index must be >= 0")
    seed = (int(bit_index) * _SEED_MULT + BIT_SALT_BASE) % _SEED_MOD
    rng = np.random.default_rng(seed)
    phases = rng.uniform(-np.pi, np.pi, size=dim)
    return np.exp(1j * phases) / np.sqrt(dim)


def _bundle(carriers: Sequence[np.ndarray]) -> np.ndarray:
    if not carriers:
        raise ValueError("carriers must be non-empty")
    s = np.sum(np.stack(carriers, axis=0), axis=0)
    n = float(np.linalg.norm(s))
    return s / n if n > 1e-12 else s


def _normalize(hv: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(hv))
    if n < 1e-12:
        return hv.copy()
    return hv / n


# ── layer ───────────────────────────────────────────────────────────────
@dataclass
class MaskLayer:
    """One layer of the stack (RES-312 §3)."""
    mask: tuple[bool, ...]
    carriers: np.ndarray
    weight: float

    def __post_init__(self) -> None:
        if not isinstance(self.mask, tuple):
            self.mask = tuple(self.mask)
        if not all(isinstance(b, (bool, np.bool_)) for b in self.mask):
            raise TypeError("mask must be a tuple of bool")
        self.weight = float(self.weight)

    @property
    def n_bits(self) -> int:
        return len(self.mask)

    @property
    def n_set(self) -> int:
        return int(sum(1 for b in self.mask if b))

    def to_dict(self) -> dict:
        return {
            "mask": list(self.mask),
            "weight": float(self.weight),
            "n_set": self.n_set,
        }


# ── stack ───────────────────────────────────────────────────────────────
@dataclass
class MaskStackConfig:
    """Configuration for a MaskStack.

    dim          hypervector dimension. Must match stream_hv and codex.
    k            number of feature bits per mask. Must be >= K_MIN (3).
    n_layers     expected layer count. add_layer raises past this.
    weight_sched callable(l) -> weight for layer l. Default 1 / (l + 1).
    seed         reserved for reproducibility. Not consumed by the current
                 deterministic carrier generation (carriers are seeded per
                 bit_index and dim, not per stack).
    """
    dim: int
    k: int = DEFAULT_K
    n_layers: int = 3
    seed: int = 0

    def __post_init__(self) -> None:
        if self.dim < 2:
            raise ValueError("dim must be >= 2")
        if self.k < K_MIN:
            raise ValueError(f"k must be >= {K_MIN}")
        if self.n_layers < 1:
            raise ValueError("n_layers must be >= 1")
        self.dim = int(self.dim)
        self.k = int(self.k)
        self.n_layers = int(self.n_layers)
        self.seed = int(self.seed)


class MaskStack:
    """Layered mask stack (RES-312 §5).

    Construction:
        stack = MaskStack(MaskStackConfig(dim=512, k=4, n_layers=3))
        stack.add_layer(mask=(True, True, True, False))
        stack.add_layer(mask=(True, True, False, False))
        stack.add_layer(mask=(True, False, False, False))
        hv = stack.encode(stream_hv)

    is_saturated(codim, depth) returns True when the caller-supplied
    sheath measurement satisfies the RES-312 §4 criterion.
    """

    def __init__(self, cfg: MaskStackConfig) -> None:
        if not isinstance(cfg, MaskStackConfig):
            raise TypeError("cfg must be a MaskStackConfig")
        self.cfg = cfg
        self._layers: list[MaskLayer] = []
        self._bit_carriers: dict[int, np.ndarray] = {}

    # ── properties ──────────────────────────────────────────────────
    @property
    def dim(self) -> int:
        return self.cfg.dim

    @property
    def k(self) -> int:
        return self.cfg.k

    @property
    def n_layers(self) -> int:
        return len(self._layers)

    @property
    def layers(self) -> list[MaskLayer]:
        return list(self._layers)

    def _carrier(self, bit_index: int) -> np.ndarray:
        if bit_index not in self._bit_carriers:
            self._bit_carriers[bit_index] = bit_carrier(bit_index, self.cfg.dim)
        return self._bit_carriers[bit_index]

    @staticmethod
    def _default_weight(l: int) -> float:
        return 1.0 / (l + 1)

    # ── construction ────────────────────────────────────────────────
    def add_layer(self, mask: Sequence[bool]) -> MaskLayer:
        """Append a layer. Validates mask shape and near-orthogonality."""
        if len(self._layers) >= self.cfg.n_layers:
            raise ValueError(
                f"stack full: n_layers={self.cfg.n_layers}"
            )
        mask_t = tuple(bool(b) for b in mask)
        if len(mask_t) != self.cfg.k:
            raise ValueError(
                f"mask length {len(mask_t)} != k {self.cfg.k}"
            )
        if not any(mask_t):
            raise ValueError("mask must set at least one bit")
        for existing in self._layers:
            if existing.mask == mask_t:
                raise ValueError(
                    f"duplicate mask {mask_t} already in stack"
                )

        # Build the layer's carrier as the bundle of the set bits' carriers.
        set_bits = [i for i, b in enumerate(mask_t) if b]
        carriers = _bundle([self._carrier(i) for i in set_bits])

        # Near-orthogonality check: require |<carriers, existing.carriers>|
        # below a threshold. Bundle of near-orthogonal φ-seeded phasors
        # can be correlated if masks overlap heavily.
        THRESH = 0.75
        for existing in self._layers:
            ip = abs(float(np.real(np.vdot(existing.carriers, carriers))))
            if ip > THRESH:
                raise ValueError(
                    f"mask {mask_t} too correlated with existing "
                    f"{existing.mask} (|<c,c>| = {ip:.3f} > {THRESH})"
                )

        weight = self._default_weight(len(self._layers))
        layer = MaskLayer(mask=mask_t, carriers=carriers, weight=weight)
        self._layers.append(layer)
        return layer

    def reset(self) -> None:
        self._layers = []
        self._bit_carriers = {}

    # ── encode ──────────────────────────────────────────────────────
    def encode(self, stream_hv: np.ndarray) -> np.ndarray:
        """Return the stacked hypervector (RES-312 §3).

            stack_hv = normalize(sum_l weight_l * bind(stream_hv, carriers_l))

        bind is the codex's exact bind: a * b * sqrt(dim).
        """
        if not self._layers:
            raise ValueError("stack has no layers")
        arr = np.asarray(stream_hv)
        if arr.shape != (self.cfg.dim,):
            raise ValueError(
                f"stream_hv shape {arr.shape} != (dim,) "
                f"= ({self.cfg.dim},)"
            )
        scale = float(np.sqrt(self.cfg.dim))
        acc = np.zeros(self.cfg.dim, dtype=np.complex128)
        for layer in self._layers:
            acc = acc + layer.weight * (arr * layer.carriers * scale)
        return _normalize(acc)

    # ── sheath criterion ────────────────────────────────────────────
    @staticmethod
    def is_saturated(
        boundary_codim: float,
        depth: float,
        codim_max: float = 0.5,
        depth_min: float = 0.05,
    ) -> bool:
        """RES-312 §4 criterion. Caller supplies the RES-304 measurement.

        A stack is saturated when the boundary fills the state space
        (codim below threshold) AND crossings are not reversible (depth
        below threshold). Either condition alone is insufficient.
        """
        return bool(
            (float(boundary_codim) < float(codim_max))
            and (float(depth) < float(depth_min))
        )

    # ── introspection ───────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "dim": int(self.cfg.dim),
            "k": int(self.cfg.k),
            "n_layers_max": int(self.cfg.n_layers),
            "n_layers": int(len(self._layers)),
            "layers": [l.to_dict() for l in self._layers],
        }

    def __repr__(self) -> str:
        return (
            f"MaskStack(dim={self.cfg.dim}, k={self.cfg.k}, "
            f"n_layers={len(self._layers)}/{self.cfg.n_layers})"
        )


__all__ = [
    "MaskStack",
    "MaskStackConfig",
    "MaskLayer",
    "bit_carrier",
    "FEATURE_BITS",
    "K_MIN",
    "DEFAULT_K",
]
