"""Layered mask stack (RES-312).

A constructive multi-resolution partition over the substrate's feature set.
At small scale, a mask is a binary selection over optional feature bits and
the partition boundary is a curve. At large scale, with layered masks, the
boundary saturates and becomes a membrane — the mask-to-sheath transition.

Local/global orientation (this revision):
    Layer carriers are ordered along a local-to-global phase axis. Local
    layers oscillate rapidly across the hypervector dimension; global layers
    oscillate slowly. Adjacent layers differ in phase frequency by a factor
    of PHI, which is the most irrational ratio available, so no two layers
    alias into each other. This ordering is the orientation axis.

    This replaces the previous design, which seeded each feature bit's
    carrier independently and bundled the set bits' carriers into one
    carrier per layer. The bundled design had two defects:

      (1) Two masks that shared bits produced correlated carriers, which
          forced a near-orthogonality rejection at add_layer. The rejection
          threshold was arbitrary and blocked legitimate nested masks.

      (2) The ordering of layers had no representation in carrier space,
          so downstream consumers (RES-307 agency routing, RES-315
          modulation) could not read orientation from the stack. A routing
          agent had to be told the layer index separately; it could not
          determine its position from the carrier alone.

    The positional design fixes both. Layers are near-orthogonal by
    construction (pairwise correlation ~1/dim), and the local/global axis
    is explicit in the phase frequency. The axis orients agency: an agent
    that reads the mask stack can determine which layer it is operating
    in from the carrier's phase frequency, without the layer index being
    passed separately.

Spec: docs/310-hierarchy/mask-stack.md

Off states (explicit):
    learned structure   off. Masks are supplied by the caller. The stack
                        does not search for optimal masks.
    compression claim   off. The stack is a re-encoding, not a reduction.
                        Information content is preserved, with crosstalk.
    semantic claim      off. Layer indices are depth-ordered on a
                        local/global axis, not semantically ordered.
    capacity guarantee  off. The stack's capacity is bounded by RES-313.
    sheath as failure   off. The sheath is a regime, not a failure.
                        Whether it is desirable is a RES-315 decision.
    bit_derived carrier off. Carriers are not derived from the mask's set
                        bits. The mask is metadata that describes the
                        feature selection; the carrier describes the
                        layer's position on the local/global axis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ..codex import PHI


# ── feature bit names (RES-312 §1) ──────────────────────────────────────
FEATURE_BITS: tuple[str, ...] = (
    "csi",
    "order_parameter",
    "direction",
)
K_MIN: int = len(FEATURE_BITS)
DEFAULT_K: int = 4


# ── positional layer carrier ────────────────────────────────────────────
def exponent_for(
    layer_index: int,
    n_layers: int,
    local_first: bool = True,
) -> int:
    """Phase exponent for a layer. Exposed for downstream consumers that
    need to reason about the axis directly (e.g. RES-307 routing)."""
    if n_layers < 1:
        raise ValueError("n_layers must be >= 1")
    if not (0 <= layer_index < n_layers):
        raise ValueError(
            f"layer_index {layer_index} out of range [0, {n_layers})"
        )
    if local_first:
        # layer 0 = local -> highest exponent
        return n_layers - layer_index + 1
    # layer 0 = global -> lowest exponent
    return layer_index + 2


def layer_carrier(
    layer_index: int,
    n_layers: int,
    dim: int,
    local_first: bool = True,
) -> np.ndarray:
    """φ-power positional carrier for a layer.

    multiplier = PHI ** exponent_for(layer_index, n_layers, local_first)
    phase[d]   = 2π · multiplier · d          for d = 0 .. dim-1
    carrier[d] = exp(i · phase[d]) / sqrt(dim)

    Adjacent layers differ in multiplier by a power of PHI, which has
    irrational fractional part, so the Dirichlet kernel between any two
    layers is ~1/dim. All pairs are near-orthogonal by construction.
    """
    if dim < 2:
        raise ValueError("dim must be >= 2")
    exponent = exponent_for(layer_index, n_layers, local_first)
    multiplier = float(PHI) ** exponent
    d = np.arange(dim, dtype=np.float64)
    phases = 2.0 * np.pi * multiplier * d
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
    carrier    positional φ-power carrier (local/global axis).
    weight     contribution to the stack bundle, default 1 / (l + 1).
    exponent   φ-exponent used to build the carrier, exposed for routing.
    """
    mask: tuple[bool, ...]
    carrier: np.ndarray
    weight: float
    exponent: int

    def __post_init__(self) -> None:
        if not isinstance(self.mask, tuple):
            self.mask = tuple(self.mask)
        if not all(isinstance(b, (bool, np.bool_)) for b in self.mask):
            raise TypeError("mask must be a tuple of bool")
        self.weight = float(self.weight)
        self.exponent = int(self.exponent)

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
            "exponent": int(self.exponent),
            "n_set": self.n_set,
        }


# ── stack ───────────────────────────────────────────────────────────────
@dataclass
class MaskStackConfig:
    """Configuration for a MaskStack.

    dim           hypervector dimension. Must match stream_hv and codex.
    k             number of feature bits per mask. Must be >= K_MIN (3).
    n_layers      expected layer count. add_layer raises past this.
    local_first   True  -> layer 0 is local (high phase freq),
                           layer n-1 is global (low phase freq).
                  False -> layer 0 is global, layer n-1 is local.
    seed          reserved. Not consumed. The current carrier generation
                  is deterministic (φ-power ladder, no RNG).
    """
    dim: int
    k: int = DEFAULT_K
    n_layers: int = 3
    local_first: bool = True
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
        self.local_first = bool(self.local_first)
        self.seed = int(self.seed)


class MaskStack:
    """Layered mask stack (RES-312 §5).

    Construction:
        stack = MaskStack(MaskStackConfig(dim=512, k=4, n_layers=3))
        stack.add_layer(mask=(True, True, True, False))
        stack.add_layer(mask=(True, True, False, False))
        stack.add_layer(mask=(True, False, False, False))
        hv = stack.encode(stream_hv)

    The mask passed to add_layer is metadata. It does not influence the
    carrier; the carrier is determined by the layer's position on the
    local/global axis. Two stacks with the same config produce the same
    carriers regardless of the masks supplied.

    is_saturated(codim, depth) returns True when the caller-supplied
    sheath measurement satisfies the RES-312 §4 criterion.
    """

    def __init__(self, cfg: MaskStackConfig) -> None:
        if not isinstance(cfg, MaskStackConfig):
            raise TypeError("cfg must be a MaskStackConfig")
        self.cfg = cfg
        self._layers: list[MaskLayer] = []

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

    def exponents(self) -> list[int]:
        """φ-exponents of every layer, in layer order. The orientation
        axis for downstream consumers."""
        return [l.exponent for l in self._layers]

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
        exponent = exponent_for(idx, self.cfg.n_layers, self.cfg.local_first)
        carrier = layer_carrier(
            idx, self.cfg.n_layers, self.cfg.dim, self.cfg.local_first
        )
        weight = 1.0 / (idx + 1)
        layer = MaskLayer(
            mask=mask_t, carrier=carrier, weight=weight, exponent=exponent
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
            "exponents": self.exponents(),
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
    "exponent_for",
    "FEATURE_BITS",
    "K_MIN",
    "DEFAULT_K",
]
