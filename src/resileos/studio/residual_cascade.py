"""Residual-guided cascade from a cheap layer-scale packet to a still candidate.

The studio codec (`scripts/studio/codec.py`, scale mode ``layer``) is the
quantizer. One scale multiplies each rank-r product. Phi-compression sets
the rank and depth ceiling below a native high-resolution budget, and the
walk starts at the cheaper end. ``KuramotoField`` is stepped outward only.
A still is a candidate. It is not a fact, not a ``local_gen`` tint, and not
a production video.

An external upscale slot runs only when that residual check is inconclusive.
It receives the residual delta of the frames that did not close, and it
returns an asset URL. No weights are vendored. With no provider the slot
stays unavailable and does not invent a URL.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from studio.codec import decode, encode, logical_bits, pack_packet  # noqa: E402

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    apollo_success,
    confidence_route,
    evidence_attach,
    residual_consistency,
    risk_classify,
)
from resileos.kin.demigods.checks import hephaestus_check
from resileos.kin.demigods.hierarchy import active_demigod
from resileos.moments import bind, fpe_encode
from resileos.phi_compress import contract_depth, contract_rank
from resileos.studio.candidates import register_candidate
from resileos.studio.codecs import project_gray
from resileos.substrate.oscillator import KuramotoField
from resileos.ui.cascade_address import cascade_address
from resileos.ui.scale_address import scale_address

# Relative residual energy at which one layer-scale packet closes the still.
# This is not a photograph score and it is not an 8×8 digit PSNR.
ACCEPT_ENERGY = 0.05
# A further outward layer has to move the residual by at least this much.
LAYER_GAIN = 0.02
_INDEX: dict[tuple[str, str], dict[str, Any]] = {}
_INDEX_CAP = 256


class VisualPathError(RuntimeError):
    """A visual or legion path tried to write a fact or skip Zeus."""


def reset_residual_index() -> None:
    """Drop accepted graphify residuals. Tests use this. It is not the core."""
    _INDEX.clear()


def query_residual(subject: str, relation: str) -> dict[str, Any]:
    """Deterministic lookup of an accepted residual candidate.

    A miss abstains. This does not call ``learn`` and it does not read a model.
    """
    row = _INDEX.get((str(subject), str(relation)))
    if row is None:
        return {
            "status": "ABSTAINED",
            "rows": [],
            "reason": "no residual rows for this choice",
            "deterministic": True,
            "learned": False,
        }
    return {
        "status": "ok",
        "obj": row["obj"],
        "packet_hash": row["packet_hash"],
        "hypervector": list(row["hypervector"]),
        "deterministic": True,
        "learned": False,
    }


def remember_accepted(
    subject: str,
    relation: str,
    obj: str,
    evolved: dict[str, Any],
) -> None:
    """Index one Eat-accepted triple by its residual hash.

    The index is what a later question reads. It is not a residual-core write.
    """
    if not subject or not relation or not obj:
        return
    digest = str(evolved.get("packet_hash") or "")
    if not digest:
        return
    vector = list(evolved.get("hypervector") or [])
    if not vector:
        vector = _claim_vector(subject, relation, obj)
    key = (str(subject), str(relation))
    _INDEX.pop(key, None)
    _INDEX[key] = {
        "obj": str(obj),
        "packet_hash": digest,
        "hypervector": vector,
    }
    while len(_INDEX) > _INDEX_CAP:
        _INDEX.pop(next(iter(_INDEX)))


def text_matrix(text: str, m: int = 8, n: int = 8) -> np.ndarray:
    """Pack text into a small matrix. Deterministic. Not a picture generator."""
    raw = str(text or "").encode("utf-8")[: m * n]
    values = np.zeros(m * n, dtype=np.float64)
    if raw:
        values[: len(raw)] = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) / 255.0
    return values.reshape(m, n)


def _claim_vector(subject: str, relation: str, obj: str) -> list[float]:
    """Bind the triple into one hypervector. Later asks read the stored record."""
    dim = 32

    def _vec(text: str, seed: int) -> np.ndarray:
        raw = np.frombuffer(str(text).encode("utf-8"), dtype=np.uint8).astype(np.float64)
        if raw.size == 0:
            raw = np.zeros(1, dtype=np.float64)
        return fpe_encode(raw, dim, seed)

    bound = bind(bind(_vec(subject, 11), _vec(relation, 12)), _vec(obj, 13))
    return [round(float(x), 6) for x in bound]


def _refuse_bypass(*, learn: Any, bypass_zeus: bool, zeus: Any) -> None:
    if bypass_zeus or zeus is not None:
        raise VisualPathError("a visual path cannot bypass Zeus routing")
    if learn is not None:
        raise VisualPathError("a visual path cannot call learn")


def _prepare_matrix(matrix: Any) -> np.ndarray:
    array = np.asarray(matrix, dtype=np.float64)
    if array.ndim == 3:
        array = project_gray(array, 8, 8)
    elif array.ndim != 2:
        raise ValueError(f"matrix must be 2-D or 3-D, got {array.shape}")
    if array.size == 0 or array.size > 256 * 256:
        raise ValueError("matrix is empty or larger than 256x256")
    if max(int(array.shape[0]), int(array.shape[1])) > 16:
        array = project_gray(array, 8, 8)
    elif array.size and float(np.nanmax(np.abs(array))) > 1.5:
        array = array / 255.0
    if not np.isfinite(array).all():
        raise ValueError("matrix is not finite")
    return np.ascontiguousarray(array, dtype=np.float64)


def _public_packet(packet: dict[str, Any]) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    for layer in packet["layers"]:
        scale = layer["scale"]
        if not isinstance(scale, (int, float)):
            raise ValueError("layer scale must be one scalar; component gains are not this path")
        ub = np.asarray(layer["Ub"])
        vb = np.asarray(layer["Vb"])
        layers.append(
            {
                "Ub": [[int(v) for v in row] for row in ub.tolist()],
                "Vb": [[int(v) for v in row] for row in vb.tolist()],
                "scale": float(scale),
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


def _hash_packet(packet: dict[str, Any]) -> str:
    clean = {key: value for key, value in packet.items() if key != "packet_hash"}
    return hashlib.sha256(pack_packet(clean)).hexdigest()


def _energy(original: np.ndarray, recon: np.ndarray) -> float:
    diff = np.asarray(original, dtype=np.float64) - np.asarray(recon, dtype=np.float64)
    denom = float(np.sum(np.asarray(original, dtype=np.float64) ** 2)) + 1e-12
    return float(np.sum(diff ** 2) / denom)


def _fit(matrix: np.ndarray, rank: int, n_layers: int, seed: int) -> dict[str, Any]:
    raw = encode(
        matrix,
        rank=int(rank),
        n_layers=int(n_layers),
        seed=int(seed),
        scale_mode="layer",
    )
    public = _public_packet(raw)
    recon = decode(public)
    energy = _energy(matrix, recon)
    scales = [float(layer["scale"]) for layer in public["layers"]]
    return {
        "packet": public,
        "recon": recon,
        "energy": energy,
        "scales": scales,
        "rank": int(public["rank"]),
        "n_layers": int(public["n_layers"]),
        "logical_bits": int(public["logical_bits"]),
    }


def _prefer(current: dict[str, Any] | None, trial: dict[str, Any]) -> dict[str, Any]:
    """Lower residual energy, then fewer bits. The engine scale is unchanged."""
    if current is None:
        return trial
    if trial["energy"] < current["energy"] - 1e-9:
        return trial
    if current["energy"] < trial["energy"] - 1e-9:
        return current
    if trial["logical_bits"] < current["logical_bits"]:
        return trial
    return current


def _oscillator(rank: int, n_layers: int, scales: list[float], energy: float) -> dict[str, Any]:
    """Outward Kuramoto step. The outer level does not drive back."""
    oscillators = max(int(rank), 2)
    depth = max(int(n_layers), 2)
    field = KuramotoField(
        oscillators,
        depth=depth,
        orientation="outward",
        scale=1.0,
        random_start=False,
        ladder="golden_powers",
    )
    theta = np.zeros(oscillators, dtype=np.float64)
    for index, scale in enumerate(scales):
        theta[index % oscillators] += float(np.arctan(scale))
    field.theta = theta
    field.step(epsilon=float(max(energy, 0.0)))
    return {
        "backend": "kuramoto",
        "orientation": field.orientation,
        "depth": depth,
        "depth_order": float(field.depth_order()),
        "r": oscillators,
    }


def _evolve_matrix(
    matrix: np.ndarray,
    *,
    requested_rank: int,
    requested_layers: int,
    seed: int,
) -> dict[str, Any]:
    height, width = int(matrix.shape[0]), int(matrix.shape[1])
    cap = min(height, width)
    requested_rank = max(1, min(int(requested_rank), cap))
    requested_layers = max(1, int(requested_layers))
    ceiling_rank = max(1, min(cap, contract_rank(requested_rank)))
    ceiling_layers = max(1, contract_depth(requested_layers))
    ranks: list[int] = []
    for rank in (1, ceiling_rank):
        if 1 <= rank <= cap and rank not in ranks:
            ranks.append(rank)
    chosen: dict[str, Any] | None = None
    for rank in ranks:
        chosen = _prefer(chosen, _fit(matrix, rank, 1, seed))
    assert chosen is not None
    while chosen["n_layers"] < ceiling_layers and chosen["energy"] > ACCEPT_ENERGY:
        nxt = _fit(matrix, chosen["rank"], chosen["n_layers"] + 1, seed)
        if abs(nxt["scales"][-1]) < 1e-8:
            break
        if chosen["energy"] - nxt["energy"] < LAYER_GAIN:
            break
        chosen = nxt
    osc = _oscillator(chosen["rank"], chosen["n_layers"], chosen["scales"], chosen["energy"])
    reference = logical_bits(height, width, requested_rank, requested_layers, "layer")
    used = int(chosen["logical_bits"])
    credit = float(used) / float(max(reference, 1))
    digest = _hash_packet(chosen["packet"])
    packet = dict(chosen["packet"])
    packet["packet_hash"] = digest
    return {
        "matrix": matrix,
        "recon": chosen["recon"],
        "packet": packet,
        "packet_hash": digest,
        "energy": float(chosen["energy"]),
        "scales": list(chosen["scales"]),
        "oscillator": osc,
        "compression": {
            "requested_rank": requested_rank,
            "requested_layers": requested_layers,
            "ceiling_rank": ceiling_rank,
            "ceiling_layers": ceiling_layers,
            "encoded_rank": int(chosen["rank"]),
            "encoded_layers": int(chosen["n_layers"]),
            "logical_bits": used,
            "reference_bits": int(reference),
            "credit_cost": credit,
            "phi_compressed": True,
            "scale_mode": "layer",
        },
    }


def _control_view(control: Any) -> dict[str, Any] | None:
    if isinstance(control, ControlPacket):
        return control.to_dict()
    if isinstance(control, dict):
        return control
    return None


def _attach(
    control: Any,
    *,
    packet: dict[str, Any],
    digest: str,
    confidence: float,
    risk: dict[str, Any],
    scar: str | None,
) -> dict[str, Any]:
    """Write the residual packet and hash onto the caller's control packet."""
    view = _control_view(control)
    if view is None:
        view = {
            "id": "residual-cascade",
            "budget_remaining": {"steps": 8, "cost": 1.0, "tokens": 1000},
            "evidence": [],
            "scars": [],
            "history": [],
            "state": {},
        }
    state = view.get("state")
    if not isinstance(state, dict):
        state = {}
        view["state"] = state
    state["residual_packet"] = packet
    state["residual_hash"] = digest
    view["confidence"] = float(confidence)
    view["risk_class"] = risk.get("risk_class")
    if isinstance(control, ControlPacket):
        control.confidence = float(confidence)
        control.risk_class = risk.get("risk_class")
    scars = view.get("scars")
    if not isinstance(scars, list):
        scars = []
        view["scars"] = scars
    if scar and scar not in scars:
        scars.append(scar)
    evidence_attach(
        {
            "packet_hash": digest,
            "codec": "studio-codec/1",
            "scale_mode": "layer",
        },
        "residual_core",
        view,
    )
    return view


