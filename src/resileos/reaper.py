"""
Reaper pass.

Splits the channels of an input vector at capacity N_saved = 36 into
two sides:

    Henad   saved side. Neoplatonic unit prior to number.
    Nexus   debt side. Roman-law bond pledged against a debt.

Channels that stay are Henad. Channels that are removed are Nexus and
are zeroed. Read-only.

Worked example: 40 channels, N_saved = 36 -> 36 Henad, 4 Nexus,
fraction 0.10.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .packet import decode_exponent


N_SAVED_DEFAULT = 36


def reaper_pass(x: np.ndarray,
                n_saved: int = N_SAVED_DEFAULT,
                weights: Optional[np.ndarray] = None,
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Split channels into Henad (saved) and Nexus (debt).

    Parameters
    ----------
    x : 1D array of non-negative values, one entry per channel.
    n_saved : capacity. Default 36.
    weights : optional ranking key. Defaults to x.

    Returns
    -------
    henad_values    same shape as x, nonzero only on Henad channels
    henad_idx       channels kept (Henad)
    nexus_idx       channels removed (Nexus)
    nexus_fraction  removed / total
    """
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError(f"x must be 1D, got shape {x.shape}")
    if n_saved < 0:
        raise ValueError("n_saved must be >= 0")
    if np.any(x < 0):
        raise ValueError("x must be non-negative")

    n = x.size
    total = float(np.sum(np.abs(x)))

    if n == 0:
        return x.copy(), np.array([], dtype=np.int64), \
               np.array([], dtype=np.int64), 0.0

    if n <= n_saved:
        return x.copy(), np.arange(n, dtype=np.int64), \
               np.array([], dtype=np.int64), 0.0

    scores = x if weights is None else np.asarray(weights, dtype=np.float64)
    if scores.shape != x.shape:
        raise ValueError(
            f"weights shape {scores.shape} != x shape {x.shape}")

    order = np.lexsort((np.arange(n), -scores))
    henad_idx = np.sort(order[:n_saved]).astype(np.int64)
    nexus_idx = np.sort(order[n_saved:]).astype(np.int64)

    henad_values = np.zeros_like(x)
    henad_values[henad_idx] = x[henad_idx]

    henad_sum = float(np.sum(np.abs(henad_values[henad_idx])))
    nexus_sum = total - henad_sum
    nexus_fraction = nexus_sum / (total + 1e-30)

    return henad_values, henad_idx, nexus_idx, nexus_fraction


def reaper_from_latent(packet: Any,
                       n_saved: int = N_SAVED_DEFAULT,
                       weights: Optional[np.ndarray] = None,
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Bridge: read lat_s_k from a packet, decode each int16 exponent via
    decode_exponent (ε = 1/64 grid), and run reaper_pass.
    """
    get = (lambda k: packet[k]) if isinstance(packet, dict) \
          else (lambda k: getattr(packet, k))
    lat_s_k = np.asarray(get("lat_s_k"), dtype=np.int16)
    x = np.array([abs(decode_exponent(int(k))) for k in lat_s_k],
                 dtype=np.float64)
    return reaper_pass(x, n_saved=n_saved, weights=weights)


__all__ = ["N_SAVED_DEFAULT", "reaper_pass", "reaper_from_latent"]
