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


# ── Residual-scale helpers (RES-200 §residual-scale grid) ──────────────────
def encode_exponent(s: float) -> int:
    """Float ε-grid value → int16 exponent with clamp (RES-202 round-trip)."""
    k = int(round(float(s) / EPS))
    return max(K_MIN, min(K_MAX, k))


def decode_exponent(k: int) -> float:
    return float(k) * EPS


# ── Packet ────────────────────────────────────────────────────────────────
@dataclass
class Packet:
    version: str
    Ub: np.ndarray
    Vb: np.ndarray
    row_s_k: np.ndarray          # int16[m]
    col_s_k: np.ndarray          # int16[n]
    lat_s_k: np.ndarray          # int16[r]
    Lambda: np.ndarray           # float32[r, r]
    mu: int                      # 0 or 1
    DeltaS: float
    F_res: float
    volume: float
    volume_ok: bool
    rank: int
    schedule_index: int
    sigma1_gate: bool = False
    sigma1_action: str = "NONE"
    packet_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("Ub", "Vb", "Lambda"):
            d[k] = np.asarray(d[k], dtype=np.float32)
        for k in ("row_s_k", "col_s_k", "lat_s_k"):
            d[k] = np.asarray(d[k], dtype=np.int16)
        return d


# ── Canonical JSON (RES-202) ──────────────────────────────────────────────
def _float_hex(x: float) -> str:
    """IEEE-754 hex, deterministic."""
    return float(x).hex()


def _canon(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return [_canon(v) for v in obj.ravel().tolist()]
    if isinstance(obj, (np.floating,)):
        return _float_hex(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, float):
        return _float_hex(obj)
    if isinstance(obj, dict):
        # sorted keys, packet_hash excluded upstream
        return {k: _canon(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    return str(obj)


def canonical_json(packet: Packet | dict[str, Any]) -> str:
    """
    Canonical JSON per RES-202:
        sorted keys, array order preserved, IEEE-754 hex floats,
        true/false/null literals, packet_hash excluded.
    """
    d = packet.to_dict() if isinstance(packet, Packet) else dict(packet)
    d.pop("packet_hash", None)
    return json.dumps(_canon(d), separators=(",", ":"), ensure_ascii=False)


def packet_hash(packet: Packet | dict[str, Any]) -> str:
    payload = canonical_json(packet).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