def _judge(evolved: dict[str, Any], view: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    energy = float(evolved["energy"])
    order = float(evolved["oscillator"]["depth_order"])
    if energy <= ACCEPT_ENERGY:
        confidence = 0.99
    else:
        agreement = 1.0 / (1.0 + energy)
        confidence = float(agreement * (0.5 + 0.5 * order))
    routed = confidence_route({"probability": confidence})
    consistency = residual_consistency(view)
    if active_demigod() is None:
        hephaestus = hephaestus_check(
            view,
            residual_packet={"packet_hash": evolved["packet_hash"]},
        )
        hephaestus_ok = bool(hephaestus.verified)
        hephaestus_body = hephaestus.to_dict()
    else:
        # A duty is already open. Nesting hephaestus_check would be a rank error.
        budget = view.get("budget_remaining") if isinstance(view.get("budget_remaining"), dict) else {}
        hephaestus_ok = bool(consistency.get("consistent")) and float(budget.get("steps", 0)) > 0 and float(budget.get("cost", 0)) > 0
        hephaestus_body = {
            "demigod": "hephaestus",
            "verified": hephaestus_ok,
            "success": hephaestus_ok,
            "reason": "checked inside an open duty without nesting",
            "outcome": "approved" if hephaestus_ok else "fail",
        }
    digest = evolved["packet_hash"]
    claimed = str(evolved["packet"].get("packet_hash") or digest)
    hash_match = claimed == digest and bool(digest)
    risk_name = str(risk.get("risk_class") or "")
    if risk_name == "deny" or not hash_match or not consistency.get("consistent") or not hephaestus_ok:
        outcome = "rejected"
    elif energy <= ACCEPT_ENERGY and routed["route"] != "escalate_or_abstain":
        outcome = "accepted"
    else:
        outcome = "inconclusive"
    if outcome == "accepted":
        apollo = apollo_success({"status": "ok"})
    elif outcome == "rejected":
        apollo = apollo_success({"status": "failed"})
    else:
        apollo = apollo_success({"status": "inconclusive"})
    escalate = outcome == "inconclusive"
    return {
        "outcome": outcome,
        "confidence": confidence,
        "route": routed["route"],
        "energy": energy,
        "escalate": escalate,
        "closes_question": outcome == "accepted",
        "apollo": apollo,
        "hephaestus": hephaestus_body,
        "residual_consistency": consistency,
        "checks": {
            "hash_match": hash_match,
            "residual_consistency": bool(consistency.get("consistent")),
            "hephaestus": hephaestus_ok,
            "apollo": bool(apollo.get("success")),
            "risk_class": risk_name,
        },
    }


def _candidate(digest: str, title: str) -> dict[str, Any] | None:
    return register_candidate(
        kind="image",
        path=f"candidate://studio/still/{digest[:12]}",
        title=title,
        world_id="studio",
        note="still candidate from a layer-scale residual packet; learn was not called",
    )


def _still_result(
    evolved: dict[str, Any],
    judged: dict[str, Any],
    *,
    prompt: str,
    stage: str,
    address: bool,
    register: bool,
) -> dict[str, Any]:
    digest = evolved["packet_hash"]
    cascade = cascade_address(0, 0, digest)
    scale = None
    if address:
        recon = np.asarray(evolved["recon"], dtype=np.float64)
        preview = np.clip(recon, 0.0, 1.0)
        rgb = np.repeat((preview * 255.0).astype(np.uint8)[..., None], 3, axis=2)
        scale = scale_address(rgb, subject="studio-still")
    candidate = None
    if register and judged["outcome"] != "rejected":
        candidate = _candidate(digest, f"CANDIDATE still {digest[:8]}")
    scale_value = evolved["scales"][0] if evolved["scales"] else 0.0
    return {
        "outcome": judged["outcome"],
        "status": judged["outcome"],
        "stage": stage,
        "prompt": prompt,
        "url": None,
        "draft": judged["outcome"] != "rejected",
        "produces_video": False,
        "learned": False,
        "learn_called": False,
        "patron": "hephaestus",
        "checkpoint": None,
        "hades_checkpoint": False,
        "packet_hash": digest,
        "residual_hash": digest,
        "residual_packet": evolved["packet"],
        "layer_scale": float(scale_value),
        "scale_mode": "layer",
        "energy": judged["energy"],
        "closes_question": judged["closes_question"],
        "escalate": judged["escalate"],
        "confidence": judged["confidence"],
        "route": judged["route"],
        "compression": evolved["compression"],
        "oscillator": evolved["oscillator"],
        "cascade": cascade,
        "scale": scale,
        "candidate": candidate,
        "apollo": judged["apollo"],
        "hephaestus": judged["hephaestus"],
        "residual_consistency": judged["residual_consistency"],
        "checks": judged["checks"],
        "provider_frames": 0,
        "provider_cost": 0.0,
        "note": (
            "Still candidate from a layer-scale residual packet. "
            "An 8x8 reconstruction error is not a photo or video score. "
            "A phase-tinted random field is not this codec. No production video is claimed."
        ),
    }


def cascade_scale(
    matrix: Any,
    *,
    control: Any = None,
    prompt: str = "",
    requested_rank: int = 4,
    requested_layers: int = 4,
    seed: int = 0,
    register: bool = True,
    address: bool = True,
    learn: Any = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
    stage: str = "draft",
) -> dict[str, Any]:
    """Evolve one matrix into a compressed still candidate and attach it."""
    _refuse_bypass(learn=learn, bypass_zeus=bypass_zeus, zeus=zeus)
    risk = risk_classify(prompt or "studio still candidate")
    try:
        prepared = _prepare_matrix(matrix)
        evolved = _evolve_matrix(
            prepared,
            requested_rank=requested_rank,
            requested_layers=requested_layers,
            seed=seed,
        )
    except (ValueError, TypeError) as exc:
        view = _attach(
            control,
            packet={},
            digest="",
            confidence=0.0,
            risk=risk,
            scar=f"codec_packet_malformed: {exc}",
        )
        return {
            "outcome": "rejected",
            "status": "rejected",
            "stage": stage,
            "prompt": prompt,
            "url": None,
            "draft": False,
            "produces_video": False,
            "learned": False,
            "learn_called": False,
            "patron": "hephaestus",
            "checkpoint": None,
            "hades_checkpoint": False,
            "packet_hash": "",
            "residual_hash": "",
            "residual_packet": None,
            "escalate": False,
            "closes_question": False,
            "reason": str(exc),
            "risk": risk,
            "note": "The matrix could not enter the residual codec.",
            "control_id": view.get("id"),
        }
    scar = None
    if risk["risk_class"] == "deny":
        scar = "risk_deny"
    view = _attach(
        control,
        packet=evolved["packet"],
        digest=evolved["packet_hash"],
        confidence=0.0,
        risk=risk,
        scar=scar,
    )
    judged = _judge(evolved, view, risk)
    if isinstance(control, ControlPacket):
        control.confidence = judged["confidence"]
    elif isinstance(control, dict):
        control["confidence"] = judged["confidence"]
    result = _still_result(
        evolved,
        judged,
        prompt=prompt,
        stage=stage,
        address=address,
        register=register,
    )
    result["risk"] = risk
    result["hypervector"] = []
    return result


def _frames_of(matrix: Any, frames: Any) -> list[Any]:
    if isinstance(frames, list) and frames:
        return list(frames)
    if matrix is not None:
        return [matrix]
    return []


def _load_claimed(packet: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    claimed = str(packet.get("packet_hash") or "")
    clean = {key: value for key, value in packet.items() if key != "packet_hash"}
    digest = _hash_packet(clean)
    recon = decode(clean)
    return clean, digest, claimed


def verify_residual(
    matrix: Any = None,
    *,
    residual_packet: dict[str, Any] | None = None,
    frames: Any = None,
    control: Any = None,
    prompt: str = "",
    learn: Any = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
) -> dict[str, Any]:
    """Accept or reject from the residual packet and its hash. No provider."""
    _refuse_bypass(learn=learn, bypass_zeus=bypass_zeus, zeus=zeus)
    if isinstance(residual_packet, dict) and matrix is None and not _frames_of(None, frames):
        risk = risk_classify(prompt or "studio still candidate")
        try:
            clean, digest, claimed = _load_claimed(residual_packet)
            recon = decode(clean)
        except (ValueError, TypeError, KeyError) as exc:
            return {
                "outcome": "rejected",
                "status": "rejected",
                "stage": "verify",
                "url": None,
                "produces_video": False,
                "learned": False,
                "learn_called": False,
                "escalate": False,
                "closes_question": False,
                "reason": str(exc),
                "risk": risk,
                "checkpoint": None,
                "hades_checkpoint": False,
                "patron": "hephaestus",
            }
        evolved = {
            "matrix": recon,
            "recon": recon,
            "packet": {**clean, "packet_hash": claimed or digest},
            "packet_hash": digest,
            "energy": 0.0 if claimed in {"", digest} else 1.0,
            "scales": [float(clean["layers"][0]["scale"])],
            "oscillator": _oscillator(
                int(clean["rank"]),
                int(clean["n_layers"]),
                [float(layer["scale"]) for layer in clean["layers"]],
                0.0,
            ),
            "compression": {
                "logical_bits": int(clean.get("logical_bits") or 0),
                "reference_bits": int(clean.get("logical_bits") or 1),
                "credit_cost": 1.0,
                "scale_mode": "layer",
                "phi_compressed": True,
                "encoded_rank": int(clean["rank"]),
                "encoded_layers": int(clean["n_layers"]),
            },
        }
        if claimed and claimed != digest:
            evolved["packet"]["packet_hash"] = claimed
            evolved["packet_hash"] = digest
        view = _attach(
            control,
            packet=evolved["packet"],
            digest=digest,
            confidence=0.0,
            risk=risk,
            scar=None if claimed in {"", digest} else "residual_hash_mismatch",
        )
        judged = _judge(evolved, view, risk)
        if claimed and claimed != digest:
            judged["outcome"] = "rejected"
            judged["escalate"] = False
            judged["closes_question"] = False
            judged["checks"]["hash_match"] = False
            judged["apollo"] = apollo_success({"status": "failed"})
            judged["checks"]["apollo"] = False
        result = _still_result(
            evolved,
            judged,
            prompt=prompt,
            stage="verify",
            address=False,
            register=False,
        )
        result["risk"] = risk
        return result
    sources = _frames_of(matrix, frames)
    if not sources:
        return {
            "outcome": "rejected",
            "status": "rejected",
            "stage": "verify",
            "url": None,
            "produces_video": False,
            "learned": False,
            "learn_called": False,
            "reason": "nothing to verify",
            "escalate": False,
            "closes_question": False,
            "checkpoint": None,
            "hades_checkpoint": False,
            "patron": "hephaestus",
        }
    result = cascade_scale(
        sources[0],
        control=control,
        prompt=prompt,
        register=False,
        address=True,
        stage="verify",
    )
    if isinstance(residual_packet, dict):
        claimed = str(residual_packet.get("packet_hash") or "")
        if claimed and claimed != result.get("packet_hash"):
            result["outcome"] = "rejected"
            result["status"] = "rejected"
            result["escalate"] = False
            result["closes_question"] = False
            result["checks"]["hash_match"] = False
            result["apollo"] = apollo_success({"status": "failed"})
            result["checks"]["apollo"] = False
            result["reason"] = "residual hash mismatch"
    failing = _failing_frames(sources, prompt)
    result["failing_frames"] = len(failing)
    result["provider_cost"] = 0.0
    result["provider_frames"] = 0
    if failing and result.get("outcome") == "accepted":
        result["outcome"] = "inconclusive"
        result["status"] = "inconclusive"
        result["escalate"] = True
        result["closes_question"] = False
        result["apollo"] = apollo_success({"status": "inconclusive"})
        if isinstance(result.get("checks"), dict):
            result["checks"]["apollo"] = False
    return result


def _failing_frames(frames: list[Any], prompt: str) -> list[dict[str, Any]]:
    failing: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        try:
            prepared = _prepare_matrix(frame)
            evolved = _evolve_matrix(prepared, requested_rank=4, requested_layers=4, seed=0)
        except (ValueError, TypeError):
            continue
        if evolved["energy"] <= ACCEPT_ENERGY:
            continue
        delta = prepared - np.asarray(evolved["recon"], dtype=np.float64)
        failing.append(
            {
                "index": index,
                "disagreement": float(evolved["energy"]),
                "packet_hash": evolved["packet_hash"],
                "delta": [round(float(value), 6) for value in delta.ravel()],
                "shape": [int(prepared.shape[0]), int(prepared.shape[1])],
            }
        )
    del prompt
    return failing


def _slot_executable() -> str:
    for name in ("RESILEOS_UPSCALE_PROVIDER", "RESILEOS_VIDEO_PROVIDER"):
        path = os.getenv(name, "").strip()
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


def _call_slot(provider_fn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Provider slot. It sees a residual delta and may return an asset URL.

    Higgsfield, Seedance, ComfyUI, and OpenAI are not wired here. Nothing
    in this function is a chat mouth. No weights are loaded.
    """
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if callable(provider_fn):
        try:
            raw = provider_fn(text)
        except Exception:
            return {"ok": False, "detail": "Video provider failed.", "url": None}
    else:
        path = _slot_executable()
        if not path:
            return {
                "ok": False,
                "detail": "No video generator is configured on this host.",
                "url": None,
            }
        from resileos.kin.studio_tools import _run_executable

        produced = _run_executable(path, text)
        if produced.get("status") != "submitted":
            return {
                "ok": False,
                "detail": str(produced.get("detail") or "Video provider returned no asset."),
                "url": None,
            }
        raw = produced.get("result") if isinstance(produced.get("result"), dict) else produced
    if not isinstance(raw, dict):
        return {"ok": False, "detail": "Video provider returned no asset.", "url": None}
    url = raw.get("url") or raw.get("video_url")
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "detail": "Video provider returned no asset.", "url": None}
    return {"ok": True, "url": url.strip(), "payload": raw, "detail": ""}


def upscale_residual(
    matrix: Any = None,
    *,
    frames: Any = None,
    residual_packet: dict[str, Any] | None = None,
    provider_fn: Any = None,
    control: Any = None,
    prompt: str = "",
    learn: Any = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
) -> dict[str, Any]:
    """Send only an unclosed residual delta. Off when the residual already closed."""
    _refuse_bypass(learn=learn, bypass_zeus=bypass_zeus, zeus=zeus)
    sources = _frames_of(matrix, frames)
    if not sources and isinstance(residual_packet, dict):
        checked = verify_residual(
            residual_packet=residual_packet,
            control=control,
            prompt=prompt,
        )
        checked["stage"] = "upscale"
        checked["status"] = "not_required" if checked.get("outcome") == "accepted" else checked.get("status")
        checked["url"] = None
        checked["provider_frames"] = 0
        checked["provider_cost"] = 0.0
        return checked
    if not sources:
        return {
            "outcome": "rejected",
            "status": "rejected",
            "stage": "upscale",
            "url": None,
            "produces_video": False,
            "learned": False,
            "learn_called": False,
            "reason": "nothing to upscale",
            "checkpoint": None,
            "hades_checkpoint": False,
            "patron": "hephaestus",
        }
    verdict = verify_residual(
        sources[0],
        frames=sources,
        residual_packet=residual_packet,
        control=control,
        prompt=prompt,
    )
    verdict["stage"] = "upscale"
    if verdict.get("outcome") == "rejected":
        verdict["status"] = "refused"
        verdict["url"] = None
        verdict["detail"] = "Upscale waits until the residual packet is consistent."
        verdict["provider_frames"] = 0
        verdict["provider_cost"] = 0.0
        return verdict
    if verdict.get("outcome") == "accepted":
        verdict["status"] = "not_required"
        verdict["url"] = None
        verdict["detail"] = "Residual packet closed the still. Upscale stays off."
        verdict["provider_frames"] = 0
        verdict["provider_cost"] = 0.0
        return verdict
    failing = _failing_frames(sources, prompt)
    if not failing:
        verdict["status"] = "not_required"
        verdict["url"] = None
        verdict["provider_frames"] = 0
        verdict["provider_cost"] = 0.0
        return verdict
    checks = verdict.get("checks") or {}
    if not (
        checks.get("hash_match")
        and checks.get("residual_consistency")
        and checks.get("hephaestus")
        and checks.get("risk_class") == "allow"
    ):
        verdict["status"] = "refused"
        verdict["url"] = None
        verdict["detail"] = "External upscale stays refused until residual and Hephaestus checks pass."
        verdict["provider_frames"] = 0
        verdict["provider_cost"] = 0.0
        return verdict
    cost = float(sum(item["disagreement"] for item in failing))
    full_cost = float(len(sources))
    payload = {
        "kind": "residual_delta",
        "packet_hash": verdict.get("packet_hash"),
        "n_frames": len(failing),
        "full_clip": False,
        "disagreement": round(cost / max(len(failing), 1), 6),
        "frames": [
            {"index": item["index"], "shape": item["shape"], "delta": item["delta"]}
            for item in failing
        ],
    }
    called = _call_slot(provider_fn, payload)
    verdict["provider_frames"] = len(failing)
    verdict["provider_cost"] = cost
    verdict["full_duration_cost"] = full_cost
    verdict["upscale_payload"] = {
        "kind": payload["kind"],
        "n_frames": payload["n_frames"],
        "full_clip": False,
        "disagreement": payload["disagreement"],
    }
    if not called["ok"]:
        verdict["status"] = "UNAVAILABLE"
        verdict["url"] = None
        verdict["draft"] = False
        verdict["detail"] = called["detail"]
        verdict["produces_video"] = False
        return verdict
    verdict["status"] = "submitted"
    verdict["url"] = called["url"]
    verdict["draft"] = False
    verdict["produces_video"] = False
    verdict["reencoded"] = False
    asset = called["payload"].get("matrix", called["payload"].get("image"))
    verdict["outcome"] = "submitted"
    verdict["next_verify"] = True
    if asset is not None:
        fresh = cascade_scale(
            asset,
            control=control,
            prompt=prompt,
            register=True,
            address=False,
            stage="upscale",
        )
        if fresh.get("packet_hash"):
            verdict["residual_packet"] = fresh.get("residual_packet")
            verdict["packet_hash"] = fresh.get("packet_hash")
            verdict["residual_hash"] = fresh.get("packet_hash")
            verdict["reencoded"] = True
    return verdict


def run_visual_stage(
    *,
    stage: str,
    prompt: str,
    matrix: Any = None,
    frames: Any = None,
    residual_packet: dict[str, Any] | None = None,
    provider_fn: Any = None,
    control: Any = None,
    learn: Any = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
) -> dict[str, Any]:
    """Draft, verify, or selectively upscale. Draft and verify do not call a provider."""
    if stage == "verify":
        return verify_residual(
            matrix,
            frames=frames,
            residual_packet=residual_packet,
            control=control,
            prompt=prompt,
            learn=learn,
            bypass_zeus=bypass_zeus,
            zeus=zeus,
        )
    if stage == "upscale":
        return upscale_residual(
            matrix,
            frames=frames,
            residual_packet=residual_packet,
            provider_fn=provider_fn,
            control=control,
            prompt=prompt,
            learn=learn,
            bypass_zeus=bypass_zeus,
            zeus=zeus,
        )
    sources = _frames_of(matrix, frames)
    if not sources and isinstance(residual_packet, dict):
        return verify_residual(
            residual_packet=residual_packet,
            control=control,
            prompt=prompt,
            learn=learn,
            bypass_zeus=bypass_zeus,
            zeus=zeus,
        )
    if not sources:
        raise ValueError("draft needs a matrix, frames, or a residual packet")
    result = cascade_scale(
        sources[0],
        control=control,
        prompt=prompt,
        register=True,
        address=True,
        learn=learn,
        bypass_zeus=bypass_zeus,
        zeus=zeus,
        stage="draft",
    )
    if len(sources) > 1:
        failing = _failing_frames(sources, prompt)
        result["failing_frames"] = len(failing)
        if failing and result.get("outcome") == "accepted":
            result["outcome"] = "inconclusive"
            result["status"] = "inconclusive"
            result["escalate"] = True
            result["closes_question"] = False
    return result
