"""Layered mask stack (RES-312).

A constructive multi-resolution partition over the substrate's feature
set. At small scale, a mask is a binary selection over optional feature
bits and the partition boundary is a curve. At large scale, with layered
masks, the boundary saturates and becomes a membrane — the mask-to-sheath
transition.

Prime tower carrier (this revision):
    Layer carriers are ordered along the prime tower's local-to-global
    axis. Local layers use the smallest primes (highest resolvable
    frequencies); global layers use the largest primes that fit under
    Nyquist. Adjacent layers differ by a prime gap, not by a constant
    log step.

    This replaces the φ-power ladder, which was an exponential index.
    An exponential ladder is uniform in log space: log(PHI ** e) = e ·
    log(PHI). The prime tower is not uniform in log space — consecutive
    primes have irregular gaps, and the Cipolla normalisation adds a
    second layer of irregularity. The φ-ladder smoothed over exactly
    the boundary structure the tower exists to encode.

    The tower's domain wall (odd branch forbidden) is the sheath
    boundary. A layer on the odd branch beyond the wall is in the
    sheath regime. `is_forbidden(n)` exposes this.

Spec: docs/310-hierarchy/mask-stack.md

Off states (explicit):
    learned structure   off. Masks are supplied by the caller. The stack
                        does not search for optimal masks.
    compression claim   off. The stack is a re-encoding, not a reduction.
    semantic claim      off. Layer indices are depth-ordered on a
                        local/global axis, not semantically ordered.
    capacity guarantee  off. Bounded by RES-313.
    sheath as failure   off. The sheath is a regime, not a failure.
    bit_derived carrier off. Carriers are not derived from mask bits.
    stochastic carrier  off. Carriers are deterministic (prime tower).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .prime_tower import PrimeTower


# ── feature bit names (RES-312 §1) ──────────────────────────────────────
FEATURE_BITS: tuple[str, ...] = (
    "csi",
    "order_parameter",
    "direction",
)
K_MIN: int = len(FEATURE_BITS)
DEFAULT_K: int = 4


# ── tower singleton (lazy) ──────────────────────────────────────────────
_tower_cache: dict[int, PrimeTower] = {}


def _get_tower(max_level: int) -> PrimeTower:
    key = int(max_level)
    if key not in _tower_cache:
        _tower_cache[key] = PrimeTower(max_level=key)
    return _tower_cache[key]


# ── carrier ─────────────────────────────────────────────────────────────
def tower_level_for(layer_index: int, n_layers: int, local_first: bool) -> int:
    """Map a stack layer index to a tower level.

    Tower levels start at 2 (T(2) = S_2). Layer 0 maps to level 2,
    layer 1 to level 3, etc. When local_first=False the mapping is
    reversed: layer 0 maps to the highest level, layer n_layers-1 to
    level 2.

    local_first=True  -> layer 0 is local (smallest prime, highest freq)
                         layer n_layers-1 is global (largest prime)
    local_first=False -> layer 0 is global (largest prime)
                         layer n_layers-1 is local (smallest prime)
    """
    if n_layers < 1:
        raise ValueError("n_layers must be >= 1")
    if not (0 <= layer_index < n_layers):
        raise ValueError(
            f"layer_index {layer_index} out of range [0, {n_layers})"
        )
    if local_first:
        return layer_index + 2
    return (n_layers - 1 - layer_index) + 2


def layer_carrier(
    layer_index: int,
    n_layers: int,
    dim: int,
    local_first: bool = True,
) -> np.ndarray:
    """Prime-tower carrier for a layer.

        n     = tower_level_for(layer_index, n_layers, local_first)
        p     = prime(n)
        phase[d] = 2π · p · d / dim       for d = 0 .. dim-1
        carrier[d] = exp(i · phase[d]) / sqrt(dim)

    The Nyquist bound is p < dim/2. The carrier is deterministic and
    near-orthogonal to every other layer's carrier by the prime-gap
    structure of the tower.
    """
    if dim < 4:
        raise ValueError("dim must be >= 4")
    level = tower_level_for(layer_index, n_layers, local_first)
    tower = _get_tower(level)
    p = tower.prime(level)
    if 2 * p >= dim:
        raise ValueError(
            f"prime p_{level}={p} exceeds Nyquist at dim={dim} "
            f"(requires 2p < dim)"
        )
    d = np.arange(dim, dtype=np.float64)
    phases = 2.0 * np.pi * float(p) * d / float(dim)
    return np.exp(1j * phases) / np.sqrt(dim)


def _normalize(hv: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(hv))
    if n < 1e-12:
        return hv.copy()
    return hv / n


# ── layer ───────────────────────────────────────────────────────────────
@dataclass
class MaskLayer:
    """One layer of the stack (RES-312 §3).

    mask       metadata: which feature bits this layer selects.
    carrier    prime-tower carrier (local/global axis).
    weight     contribution to the stack bundle, default 1 / (l + 1).
    tower_level  tower level n used to build the carrier (>= 2).
    prime      prime p_n used as the carrier frequency.
    branch     'even' or 'odd'.
    """
    mask: tuple[bool, ...]
    carrier: np.ndarray
    weight: float
    tower_level: int
    prime: int
    branch: str

    def __post_init__(self) -> None:
        if not isinstance(self.mask, tuple):
            self.mask = tuple(self.mask)
        if not all(isinstance(b, (bool, np.bool_)) for b in self.mask):
            raise TypeError("mask must be a tuple of bool")
        self.weight = float(self.weight)
        self.tower_level = int(self.tower_level)
        self.prime = int(self.prime)
        if self.branch not in ("even", "odd"):
            raise ValueError("branch must be 'even' or 'odd'")

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
            "tower_level": int(self.tower_level),
            "prime": int(self.prime),
            "branch": self.branch,
            "n_set": self.n_set,
        }


# ── config ──────────────────────────────────────────────────────────────
@dataclass
class MaskStackConfig:
    """Configuration for a MaskStack.

    dim           hypervector dimension. Must match stream_hv and codex.
    k             number of feature bits per mask. Must be >= K_MIN (3).
    n_layers      expected layer count. add_layer raises past this.
    local_first   True  -> layer 0 is local (smallest prime),
                           layer n-1 is global (largest prime).
                  False -> layer 0 is global, layer n-1 is local.
    seed          reserved. Not consumed. The prime tower is
                  deterministic.
    """
    dim: int
    k: int = DEFAULT_K
    n_layers: int = 3
    local_first: bool = True
    seed: int = 0

    def __post_init__(self) -> None:
        if self.dim < 4:
            raise ValueError("dim must be >= 4")
        if self.k < K_MIN:
            raise ValueError(f"k must be >= {K_MIN}")
        if self.n_layers < 1:
            raise ValueError("n_layers must be >= 1")
        self.dim = int(self.dim)
        self.k = int(self.k)
        self.n_layers = int(self.n_layers)
        self.local_first = bool(self.local_first)
        self.seed = int(self.seed)
        # Validate the tower has enough usable levels at this dim.
        tower = _get_tower(self.n_layers + 2)
        if self.n_layers > tower.n_usable(self.dim):
            raise ValueError(
                f"n_layers={self.n_layers} exceeds tower's usable "
                f"levels ({tower.n_usable(self.dim)}) at dim={self.dim}"
            )


# ── stack ───────────────────────────────────────────────────────────────
class MaskStack:
    """Layered mask stack (RES-312 §5).

    Construction:
        stack = MaskStack(MaskStackConfig(dim=512, k=4, n_layers=3))
        stack.add_layer(mask=(True, True, True, False))
        stack.add_layer(mask=(True, True, False, False))
        stack.add_layer(mask=(True, False, False, False))
        hv = stack.encode(stream_hv)

    The mask passed to add_layer is metadata. The carrier is determined
    by the layer's tower level, which is determined by its position.
    Two stacks with the same config produce the same carriers
    regardless of the masks supplied.

    `is_saturated(codim, depth)` returns True when the caller-supplied
    sheath measurement satisfies the RES-312 §4 criterion.

    `tower_levels()`, `primes()`, `branches()` expose the orientation
    axis for downstream consumers (RES-307 routing).
    """

    def __init__(self, cfg: MaskStackConfig) -> None:
        if not isinstance(cfg, MaskStackConfig):
            raise TypeError("cfg must be a MaskStackConfig")
        self.cfg = cfg
        self._layers: list[MaskLayer] = []
        self._tower = _get_tower(cfg.n_layers + 2)

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
    def local_first(self) -> bool:
        return self.cfg.local_first

    @property
    def layers(self) -> list[MaskLayer]:
        return list(self._layers)

    def tower_levels(self) -> list[int]:
        """Tower levels of every layer, in layer order."""
        return [l.tower_level for l in self._layers]

    def primes(self) -> list[int]:
        """Prime frequencies of every layer, in layer order."""
        return [l.prime for l in self._layers]

    def branches(self) -> list[str]:
        """Branch labels of every layer, in layer order."""
        return [l.branch for l in self._layers]

    def is_forbidden(self, layer_index: int) -> bool:
        """True when the layer is on the domain-forbidden odd branch."""
        if not (0 <= layer_index < len(self._layers)):
            raise IndexError(
                f"layer_index {layer_index} out of range"
            )
        return self._tower.is_forbidden(
            self._layers[layer_index].tower_level
        )

    # ── construction ────────────────────────────────────────────────
    def add_layer(self, mask: Sequence[bool]) -> MaskLayer:
        """Append a layer. The carrier is positional; the mask is
        metadata. Validation is limited to shape and non-emptiness."""
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

        idx = len(self._layers)
        level = tower_level_for(idx, self.cfg.n_layers, self.cfg.local_first)
        carrier = layer_carrier(
            idx, self.cfg.n_layers, self.cfg.dim, self.cfg.local_first
        )
        p = self._tower.prime(level)
        branch = self._tower.branch(level)
        weight = 1.0 / (idx + 1)
        layer = MaskLayer(
            mask=mask_t,
            carrier=carrier,
            weight=weight,
            tower_level=level,
            prime=p,
            branch=branch,
        )
        self._layers.append(layer)
        return layer

    def reset(self) -> None:
        self._layers = []

    # ── encode ──────────────────────────────────────────────────────
    def encode(self, stream_hv: np.ndarray) -> np.ndarray:
        """Return the stacked hypervector (RES-312 §3).

            stack_hv = normalize(sum_l weight_l * bind(stream_hv, carrier_l))

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
            acc = acc + layer.weight * (arr * layer.carrier * scale)
        return _normalize(acc)

    # ── sheath criterion ────────────────────────────────────────────
    @staticmethod
    def is_saturated(
        boundary_codim: float,
        depth: float,
        codim_max: float = 0.5,
        depth_min: float = 0.05,
    ) -> bool:
        """RES-312 §4 criterion. Caller supplies the RES-304 measurement."""
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
            "local_first": bool(self.cfg.local_first),
            "tower_levels": self.tower_levels(),
            "primes": self.primes(),
            "branches": self.branches(),
            "layers": [l.to_dict() for l in self._layers],
        }

    def __repr__(self) -> str:
        return (
            f"MaskStack(dim={self.cfg.dim}, k={self.cfg.k}, "
            f"n_layers={len(self._layers)}/{self.cfg.n_layers}, "
            f"local_first={self.cfg.local_first})"
        )


__all__ = [
    "MaskStack",
    "MaskStackConfig",
    "MaskLayer",
    "layer_carrier",
    "tower_level_for",
    "FEATURE_BITS",
    "K_MIN",
    "DEFAULT_K",
]
