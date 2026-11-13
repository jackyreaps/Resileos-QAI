"""Temporal residual clip codec.

Frame 0 is a base packet from the studio codec (layer scale, bipolar
factors, one scale per layer). Each later frame is the residual of that
frame against the previous packet's chain reconstruction, encoded with
the same stack as a delta packet.

The sequence is one base packet, the delta packets for frames that clear
the temporal sigma gate, and a SHA-256 over those packets. A later frame
whose residual RMS stays at or under the gate is marked
``residual-consistent, reuse previous packet`` and does not add a packet.
Bits per frame are the studio logical bits of the packets that were stored.

Phase step and mirror energy are ``motion_vector`` and ``mirror_check``
from ``residual_frame``. This module does not reimplement that math, does
not sample a prompt, and does not call ``ResidualCore.step``, ``learn``,
or ``_scar_update``.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from studio.codec import decode, encode  # noqa: E402
from studio.codec import logical_bits, pack_packet  # noqa: E402

from resileos.phi_compress import contract_depth, contract_rank
from resileos.studio.residual_cascade import ACCEPT_ENERGY, LAYER_GAIN
from resileos.ui.frame_codec import project_gray
from resileos.ui.five_pin import keep_packet
from resileos.ui.residual_frame import (
    apply_residual,
    as_gray,
    bilinear_upsample,
    frame_residual,
    mirror_check,
    motion_vector,
)

CLIP_VERSION = "studio-clip/1"
# RMS of R_t = frame_t - previous reconstruction. At or under this, the
# frame reuses the previous packet and is not a generative escalation.
TEMPORAL_SIGMA = 0.05
REUSE_MARK = "residual-consistent, reuse previous packet"
_MAX_FRAMES = 8
_MAX_SIDE = 16


def _factor_lists(array: Any) -> list[list[int]]:
    signed = np.sign(np.asarray(array, dtype=np.float64))
    signed = np.array(signed, dtype=np.float64, copy=True)
    signed[signed == 0.0] = 1.0
    return [[int(value) for value in row] for row in signed.tolist()]


def _scale_token(value: Any) -> str:
    """Float32 scale as hex so a JSON round trip does not move the hash."""
    return np.asarray(np.float32(value)).tobytes().hex()


def _scale_float(value: Any) -> float:
    if isinstance(value, str):
        raw = bytes.fromhex(value)
        if len(raw) != 4:
            raise ValueError("scale hex must be 4 bytes")
        return float(np.frombuffer(raw, dtype=np.float32)[0])
    if isinstance(value, (list, tuple)):
        raise ValueError("layer scale must be one scalar")
    return float(value)


def numeric_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Packet with numeric scales, ready for the studio decode and pack."""
    if packet.get("scale_mode") != "layer":
        raise ValueError("clip packets use one scale per layer")
    layers: list[dict[str, Any]] = []
    for layer in packet["layers"]:
        if isinstance(layer.get("scale"), (list, tuple)):
            raise ValueError("layer scale must be one scalar")
        scale = _scale_float(layer["scale"])
        layers.append(
            {
                "Ub": layer["Ub"],
                "Vb": layer["Vb"],
                "scale": scale,
            }
        )
    return {
        "version": packet["version"],
        "shape": [int(packet["shape"][0]), int(packet["shape"][1])],
        "rank": int(packet["rank"]),
        "n_layers": int(packet["n_layers"]),
        "scale_mode": "layer",
        "basis": str(packet.get("basis") or "random"),
        "layers": layers,
        "logical_bits": int(packet["logical_bits"]),
    }


def _public_packet(raw: dict[str, Any]) -> dict[str, Any]:
    numeric = numeric_packet(
        {
            **raw,
            "layers": [
                {
                    "Ub": _factor_lists(layer["Ub"]),
                    "Vb": _factor_lists(layer["Vb"]),
                    "scale": float(layer["scale"]),
                }
                for layer in raw["layers"]
            ],
        }
    )
    stored_layers = []
    for layer in numeric["layers"]:
        stored_layers.append(
            {
                "Ub": layer["Ub"],
                "Vb": layer["Vb"],
                "scale": _scale_token(layer["scale"]),
            }
        )
    stored = dict(numeric)
    stored["layers"] = stored_layers
    stored["logical_bits"] = int(
        logical_bits(
            int(numeric["shape"][0]),
            int(numeric["shape"][1]),
            int(numeric["rank"]),
            int(numeric["n_layers"]),
            "layer",
        )
    )
    return stored


