"""Language: speak, summarise, translate, grammar, etymology, cycle.

One module. Uses the mouth, the language tool, perception, and the kin.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from resileos.ui.custom_mouth import answer, epistemic_label
from resileos.ui.language_tool import detect_language, native_or_translate, translate
from resileos.ui.perceive_language import perceive_language


# ── speak ──────────────────────────────────────────────────────────────

def speak(rows, question="", *, model_fn=None):
    return answer(rows, question, model_fn=model_fn)


def summarise(rows, *, limit=5):
    if not rows:
        return "Nothing stored on that."
    return speak(rows[:limit])["text"]


def to_language(text, target="en", *, prefer_native=False):
    if prefer_native:
        return native_or_translate(text, prefer_native=True)
    return translate(text, target=target)


def grammar_of(rows):
    subjects = {r.get("subject") for r in rows if r.get("subject")}
    relations = {r.get("relation") for r in rows if r.get("relation")}
    return {
        "clauses": len(rows),
        "subjects": len(subjects),
        "predicates": len(relations),
        "complexity": len(relations) + (1 if len(subjects) > 1 else 0),
    }


def etymology(term, roots=None):
    hits = [r for r in (roots or []) if r.get("term") == term]
    return {"term": term, "found": bool(hits), "roots": hits}


def codex(rows, *, question="", target=None, roots=None, model_fn=None, psyche=None):
    """Speak, grammar, address, detect. Optional translate, roots, and kin."""
    spoken = speak(rows, question, model_fn=model_fn)
    perc = perceive_language(spoken["text"], subject="utterance")
    out = {
        "speak": spoken,
        "grammar": grammar_of(rows),
        "address": perc.get("address"),
        "detect": detect_language(spoken["text"]),
        "epistemic": epistemic_label(rows),
    }
    if target:
        out["translate"] = to_language(spoken["text"], target)
    if roots:
        out["etymology"] = [etymology(r.get("obj"), roots) for r in rows if r.get("obj")]
    if psyche is not None:
        from resileos.kin.wire_perception import wire_perception
        out["kin"] = wire_perception(psyche, perc)
    return out


# ── cycle: search, check, learn, speak ─────────────────────────────────

def namespace(kind, name):
    k = kind if str(kind).endswith(":") else f"{kind}:"
    return f"{k}{name}"


def lookup(store_query, subject, relation):
    val = store_query(subject, relation)
    if not val:
        return {"found": False, "subject": subject, "relation": relation}
    return {"found": True, "subject": subject, "relation": relation, "obj": val}


def fact_check(store_query, subject, relation, claimed):
    got = lookup(store_query, subject, relation)
    if not got["found"]:
        return {"status": "unknown", "claimed": claimed}
    if str(got["obj"]) == str(claimed):
        return {"status": "match", "obj": got["obj"]}
    return {"status": "mismatch", "obj": got["obj"], "claimed": claimed}


def learn_into(store_learn, ns, relation, obj):
    store_learn(ns, relation, obj)
    return {"subject": ns, "relation": relation, "obj": obj, "learned": True}


def cycle(store_query, store_learn, *, kind, name, relation, obj=None, claimed=None, question="", psyche=None):
    """Lookup, optional fact-check, optional learn, then codex (and kin)."""
    ns = namespace(kind, name)
    out = {"namespace": ns, "lookup": lookup(store_query, ns, relation)}
    if obj is not None:
        out["learn"] = learn_into(store_learn, ns, relation, obj)
        out["lookup"] = lookup(store_query, ns, relation)
    if claimed is not None:
        out["fact_check"] = fact_check(store_query, ns, relation, claimed)
    rows = []
    if out["lookup"].get("found"):
        rows = [{"subject": ns, "relation": relation, "obj": out["lookup"]["obj"]}]
    out["codex"] = codex(rows, question=question, psyche=psyche)
    return out
