"""Verify a temporal residual clip, then checkpoint or upscale.

Draft and verify compress and check frames that already exist. They do
not sample a prompt. Upscale follows the still contract: off when the
residual closes, refused on a bad hash, a Hephaestus failure, or a deny
risk, and only the failing-frame residual deltas leave when the check is
inconclusive. With no provider the status is UNAVAILABLE and the URL is
null.

A passing sequence is the only one marked sequence_verified. That is the
only one written to Hades (lesson and packet hash, not the frame history)
and the only one registered as a candidate. Mouth stays off unless that
flag is set.

Hermes ranks context the caller supplied. It does not invent triples.
"""
from __future__ import annotations

import os
import re
from typing import Any

import numpy as np

from resileos.harness.packet import ControlPacket, VideoPacket
from resileos.harness.tools import (
    apollo_success,
    residual_consistency,
    risk_classify,
    verify_on_stop,
)
from resileos.kin.demigods.checks import hephaestus_check, themis_check
from resileos.kin.hades import Hades
from resileos.kin.hermes import HermesBudget, make_hermes_navigator
from resileos.kin.residual_trace import append_stage
from resileos.studio.candidates import register_candidate
from resileos.studio.clip_metrics import clip_check_metrics
from resileos.studio.clip_codec import (
    TEMPORAL_SIGMA,
    decode_sequence,
    encode_sequence,
    packet_hash,
    prepare_frames,
    public_sequence,
    sequence_digest,
)
from resileos.studio.residual_cascade import ACCEPT_ENERGY, VisualPathError
from resileos.ui.residual_frame import frame_residual, motion_vector

_STAGES = {"draft", "verify", "upscale"}
_HISTORY_KEYS = ("event", "stage", "packet_hash", "outcome", "checkpoint_id")


def _refuse(*, learn: Any, bypass_zeus: bool, zeus: Any) -> None:
    if bypass_zeus or zeus is not None:
        raise VisualPathError("a visual path cannot bypass Zeus routing")
    if learn is not None:
        raise VisualPathError("a visual path cannot call learn")


def _hades_dir() -> str:
    return os.environ.get("RESILEOS_HADES_DIR", "data/hades")


def _control_id(control: Any) -> str:
    if isinstance(control, ControlPacket):
        return str(control.id or "clip")[:80]
    if isinstance(control, dict) and control.get("id"):
        return str(control["id"])[:80]
    return "clip"


def _budget(control: Any) -> dict[str, float]:
    raw: Any = None
    if isinstance(control, ControlPacket):
        raw = control.budget_remaining
    elif isinstance(control, dict):
        raw = control.get("budget_remaining")
    if not isinstance(raw, dict):
        raw = {"steps": 8, "cost": 1.0}
    try:
        steps = float(raw.get("steps", 8))
        cost = float(raw.get("cost", 1.0))
    except (TypeError, ValueError):
        steps, cost = 8.0, 1.0
    if steps <= 0:
        steps = 8.0
    if cost <= 0:
        cost = 1.0
    return {"steps": steps, "cost": cost}


def _rank_context(context: Any, prompt: str) -> tuple[list[Any], dict[str, int]]:
    """Hermes ranks supplied items. An empty list stays empty."""
    items: list[Any] = []
    if isinstance(context, list) and context:
        items.extend(context[:32])
    elif prompt:
        items.append(prompt)
    navigate, _handler = make_hermes_navigator()
    budget = HermesBudget(max_depth=2, max_items=8)
    ranked = list(navigate(items, budget))
    return ranked, {
        "used": int(budget.used),
        "max_items": int(budget.max_items),
        "max_depth": int(budget.max_depth),
    }


