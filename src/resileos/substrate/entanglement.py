"""Entanglement-style correlation measures for the substrate phase field.

The KuramotoField's r oscillators have phases theta in [0, 2pi). This
module partitions the field into two subsystems and computes:

    - mutual information between the subsystems' binned phase
      distributions
    - a CHSH-style correlator on binary thresholded outcomes

The CHSH test is the standard Bell test. A deterministic classical
hidden-variable model cannot exceed 2. The substrate is such a model:
the phase vector (theta_A, theta_B) at any time is the hidden
variable, and outcomes are deterministic functions of it. So the
expected result is CHSH <= 2 in all regimes.

This module reports the value. It does not claim violation unless the
measured value exceeds 2. The interpretation rule:

    LOCKED CHSH > 2   -> the substrate correlations look quantum-like
                         under this coarse-graining.
    all regimes <= 2  -> classical phase field. Any "quantum" behaviour
                         attributed to the substrate is external
                         interpretation, not an emergent property.

RES-308 (constructive head) is a separate classical directional head
and does not depend on this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .oscillator import KuramotoField


# ── partition ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Partition:
    indices_a: tuple[int, ...]
    indices_b: tuple[int, ...]

    def __post_init__(self) -> None:
        if set(self.indices_a) & set(self.indices_b):
            raise ValueError("partition groups must be disjoint")
        if not self.indices_a or not self.indices_b:
            raise ValueError("both groups must be non-empty")

    @property
    def size_a(self) -> int:
        return len(self.indices_a)

    @property
    def size_b(self) -> int:
        return len(self.indices_b)

    @property
    def total(self) -> int:
        return self.size_a + self.size_b


def partition(
    r: int,
    scheme: str = "half",
    seed: int = 0,
    indices_a: Optional[list[int]] = None,
    indices_b: Optional[list[int]] = None,
) -> Partition:
    """Split r oscillators into two disjoint groups.

    Schemes:
        "half"      first ceil(r/2) vs rest
        "even_odd"  even indices vs odd indices
        "random"    seeded random split (half and half)
        "custom"    explicit index lists via indices_a, indices_b
    """
    if r < 2:
        raise ValueError("r must be >= 2 for a partition")
    if scheme == "half":
        cut = (r + 1) // 2
        a = tuple(range(cut))
        b = tuple(range(cut, r))
    elif scheme == "even_odd":
        a = tuple(i for i in range(r) if i % 2 == 0)
        b = tuple(i for i in range(r) if i % 2 == 1)
    elif scheme == "random":
        rng = np.random.default_rng(seed)
        perm = rng.permutation(r)
        cut = r // 2
        a = tuple(sorted(int(i) for i in perm[:cut]))
        b = tuple(sorted(int(i) for i in perm[cut:]))
    elif scheme == "custom":
        if indices_a is None or indices_b is None:
            raise ValueError(
                "scheme='custom' requires indices_a and indices_b"
            )
        a = tuple(int(i) for i in indices_a)
        b = tuple(int(i) for i in indices_b)
        if any(not (0 <= i < r) for i in a + b):
            raise ValueError("indices out of range")
    else:
        raise ValueError(f"unknown scheme: {scheme!r}")
    return Partition(indices_a=a, indices_b=b)


# ── sampling ────────────────────────────────────────────────────────────
def sample_field(
    field: KuramotoField,
    n_steps: int,
    warmup: int = 0,
    W: Optional[np.ndarray] = None,
    epsilon: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Drive field for n_steps after warmup. Return (thetas, R_history).

    thetas has shape (n_steps, r). R_history has shape (n_steps,).
    """
    if W is None:
        W = np.ones((field.r, field.r)) - np.eye(field.r)
    for _ in range(warmup):
        field.step(epsilon=epsilon, W=W)
    thetas = np.zeros((n_steps, field.r), dtype=np.float64)
    rs = np.zeros(n_steps, dtype=np.float64)
    for i in range(n_steps):
        field.step(epsilon=epsilon, W=W)
        thetas[i] = field.theta.copy()
        rs[i] = field.order_parameter()
    return thetas, rs


# ── outcomes ────────────────────────────────────────────────────────────
def binary_outcome(theta_sub: np.ndarray, setting: float) -> int:
    """Majority-vote binary outcome for a subsystem at a given setting.

    Each oscillator votes sign(cos(theta_i - setting)) in {+1, -1}.
    The subsystem outcome is the sign of the sum. Ties resolve to +1.
    """
    votes = np.sign(np.cos(theta_sub - setting))
    votes[votes == 0.0] = 1.0
    total = float(np.sum(votes))
    return 1 if total >= 0.0 else -1


def correlator(
    thetas: np.ndarray,
    partition: Partition,
    a: float,
    b: float,
) -> float:
    """E(a, b) = mean over samples of A(theta_A, a) * B(theta_B, b)."""
    if thetas.shape[1] != partition.total:
        raise ValueError(
            f"thetas has {thetas.shape[1]} oscillators; "
            f"partition covers {partition.total}"
        )
    n = thetas.shape[0]
    theta_a = thetas[:, list(partition.indices_a)]
    theta_b = thetas[:, list(partition.indices_b)]
    a_out = np.zeros(n, dtype=np.int64)
    b_out = np.zeros(n, dtype=np.int64)
    for i in range(n):
        a_out[i] = binary_outcome(theta_a[i], a)
        b_out[i] = binary_outcome(theta_b[i], b)
    return float(
        np.mean(a_out.astype(np.float64) * b_out.astype(np.float64))
    )