def _energy(original: np.ndarray, recon: np.ndarray) -> float:
    diff = np.asarray(original, dtype=np.float64) - np.asarray(recon, dtype=np.float64)
    denom = float(np.sum(np.asarray(original, dtype=np.float64) ** 2)) + 1e-12
    return float(np.sum(diff**2) / denom)


def _fit(matrix: np.ndarray, rank: int, n_layers: int, seed: int) -> dict[str, Any]:
    raw = encode(
        matrix,
        rank=int(rank),
        n_layers=int(n_layers),
        seed=int(seed),
        scale_mode="layer",
    )
    public = _public_packet(raw)
    numeric = numeric_packet(public)
    recon = decode(numeric)
    return {
        "packet": public,
        "recon": recon,
        "energy": _energy(matrix, recon),
        "scales": [float(layer["scale"]) for layer in numeric["layers"]],
        "rank": int(public["rank"]),
        "n_layers": int(public["n_layers"]),
        "logical_bits": int(public["logical_bits"]),
    }


def _prefer(current: dict[str, Any] | None, trial: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return trial
    if trial["energy"] < current["energy"] - 1e-9:
        return trial
    if current["energy"] < trial["energy"] - 1e-9:
        return current
    if trial["logical_bits"] < current["logical_bits"]:
        return trial
    return current


def _encode_residual(matrix: np.ndarray, *, rank: int, n_layers: int, seed: int) -> dict[str, Any]:
    """Greedy layer-scale stack. Same close rule as the still cascade."""
    height, width = int(matrix.shape[0]), int(matrix.shape[1])
    cap = min(height, width)
    requested_rank = max(1, min(int(rank), cap))
    requested_layers = max(1, int(n_layers))
    ceiling_rank = max(1, min(cap, contract_rank(requested_rank)))
    ceiling_layers = max(1, contract_depth(requested_layers))
    ranks: list[int] = []
    for item in (1, ceiling_rank):
        if 1 <= item <= cap and item not in ranks:
            ranks.append(item)
    chosen: dict[str, Any] | None = None
    for item in ranks:
        chosen = _prefer(chosen, _fit(matrix, item, 1, seed))
    assert chosen is not None
    while chosen["n_layers"] < ceiling_layers and chosen["energy"] > ACCEPT_ENERGY:
        nxt = _fit(matrix, chosen["rank"], chosen["n_layers"] + 1, seed)
        if abs(float(nxt["scales"][-1])) < 1e-8:
            break
        if chosen["energy"] - nxt["energy"] < LAYER_GAIN:
            break
        chosen = nxt
    return chosen


def packet_hash(packet: dict[str, Any]) -> str:
    return hashlib.sha256(pack_packet(numeric_packet(packet))).hexdigest()


def sequence_digest(base: dict[str, Any], deltas: list[dict[str, Any]]) -> str:
    """SHA-256 over the base packet and the delta packets, in order."""
    hasher = hashlib.sha256()
    hasher.update(pack_packet(numeric_packet(base)))
    for delta in deltas:
        hasher.update(pack_packet(numeric_packet(delta)))
    return hasher.hexdigest()


def _as_frames(frames: Any) -> list[Any]:
    if isinstance(frames, np.ndarray) and frames.ndim == 3:
        return [frames[index] for index in range(int(frames.shape[0]))]
    if isinstance(frames, (list, tuple)):
        return list(frames)
    raise ValueError("frames must be a list of gray or color matrices")


def prepare_frames(frames: Any) -> list[np.ndarray]:
    """Gray frames on one grid. Larger than 16 on a side is projected to 8×8."""
    raw = _as_frames(frames)
    if not raw:
        raise ValueError("a clip needs at least one frame")
    if len(raw) > _MAX_FRAMES:
        raw = raw[:_MAX_FRAMES]
    prepared: list[np.ndarray] = []
    for frame in raw:
        prepared.append(as_gray(frame))
    shape = prepared[0].shape
    aligned: list[np.ndarray] = []
    for frame in prepared:
        if frame.shape != shape:
            frame = bilinear_upsample(frame, (int(shape[0]), int(shape[1])))
        aligned.append(frame)
    if max(int(shape[0]), int(shape[1])) > _MAX_SIDE:
        aligned = [project_gray(frame, 8, 8) for frame in aligned]
    return aligned


def temporal_magnitude(residual: Any) -> float:
    """RMS of a temporal residual. Not a bit count and not a savings claim."""
    array = np.asarray(residual, dtype=np.float64)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("temporal residual must be finite")
    return float(np.sqrt(np.mean(array * array)))


def _bits_report(
    base: dict[str, Any],
    deltas: list[dict[str, Any]],
    *,
    frames: int,
    reused: int,
    generative: int,
) -> dict[str, Any]:
    delta_bits = [int(packet["logical_bits"]) for packet in deltas]
    mean_delta = float(np.mean(delta_bits)) if delta_bits else 0.0
    return {
        "base": int(base["logical_bits"]),
        "deltas": delta_bits,
        "mean_delta": mean_delta,
        "frames": int(frames),
        "reused_frames": int(reused),
        "generative_frames": int(generative),
    }


def encode_sequence(
    frames: Any,
    *,
    rank: int = 4,
    n_layers: int = 4,
    seed: int = 0,
) -> dict[str, Any]:
    """Encode supplied frames. Nothing here samples pixels from a prompt."""
    prepared = prepare_frames(frames)
    packets: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    recons: list[np.ndarray] = []
    previous = np.zeros_like(prepared[0])
    previous_hash = ""
    magnitudes: list[float] = []
    for index, frame in enumerate(prepared):
        residual = frame_residual(frame, previous)
        magnitude = temporal_magnitude(residual)
        magnitudes.append(magnitude)
        motion = motion_vector(residual)
        mirror = mirror_check(residual)
        under_gate = index > 0 and magnitude <= TEMPORAL_SIGMA
        if under_gate:
            current = np.array(previous, copy=True)
            recons.append(current)
            steps.append(
                {
                    "index": index,
                    "kind": "reuse",
                    "disposition": REUSE_MARK,
                    "packet_hash": previous_hash,
                    "logical_bits": 0,
                    "residual_energy": _energy(frame, current),
                    "coding_energy": 0.0,
                    "temporal_magnitude": magnitude,
                    "escalated": False,
                    "keyframe": False,
                    "motion": motion,
                    "mirror": mirror,
                }
            )
            timeline.append(
                {
                    "index": index,
                    "source": "reuse",
                    "disposition": REUSE_MARK,
                    "packet_hash": previous_hash,
                }
            )
            continue
        coded = _encode_residual(residual, rank=rank, n_layers=n_layers, seed=seed)
        decoded_residual = np.asarray(coded["recon"], dtype=np.float64)
        current = apply_residual(previous, decoded_residual)
        digest = packet_hash(coded["packet"])
        packets.append(coded["packet"])
        recons.append(current)
        kind = "base" if index == 0 else "delta"
        escalated = index > 0
        steps.append(
            {
                "index": index,
                "kind": kind,
                "disposition": "base keyframe" if index == 0 else "escalated",
                "packet_hash": digest,
                "logical_bits": int(coded["logical_bits"]),
                "residual_energy": _energy(frame, current),
                "coding_energy": float(coded["energy"]),
                "temporal_magnitude": magnitude,
                "escalated": escalated,
                "keyframe": True,
                "motion": motion,
                "mirror": mirror,
            }
        )
        timeline.append(
            {
                "index": index,
                "source": "base" if index == 0 else "delta",
                "disposition": "base keyframe" if index == 0 else "escalated",
                "packet_hash": digest,
            }
        )
        previous = current
        previous_hash = digest
    base = packets[0]
    deltas = packets[1:]
    digest = sequence_digest(base, deltas)
    energies = [float(step["residual_energy"]) for step in steps]
    later = magnitudes[1:]
    keyframe_ids = [int(step["index"]) for step in steps if step["keyframe"]]
    reused = sum(1 for step in steps if step["kind"] == "reuse")
    generative = sum(1 for step in steps if step["escalated"])
    return {
        "version": CLIP_VERSION,
        "base": base,
        "deltas": deltas,
        "timeline": timeline,
        "sequence_hash": digest,
        "bits_per_frame": _bits_report(
            base,
            deltas,
            frames=len(prepared),
            reused=reused,
            generative=generative,
        ),
        "steps": steps,
        "shape": [int(prepared[0].shape[0]), int(prepared[0].shape[1])],
        "n_frames": len(prepared),
        "frame_energy": energies,
        "energy": float(np.mean(energies)) if energies else 0.0,
        "energy_closed": bool(energies) and max(energies) <= ACCEPT_ENERGY,
        # Recorded only. Does not replace TEMPORAL_SIGMA or ACCEPT_ENERGY.
        "kept": keep_packet(float(np.mean(energies)) if energies else 0.0),
        "sigma": TEMPORAL_SIGMA,
        "temporal_delta": float(max(later) if later else 0.0),
        "keyframe_ids": keyframe_ids,
        "frame_residuals": [str(step["packet_hash"]) for step in steps],
        "learned": False,
        "learn_called": False,
        "scar_matrix_updated": False,
        "step_core": False,
        "generative": False,
        "engine": "studio-codec/1",
        "scale_mode": "layer",
        "_prepared": prepared,
        "_recons": recons,
    }


def decode_sequence(sequence: dict[str, Any]) -> list[np.ndarray]:
    """Rebuild the chain from the base packet and the delta packets."""
    if not isinstance(sequence, dict) or sequence.get("version") != CLIP_VERSION:
        raise ValueError("packet is not a clip sequence")
    base = sequence.get("base")
    deltas = sequence.get("deltas")
    if not isinstance(base, dict) or not isinstance(deltas, list):
        raise ValueError("clip sequence needs a base packet and delta packets")
    current = decode(numeric_packet(base))
    timeline = sequence.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        frames = [np.asarray(current, dtype=np.float64)]
        for delta in deltas:
            if not isinstance(delta, dict):
                raise ValueError("a delta packet is missing")
            residual = decode(numeric_packet(delta))
            current = apply_residual(current, residual)
            frames.append(np.asarray(current, dtype=np.float64))
        return frames
    frames = []
    delta_index = 0
    for item in timeline:
        if not isinstance(item, dict):
            raise ValueError("timeline entry is missing")
        source = str(item.get("source") or "")
        if source == "base":
            frames.append(np.asarray(current, dtype=np.float64))
            continue
        if source == "reuse":
            frames.append(np.array(current, dtype=np.float64, copy=True))
            continue
        if source == "delta":
            if delta_index >= len(deltas) or not isinstance(deltas[delta_index], dict):
                raise ValueError("a delta packet is missing")
            residual = decode(numeric_packet(deltas[delta_index]))
            delta_index += 1
            current = apply_residual(current, residual)
            frames.append(np.asarray(current, dtype=np.float64))
            continue
        raise ValueError("unknown timeline source")
    if delta_index != len(deltas):
        raise ValueError("delta packets do not match the timeline")
    return frames


def public_sequence(encoded: dict[str, Any]) -> dict[str, Any]:
    """Drop the working arrays. Safe to store and to send as JSON."""
    return {
        key: value
        for key, value in encoded.items()
        if key not in {"_prepared", "_recons"}
    }


__all__ = [
    "CLIP_VERSION",
    "REUSE_MARK",
    "TEMPORAL_SIGMA",
    "decode_sequence",
    "encode_sequence",
    "numeric_packet",
    "packet_hash",
    "prepare_frames",
    "public_sequence",
    "sequence_digest",
    "temporal_magnitude",
]
