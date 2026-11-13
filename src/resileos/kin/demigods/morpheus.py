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