def chsh_value(
    thetas: np.ndarray,
    partition: Partition,
    settings: tuple[float, float, float, float] = (
        0.0, np.pi / 2, np.pi / 4, -np.pi / 4,
    ),
) -> dict:
    """S = E(a1,b1) + E(a1,b2) + E(a2,b1) - E(a2,b2).

    Default settings are the standard CHSH-optimal angles for the
    quantum prediction. For a classical hidden-variable model (which
    the substrate is), |S| <= 2 always.
    """
    a1, a2, b1, b2 = settings
    e11 = correlator(thetas, partition, a1, b1)
    e12 = correlator(thetas, partition, a1, b2)
    e21 = correlator(thetas, partition, a2, b1)
    e22 = correlator(thetas, partition, a2, b2)
    S = e11 + e12 + e21 - e22
    return {
        "settings": {"a1": a1, "a2": a2, "b1": b1, "b2": b2},
        "E_a1_b1": e11,
        "E_a1_b2": e12,
        "E_a2_b1": e21,
        "E_a2_b2": e22,
        "S": float(S),
        "classical_bound": 2.0,
        "tsirelson_bound": 2.0 * np.sqrt(2.0),
        "violates_classical": bool(abs(S) > 2.0 + 1e-9),
    }


# ── mutual information ──────────────────────────────────────────────────
def mutual_information(
    thetas: np.ndarray,
    partition: Partition,
    n_bins: int = 8,
) -> float:
    """MI between circular-mean phase distributions of the two groups."""
    if thetas.shape[1] != partition.total:
        raise ValueError(
            f"thetas has {thetas.shape[1]} oscillators; "
            f"partition covers {partition.total}"
        )
    theta_a = thetas[:, list(partition.indices_a)]
    theta_b = thetas[:, list(partition.indices_b)]

    def circ_mean(x: np.ndarray) -> np.ndarray:
        return np.arctan2(
            np.mean(np.sin(x), axis=1), np.mean(np.cos(x), axis=1),
        ) % (2 * np.pi)

    mean_a = circ_mean(theta_a)
    mean_b = circ_mean(theta_b)
    bins = np.linspace(0.0, 2 * np.pi, n_bins + 1)
    joint, _, _ = np.histogram2d(mean_a, mean_b, bins=[bins, bins])
    joint = joint / joint.sum()
    p_a = joint.sum(axis=1)
    p_b = joint.sum(axis=0)
    mi = 0.0
    for i in range(n_bins):
        for j in range(n_bins):
            pij = joint[i, j]
            if pij > 0 and p_a[i] > 0 and p_b[j] > 0:
                mi += pij * np.log(pij / (p_a[i] * p_b[j]))
    return float(mi)


# ── scan ────────────────────────────────────────────────────────────────
def scan_regimes(
    r: int = 8,
    n_samples: int = 2000,
    warmup: int = 500,
    seed: int = 0,
    scheme: str = "half",
) -> dict:
    """Drive the field to three coupling regimes and report CHSH + MI.

    Returns a dict keyed by regime name with:
        kappa, R_mean, R_std, CHSH, correlators, MI, violates_classical,
        interpretation
    """
    settings = (0.0, np.pi / 2, np.pi / 4, -np.pi / 4)
    part = partition(r, scheme=scheme, seed=seed)

    out: dict = {}
    for regime, kappa in (
        ("EXPLORING", 0.1),
        ("MIXED", 1.0),
        ("LOCKED", 5.0),
    ):
        field = KuramotoField(
            r=r,
            ladder="golden_powers",
            kappa=kappa,
            alpha=0.5,
            dt=0.1,
            random_start=True,
            seed=seed,
        )
        thetas, rs = sample_field(
            field, n_steps=n_samples, warmup=warmup, epsilon=1.0,
        )
        chsh = chsh_value(thetas, part, settings)
        mi = mutual_information(thetas, part, n_bins=8)
        if chsh["violates_classical"]:
            interp = (
                "violates classical bound; evidence for emergence reading"
            )
        else:
            interp = (
                "within classical bound; consistent with classical "
                "phase field"
            )
        out[regime] = {
            "kappa": kappa,
            "R_mean": float(np.mean(rs)),
            "R_std": float(np.std(rs)),
            "CHSH": chsh["S"],
            "correlators": {
                "E_a1_b1": chsh["E_a1_b1"],
                "E_a1_b2": chsh["E_a1_b2"],
                "E_a2_b1": chsh["E_a2_b1"],
                "E_a2_b2": chsh["E_a2_b2"],
            },
            "MI": mi,
            "violates_classical": chsh["violates_classical"],
            "interpretation": interp,
        }
    return out


__all__ = [
    "Partition",
    "partition",
    "sample_field",
    "binary_outcome",
    "correlator",
    "chsh_value",
    "mutual_information",
    "scan_regimes",
]
