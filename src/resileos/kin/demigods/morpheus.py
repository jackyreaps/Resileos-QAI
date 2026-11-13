"""Morpheus — dream consolidation from Hades checkpoints and idle cycles.

Replays logged turns and candidate branches, compresses a recurring
pattern with the studio residual codec, and asks Hephaestus and Themis
before anything can be promoted. Promotion goes through Zeus. This
module uses numpy on CPU. An optional backend may replace the codec
call. It does not import a training framework or a GPU runtime.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Callable

import numpy as np

from resileos.harness.packet import ControlPacket
from resileos.harness.separated import Proposal, Verdict, zeus_head
from resileos.kin.demigods.checks import hephaestus_check, themis_check


def _key(turn: dict[str, Any]) -> tuple[str, str, str] | None:
    subject = str(turn.get("subject") or "").strip()
    relation = str(turn.get("relation") or "").strip()
    obj = turn.get("obj")
    if obj in (None, ""):
        obj = turn.get("candidate")
    obj_text = "" if obj in (None, "") else str(obj).strip()
    if not (subject and relation and obj_text):
        return None
    return subject, relation, obj_text


def replay(turns: list[dict[str, Any]], *, min_count: int = 2) -> list[dict[str, Any]]:
    """Count recurring triples. A candidate observation stays unverified."""
    counts: Counter[tuple[str, str, str]] = Counter()
    candidate_only: dict[tuple[str, str, str], bool] = {}
    scars: dict[tuple[str, str, str], list[str]] = {}
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        key = _key(turn)
        if key is None:
            continue
        counts[key] += 1
        status = str(turn.get("status") or "").upper()
        was_candidate = status == "CANDIDATE"
        prior = candidate_only.get(key, True)
        candidate_only[key] = prior and was_candidate
        if turn.get("scars"):
            scars[key] = [str(item) for item in turn["scars"]]
    patterns = []
    for key, count in sorted(counts.items()):
        if count < min_count:
            continue
        subject, relation, obj = key
        patterns.append(
            {
                "subject": subject,
                "relation": relation,
                "obj": obj,
                "count": int(count),
                "candidate_only": bool(candidate_only.get(key, False)),
                "scars": list(scars.get(key) or []),
            }
        )
    return patterns


def matrix_for(pattern: dict[str, Any], *, size: int = 8) -> np.ndarray:
    """Deterministic CPU matrix. Not a learned weight."""
    text = f"{pattern.get('subject')}|{pattern.get('relation')}|{pattern.get('obj')}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    return rng.standard_normal((size, size)).astype(np.float64)


def compress(pattern: dict[str, Any], *, backend: Callable[[np.ndarray], Any] | None = None) -> dict[str, Any]:
    matrix = matrix_for(pattern)
    if backend is not None:
        packet = backend(matrix)
    else:
        from studio.codec import encode

        packet = encode(matrix, rank=2, n_layers=2, seed=0)
    digest = hashlib.sha256(repr(sorted(pattern.items())).encode("utf-8")).hexdigest()
    return {"packet": packet, "packet_hash": digest, "backend": "hook" if backend else "studio-codec"}


def _control(packet_hash: str, *, scars: list[str] | None = None) -> ControlPacket:
    control = ControlPacket(id=f"morpheus-{packet_hash[:8]}")
    control.evidence = [
        {"source": "probe", "result": {"matched": 1, "packet_hash": packet_hash}},
    ]
    control.scars = list(scars or [])
    control.verified = False
    return control


def gate_pattern(pattern: dict[str, Any], compressed: dict[str, Any]) -> dict[str, Any]:
    """Hephaestus scar check and Themis consistency. Neither one learns."""
    control = _control(
        str(compressed.get("packet_hash") or ""),
        scars=list(pattern.get("scars") or []),
    )
    hephaestus = hephaestus_check(control)
    if pattern.get("candidate_only"):
        lesson = "turn: verified=false candidate only"
        apollo = {"status": "abstain"}
    else:
        lesson = "turn: verified=true recurring pattern"
        apollo = {"status": "ok"}
    themis = themis_check(control, apollo, lesson)
    ok = bool(getattr(hephaestus, "verified", False) and getattr(themis, "verified", False))
    return {
        "ok": ok,
        "hephaestus": bool(getattr(hephaestus, "verified", False)),
        "themis": bool(getattr(themis, "verified", False)),
        "lesson": lesson,
        "hephaestus_reason": getattr(hephaestus, "reason", ""),
        "themis_reason": getattr(themis, "reason", ""),
    }


def promote(
    pattern: dict[str, Any],
    learn_fn: Callable[[str, str, str], None],
    *,
    approve: bool,
) -> dict[str, Any]:
    """Zeus applies the triple only when the reviewer approves."""
    subject = str(pattern["subject"])
    relation = str(pattern["relation"])
    obj = str(pattern["obj"])
    control = ControlPacket(id=f"morpheus-promote-{subject}")
    proposal = Proposal(
        id=control.id,
        writer="morpheus",
        action_type="learn",
        result={"status": "ok" if approve else "no"},
        claims=[(subject, relation, obj)],
        packet=control,
    )

    def review(item: Proposal) -> Verdict:
        if approve:
            return Verdict(item.id, "morpheus-gate", True, "gates passed", [])
        return Verdict(item.id, "morpheus-gate", False, "gates failed", [])

    return zeus_head(proposal, [("morpheus-gate", review)], learn_fn)


def run_idle(
    turns: list[dict[str, Any]],
    learn_fn: Callable[[str, str, str], None],
    *,
    backend: Callable[[np.ndarray], Any] | None = None,
    min_count: int = 2,
) -> dict[str, Any]:
    """One idle pass. ``learn_fn`` runs only inside Zeus after the gates pass."""
    results = []
    for pattern in replay(turns, min_count=min_count):
        compressed = compress(pattern, backend=backend)
        gate = gate_pattern(pattern, compressed)
        head = promote(pattern, learn_fn, approve=bool(gate["ok"]))
        results.append(
            {
                "pattern": pattern,
                "packet_hash": compressed["packet_hash"],
                "backend": compressed["backend"],
                "gate": gate,
                "applied": bool(head.get("applied")),
                "learned_direct": False,
            }
        )
    return {
        "patterns": len(results),
        "results": results,
        "device": "cpu",
        "writes_before_review": False,
    }


def dream_factor_candidates(
    aggregates: list[dict[str, Any]],
    *,
    min_improvement: float = 0.0,
) -> dict[str, Any]:
    """Recombine content-free factor aggregates into unverified candidates.

    This is the dream / creative consolidation path for residual
    factors: error and scar signals, factorization fingerprints,
    belt and orientation coordinates, and residual improvement.
    Candidates stay unverified. This function never calls learn,
    never writes Titanos, and never updates a scar matrix. A later
    verification gate (Eat, with reviewer approval) is the only way
    a candidate can be stored.
    """
    candidates: list[dict[str, Any]] = []
    for item in aggregates or []:
        if not isinstance(item, dict):
            continue
        body = item.get("aggregate") if isinstance(item.get("aggregate"), dict) else item
        error = float(body.get("error") or 0.0)
        scar = float(body.get("scar") or 0.0)
        improvement = float(body.get("improvement") or 0.0)
        if improvement < float(min_improvement) and error <= 0.0 and scar <= 0.0:
            # Nothing to improve: skip empty or flat aggregates.
            if not body.get("fingerprint") and not body.get("bins"):
                continue
        candidate = {
            "kind": "factor_improvement",
            "verified": False,
            "fingerprint": body.get("fingerprint"),
            "belt": body.get("belt"),
            "chroma": body.get("chroma"),
            "scale_level": body.get("scale_level"),
            "factor_count": body.get("factor_count"),
            "error": error,
            "scar": scar,
            "improvement": improvement,
            "phi_weight": body.get("phi_weight"),
            "bins": body.get("bins"),
            "count": body.get("n") or body.get("count"),
            "aggregate": dict(body),
            "writes": False,
            "learned": False,
            "scar_matrix_updated": False,
        }
        candidates.append(candidate)
    return {
        "candidates": candidates,
        "verified": False,
        "writes": False,
        "learned": False,
        "scar_matrix_updated": False,
        "writes_titanos": False,
        "stage": "morpheus",
    }


def offer_factor_candidate(
    candidate: dict[str, Any],
    *,
    verified: bool,
    to_scale: str = "local",
    ident: str = "cohort",
) -> dict[str, Any]:
    """Verification gate for a dream factor candidate.

    Unverified candidates stay candidates. A verified candidate is
    turned into an Eat envelope and is not written here. This gate
    does not call learn, does not touch scars, and does not write
    Titanos.
    """
    body = dict(candidate or {})
    if not verified or not body:
        return {
            "ok": False,
            "decision": "refuse",
            "reason": "unverified; stays a candidate",
            "candidate": body,
            "verified": False,
            "writes": False,
            "learned": False,
            "scar_matrix_updated": False,
        }
    from resileos.persona.residual_factors import FACTOR_RELATION
    from resileos.persona.promote import subject_at
    import json

    offered = dict(body)
    offered["verified"] = True
    subject = subject_at(to_scale, ident)
    obj = json.dumps(
        {
            "fingerprint": offered.get("fingerprint"),
            "belt": offered.get("belt"),
            "chroma": offered.get("chroma"),
            "scale_level": offered.get("scale_level"),
            "factor_count": offered.get("factor_count"),
            "error": offered.get("error"),
            "scar": offered.get("scar"),
            "improvement": offered.get("improvement"),
            "phi_weight": offered.get("phi_weight"),
            "bins": offered.get("bins"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "ok": True,
        "decision": "accept",
        "verified": True,
        "subject": subject,
        "relation": FACTOR_RELATION,
        "obj": obj,
        "envelope": {"claim": {"subject": subject, "relation": FACTOR_RELATION, "obj": obj}, "source": "morpheus-dream"},
        "candidate": offered,
        "writes": False,
        "learned": False,
        "scar_matrix_updated": False,
        "writes_titanos": False,
        "note": "write only through Eat with reviewer approval",
    }
