"""Training seed: batch facts into the store with a gate.

This is the infrastructure path for learned facts.
It is not gradient training of a language model. It is
verifier-gated ingestion so the store grows with facts
that can be recalled exactly and derived with provenance.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.framework_gate import gate_candidate


def seed_facts(
    facts: list[dict[str, str]],
    *,
    eat_fn: Optional[Callable[..., Any]] = None,
    learn_fn: Optional[Callable[..., Any]] = None,
    stored: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Gate and optionally learn a batch of triples.

    eat_fn(claim) -> decision with .accepted
    learn_fn(subject, relation, obj) -> None
    """
    stored = list(stored or [])
    accepted = 0
    rejected = 0
    rows = []
    for f in facts:
        claim = f"{f.get('subject')} {f.get('relation')} {f.get('obj')}"
        ok = True
        if eat_fn is not None:
            d = eat_fn(claim)
            ok = bool(getattr(d, "accepted", False))
        gated = gate_candidate(f, stored=stored, eat_accepted=ok)
        if ok and learn_fn is not None:
            learn_fn(f["subject"], f["relation"], f["obj"])
            stored.append(f)
            accepted += 1
            gated["learned"] = True
        else:
            rejected += 1
            gated["learned"] = False
        rows.append(gated)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "rows": rows,
        "note": "Learned facts are exact. Rejected facts are not in the store.",
    }