def _short_event(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _HISTORY_KEYS:
        if key not in item:
            continue
        value = item[key]
        if isinstance(value, str):
            out[key] = value[:80]
        elif value is None and key == "checkpoint_id":
            out[key] = None
    return out


def _history(prior: Any, event: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(prior, list):
        for item in prior[-7:]:
            short = _short_event(item)
            if short:
                rows.append(short)
    rows.append(_short_event(event))
    return rows[-8:]


def _remember(control: Any, event: dict[str, Any]) -> None:
    if isinstance(control, ControlPacket):
        control.append(event)
        return
    if isinstance(control, dict):
        history = control.get("history")
        if not isinstance(history, list):
            history = []
            control["history"] = history
        history.append(dict(event))
        del history[:-8]


def _preview(frames: list[np.ndarray]) -> list[list[list[float]]]:
    shown: list[list[list[float]]] = []
    for frame in frames:
        clipped = np.clip(np.asarray(frame, dtype=np.float64), 0.0, 1.0)
        shown.append([[round(float(value), 4) for value in row] for row in clipped])
    return shown


def _mouth(sequence_verified: bool) -> bool:
    """Mouth follows this clip cycle.

    A verified sequence is the cycle that authorizes prose on this surface.
    ``should_render_prose`` also reads a process-global Metis policy from
    whatever ran last. That leftover policy is not this cycle, so a verified
    clip is not closed by it. An unverified clip stays silent.
    """
    return bool(sequence_verified)


def _pair_consistency(hashes: list[str]) -> tuple[float, bool, dict[str, Any]]:
    """Harness residual_consistency between consecutive decoded steps."""
    if not hashes:
        packet = {"scars": ["missing_frame"], "evidence": [], "budget_remaining": {"steps": 8, "cost": 1.0}}
        result = residual_consistency(packet)
        return 0.0, False, result
    if len(hashes) == 1:
        packet = {
            "scars": [],
            "evidence": [{"source": "residual_core", "result": {"packet_hash": hashes[0]}}],
            "budget_remaining": {"steps": 8, "cost": 1.0},
            "history": [],
        }
        result = residual_consistency(packet)
        ok = bool(result.get("consistent"))
        return (1.0 if ok else 0.0), ok, result
    flags: list[bool] = []
    last: dict[str, Any] = {}
    for left, right in zip(hashes, hashes[1:]):
        packet = {
            "scars": [],
            "evidence": [
                {"source": "residual_core", "result": {"packet_hash": left}},
                {"source": "residual_core", "result": {"packet_hash": right}},
            ],
            "budget_remaining": {"steps": 8, "cost": 1.0},
            "history": [],
        }
        last = residual_consistency(packet)
        flags.append(bool(last.get("consistent")))
    score = float(sum(1.0 if flag else 0.0 for flag in flags) / len(flags))
    return score, all(flags), last


def _blank_bits() -> dict[str, Any]:
    return {"base": 0, "deltas": [], "mean_delta": 0.0, "frames": 0}


def _attach_video(body: dict[str, Any], stage: str) -> None:
    """Public VideoPacket fields. Hashes and counts, not pixels in the packet."""
    sequence = body.get("sequence")
    if not isinstance(sequence, dict):
        return
    steps = sequence.get("steps") if isinstance(sequence.get("steps"), list) else []
    hashes = [str(step.get("packet_hash") or "") for step in steps if isinstance(step, dict)]
    keyframes = [int(step["index"]) for step in steps if isinstance(step, dict) and step.get("keyframe")]
    reused = sum(1 for step in steps if isinstance(step, dict) and step.get("kind") == "reuse")
    generative = sum(1 for step in steps if isinstance(step, dict) and step.get("escalated"))
    stage_name = stage if stage in {"draft", "verify", "upscale"} else "draft"
    previews = body.get("preview") if isinstance(body.get("preview"), list) else []
    try:
        metrics = clip_check_metrics(previews)
    except (TypeError, ValueError):
        metrics = clip_check_metrics([])
    body["check_metrics"] = metrics
    packet = VideoPacket(
        id=str(body.get("packet_hash") or "clip")[:80],
        frame_residuals=hashes,
        temporal_delta=float(sequence.get("temporal_delta") or 0.0),
        keyframe_ids=keyframes,
        provider_stage=stage_name,
        scene_script_hash=None,
        check_metrics=metrics,
    )
    body["video_packet"] = packet.to_dict()
    body["cost"] = {
        "reused_frames": reused,
        "generative_frames": generative,
        "sigma": float(sequence.get("sigma") or TEMPORAL_SIGMA),
        "unit": "rms",
    }
    body["keyframes"] = [
        {"index": index, "frame": previews[index]}
        for index in keyframes
        if 0 <= index < len(previews)
    ]
    body["dispositions"] = [
        {
            "index": int(step["index"]),
            "disposition": step.get("disposition"),
            "temporal_magnitude": step.get("temporal_magnitude"),
        }
        for step in steps
        if isinstance(step, dict) and "index" in step
    ]


def _finish(
    body: dict[str, Any],
    *,
    control: Any,
    stage: str,
    control_id: str,
    digest: str,
    energy: float,
    score: float,
    verify_result: str,
    budget_used: dict[str, float],
    checkpoint_id: str | None,
    prior_history: Any,
) -> dict[str, Any]:
    trace_stage = stage if stage in {"draft", "verify", "upscale"} else "draft"
    _attach_video(body, trace_stage)
    append_stage(
        {
            "control_id": control_id,
            "stage": trace_stage,
            "packet_hash": digest,
            "residual_energy": energy,
            "consistency_score": score,
            "verify_result": verify_result,
            "budget_used": budget_used,
            "checkpoint_id": checkpoint_id,
        }
    )
    event = {
        "event": "clip_stage",
        "stage": trace_stage,
        "packet_hash": digest,
        "outcome": verify_result,
        "checkpoint_id": checkpoint_id,
    }
    body["history"] = _history(prior_history, event)
    _remember(control, event)
    body["step_core"] = False
    body["scar_matrix_updated"] = False
    body["learned"] = False
    body["learn_called"] = False
    body["generative"] = False
    body["produces_video"] = False
    body["patron"] = "hephaestus"
    body["full_clip"] = False
    body["provider_frames"] = int(body.get("provider_frames") or 0)
    body["provider_cost"] = float(body.get("provider_cost") or 0.0)
    if "url" not in body or not body["url"]:
        body["url"] = None
    return body


def _common(
    *,
    stage: str,
    prompt: str,
    status: str,
    outcome: str,
    sequence_verified: bool,
    ranked: list[Any],
    hermes_budget: dict[str, int],
    risk: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "outcome": outcome,
        "prompt": prompt,
        "url": None,
        "draft": stage == "draft" and outcome == "drafted",
        "sequence_verified": sequence_verified,
        "verified_sequence": sequence_verified,
        "mouth": _mouth(sequence_verified),
        "candidate": None,
        "checkpoint": None,
        "checkpoint_id": None,
        "hades_checkpoint": False,
        "upscale_enabled": False,
        "context_ranked": ranked,
        "hermes_budget": hermes_budget,
        "risk": risk,
        "bits_per_frame": _blank_bits(),
        "badge": {
            "energy": 0.0,
            "consistency_score": 0.0,
            "base_bits": 0,
            "mean_delta_bits": 0.0,
            "sequence_verified": sequence_verified,
        },
        "preview": [],
        "sequence": None,
        "checks": {},
        "note": (
            "Temporal residual clip. The codec compresses and checks frames "
            "that were supplied. It does not generate video."
        ),
        "provider_called": False,
        "cost": {
            "reused_frames": 0,
            "generative_frames": 0,
            "sigma": TEMPORAL_SIGMA,
            "unit": "rms",
        },
        "keyframes": [],
        "dispositions": [],
        "video_packet": None,
    }


def _load_sequence(
    frames: Any,
    sequence: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[np.ndarray] | None, str]:
    prepared: list[np.ndarray] | None = None
    if frames is not None and frames != [] and not (isinstance(frames, list) and len(frames) == 0):
        try:
            prepared = prepare_frames(frames)
        except (TypeError, ValueError) as exc:
            return None, None, str(exc)
    if isinstance(sequence, dict):
        return sequence, prepared, ""
    if prepared is None:
        return None, None, ""
    try:
        encoded = encode_sequence(prepared)
    except (TypeError, ValueError) as exc:
        return None, prepared, str(exc)
    return public_sequence(encoded), prepared, ""


def _step_hashes(sequence: dict[str, Any]) -> list[str]:
    steps = sequence.get("steps")
    if isinstance(steps, list) and steps:
        hashes = [
            str(step["packet_hash"])
            for step in steps
            if isinstance(step, dict) and step.get("packet_hash")
        ]
        if len(hashes) == len(steps):
            return hashes
    hashes = [packet_hash(sequence["base"])]
    for delta in sequence["deltas"]:
        hashes.append(packet_hash(delta))
    return hashes


def _frame_energies(
    prepared: list[np.ndarray] | None,
    decoded: list[np.ndarray],
    *,
    hash_ok: bool,
) -> list[float]:
    if prepared is None:
        if hash_ok:
            return [0.0 for _ in decoded]
        return [1.0 for _ in decoded]
    if len(prepared) != len(decoded):
        raise ValueError("frame count does not match the packet sequence")
    energies: list[float] = []
    for frame, recon in zip(prepared, decoded):
        if frame.shape != recon.shape:
            raise ValueError("frame shape does not match the decoded packet")
        diff = np.asarray(frame, dtype=np.float64) - np.asarray(recon, dtype=np.float64)
        denom = float(np.sum(np.asarray(frame, dtype=np.float64) ** 2)) + 1e-12
        energies.append(float(np.sum(diff**2) / denom))
    return energies


def _failing_deltas(
    prepared: list[np.ndarray],
    decoded: list[np.ndarray],
    energies: list[float],
) -> list[dict[str, Any]]:
    failing: list[dict[str, Any]] = []
    previous = np.zeros_like(prepared[0])
    for index, frame in enumerate(prepared):
        residual = frame_residual(frame, previous)
        if energies[index] > ACCEPT_ENERGY:
            motion = motion_vector(residual)
            failing.append(
                {
                    "index": index,
                    "shape": [int(residual.shape[0]), int(residual.shape[1])],
                    "delta": [round(float(value), 6) for value in residual.ravel()],
                    "motion": {
                        "v_x": motion["v_x"],
                        "v_y": motion["v_y"],
                        "unit": "phase_step",
                    },
                    "disagreement": round(float(energies[index]), 6),
                }
            )
        previous = np.asarray(decoded[index], dtype=np.float64)
    return failing


def _clears_sigma(sequence: dict[str, Any], index: int) -> bool:
    """True when this frame is allowed to escalate past the sigma gate."""
    steps = sequence.get("steps") if isinstance(sequence, dict) else None
    if not isinstance(steps, list):
        return True
    for step in steps:
        if not isinstance(step, dict) or int(step.get("index", -1)) != index:
            continue
        if step.get("kind") == "reuse":
            return False
        try:
            return float(step.get("temporal_magnitude")) > TEMPORAL_SIGMA
        except (TypeError, ValueError):
            return False
    return True


def _judge(
    sequence: dict[str, Any],
    decoded: list[np.ndarray],
    prepared: list[np.ndarray] | None,
    *,
    prompt: str,
    budget: dict[str, float],
    control_id: str,
) -> dict[str, Any]:
    risk = risk_classify(prompt or "studio clip")
    claimed = str(sequence.get("sequence_hash") or "")
    try:
        digest = sequence_digest(sequence["base"], list(sequence["deltas"]))
        hashes = _step_hashes(sequence)
        energies = _frame_energies(prepared, decoded, hash_ok=claimed == digest)
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "risk": risk,
            "digest": "",
            "energies": [],
            "energy": 1.0,
            "energy_closed": False,
            "score": 0.0,
            "consistent": False,
            "hash_match": False,
            "hephaestus_ok": False,
            "hephaestus": {"verified": False, "reason": str(exc)},
            "apollo": apollo_success({"status": "failed"}),
            "verify_on_stop": {"verified": False, "reason": str(exc)},
            "themis": None,
            "themis_ok": False,
            "sequence_verified": False,
            "outcome": "rejected",
            "lesson": "verified=false clip packet could not be decoded",
            "decoded": [],
            "failing": [],
        }
    hash_ok = bool(claimed) and claimed == digest
    if not claimed:
        hash_ok = False
    energy_closed = bool(energies) and max(energies) <= ACCEPT_ENERGY
    if prepared is None and hash_ok:
        energy_closed = True
        energies = [0.0 for _ in decoded]
    mean_energy = float(np.mean(energies)) if energies else 1.0
    scars: list[str] = []
    if risk["risk_class"] == "deny":
        scars.append("risk_deny")
    if not hash_ok:
        scars.append("residual_hash_mismatch")
    evidence = [
        {
            "source": "residual_core",
            "result": {"packet_hash": digest, "codec": "studio-clip/1"},
        }
    ]
    score, pairs_ok, pair_result = _pair_consistency(hashes if hash_ok else [""])
    packet = {
        "id": control_id,
        "budget_remaining": dict(budget),
        "evidence": evidence,
        "scars": scars,
        "history": [],
        "verified": False,
    }
    sequence_consistency = residual_consistency(packet)
    consistent = bool(sequence_consistency.get("consistent")) and pairs_ok and hash_ok
    heph = hephaestus_check(packet, residual_packet={"packet_hash": digest})
    heph_ok = bool(heph.verified) and consistent and hash_ok and risk["risk_class"] != "deny"
    preliminary = heph_ok and energy_closed and not scars
    apollo = apollo_success({"status": "ok" if preliminary else ("failed" if scars or not hash_ok or not consistent else "inconclusive")})
    stop = verify_on_stop(packet, apollo, require_evidence=True)
    lesson = (
        f"verified=true residual sequence {digest}"
        if preliminary and stop.get("verified")
        else f"verified=false residual sequence {digest}"
    )
    themis = themis_check(
        packet,
        {"status": "ok" if preliminary and stop.get("verified") else "failed"},
        lesson,
        residual_packet={"packet_hash": digest},
    )
    themis_ok = bool(themis.verified)
    sequence_verified = bool(preliminary and stop.get("verified") and themis_ok and energy_closed)
    if scars or not hash_ok or not consistent or not heph.verified:
        outcome = "rejected"
    elif sequence_verified:
        outcome = "verified"
    else:
        outcome = "inconclusive"
    failing: list[dict[str, Any]] = []
    if prepared is not None and outcome == "inconclusive":
        failing = _failing_deltas(prepared, decoded, energies)
    return {
        "ok": True,
        "reason": "",
        "risk": risk,
        "digest": digest,
        "energies": energies,
        "energy": mean_energy,
        "energy_closed": energy_closed and outcome != "rejected",
        "score": score,
        "consistent": consistent,
        "pair": pair_result,
        "sequence_consistency": sequence_consistency,
        "hash_match": hash_ok,
        "hephaestus_ok": bool(heph.verified) and not scars,
        "hephaestus": heph.to_dict(),
        "apollo": apollo,
        "verify_on_stop": stop,
        "themis": themis.to_dict(),
        "themis_ok": themis_ok,
        "sequence_verified": sequence_verified,
        "outcome": outcome,
        "lesson": lesson if sequence_verified else f"verified=false residual sequence {digest}",
        "decoded": decoded,
        "failing": failing,
        "bits": sequence.get("bits_per_frame") if isinstance(sequence.get("bits_per_frame"), dict) else _blank_bits(),
    }


def _save_checkpoint(
    *,
    control_id: str,
    digest: str,
    lesson: str,
    budget: dict[str, float],
    store_dir: str,
    frame_residuals: list[str] | None = None,
    temporal_delta: float = 0.0,
    keyframe_ids: list[int] | None = None,
    provider_stage: str = "verify",
) -> dict[str, Any]:
    holder = VideoPacket(
        id=control_id,
        frame_residuals=list(frame_residuals or []),
        temporal_delta=float(temporal_delta),
        keyframe_ids=list(keyframe_ids or []),
        provider_stage=provider_stage,
        scene_script_hash=None,
    )
    holder.verified = True
    holder.budget_remaining = dict(budget)
    holder.evidence = [
        {"source": "residual_core", "result": {"packet_hash": digest, "codec": "studio-clip/1"}}
    ]
    holder.history = []
    holder.scars = []
    store = Hades(store_dir)
    saved = store.save(
        holder,
        residual_packet_hash=digest,
        lesson=lesson,
        extra={
            "kind": "clip",
            "frame_residuals": list(holder.frame_residuals),
            "temporal_delta": holder.temporal_delta,
            "keyframe_ids": list(holder.keyframe_ids),
            "provider_stage": holder.provider_stage,
            "scene_script_hash": None,
        },
    )
    return {
        "id": saved.id,
        "lesson": saved.lesson,
        "residual_hash": saved.residual_packet_hash,
        "verified": saved.verified,
    }


def _apply_judge(body: dict[str, Any], judged: dict[str, Any], sequence: dict[str, Any] | None) -> None:
    bits = judged.get("bits") if isinstance(judged.get("bits"), dict) else _blank_bits()
    energy = float(judged.get("energy") or 0.0)
    score = float(judged.get("score") or 0.0)
    verified = bool(judged.get("sequence_verified"))
    body["sequence"] = sequence
    body["packet_hash"] = judged.get("digest") or ""
    body["residual_hash"] = judged.get("digest") or ""
    body["energy"] = energy
    body["bits_per_frame"] = bits
    body["preview"] = _preview(judged.get("decoded") or [])
    body["sequence_verified"] = verified
    body["verified_sequence"] = verified
    body["mouth"] = _mouth(verified)
    body["checks"] = {
        "hash_match": bool(judged.get("hash_match")),
        "residual_consistency": bool(judged.get("consistent")),
        "consistency_score": score,
        "hephaestus": bool(judged.get("hephaestus_ok")),
        "apollo": bool((judged.get("apollo") or {}).get("success")),
        "verify_on_stop": bool((judged.get("verify_on_stop") or {}).get("verified")),
        "themis": bool(judged.get("themis_ok")) if judged.get("themis") is not None else None,
        "risk_class": (judged.get("risk") or {}).get("risk_class"),
        "energy_closed": bool(judged.get("energy_closed")),
    }
    body["hephaestus"] = judged.get("hephaestus")
    body["apollo"] = judged.get("apollo")
    body["themis"] = judged.get("themis")
    body["verify_on_stop"] = judged.get("verify_on_stop")
    body["residual_consistency"] = judged.get("sequence_consistency")
    body["badge"] = {
        "energy": energy,
        "consistency_score": score,
        "base_bits": int(bits.get("base") or 0),
        "mean_delta_bits": float(bits.get("mean_delta") or 0.0),
        "sequence_verified": verified,
    }
    body["lesson"] = judged.get("lesson") or ""
    body["risk"] = judged.get("risk")


def run_sequence_stage(
    *,
    stage: str,
    prompt: str = "",
    frames: Any = None,
    sequence: dict[str, Any] | None = None,
    context: Any = None,
    control: Any = None,
    provider_fn: Any = None,
    learn: Any = None,
    bypass_zeus: bool = False,
    zeus: Any = None,
    history: Any = None,
    register: bool = True,
    store_dir: str | None = None,
) -> dict[str, Any]:
    """Draft, verify, or upscale one supplied clip. Draft does not call a provider."""
    _refuse(learn=learn, bypass_zeus=bypass_zeus, zeus=zeus)
    prompt = str(prompt or "")[:2000]
    ranked, hermes_budget = _rank_context(context, prompt)
    risk = risk_classify(prompt or "studio clip")
    control_id = _control_id(control)
    budget = _budget(control)
    hades_dir = store_dir or _hades_dir()
    prior = history
    if prior is None and isinstance(control, dict):
        prior = control.get("clip_history")
    stage_name = stage if stage in _STAGES else ""
    if stage_name == "":
        body = _common(
            stage="draft",
            prompt=prompt,
            status="refused",
            outcome="rejected",
            sequence_verified=False,
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=risk,
        )
        body["detail"] = "Unknown forge stage."
        body["reason"] = "Unknown forge stage."
        return _finish(
            body,
            control=control,
            stage="draft",
            control_id=control_id,
            digest="",
            energy=0.0,
            score=0.0,
            verify_result="rejected",
            budget_used={"steps": 0, "cost": 0.0},
            checkpoint_id=None,
            prior_history=prior,
        )

    has_frames = frames is not None and not (isinstance(frames, (list, tuple)) and len(frames) == 0)
    has_sequence = isinstance(sequence, dict)
    if stage_name == "draft" and not has_frames and not has_sequence:
        body = _common(
            stage="draft",
            prompt=prompt,
            status="UNAVAILABLE",
            outcome="unavailable",
            sequence_verified=False,
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=risk,
        )
        body["detail"] = "No video generator is configured on this host."
        body["draft"] = False
        return _finish(
            body,
            control=control,
            stage="draft",
            control_id=control_id,
            digest="",
            energy=0.0,
            score=0.0,
            verify_result="unavailable",
            budget_used={"steps": 0, "cost": 0.0},
            checkpoint_id=None,
            prior_history=prior,
        )

    loaded, prepared, error = _load_sequence(frames if has_frames else None, sequence if has_sequence else None)
    if loaded is None:
        body = _common(
            stage=stage_name,
            prompt=prompt,
            status="rejected",
            outcome="rejected",
            sequence_verified=False,
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=risk,
        )
        body["detail"] = error or "nothing to verify"
        body["reason"] = body["detail"]
        return _finish(
            body,
            control=control,
            stage=stage_name,
            control_id=control_id,
            digest="",
            energy=0.0,
            score=0.0,
            verify_result="rejected",
            budget_used={"steps": 1, "cost": 0.0},
            checkpoint_id=None,
            prior_history=prior,
        )
    try:
        decoded = decode_sequence(loaded)
    except (TypeError, ValueError, KeyError) as exc:
        body = _common(
            stage=stage_name,
            prompt=prompt,
            status="rejected",
            outcome="rejected",
            sequence_verified=False,
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=risk,
        )
        body["detail"] = str(exc)
        body["reason"] = str(exc)
        return _finish(
            body,
            control=control,
            stage=stage_name,
            control_id=control_id,
            digest="",
            energy=0.0,
            score=0.0,
            verify_result="rejected",
            budget_used={"steps": 1, "cost": 0.0},
            checkpoint_id=None,
            prior_history=prior,
        )

    if stage_name == "draft":
        digest = ""
        try:
            digest = sequence_digest(loaded["base"], list(loaded["deltas"]))
        except (TypeError, ValueError, KeyError):
            digest = str(loaded.get("sequence_hash") or "")
        energies: list[float] = []
        if prepared is not None and len(prepared) == len(decoded):
            try:
                energies = _frame_energies(prepared, decoded, hash_ok=True)
            except (TypeError, ValueError):
                energies = []
        elif isinstance(loaded.get("frame_energy"), list) and loaded["frame_energy"]:
            try:
                energies = [float(value) for value in loaded["frame_energy"]]
            except (TypeError, ValueError):
                energies = []
        energy = float(np.mean(energies)) if energies else 0.0
        bits = loaded.get("bits_per_frame") if isinstance(loaded.get("bits_per_frame"), dict) else _blank_bits()
        body = _common(
            stage="draft",
            prompt=prompt,
            status="drafted",
            outcome="drafted",
            sequence_verified=False,
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=risk,
        )
        body["sequence"] = loaded
        body["preview"] = _preview(decoded)
        body["packet_hash"] = digest
        body["residual_hash"] = digest
        body["energy"] = energy
        body["bits_per_frame"] = bits
        body["badge"] = {
            "energy": energy,
            "consistency_score": 0.0,
            "base_bits": int(bits.get("base") or 0),
            "mean_delta_bits": float(bits.get("mean_delta") or 0.0),
            "sequence_verified": False,
        }
        body["energy_closed"] = bool(energies) and max(energies) <= ACCEPT_ENERGY
        body["detail"] = "Draft packet from supplied frames. Verify has not run."
        return _finish(
            body,
            control=control,
            stage="draft",
            control_id=control_id,
            digest=digest if len(digest) == 64 else "",
            energy=energy,
            score=0.0,
            verify_result="drafted",
            budget_used={"steps": 1, "cost": round(energy, 6)},
            checkpoint_id=None,
            prior_history=prior,
        )

    judged = _judge(
        loaded,
        decoded,
        prepared,
        prompt=prompt,
        budget=budget,
        control_id=control_id,
    )
    outcome = str(judged["outcome"])
    if stage_name == "verify":
        status = outcome
        body = _common(
            stage="verify",
            prompt=prompt,
            status=status,
            outcome=outcome,
            sequence_verified=bool(judged["sequence_verified"]),
            ranked=ranked,
            hermes_budget=hermes_budget,
            risk=judged["risk"],
        )
        _apply_judge(body, judged, loaded)
        checkpoint_id = None
        if judged["sequence_verified"]:
            saved = _save_checkpoint(
                control_id=control_id,
                digest=str(judged["digest"]),
                lesson=str(judged["lesson"]),
                budget=budget,
                store_dir=hades_dir,
                frame_residuals=list(loaded.get("frame_residuals") or []),
                temporal_delta=float(loaded.get("temporal_delta") or 0.0),
                keyframe_ids=[int(item) for item in loaded.get("keyframe_ids") or []],
                provider_stage="verify",
            )
            body["checkpoint"] = saved
            body["checkpoint_id"] = saved["id"]
            body["hades_checkpoint"] = True
            body["lesson"] = saved["lesson"]
            checkpoint_id = saved["id"]
            if register:
                body["candidate"] = register_candidate(
                    kind="clip",
                    path=f"candidate://studio/clip/{str(judged['digest'])[:12]}",
                    title=f"CANDIDATE clip {str(judged['digest'])[:8]}",
                    world_id="studio",
                    note="verified residual clip; learn was not called",
                )
        body["upscale_enabled"] = outcome in {"verified", "inconclusive"}
        if judged.get("reason"):
            body["reason"] = judged["reason"]
        return _finish(
            body,
            control=control,
            stage="verify",
            control_id=control_id,
            digest=str(judged.get("digest") or ""),
            energy=float(judged.get("energy") or 0.0),
            score=float(judged.get("score") or 0.0),
            verify_result=outcome if outcome in {"verified", "inconclusive", "rejected"} else "rejected",
            budget_used={"steps": 1, "cost": round(float(judged.get("energy") or 0.0), 6)},
            checkpoint_id=checkpoint_id,
            prior_history=prior,
        )

    body = _common(
        stage="upscale",
        prompt=prompt,
        status="refused",
        outcome=outcome,
        sequence_verified=bool(judged["sequence_verified"]),
        ranked=ranked,
        hermes_budget=hermes_budget,
        risk=judged["risk"],
    )
    _apply_judge(body, judged, loaded)
    checks = body["checks"]
    if outcome == "rejected" or not checks.get("hash_match") or not checks.get("hephaestus") or checks.get("risk_class") == "deny":
        body["status"] = "refused"
        body["detail"] = "Upscale waits until the residual packet is consistent."
        if checks.get("risk_class") == "deny" or not checks.get("hephaestus"):
            body["detail"] = "External upscale stays refused until residual and Hephaestus checks pass."
        body["url"] = None
        body["upscale_enabled"] = False
        return _finish(
            body,
            control=control,
            stage="upscale",
            control_id=control_id,
            digest=str(judged.get("digest") or ""),
            energy=float(judged.get("energy") or 0.0),
            score=float(judged.get("score") or 0.0),
            verify_result="refused",
            budget_used={"steps": 1, "cost": round(float(judged.get("energy") or 0.0), 6)},
            checkpoint_id=None,
            prior_history=prior,
        )
    if outcome == "verified" or checks.get("energy_closed"):
        body["status"] = "not_required"
        body["detail"] = "Residual packet closed the sequence. Upscale stays off."
        body["url"] = None
        body["upscale_enabled"] = True
        body["provider_frames"] = 0
        body["provider_cost"] = 0.0
        return _finish(
            body,
            control=control,
            stage="upscale",
            control_id=control_id,
            digest=str(judged.get("digest") or ""),
            energy=float(judged.get("energy") or 0.0),
            score=float(judged.get("score") or 0.0),
            verify_result="not_required",
            budget_used={"steps": 1, "cost": round(float(judged.get("energy") or 0.0), 6)},
            checkpoint_id=None,
            prior_history=prior,
        )
    if not (
        checks.get("hash_match")
        and checks.get("residual_consistency")
        and checks.get("hephaestus")
        and checks.get("risk_class") == "allow"
    ):
        body["status"] = "refused"
        body["detail"] = "External upscale stays refused until residual and Hephaestus checks pass."
        body["url"] = None
        body["upscale_enabled"] = False
        return _finish(
            body,
            control=control,
            stage="upscale",
            control_id=control_id,
            digest=str(judged.get("digest") or ""),
            energy=float(judged.get("energy") or 0.0),
            score=float(judged.get("score") or 0.0),
            verify_result="refused",
            budget_used={"steps": 1, "cost": round(float(judged.get("energy") or 0.0), 6)},
            checkpoint_id=None,
            prior_history=prior,
        )
    failing = [
        item
        for item in list(judged.get("failing") or [])
        if _clears_sigma(loaded, int(item["index"]))
    ]
    if not failing:
        body["status"] = "not_required"
        body["detail"] = "Residual packet closed the sequence. Upscale stays off."
        body["url"] = None
        body["provider_frames"] = 0
        body["provider_cost"] = 0.0
        body["upscale_enabled"] = True
        return _finish(
            body,
            control=control,
            stage="upscale",
            control_id=control_id,
            digest=str(judged.get("digest") or ""),
            energy=float(judged.get("energy") or 0.0),
            score=float(judged.get("score") or 0.0),
            verify_result="not_required",
            budget_used={"steps": 1, "cost": round(float(judged.get("energy") or 0.0), 6)},
            checkpoint_id=None,
            prior_history=prior,
        )
    cost = float(sum(item["disagreement"] for item in failing))
    if prepared is not None:
        full_cost = float(sum(float(np.mean(np.asarray(frame) ** 2)) for frame in prepared))
    else:
        full_cost = float(sum(judged.get("energies") or [])) or cost
    payload = {
        "kind": "residual_delta",
        "packet_hash": judged.get("digest"),
        "n_frames": len(failing),
        "full_clip": False,
        "disagreement": round(cost / max(len(failing), 1), 6),
        "frames": [
            {
                "index": item["index"],
                "shape": item["shape"],
                "delta": item["delta"],
                "motion": item["motion"],
            }
            for item in failing
        ],
    }
    from resileos.studio.residual_cascade import _call_slot

    body["provider_called"] = True
    called = _call_slot(provider_fn, payload)
    body["provider_frames"] = len(failing)
    body["provider_cost"] = cost
    body["full_duration_cost"] = full_cost
    body["upscale_payload"] = {
        "kind": "residual_delta",
        "n_frames": len(failing),
        "full_clip": False,
        "disagreement": payload["disagreement"],
    }
    body["upscale_enabled"] = True
    if not called["ok"]:
        body["status"] = "UNAVAILABLE"
        body["url"] = None
        body["draft"] = False
        body["detail"] = called["detail"]
        verify_result = "unavailable"
    else:
        body["status"] = "submitted"
        body["url"] = called["url"]
        body["draft"] = False
        body["detail"] = ""
        body["reencoded"] = False
        body["next_verify"] = True
        verify_result = "submitted"
    body["sequence_verified"] = False
    body["verified_sequence"] = False
    body["mouth"] = False
    body["candidate"] = None
    body["badge"]["sequence_verified"] = False
    return _finish(
        body,
        control=control,
        stage="upscale",
        control_id=control_id,
        digest=str(judged.get("digest") or ""),
        energy=float(judged.get("energy") or 0.0),
        score=float(judged.get("score") or 0.0),
        verify_result=verify_result,
        budget_used={"steps": 1, "cost": round(cost, 6)},
        checkpoint_id=None,
        prior_history=prior,
    )


def restore_clip_checkpoint(ckpt_id: str, *, store_dir: str | None = None) -> dict[str, Any]:
    """Fresh packet from a clip checkpoint. History of frames is not restored."""
    if not isinstance(ckpt_id, str) or re.fullmatch(r"[0-9a-f]{12}", ckpt_id) is None:
        fresh = ControlPacket(id="fresh")
        fresh.verified = False
        return {
            "checkpoint_id": None,
            "lesson": "",
            "residual_hash": None,
            "verified": False,
            "fresh": {
                "id": fresh.id,
                "verified": False,
                "history": [],
                "scars": [],
            },
        }
    store = Hades(store_dir or _hades_dir())
    loaded = store.load(ckpt_id)
    fresh = store.restore_fresh(ckpt_id)
    history = []
    for item in list(fresh.history or [])[-8:]:
        if isinstance(item, dict):
            history.append(
                {
                    "event": item.get("event"),
                    "lesson": item.get("lesson"),
                    "from": item.get("from"),
                }
            )
    return {
        "checkpoint_id": loaded.id if loaded is not None else None,
        "lesson": loaded.lesson if loaded is not None else "",
        "residual_hash": loaded.residual_packet_hash if loaded is not None else None,
        "verified": bool(loaded.verified) if loaded is not None else False,
        "fresh": {
            "id": fresh.id,
            "verified": bool(fresh.verified),
            "history": history,
            "scars": list(fresh.scars or []),
        },
    }


def checkpoint_verified_clip(
    *,
    prompt: str = "",
    frames: Any = None,
    sequence: dict[str, Any] | None = None,
    store_dir: str | None = None,
) -> dict[str, Any]:
    """Hades checkpoint for a sequence that verifies. Refuses the rest.

    The saved record is the lesson and the packet hash. Frame pixels are
    not written.
    """
    produced = run_sequence_stage(
        stage="verify",
        prompt=prompt,
        frames=frames,
        sequence=sequence,
        register=False,
        store_dir=store_dir,
    )
    if not produced.get("sequence_verified"):
        return {
            "status": "refused",
            "checkpoint_id": None,
            "lesson": produced.get("lesson") or "",
            "residual_hash": produced.get("residual_hash"),
            "verified": False,
            "detail": "Checkpoint waits until the sequence is verified.",
            "url": None,
        }
    return {
        "status": "checkpoint",
        "checkpoint_id": produced.get("checkpoint_id"),
        "lesson": produced.get("lesson") or "",
        "residual_hash": produced.get("residual_hash"),
        "verified": True,
        "detail": "",
        "url": None,
    }


__all__ = ["checkpoint_verified_clip", "restore_clip_checkpoint", "run_sequence_stage"]
