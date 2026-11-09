"""Framework-native free-text encoder (no external LLM / HF).

Maps a natural-language question to a discrete gate selection against the
live store vocabulary. Design is aligned with QD-TER Human-Medium v10
Part V (Language as a Gate Between the Global and the Local):

- Language is a bounded-capacity gate on a final fold (L5 / §7.1): a
  symbol σ ∈ Σ selects which local residue is written / queried.
- At most log2 |Σ| bits of gate information per use; the store residue
  itself is bounded by the descent compression (at most log2 |S3| bits
  under the candidate F2 reading — candidate, not locked).
- Syndrome analogy (§7.2): a short symbol selects one of a small number
  of channels, or "none" (abstain / unresolved).
- Dual residue (§2.5): otx_like = flexible / projective path;
  gbx_like = rigid / exact band readout. The encoder only *labels*
  which sector a resolved triple prefers; it does not implement biology.

Temporal extraction (RES-332, added 2026-11-09):

- Queries that contain an explicit temporal marker ("in 1800",
  "as of 1900", "circa 1450", "during 1750", "around 1820") extract the
  year and return it as `as_of` on the GateSelection.
- The date phrase is stripped from the text *before* pattern matching,
  so "what is Zeus's domain in 1800" resolves to (Zeus, domain, forward)
  with as_of="1800-01-01", not to a relation named "domain in 1800".
- Extraction is coarse-grained: "in YYYY" maps to "YYYY-01-01" (start
  of year). Callers that need finer granularity (specific month, ISO
  date) should pass `as_of` explicitly to the route, not rely on
  extraction from free text.
- `as_of=None` means "current state" and is the pre-temporal default.
- No as_of is extracted from ambiguous phrases like "the 1800s",
  "recently", "historically" — those fall through to current-state
  lookup.

This module does not call transformers, hosted APIs, or any external
model. Unresolvable input returns None so the route can 400 rather than
invent structure (persistent residue is never written by the encoder).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Optional


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", _norm(text))


# ── temporal extraction (RES-332) ──────────────────────────────────────
# Matches 4-digit years 1000-2999, but only when preceded by a clear
# temporal marker. The marker is stripped along with the year.
_DATE_MARKER_RE = re.compile(
    r"\b(?:as\s+of|in|during|circa|around|about)\s+(?P<y>1[0-9]{3}|2[0-9]{3})\b",
    re.I,
)
_YEAR_SUFFIX_RE = re.compile(
    r"\b(?P<y>1[0-9]{3}|2[0-9]{3})\s*(?:ad|ce)\b",
    re.I,
)


def _extract_date(text: str) -> tuple[str, Optional[str]]:
    """Return (text_without_date_phrase, iso_date_or_None).

    Matches the first temporal phrase only. Uses "YYYY-01-01" as the
    as_of (start of year). If multiple dates appear, only the first is
    used; callers that need ranges should pass explicit as_of.
    """
    m = _DATE_MARKER_RE.search(text)
    if m:
        year = int(m.group("y"))
        cleaned = (text[: m.start()] + " " + text[m.end() :]).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned, f"{year:04d}-01-01"

    m = _YEAR_SUFFIX_RE.search(text)
    if m:
        year = int(m.group("y"))
        cleaned = (text[: m.start()] + " " + text[m.end() :]).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned, f"{year:04d}-01-01"

    return text, None


# ── surface patterns ───────────────────────────────────────────────────
# Pattern order matters. The patterns operate on the date-stripped text.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        r"^\s*(?:what(?:'s| is| are)?)\s+(?P<sub>.+?)(?:'s|s')\s+(?P<rel>[\w\s]+?)\s*\??\s*$",
        re.I,
    ), "forward"),
    (re.compile(
        r"^\s*(?:who|what)\s+(?:is|are)\s+(?:the\s+)?(?P<rel>[\w\s]+?)\s+of\s+(?P<sub>.+?)\s*\??\s*$",
        re.I,
    ), "inverse_of"),
    (re.compile(
        r"^\s*(?P<sub>[\w\s]+?)(?:'s|s')\s+(?P<rel>[\w\s]+?)\s*\??\s*$",
        re.I,
    ), "forward"),
    (re.compile(
        r"^\s*(?P<sub>[\w]+)\s+(?P<rel>[\w]+)\s*\??\s*$",
        re.I,
    ), "forward"),
    (re.compile(
        r"^\s*(?P<rel>[\w\s]+?)\s+of\s+(?P<sub>.+?)\s*\??\s*$",
        re.I,
    ), "inverse_of"),
    (re.compile(
        r"^\s*(?:who|what)\s+has\s+(?P<rel>[\w\s]+?)\s+(?P<sub>.+?)\s*\??\s*$",
        re.I,
    ), "inverse"),
]


def _best_match(raw: str, vocab: Iterable[str]) -> Optional[str]:
    raw_n = _norm(raw).replace(" ", "_")
    raw_space = _norm(raw)
    items = list(vocab)
    for v in items:
        if _norm(v) == raw_space or _norm(v).replace(" ", "_") == raw_n:
            return v
    hits = [v for v in items if _norm(v) in raw_space or raw_space in _norm(v)]
    if len(hits) == 1:
        return hits[0]
    tokens = set(_tokenize(raw))
    if not tokens:
        return None
    scored: list[tuple[float, str]] = []
    for v in items:
        vt = set(_tokenize(v))
        if not vt:
            continue
        j = len(tokens & vt) / len(tokens | vt)
        if j >= 0.5:
            scored.append((j, v))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]
    return None


@dataclass(frozen=True)
class GateSelection:
    """Discrete gate output of the language encoder (Part V §7.1).

    ``subject``, ``relation``, ``inverse`` are the store triple.
    ``symbol_index`` is a stable id in 0..|Σ|-1 over the live relation
    alphabet (channel selection). ``gate_capacity_bits`` is log2 |Σ|.
    ``sector`` is a label only: ``gbx_like`` (rigid exact) or
    ``otx_like`` (flexible path / multi-hop preferred). ``none`` means
    unresolved (syndrome zero / abstain path).

    ``as_of`` (RES-332) is the extracted temporal marker, ISO 8601
    ``YYYY-MM-DD``, or None for current-state. When non-None, the
    route must forward this to the store's temporal filter; when
    None, the store applies its default current-state filter.
    """

    subject: str
    relation: str
    inverse: bool
    symbol_index: int
    gate_capacity_bits: float
    sector: str  # "gbx_like" | "otx_like"
    pattern_kind: str
    as_of: Optional[str] = None

    def as_triple(self) -> tuple[str, str, bool]:
        return self.subject, self.relation, self.inverse


def _sector_for(kind: str, inverse: bool, relation: str) -> str:
    if not inverse and not relation.endswith("_of"):
        return "gbx_like"
    return "otx_like"


def encode_question(
    text: str,
    *,
    entities: Iterable[str],
    relations: Iterable[str],
) -> Optional[tuple[str, str, bool]]:
    """Return ``(subject, relation, inverse)`` or ``None``.

    Thin wrapper over ``encode_gate`` for existing call sites that do
    not need temporal metadata. Callers that want ``as_of`` (RES-332)
    should use ``encode_gate`` directly.
    """
    g = encode_gate(text, entities=entities, relations=relations)
    return None if g is None else g.as_triple()


def encode_gate(
    text: str,
    *,
    entities: Iterable[str],
    relations: Iterable[str],
) -> Optional[GateSelection]:
    """Full gate selection: triple + symbol index + sector + capacity
    + extracted temporal marker (RES-332).

    ``relations`` defines the alphabet Σ. Capacity is log2 |Σ| bits per
    Part V §7.1.

    The temporal marker (if present) is extracted *before* pattern
    matching, so a phrase like "domain in 1800" resolves to
    relation="domain", as_of="1800-01-01" rather than to a relation
    named "domain in 1800".
    """
    text = (text or "").strip()
    if not text:
        return None

    ents = list(entities)
    rels = list(relations)
    if not ents or not rels:
        return None

    # RES-332: strip date phrase first so patterns match the semantic
    # query, not the temporal suffix.
    cleaned_text, as_of = _extract_date(text)

    n_sym = len(rels)
    capacity = math.log2(n_sym) if n_sym > 0 else 0.0
    rel_index = {r: i for i, r in enumerate(rels)}

    for pat, kind in _PATTERNS:
        m = pat.search(cleaned_text)
        if not m:
            continue
        gd = m.groupdict()
        sub = _best_match(gd.get("sub") or "", ents)
        rel = _best_match(gd.get("rel") or "", rels)
        if sub is None or rel is None:
            continue
        if kind == "forward":
            inv = False
        elif kind == "inverse_of":
            inv = rel.endswith("_of") or rel in {
                "parent", "parent_of", "child", "child_of",
                "sibling", "sibling_of", "spouse", "spouse_of",
            }
        else:
            inv = True
        return GateSelection(
            subject=sub,
            relation=rel,
            inverse=inv,
            symbol_index=int(rel_index[rel]),
            gate_capacity_bits=capacity,
            sector=_sector_for(kind, inv, rel),
            pattern_kind=kind,
            as_of=as_of,
        )

    found_e = [e for e in ents if _norm(e) in _norm(cleaned_text)]
    found_r = [
        r for r in rels
        if _norm(r).replace("_", " ") in _norm(cleaned_text)
        or _norm(r) in _norm(cleaned_text)
    ]
    if len(found_e) == 1 and len(found_r) == 1:
        rel = found_r[0]
        return GateSelection(
            subject=found_e[0],
            relation=rel,
            inverse=False,
            symbol_index=int(rel_index[rel]),
            gate_capacity_bits=capacity,
            sector="gbx_like",
            pattern_kind="overlap",
            as_of=as_of,
        )
    return None
