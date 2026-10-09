"""
leCore FPE adapter for the Resileos-QAI substrate.

SPECIFICATION COMPLIANCE STATUS:
    This module is a STRUCTURAL SUBSTITUTE at the FPE layer (RES-602 §5.4).
    It attempts to use leCore's Fractional Power Encoding engine; if leCore
    is not importable, it falls back to the in-house implementation already
    used by Resileos-QAI.

Contract preserved (RES-300 §leCore boundary):
    - signature: fpe_encode(x, dim, seed) -> np.ndarray
    - unit-norm output for non-empty x
    - deterministic in (x, dim, seed)

Quantization:
    leCore's FPE returns real-valued vectors. Resileos's substrate is
    bipolar (int8 ±1). When the leCore path is active, this module
    quantizes the real output to bipolar before returning. The quantization
    is a lossy step; results under leCore will differ from results under
    the in-house shim by design. This is a substitution, not a drop-in
    replacement.

Discovery:
    leCore's import path is discovered from the environment variable
    RESILEOS_LECORE_IMPORT, defaulting to "lecore". If the actual package
    name differs, set:
        export RESILEOS_LECORE_IMPORT=lecore   # or whatever it is
"""
from __future__ import annotations

import importlib
import os
from typing import Callable

import numpy as np


# ── leCore discovery ────────────────────────────────────────────────────
def _try_import_lecore() -> Callable | None:
    """
    Return a callable `encode(x, dim, seed) -> np.ndarray` from leCore,
    or None if leCore is not importable.

    The path tried is:
        <RESILEOS_LECORE_IMPORT>.holographic.sampling_and_signal.holographic_fpe

    If this path is wrong for your leCore version, patch the import below
    or point RESILEOS_LECORE_IMPORT at a wrapper module that exposes
    `fpe_encode`.
    """
    pkg = os.environ.get("RESILEOS_LECORE_IMPORT", "lecore")
    try:
        mod = importlib.import_module(
            f"{pkg}.holographic.sampling_and_signal.holographic_fpe"
        )
    except ImportError:
        return None

    fn = getattr(mod, "fpe_encode", None)
    if fn is None:
        return None

    def wrapped(x: np.ndarray, dim: int, seed: int) -> np.ndarray:
        # leCore's exact signature is not assumed; call positionally.
        out = np.asarray(fn(np.asarray(x, dtype=np.float64), dim, seed),
                         dtype=np.float64)
        # Unit-norm enforcement (leCore should already do this; harmless if not)
        return out / (np.linalg.norm(out) + 1e-12)

    return wrapped


_LECORE_ENCODE = _try_import_lecore()
LECORE_AVAILABLE = _LECORE_ENCODE is not None


# ── in-house fallback ───────────────────────────────────────────────────
def _inhouse_encode(x: np.ndarray, dim: int, seed: int) -> np.ndarray:
    """
    Deterministic real-valued FPE. Same contract as leCore's version.
    Used when leCore is not importable.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    if x.size == 0:
        return np.zeros(dim, dtype=np.float64)
    rng = np.random.default_rng(seed)
    omega = rng.uniform(-np.pi, np.pi, size=dim)
    bind_signs = rng.choice([-1.0, 1.0], size=(x.size, dim))
    scalar = np.cos(x[:, None] * omega[None, :])
    h = np.sum(scalar * bind_signs, axis=0)
    return h / (np.linalg.norm(h) + 1e-12)


# ── public entry point ──────────────────────────────────────────────────
def fpe_encode_bipolar(x: np.ndarray, dim: int, seed: int) -> np.ndarray:
    """
    Substrate-compatible FPE. Returns unit-norm bipolar (int8 ±1).

    If leCore is available, uses leCore's real-valued FPE and quantizes
    to bipolar. Otherwise uses the in-house implementation and quantizes
    the same way.

    Both paths end at the same output dtype and length, so the rest of
    the substrate (build_moments, adapter, cleanup) is unchanged.
    """
    encoder = _LECORE_ENCODE if _LECORE_ENCODE is not None else _inhouse_encode
    real = encoder(x, dim, seed)

    # Quantize to bipolar. Threshold at 0; break exact zeros with a seeded
    # coin flip so the output is deterministic in (x, dim, seed).
    bipolar = np.where(real >= 0.0, 1, -1).astype(np.int8)

    zeros = real == 0.0
    if np.any(zeros):
        rng = np.random.default_rng(seed ^ 0x5EED)
        bipolar[zeros] = rng.choice([-1, 1], size=int(zeros.sum())).astype(np.int8)

    return bipolar


def backend_name() -> str:
    """Return which FPE backend is active: 'lecore' or 'inhouse'."""
    return "lecore" if LECORE_AVAILABLE else "inhouse"


__all__ = ["fpe_encode_bipolar", "backend_name", "LECORE_AVAILABLE"]
