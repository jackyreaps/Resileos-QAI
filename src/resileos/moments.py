"""
Moment-bundle contract: (μ_hv, ν_hv) from a control packet.
Owning doc: RES-301.

FPE backend:
    The substrate uses a bipolar FPE. The backend is selected at import
    time by `resileos.substrate.fpe`:
        - leCore's FPE if importable, quantized to bipolar
        - in-house FPE otherwise
    Both paths satisfy the RES-300 §leCore boundary contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .substrate.fpe import fpe_encode_bipolar, backend_name


@dataclass(frozen=True)
class Seeds:
    factor: int
    scale: int
    scar: int
    monitor: int
    permute_uv: int
    permute_scar: int
    permute_scale: int
    permute_mon: int

    @classmethod
    def derived(cls, base: int) -> "Seeds":
        """RES-400 derived rule: permute_* = base + {0,1,2,3}."""
        return cls(
            factor=base, scale=base, scar=base, monitor=base,
            permute_uv=base + 0, permute_scar=base + 1,
            permute_scale=base + 2, permute_mon=base + 3,
        )


def fpe_encode(x: np.ndarray, dim: int, seed: int) -> np.ndarray:
    """
    Bipolar FPE. Backend selected by `resileos.substrate.fpe`.
    See module docstring.
    """
    return fpe_encode_bipolar(x, dim, seed)


def bundle(*vecs: np.ndarray) -> np.ndarray:
    s = np.sum(vecs, axis=0)
    return s / (np.linalg.norm(s) + 1e-12)


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    p = a * b
    return p / (np.linalg.norm(p) + 1e-12)


def permute(v: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return v[rng.permutation(len(v))]


def _mix_to_cos(mu: np.ndarray, nu: np.ndarray, target: float) -> np.ndarray:
    mu = mu / (np.linalg.norm(mu) + 1e-12)
    nu = nu / (np.linalg.norm(nu) + 1e-12)
    c = float(np.dot(mu, nu))
    a = 1.0 - target * target
    b = 2.0 * c * (1.0 - target * target)
    d = c * c - target * target
    disc = b * b - 4.0 * a * d
    if disc < 0.0 or a == 0.0:
        return nu
    g = (-b + np.sqrt(disc)) / (2.0 * a)
    out = nu + g * mu
    return out / (np.linalg.norm(out) + 1e-12)


def build_moments(packet: dict[str, Any] | Any,
                  dim: int,
                  seeds: Seeds,
                  target_cos: float = 0.3) -> tuple[np.ndarray, np.ndarray]:
    """
    μ_hv = bundle(M_U, M_V, M_scale, M_scar, M_mon)
    ν_hv = bundle(permute(M_U), permute(M_V),
                  M_scale_nu, permute(M_scar), M_mon_nu)
    with distinct seeds/permutations for scale and mon (RES-301).
    """
    get = (lambda k: packet[k]) if isinstance(packet, dict) else (lambda k: getattr(packet, k))

    M_U = fpe_encode(np.asarray(get("Ub")).ravel(), dim, seeds.factor)
    M_V = fpe_encode(np.asarray(get("Vb")).ravel(), dim, seeds.factor + 1)

    M_scale = bundle(
        fpe_encode(get("row_s_k"), dim, seeds.scale + 0),
        fpe_encode(get("col_s_k"), dim, seeds.scale + 1),
        fpe_encode(get("lat_s_k"), dim, seeds.scale + 2),
    )
    M_scar = fpe_encode(np.asarray(get("Lambda")).ravel(), dim, seeds.scar)
    M_mon = bind(
        fpe_encode(np.array([get("mu")], dtype=np.float64), dim, seeds.monitor + 0),
        fpe_encode(np.array([get("DeltaS")], dtype=np.float64), dim, seeds.monitor + 1),
    )

    mu_hv = bundle(M_U, M_V, M_scale, M_scar, M_mon)

    M_scale_nu = bundle(
        fpe_encode(get("row_s_k"), dim, seeds.permute_scale + 0),
        fpe_encode(get("col_s_k"), dim, seeds.permute_scale + 1),
        fpe_encode(get("lat_s_k"), dim, seeds.permute_scale + 2),
    )
    M_mon_nu = bind(
        fpe_encode(np.array([get("mu")], dtype=np.float64), dim, seeds.permute_mon + 0),
        fpe_encode(np.array([get("DeltaS")], dtype=np.float64), dim, seeds.permute_mon + 1),
    )

    nu_hv = bundle(
        permute(M_U, seeds.permute_uv),
        permute(M_V, seeds.permute_uv + 1),
        M_scale_nu,
        permute(M_scar, seeds.permute_scar),
        M_mon_nu,
    )

    nu_hv = _mix_to_cos(mu_hv, nu_hv, target=target_cos)
    return mu_hv, nu_hv


__all__ = [
    "Seeds", "fpe_encode", "bundle", "bind", "permute",
    "build_moments", "backend_name",
]
