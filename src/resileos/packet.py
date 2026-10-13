"""
Control packet schema, canonical serialization, and hashing.
Owning docs: RES-201 (schema), RES-202 (canonicalization).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

EPS = 1.0 / 64.0
K_MIN, K_MAX = -16, 16


def encode_exponent(s: float) -> int:
    """Float ε-grid value → int16 exponent with clamp (RES-202 round-trip)."""
    k = int(round(float(s) / EPS))
    return max(K_MIN, min(K_MAX, k))


def decode_exponent(k: int) -> float:
    return float(k) * EPS


@dataclass
class Packet:
    version: str
    Ub: np.ndarray
    Vb: np.ndarray
    row_s_k: np.ndarray
    col_s_k: np.ndarray
    lat_s_k: np.ndarray
    Lambda: np.ndarray           # scar matrix, diagonal pinned to 1
    mu: int
    DeltaS: float
    F_res: float
    volume: float
    volume_ok: bool
    rank: int
    schedule_index: int
    sigma1_gate: bool = False
    sigma1_action: str = "NONE"
    packet_hash: str = ""
    # Non-conservative extension (RES-200 §extension). Complex diagonal
    # with prod(D) = 1. Defaults to empty; the core fills it in. When
    # empty, the packet represents conservative mode (D = I).
    # J = diag(D) + strict_lower(Lambda), so det(J) = prod(D) = 1.
    D: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.complex128)
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("Ub", "Vb", "Lambda"):
            d[k] = np.asarray(d[k], dtype=np.float32)
        for k in ("row_s_k", "col_s_k", "lat_s_k"):
            d[k] = np.asarray(d[k], dtype=np.int16)
        d["D"] = np.asarray(self.D, dtype=np.complex128)
        return d


# ── canonical JSON (RES-202) ──────────────────────────────────────────
def _float_hex(x: float) -> str:
    return float(x).hex()


def _complex_hex(z: complex) -> dict:
    return {"re": _float_hex(z.real), "im": _float_hex(z.imag)}


def _canon(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return [_canon(v) for v in obj.ravel().tolist()]
    if isinstance(obj, (np.floating,)):
        return _float_hex(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.complexfloating, complex)):
        z = complex(obj)
        return _complex_hex(z)
    if isinstance(obj, float):
        return _float_hex(obj)
    if isinstance(obj, dict):
        return {k: _canon(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    return str(obj)


def canonical_json(packet) -> str:
    """
    Canonical JSON per RES-202: sorted keys, array order preserved,
    IEEE-754 hex floats, true/false/null literals, packet_hash excluded.
    Complex values are encoded as {"re": hex, "im": hex}.
    """
    d = packet.to_dict() if isinstance(packet, Packet) else dict(packet)
    d.pop("packet_hash", None)
    return json.dumps(_canon(d), separators=(",", ":"), ensure_ascii=False)


def packet_hash(packet) -> str:
    payload = canonical_json(packet).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
