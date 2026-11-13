"""Content-free residual factors for hub training.

By default, a verified contribution of residual factors — bins, belt
and chroma coordinates, φ-weighted aggregates, counts, error and scar
signals, and a factorization fingerprint — may train ``org:`` and
``world:`` without opt-in. Raw text, frames, and any reversible
encoding of them are never included. A contributor or tenant may set
``opt_out=True`` to stay out of this default path.

Opt-in is the more open level: sharing richer material up a tier.
That path stays on ``resileos.persona.promote`` and still needs
explicit opt-in, verification, and a write through Eat.

Energy below 1/64 is dropped. Factor lists are capped at the waist
(36). An aggregate is emitted only when at least
``MIN_CONTRIBUTORS`` verified, not-opted-out contributions are
present. Numeric values are quantized onto the debt-quantum grid
(ε = 1/64).

This module does not call learn or write a scar. When a Titanos
instance is given, the aggregate envelope is handed to
``eat_commit_envelopes`` so Eat and the reviewers remain the only
writers. Otherwise the envelope is returned for Eat to consume.
The Titanos triple stores this factor aggregate, not source content.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from resileos.persona.promote import subject_at
from resileos.ui.cascade_address import (
    BELT,
    DYADIC,
    EPSILON,
    TRIADIC,
    WAIST,
    clip_factors,
    keep_packet,
    orientation_scale,
)
from resileos.ui.suite_residual import suite_residual

MIN_CONTRIBUTORS = 3
FACTOR_RELATION = "residual_factors"
FACTOR_VERSION = "residual-factors/1"

_CONTENT_KEYS = frozenset(
    {
        "text",
        "content",
        "body",
        "frame",
        "frames",
        "pixels",
        "image",
        "arr",
        "payload",
        "obj",
        "object",
        "snippet",
        "title",
        "message",
        "utterance",
    }
)


def _quantize(value: float) -> float:
    """Snap a real onto the debt-quantum grid, ε = 1/64."""
    return float(round(float(value) / EPSILON) * EPSILON)


def _fingerprint(fields: dict[str, Any]) -> str:
    """Structural signature of a factorization, not of source content."""
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _bin_of(
    residual_bin: str | None,
    mean_luma: float | None,
    edge_density: float | None,
    belt: int,
) -> str:
    if residual_bin:
        return str(residual_bin)
    luma = 0.0 if mean_luma is None else float(mean_luma)
    edge = 0.0 if edge_density is None else float(edge_density)
    return suite_residual(luma, edge, int(belt))


def factorize(
    *,
    energy: float,
    verified: bool,
    residual_bin: str | None = None,
    mean_luma: float | None = None,
    edge_density: float | None = None,
    belt: int = BELT,
    orientation: str | None = None,
    factor_count: int = 0,
    error: float | None = None,
    scar_energy: float | None = None,
    previous_energy: float | None = None,
    opt_out: bool = False,
    ident: str | None = None,
) -> dict[str, Any] | None:
    """Return one content-free factor record, or None if it must not train.

    Unverified, opted-out, or sub-quantum contributions are dropped.
    Extra content fields are not accepted: only the named arguments
    are read.
    """
    if not verified or opt_out:
        return None
    if not keep_packet(energy):
        return None
    count = max(0, min(int(factor_count), WAIST))
    residual = _bin_of(residual_bin, mean_luma, edge_density, belt)
    level = 0
    orientation_name = ""
    weight = 1.0
    if orientation:
        control = orientation_scale(orientation)
        level = int(control["scale_level"])
        orientation_name = str(control["orientation"])
        weight = float(control["phi_weight"])
    err = _quantize(energy if error is None else error)
    scar = _quantize(0.0 if scar_energy is None else scar_energy)
    improvement = 0.0
    if previous_energy is not None:
        improvement = _quantize(float(previous_energy) - float(energy))
    chroma = {"dyadic": DYADIC, "triadic": TRIADIC}
    structure = {
        "bin": residual,
        "belt": int(BELT),
        "chroma": chroma,
        "scale_level": level,
        "orientation": orientation_name,
        "factor_count": count,
        "error": err,
        "scar": scar,
        "improvement": improvement,
        "phi_weight": _quantize(weight),
    }
    record = {
        "version": FACTOR_VERSION,
        "verified": True,
        "energy": _quantize(energy),
        **structure,
        "fingerprint": _fingerprint(structure),
    }
    if ident:
        # Kept only for opt-out matching. Never copied into an aggregate.
        record["ident"] = str(ident)
    return record


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return _quantize(sum(values) / len(values))


def aggregate_factors(
    contributions: Iterable[dict[str, Any] | None],
    *,
    to_scale: str,
    ident: str,
    min_contributors: int = MIN_CONTRIBUTORS,
    opt_out_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Combine verified residual factors for one outward hub.

    ``to_scale`` is ``local`` (org:) or ``global`` (world:). Individual
    contributions go to the local hub; local aggregates may go to
    global. Nothing is emitted until ``min_contributors`` records
    remain after opt-out. The result does not write; it returns an
    Eat envelope whose object is the factor aggregate.
    """
    blocked = {str(item) for item in (opt_out_ids or []) if str(item).strip()}
    kept: list[dict[str, Any]] = []
    for item in contributions:
        if not isinstance(item, dict):
            continue
        if item.get("ident") and str(item["ident"]) in blocked:
            continue
        if item.get("opt_out"):
            continue
        if not item.get("verified"):
            continue
        if not keep_packet(float(item.get("energy") or 0.0)):
            continue
        kept.append(item)
    if to_scale not in {"local", "global"}:
        return {
            "ok": False,
            "decision": "refuse",
            "reason": "residual factors only train local or global hubs",
            "writes": False,
            "learned": False,
        }
    if len(kept) < int(min_contributors):
        return {
            "ok": False,
            "decision": "refuse",
            "reason": "below minimum contributor count",
            "count": len(kept),
            "min_contributors": int(min_contributors),
            "writes": False,
            "learned": False,
        }
    bins: dict[str, int] = {}
    for item in kept:
        label = str(item.get("bin") or "")
        bins[label] = bins.get(label, 0) + 1
    # Prefer recurring bins, then a stable label order, then cap at the waist.
    ranked = sorted(bins.items(), key=lambda pair: (-pair[1], pair[0]))
    bin_rows = clip_factors([{"bin": name, "n": n} for name, n in ranked])
    errors = [float(item.get("error") or 0.0) for item in kept]
    scars = [float(item.get("scar") or 0.0) for item in kept]
    gains = [float(item.get("improvement") or 0.0) for item in kept]
    weights = [float(item.get("phi_weight") or 1.0) for item in kept]
    counts = [int(item.get("factor_count") or 0) for item in kept]
    levels = [int(item.get("scale_level") or 0) for item in kept]
    structure = {
        "v": FACTOR_VERSION,
        "n": len(kept),
        "bins": bin_rows,
        "belt": BELT,
        "chroma": {"dyadic": DYADIC, "triadic": TRIADIC},
        "scale_level": int(round(sum(levels) / len(levels))) if levels else 0,
        "phi_weight": _mean(weights),
        "error": _mean(errors),
        "scar": _mean(scars),
        "improvement": _mean(gains),
        "factor_count": int(round(sum(counts) / len(counts))) if counts else 0,
    }
    structure["factor_count"] = max(0, min(structure["factor_count"], WAIST))
    structure["fingerprint"] = _fingerprint(structure)
    subject = subject_at(to_scale, ident)
    obj = json.dumps(structure, sort_keys=True, separators=(",", ":"))
    envelope = {
        "claim": {
            "subject": subject,
            "relation": FACTOR_RELATION,
            "obj": obj,
        },
        "source": "residual-factors",
    }
    return {
        "ok": True,
        "decision": "accept",
        "scale": to_scale,
        "subject": subject,
        "relation": FACTOR_RELATION,
        "obj": obj,
        "aggregate": structure,
        "envelope": envelope,
        "count": len(kept),
        "writes": False,
        "learned": False,
        "content": False,
    }


