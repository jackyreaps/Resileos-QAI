"""Gate a studio packet with the checks that already exist.

Hephaestus sees a harness control packet: well-formed, no scars, budget,
capacity. residual_consistency sees the codec hash. Themis runs when that
evidence and a lesson exist. A malformed codec packet is a scar, so
Hephaestus fails it.

This module does not call learn and does not read or write Lambda.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
from studio.codec import decode, pack_packet, unpack_packet

from resileos.harness.tools import residual_consistency
from resileos.kin.demigods.checks import atlas_check, hephaestus_check, themis_check
from resileos.studio.codecs import packet_summary


def _finite_decode(packet: dict[str, Any]) -> tuple[bool, str]:
    if packet.get("version") != "studio-codec/1":
        return False, "version is not studio-codec/1"
    if packet.get("scale_mode") != "component":
        return False, "studio mode requires per-component scales"
    layers = packet.get("layers") or []
    rank = int(packet.get("rank") or 0)
    if not layers or rank < 1:
        return False, "packet has no layers"
    for layer in layers:
        scale = layer.get("scale")
        if not isinstance(scale, (list, tuple)) or len(scale) != rank:
            return False, "a layer is missing per-component scales"
        ub = np.asarray(layer.get("Ub"))
        vb = np.asarray(layer.get("Vb"))
        if ub.shape != (int(packet["shape"][0]), rank) or vb.shape != (rank, int(packet["shape"][1])):
            return False, "factor shape does not match the packet"
        if np.any(np.abs(np.abs(ub) - 1.0) > 1e-5) or np.any(np.abs(np.abs(vb) - 1.0) > 1e-5):
            return False, "factors are not ±1"
    try:
        restored = unpack_packet(pack_packet(packet))
        image = decode(restored)
    except (ValueError, TypeError) as exc:
        return False, f"packet does not decode: {exc}"
    if image.shape != (int(packet["shape"][0]), int(packet["shape"][1])):
        return False, "decode shape disagrees with the packet"
    if not np.isfinite(image).all():
        return False, "decode is not finite"
    return True, "round trip produced a finite image"


def codec_packet_hash(packet: dict[str, Any]) -> str:
    return hashlib.sha256(pack_packet(packet)).hexdigest()


def gate_studio_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Return Hephaestus, residual consistency, and Themis verdicts.

    Themis's lesson says verified=true only when the packet itself round-trips.
    Apollo's status is that same check. Neither one is a judgment of taste.
    """
    ok, reason = _finite_decode(packet)
    digest = ""
    evidence: list[dict[str, Any]] = []
    scars: list[str] = []
    if ok:
        digest = codec_packet_hash(packet)
        evidence.append(
            {
                "source": "residual_core",
                "result": {"packet_hash": digest, "codec": "studio-codec/1"},
            }
        )
    else:
        scars.append(f"codec_packet_malformed: {reason}")
    control = {
        "id": "studio-codec",
        "budget_remaining": {"steps": 8, "cost": 1.0},
        "scars": scars,
        "evidence": evidence,
        "history": [],
        "state": {"n_facts": 0},
    }
    consistency = residual_consistency(control)
    residual = {"packet_hash": digest} if digest else None
    hephaestus = hephaestus_check(control, residual_packet=residual)
    # Capacity moved to Atlas. n_facts stays a declared load, not a Hephaestus argument.
    atlas_check(control, n_facts=0, residual_packet=residual)
    if ok:
        lesson = (
            "studio-codec/1 per-component packet decoded to a finite image. "
            "verified=true"
        )
        apollo = {"status": "ok", "reason": reason}
    else:
        lesson = f"studio packet failed the codec check. verified=false ({reason})"
        apollo = {"status": "failed", "reason": reason}
    themis = themis_check(
        control,
        apollo,
        lesson,
        residual_packet=residual,
    )
    return {
        "well_formed": ok,
        "reason": reason,
        "packet_hash": digest or None,
        "residual_consistency": consistency,
        "hephaestus": hephaestus.to_dict(),
        "themis": themis.to_dict(),
        "lesson": lesson,
        "learned": False,
        "scar_matrix_updated": False,
        "summary": packet_summary(packet) if ok else None,
    }
