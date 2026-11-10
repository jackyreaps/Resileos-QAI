"""Hub ledger over Titanos learn / ask_list.

Subjects are ``user:<id>``. Listing reads ``ask_list`` so the memory strip
shows the same rows a recall would. Edit and delete touch only that
subject's fact log, then ``learn`` writes the replacement. Band math stays
inside Titanos.
"""
from __future__ import annotations

import re
from typing import Any

# hub-namespace.md v1, including ``stated``.
HUB_RELATIONS = ("prefers", "stated", "setting", "note")

_ID = re.compile(r"[^a-z0-9_]")


def normalize_hub_id(hub_id: str) -> str:
    """Lowercase ``[a-z0-9_]{1,64}``. A leading ``user:`` is stripped."""
    raw = (hub_id or "").strip().lower()
    if raw.startswith("user:"):
        raw = raw[5:]
    cleaned = _ID.sub("", raw)[:64]
    if not cleaned:
        raise ValueError("hub_id must contain at least one [a-z0-9_] character")
    return cleaned


def user_subject(hub_id: str) -> str:
    return f"user:{normalize_hub_id(hub_id)}"


def _facts(titanos: Any) -> list:
    facts = getattr(titanos, "facts", None)
    if not isinstance(facts, list):
        raise TypeError("titanos.facts is not a list")
    return facts


def _match_bounds(facts: list, subject: str, relation: str, obj: str) -> tuple[str | None, str | None]:
    for fact in facts:
        if len(fact) < 3:
            continue
        if fact[0] == subject and fact[1] == relation and fact[2] == obj:
            valid_from = fact[3] if len(fact) > 3 else None
            valid_to = fact[4] if len(fact) > 4 else None
            return valid_from, valid_to
    return None, None


def list_user_ledger(titanos: Any, hub_id: str) -> dict[str, Any]:
    """Current triples for ``user:<id>``, one row per ask_list object."""
    subject = user_subject(hub_id)
    facts = list(_facts(titanos))
    relations: list[str] = []
    for fact in facts:
        if len(fact) >= 3 and fact[0] == subject and fact[1] not in relations:
            relations.append(fact[1])
    triples: list[dict[str, Any]] = []
    for relation in relations:
        rows = list(titanos.ask_list(subject, relation))
        for obj in rows:
            valid_from, valid_to = _match_bounds(facts, subject, relation, obj)
            triples.append(
                {
                    "subject": subject,
                    "relation": relation,
                    "obj": obj,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                }
            )
    return {
        "hub_id": normalize_hub_id(hub_id),
        "subject": subject,
        "triples": triples,
    }


def _require_present(titanos: Any, subject: str, relation: str, obj: str) -> None:
    rows = list(titanos.ask_list(subject, relation))
    if obj not in rows:
        raise KeyError(f"no current triple {subject} {relation} {obj}")


def _drop_exact(titanos: Any, subject: str, relation: str, obj: str) -> int:
    if not subject.startswith("user:"):
        raise ValueError("the hub ledger only edits user: subjects")
    facts = _facts(titanos)
    kept = []
    removed = 0
    for fact in facts:
        if len(fact) >= 3 and fact[0] == subject and fact[1] == relation and fact[2] == obj:
            removed += 1
            continue
        kept.append(fact)
    if removed:
        facts[:] = kept
    return removed


def delete_user_triple(titanos: Any, hub_id: str, relation: str, obj: str) -> dict[str, Any]:
    subject = user_subject(hub_id)
    relation = (relation or "").strip()
    obj = (obj or "").strip()
    if not relation or not obj:
        raise ValueError("relation and obj are required")
    _require_present(titanos, subject, relation, obj)
    removed = _drop_exact(titanos, subject, relation, obj)
    ledger = list_user_ledger(titanos, hub_id)
    ledger["removed"] = removed
    return ledger


def edit_user_triple(
    titanos: Any,
    hub_id: str,
    relation: str,
    obj: str,
    *,
    new_relation: str | None = None,
    new_obj: str | None = None,
) -> dict[str, Any]:
    """Replace one current triple. The new row is written with ``learn``."""
    subject = user_subject(hub_id)
    relation = (relation or "").strip()
    obj = (obj or "").strip()
    if not relation or not obj:
        raise ValueError("relation and obj are required")
    replacement_relation = (new_relation if new_relation is not None else relation).strip()
    replacement_obj = (new_obj if new_obj is not None else obj).strip()
    if not replacement_relation or not replacement_obj:
        raise ValueError("replacement relation and obj must be non-empty")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", replacement_relation):
        raise ValueError("relation must be a token of [A-Za-z0-9_]{1,64}")
    _require_present(titanos, subject, relation, obj)
    if replacement_relation == relation and replacement_obj == obj:
        ledger = list_user_ledger(titanos, hub_id)
        ledger["removed"] = 0
        ledger["wrote"] = False
        return ledger
    removed = _drop_exact(titanos, subject, relation, obj)
    titanos.learn(subject, replacement_relation, replacement_obj)
    ledger = list_user_ledger(titanos, hub_id)
    ledger["removed"] = removed
    ledger["wrote"] = True
    return ledger
