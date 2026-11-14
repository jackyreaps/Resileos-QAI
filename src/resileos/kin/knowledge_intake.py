"""Admin → Knowledge → Add facts: files or pasted text in, reviewed facts out.

Each item goes: read the text → (``.lean``) check the proof → pull out
rigid triples or quintuples → ``check_envelope`` (``eat_filter``) →
preview. Nothing is written in preview. ``commit_facts`` sends only the
facts the admin confirmed through ``eat_commit_envelopes``, so Eat stays
the only writer and every write passes the Zeus reviewers.

What counts as a fact, by format:

* ``.csv``: rows of ``subject, relation, object[, valid_from, valid_to]``
  (a header row naming those columns is fine).
* ``.json``: a list of ``{"subject", "relation", "object"|"obj",
  "valid_from"?, "valid_to"?}`` or of 3–5 item lists.
* ``.txt`` / ``.md`` / pasted text: one fact per line as
  ``subject | relation | object [| valid_from | valid_to]`` (markdown
  table rows work) or ``(subject, relation, object)``. Other lines are
  prose and are held back as "not clear facts".
* ``.lean``: the file is checked with Lean. If it checks, each
  ``theorem``/``lemma`` name becomes a candidate
  ``(name, "proved_in", "Lean 4")``. It is still a candidate: Eat and the
  reviewers decide.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Any, Callable, Optional

from resileos.kin.eat_envelope import (
    _already_stored,
    _batch_conflicts,
    check_envelope,
    eat_commit_envelopes,
    stored_conflicts,
)

MAX_ITEMS = 12
MAX_FACTS = 200
KINDS = {".txt": "text", ".md": "text", ".csv": "csv", ".json": "json", ".lean": "lean"}
_HEADER = {"subject", "relation", "object", "obj", "valid_from", "valid_to"}
_TUPLE = re.compile(r"^\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*,\s*([^()]+?)\s*\)$")
_THEOREM = re.compile(r"(?m)^\s*(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?(theorem|lemma)\s+([A-Za-z_][\w.']*)")


def kind_of(name: str) -> Optional[str]:
    ext = os.path.splitext(str(name or "").lower())[1] or ".txt"
    return KINDS.get(ext)


def _claim(parts: list[Any]) -> Optional[dict[str, Any]]:
    parts = [" ".join(str(p if p is not None else "").split()) for p in parts]
    if len(parts) < 3 or len(parts) > 5 or not all(parts[:3]):
        return None
    out = {"subject": parts[0], "relation": parts[1], "obj": parts[2]}
    if len(parts) > 3 and parts[3]:
        out["valid_from"] = parts[3]
    if len(parts) > 4 and parts[4]:
        out["valid_to"] = parts[4]
    return out


def _from_dict(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    obj = row.get("obj", row.get("object"))
    return _claim([row.get("subject"), row.get("relation"), obj, row.get("valid_from"),
                   row.get("valid_to", row.get("valid_until"))])


def extract(name: str, text: str) -> dict[str, Any]:
    """Candidates (claim dicts) and prose lines held back, for one item."""
    kind = kind_of(name)
    facts: list[dict[str, Any]] = []
    prose: list[str] = []
    if kind == "csv":
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        head = [c.strip().lower() for c in rows[0]] if rows else []
        if head and "subject" in head and set(h for h in head if h) <= _HEADER:
            dict_rows = [dict(zip(head, r)) for r in rows[1:]]
            for r, raw in zip(dict_rows, rows[1:]):
                claim = _from_dict(r)
                facts.append(claim) if claim else prose.append(",".join(raw))
        else:
            for r in rows:
                claim = _claim(r)
                facts.append(claim) if claim else prose.append(",".join(r))
    elif kind == "json":
        try:
            data = json.loads(text)
        except ValueError:
            return {"kind": kind, "facts": [], "prose": [], "error": "That JSON couldn't be read."}
        rows = data if isinstance(data, list) else data.get("facts", []) if isinstance(data, dict) else []
        for r in rows:
            claim = _from_dict(r) if isinstance(r, dict) else _claim(list(r)) if isinstance(r, list) else None
            facts.append(claim) if claim else prose.append(json.dumps(r)[:200])
    elif kind == "text":
        for line in str(text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("|") or " | " in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    continue
                if {c.lower() for c in cells if c} <= _HEADER:
                    continue
                claim = _claim(cells)
            else:
                m = _TUPLE.match(line)
                claim = _claim(list(m.groups())) if m else None
            facts.append(claim) if claim else prose.append(line[:300])
    return {"kind": kind, "facts": facts[:MAX_FACTS], "prose": prose}


def _proof(text: str, lean_fn: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    result = lean_fn(text)
    status = str(result.get("status") or "UNAVAILABLE")
    names = list(dict.fromkeys(m.group(2) for m in _THEOREM.finditer(text))) if status == "CHECKED" else []
    return {"status": status, "summary": result.get("summary", ""), "line": result.get("line"),
            "facts": [{"subject": n, "relation": "proved_in", "obj": "Lean 4"} for n in names]}


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def preview_items(items: list[dict[str, Any]], *, titanos: Any = None,
                  lean_fn: Optional[Callable[[str], dict[str, Any]]] = None) -> dict[str, Any]:
    """Check every item. Nothing is written."""
    if lean_fn is None:
        from resileos.verify.lean_check import check_lean as lean_fn  # type: ignore[assignment]
    out = []
    for item in list(items or [])[:MAX_ITEMS]:
        name = str(item.get("name") or "pasted.txt")[:120]
        text = str(item.get("text") or "")
        kind = kind_of(name)
        row: dict[str, Any] = {"name": name, "kind": kind, "facts": [], "held_back": 0, "proof": None}
        if kind is None:
            row["status"] = "Can't read this type. Use text, Markdown, CSV, JSON, or Lean."
            out.append(row)
            continue
        if kind == "lean":
            proof = _proof(text, lean_fn)
            row["proof"] = {k: proof[k] for k in ("status", "summary", "line")}
            claims, prose = proof["facts"], []
            if proof["status"] != "CHECKED":
                row["status"] = {"FAILED": "Proof doesn't check" + (f" (line {proof['line']})" if proof.get("line") else ""),
                                 "INCOMPLETE": "Proof isn't finished (uses sorry)",
                                 "TIMEOUT": "Proof check timed out"}.get(proof["status"], "Couldn't check the proof: " + str(proof["summary"]))
                out.append(row)
                continue
        else:
            got = extract(name, text)
            if got.get("error"):
                row["status"] = got["error"]
                out.append(row)
                continue
            claims, prose = got["facts"], got["prose"]
        row["_prose"] = prose
        row["_checks"] = []
        for claim in claims:
            check = check_envelope({"claim": claim, "source": f"admin:{name}"})
            if check.action == "accept" and titanos is not None:
                found = stored_conflicts(titanos, check)
                if found:
                    check.action, check.reason = "conflict", "overlaps_stored_fact"
                    check.conflicts_with.extend(found)
                elif _already_stored(titanos, check):
                    check.action, check.reason = "abstain", "already_stored"
            row["_checks"].append(check)
        out.append(row)
    # Facts in one batch that overlap each other conflict too (same rule as commit).
    every = [c for r in out for c in r.get("_checks", [])]
    if titanos is not None and every:
        _batch_conflicts(every, titanos)
    for row in out:
        checks = row.pop("_checks", None)
        if checks is None:
            continue
        prose = row.pop("_prose", [])
        row["facts"] = [
            {"subject": c.subject, "relation": c.relation, "obj": c.obj, "valid_from": c.valid_from,
             "valid_to": c.valid_to, "action": c.action, "reason": c.reason, "conflicts": list(c.conflicts_with)}
            for c in checks
        ]
        kind = row["kind"]
        ready = sum(1 for f in row["facts"] if f["action"] == "accept")
        conflicts = sum(1 for f in row["facts"] if f["action"] == "conflict")
        row["held_back"] = len(prose) + sum(
            1 for f in row["facts"] if f["action"] not in {"accept", "conflict"} and f["reason"] != "already_stored"
        )
        parts = []
        if kind == "lean":
            parts.append("Proof checks" + (f", {_n(ready, 'fact')} ready to save" if ready else ""))
        elif ready:
            parts.append(f"{_n(ready, 'fact')} ready to save")
        stored_c = sum(1 for f in row["facts"] if f["reason"] == "overlaps_stored_fact")
        if stored_c:
            parts.append(f"{stored_c} conflict{'s' if stored_c != 1 else ''} with an existing fact")
        if conflicts - stored_c:
            n = conflicts - stored_c
            parts.append(f"{n} conflict{'s' if n != 1 else ''} with another fact you're adding")
        if row["held_back"]:
            parts.append(f"held back {row['held_back']} (not clear facts)")
        stored = sum(1 for f in row["facts"] if f["reason"] == "already_stored")
        if stored:
            parts.append(f"{stored} already saved")
        row["status"] = "; ".join(parts) if parts else "No facts found"
        row["ready"] = ready
    return {"items": out, "ready": sum(r.get("ready", 0) for r in out)}


def commit_facts(facts: list[dict[str, Any]], *, titanos: Any, ask_fn: Any = None, source: str = "admin",
                 lessons: Any = None) -> dict[str, Any]:
    """Save the facts the admin confirmed, through Eat and the reviewers."""
    envelopes = []
    for fact in list(facts or [])[:MAX_FACTS]:
        claim = _from_dict(fact if isinstance(fact, dict) else {})
        envelopes.append({"claim": claim, "source": f"{source}:{str(fact.get('item') or 'paste')[:120]}"}
                         if claim else {"claim": None})
    result = eat_commit_envelopes(envelopes, titanos=titanos, ask_fn=ask_fn, lessons=lessons)
    rows = result["results"]
    saved = sum(1 for r in rows if r["action"] == "committed")
    conflicts = sum(1 for r in rows if r["action"] == "conflict")
    held = len(rows) - saved - conflicts
    parts = [f"Saved {_n(saved, 'fact')}"] if saved else ["Nothing saved"]
    if conflicts:
        parts.append(f"{conflicts} conflict{'s' if conflicts != 1 else ''} with an existing fact")
    if held:
        parts.append(f"held back {held}")
    return {"status": "; ".join(parts), "saved": saved, "conflicts": conflicts, "held_back": held,
            "results": rows, "applied": result["summary"]["applied"]}


__all__ = ["KINDS", "commit_facts", "extract", "kind_of", "preview_items"]