def offer_to_eat(
    result: dict[str, Any],
    *,
    titanos: Any | None = None,
    eat_kw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hand an accepted aggregate to Eat, or return the envelope.

    When ``titanos`` is omitted the envelope is left for Eat to
    consume. This function never calls ``Titanos.learn`` directly.
    """
    out = dict(result)
    if not result.get("ok"):
        return out
    envelope = result["envelope"]
    if titanos is None:
        out["eat"] = "pending"
        return out
    from resileos.kin.eat_envelope import eat_commit_envelopes

    committed = eat_commit_envelopes([envelope], titanos=titanos, eat_kw=eat_kw)
    out["eat"] = committed
    out["writes"] = False
    out["learned"] = bool(committed.get("summary", {}).get("applied"))
    return out


def contains_content(blob: Any, secrets: Iterable[str], pixels: Iterable[Any] = ()) -> bool:
    """True if any secret string or pixel payload appears in ``blob``."""
    text = blob if isinstance(blob, str) else json.dumps(blob, default=list)
    for secret in secrets:
        if secret and secret in text:
            return True
    packed = text.encode("utf-8") if isinstance(text, str) else b""
    for frame in pixels:
        try:
            import numpy as np

            raw = np.asarray(frame).tobytes()
        except Exception:
            continue
        if raw and raw in packed:
            return True
    return False
