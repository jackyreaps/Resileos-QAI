"""Hermes crawl: our own index first, origin pages next, Eat decides.

Five pieces, all generators (no ``learn_fn``, ``writes_residual`` False):

* **native_search** (Hermes Agoraios): searches our own crawl index
  (``NativeIndex``). A third-party search backend is a *fallback only*,
  off by default, behind the ``SearchFallback`` interface, and every
  packet it returns is labelled ``origin: "fallback:<name>"``.
* **pheme_buzz** (Pheme, rumour): rising terms and entity pairs between
  two sets of packets. A routing hint for the next wave, never a fact.
* **ichnaea_fanout** (Ichnaea, the tracker): follows packets to their
  original pages through ``assist.guarded_fetch`` (SSRF guard, connects
  to the checked IP) and extracts claim spans with provenance plus
  ``valid_from`` / ``valid_to`` / ``as_of``. Pages it reads go into our
  own index, so the crawler feeds native search.
* **eat_bridge**: every candidate goes through ``eat_envelope``
  (``eat_filter`` then Zeus reviewers through ``SeparatedCycle``). Prose
  abstains. Only clean structured triples or quintuples reach Zeus.
  Hades gets one lesson-only note when a wave is noisy.
* **crawl_trace** (Iris): read-only reader for the crawl audit JSONL.

Quintuple = (subject, relation, object, valid_from, valid_to). A triple
sits at cascade frame 3 (edge); a quintuple with at least one bound sits
at frame 5 (belt). Wave depth d runs frames (3, 5, 9, 12)[:d]: wave i
follows up to that frame's count of origin pages. Ranking is PHI-decayed
by wave (score = relevance * PHI^-(wave-1), normalised to the best),
anything under EPSILON = 1/64 is dropped, and at most WAIST = 36 are kept.

The traffic/funding ``tier`` tag on a packet is for audit and routing
only. It never weights truth and never reaches Eat: ``check_envelope``
reads only the claim fields, and attention keys are stripped.
"""
from __future__ import annotations

import html
import json
import math
import os
import re
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol
from urllib.parse import urlsplit

from resileos.ui.cascade_address import CASCADE_FRAMES, EPSILON, WAIST

PACKET_VERSION = "hermes-crawl/1"
_WORD = re.compile(r"[a-z0-9][a-z0-9'-]{1,}")
_STOP = frozenset(
    "the a an and or of to in on for with by at from is are was were be been this that it its as not but "
    "you your we our they their he she his her them what which who when where how why can will just "
    "about into over than then there these those also more most other some such only own same so very".split()
)
_SNIPPET = 300
_INDEX_TEXT = 20_000


def _now(now: Optional[datetime] = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(str(text or "").lower()) if w not in _STOP]


def _plain(text: Any, cap: int) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", str(text or ""))
    raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return " ".join(raw.split())[:cap]


def domain_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# ── traffic / funding tier (audit and routing only) ────────────────────
_REFERENCE = ("wikipedia.org", "wikidata.org", "britannica.com", "arxiv.org", "doi.org")


def source_tier(url: str) -> str:
    """A coarse tag: institutional | reference | commercial | unknown.

    Audit and routing only. It is never a truth weight and never reaches
    Eat or Titanos.
    """
    host = domain_of(url)
    if not host:
        return "unknown"
    if host.endswith((".gov", ".edu", ".int", ".mil")) or ".gov." in host or ".ac." in host:
        return "institutional"
    if any(host == d or host.endswith("." + d) for d in _REFERENCE):
        return "reference"
    return "commercial"


def make_packet(url: str, snippet: str, *, origin: str, title: str = "", retrieved_at: Optional[str] = None,
                relevance: float = 0.0, label: str = "") -> dict[str, Any]:
    return {
        "version": PACKET_VERSION,
        "url": url,
        "domain": domain_of(url),
        "retrieved_at": retrieved_at or _now(),
        "tier": source_tier(url),
        "title": _plain(title, 200),
        "snippet": _plain(snippet, _SNIPPET),
        "origin": origin,
        "origin_label": label or ("Our index" if origin == "native" else origin),
        "relevance": float(relevance),
        "trust": "untrusted",
    }


# ── our own index ──────────────────────────────────────────────────────
def index_path() -> Path:
    return Path(os.environ.get("RESILEOS_HERMES_INDEX", "data/hermes_index.jsonl"))


class NativeIndex:
    """A small BM25 index over pages our crawler has read. JSONL on disk."""

    def __init__(self, path: str | Path | None = None, *, persist: bool = True):
        self.path = Path(path) if path else index_path()
        self.persist = persist
        self._lock = threading.Lock()
        self.docs: dict[str, dict[str, Any]] = {}
        if persist and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("url"):
                    self.docs[row["url"]] = row

    def add(self, url: str, text: str, *, title: str = "", retrieved_at: Optional[str] = None) -> None:
        body = _plain(text, _INDEX_TEXT)
        if not url or not body:
            return
        row = {"url": url, "title": _plain(title, 200), "text": body, "retrieved_at": retrieved_at or _now()}
        with self._lock:
            self.docs[url] = row
            if self.persist:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def __len__(self) -> int:
        return len(self.docs)

    def search(self, query: str, k: int = 8) -> list[tuple[float, dict[str, Any]]]:
        terms = list(dict.fromkeys(_tokens(query)))
        if not terms or not self.docs:
            return []
        docs = list(self.docs.values())
        toks = [_tokens(d["title"] + " " + d["text"]) for d in docs]
        avg = sum(len(t) for t in toks) / max(1, len(toks))
        df = Counter(w for t in toks for w in set(t))
        n = len(docs)
        scored = []
        for doc, words in zip(docs, toks):
            tf = Counter(words)
            score = 0.0
            for term in terms:
                if not tf[term]:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                f = tf[term]
                score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(words) / max(1.0, avg)))
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["url"]))
        return scored[: max(1, int(k))]


_SHARED: dict[str, NativeIndex] = {}


def shared_index() -> NativeIndex:
    """The process-wide index at ``RESILEOS_HERMES_INDEX``."""
    key = str(index_path())
    if key not in _SHARED:
        _SHARED[key] = NativeIndex(key)
    return _SHARED[key]


def _snippet_for(text: str, query: str) -> str:
    want = set(_tokens(query))
    best, hit = text[:_SNIPPET], 0
    for sentence in re.split(r"(?<=[.!?])\s+", text[:8000]):
        have = set(_tokens(sentence))
        if len(want & have) > hit:
            best, hit = sentence, len(want & have)
    return best[:_SNIPPET]


# ── pluggable third-party fallback (off by default) ────────────────────
class SearchFallback(Protocol):
    """A third-party search backend used only when our index has nothing.

    ``name`` is a short id, ``label`` the plain words shown in the trail.
    ``search`` returns ``[{"url", "title", "snippet"}]``. It is off unless
    ``RESILEOS_SEARCH_FALLBACK`` names it or a caller passes one.
    """

    name: str
    label: str

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...


class DuckDuckGoFallback:
    """Wraps the existing ``harness.legions.search.web_search``. No new service."""

    name = "duckduckgo"
    label = "Third-party fallback (DuckDuckGo)"

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        from resileos.harness.legions.search import web_search
        from resileos.kin.outer_legions import _resolve

        raw = _resolve(web_search(query, max_results=max_results))
        if not isinstance(raw, dict) or raw.get("status") != "SUCCESS":
            return []
        return [r for r in raw.get("results") or [] if isinstance(r, dict)]


FALLBACKS: dict[str, Callable[[], SearchFallback]] = {"duckduckgo": DuckDuckGoFallback}


def fallback_from_env() -> Optional[SearchFallback]:
    name = (os.environ.get("RESILEOS_SEARCH_FALLBACK") or "").strip().lower()
    factory = FALLBACKS.get(name)
    return factory() if factory else None


def native_search(query: str, *, index: NativeIndex, fallback: Optional[SearchFallback] = None,
                  max_results: int = 8, now: Optional[datetime] = None) -> dict[str, Any]:
    """Our index first. The fallback runs only when the index has no match."""
    query = str(query or "").strip()
    if not query:
        return {"status": "UNAVAILABLE", "reason": "empty query", "packets": [], "fallback_used": None}
    stamp = _now(now)
    packets = [
        make_packet(doc["url"], _snippet_for(doc["text"], query), origin="native", title=doc.get("title", ""),
                    retrieved_at=doc.get("retrieved_at") or stamp, relevance=score)
        for score, doc in index.search(query, max_results)
    ]
    used = None
    if not packets and fallback is not None:
        try:
            rows = fallback.search(query, max_results)
        except Exception:  # backend down; say so, invent nothing
            rows = []
        n = len(rows)
        for i, row in enumerate(rows[:max_results]):
            url = str(row.get("url") or "").strip()
            if url.startswith(("http://", "https://")):
                packets.append(make_packet(url, row.get("snippet", ""), origin=f"fallback:{fallback.name}",
                                           title=row.get("title", ""), retrieved_at=stamp,
                                           relevance=float(n - i), label=fallback.label))
        used = fallback.name
    return {"status": "OK" if packets else "EMPTY", "packets": packets, "fallback_used": used,
            "index_size": len(index)}


def search_results(query: str, max_results: int = 3) -> dict[str, Any]:
    """``web_search``-shaped results from our index (fallback only if on)."""
    found = native_search(query, index=shared_index(), fallback=fallback_from_env(), max_results=max_results)
    rows = [{"title": p["title"] or p["url"], "url": p["url"], "snippet": p["snippet"], "origin": p["origin_label"]}
            for p in found["packets"]]
    return {"status": "SUCCESS" if found["status"] != "UNAVAILABLE" else "ERROR", "query": query, "results": rows,
            "evidence_summary": " ".join(r["snippet"] for r in rows), "fallback_used": found.get("fallback_used"),
            **({"error": found.get("reason")} if found["status"] == "UNAVAILABLE" else {})}


# ── Pheme: rising terms (routing hint only) ────────────────────────────
_ENTITY = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*)\b")


def pheme_buzz(recent: Iterable[str], baseline: Iterable[str] = (), *, top: int = 6) -> dict[str, Any]:
    recent = [str(t or "") for t in recent]
    baseline = [str(t or "") for t in baseline]
    now_c = Counter(w for t in recent for w in set(_tokens(t)))
    base_c = Counter(w for t in baseline for w in set(_tokens(t)))
    rn, bn = max(1, len(recent)), max(1, len(baseline))
    rising = []
    for term, count in now_c.items():
        if count < 2:
            continue
        lift = ((count / rn) + 1e-9) / ((base_c[term] + 1) / (bn + 1))
        if lift > 1.0:
            rising.append({"term": term, "lift": round(lift, 3)})
    rising.sort(key=lambda r: (-r["lift"], r["term"]))
    pairs = Counter()
    for text in recent:
        names = sorted(set(m.group(1) for m in _ENTITY.finditer(text)))[:8]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pairs[(a, b)] += 1
    top_pairs = [{"pair": list(p), "count": c} for p, c in pairs.most_common(top) if c >= 2]
    return {"routing_hint": rising[:top], "pairs": top_pairs, "is_fact": False,
            "use": "routing hint only; never stored"}


# ── quintuples and claim spans ─────────────────────────────────────────
@dataclass(frozen=True)
class Quintuple:
    subject: str
    relation: str
    obj: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

    @property
    def frame(self) -> int:
        """3 (edge) for a bare triple, 5 (belt) once time bounds it."""
        return 5 if (self.valid_from or self.valid_to) else 3

    def claim(self) -> dict[str, Any]:
        out = {"subject": self.subject, "relation": self.relation, "obj": self.obj}
        if self.valid_from:
            out["valid_from"] = self.valid_from
        if self.valid_to:
            out["valid_to"] = self.valid_to
        return out


_LD = re.compile(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>')
_LD_PROPS = {
    "addressCountry", "addressLocality", "author", "birthDate", "birthPlace", "capital", "containedInPlace",
    "deathDate", "founder", "foundingDate", "foundingLocation", "jobTitle", "location", "memberOf",
    "nationality", "parentOrganization", "worksFor", "alumniOf", "headquarters",
}
_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _scalar(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id")
    if isinstance(value, (str, int, float)) and str(value).strip():
        return " ".join(str(value).split())[:200]
    return None


def _date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    m = _DATE.match(text)
    if not m:
        return None
    part = m.group(0)
    return part if len(part) == 10 else (part + "-01-01")[:10] if len(part) == 4 else part + "-01"


def _ld_objects(raw: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in _LD.findall(raw or ""):
        try:
            data = json.loads(html.unescape(block.strip()))
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, dict):
                if isinstance(item.get("@graph"), list):
                    stack.extend(item["@graph"])
                out.append(item)
            elif isinstance(item, list):
                stack.extend(item)
    return out


def extract_claims(url: str, raw: str, *, retrieved_at: Optional[str] = None, max_prose: int = 3) -> list[dict[str, Any]]:
    """Claim spans from one page, each with provenance.

    Structured (schema.org JSON-LD) becomes a quintuple claim. Plain
    sentences become prose claims, which Eat abstains on.
    """
    stamp = retrieved_at or _now()
    tier = source_tier(url)
    out: list[dict[str, Any]] = []
    for obj in _ld_objects(raw):
        subject = _scalar(obj.get("name"))
        if not subject:
            continue
        as_of = _date(obj.get("dateModified") or obj.get("datePublished"))
        vf, vt = _date(obj.get("startDate")), _date(obj.get("endDate"))
        for prop in sorted(_LD_PROPS & set(obj)):
            value = _scalar(obj[prop])
            if not value:
                continue
            q = Quintuple(subject, _snake(prop), value, vf, vt)
            span = f'"{prop}": {json.dumps(obj[prop], ensure_ascii=False)[:200]}'
            out.append({"claim": q.claim(), "frame": q.frame, "source": url, "span": span, "as_of": as_of,
                        "retrieved_at": stamp, "tier": tier, "kind": "structured"})
    text = _plain(raw, 8000)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if 30 <= len(s) <= 300][:max_prose]
    for sentence in sentences:
        start = text.find(sentence)
        out.append({"claim": sentence, "frame": None, "source": url,
                    "span": {"start": start, "end": start + len(sentence)}, "as_of": None,
                    "retrieved_at": stamp, "tier": tier, "kind": "prose"})
    return out


def _default_fetch(url: str) -> dict[str, Any]:
    from resileos.chat.assist import guarded_fetch
    from resileos.kin.outer_legions import _resolve

    return _resolve(guarded_fetch(url))


def ichnaea_fanout(packets: list[dict[str, Any]], *, max_follow: int, index: Optional[NativeIndex] = None,
                   fetch_fn: Optional[Callable[[str], Any]] = None) -> dict[str, Any]:
    """Follow packets to their origin pages and extract claim spans."""
    from resileos.kin.outer_legions import _resolve

    fetch = fetch_fn or _default_fetch
    followed, candidates, blocked, pages = [], [], 0, []
    seen_urls: set[str] = set()
    for packet in packets:
        if len(followed) >= max_follow:
            break
        url = str(packet.get("url") or "")
        if not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            page = _resolve(fetch(url))
        except Exception:
            page = {"status": "ERROR"}
        if not isinstance(page, dict) or page.get("status") != "SUCCESS":
            blocked += 1
            continue
        stamp = _now()
        final = str(page.get("url") or url)
        raw = str(page.get("content") or "")
        followed.append(final)
        pages.append({"url": final, "text": _plain(raw, 4000)})
        if index is not None:
            index.add(final, raw, title=packet.get("title", ""), retrieved_at=stamp)
        candidates.extend(extract_claims(final, raw, retrieved_at=stamp))
    return {"followed": followed, "pages": pages, "candidates": candidates, "not_opened": blocked}


# ── PHI ranking over waves ─────────────────────────────────────────────
def phi_rank(items: list[dict[str, Any]]) -> dict[str, Any]:
    """score = relevance * PHI^-(wave-1), normalised to the best.

    Drop anything under EPSILON (1/64); keep at most WAIST (36).
    """
    from resileos.ui.cascade_address import phi_level_weight

    scored = []
    for item in items:
        rel = max(0.0, float(item.get("relevance") or 0.0))
        scored.append((rel * phi_level_weight(int(item.get("wave") or 1) - 1), item))
    best = max((s for s, _ in scored), default=0.0)
    kept, dropped = [], 0
    for score, item in sorted(scored, key=lambda p: (-p[0], str(p[1].get("url")))):
        weight = score / best if best > 0 else 0.0
        if weight < EPSILON or len(kept) >= WAIST:
            dropped += 1
            continue
        kept.append({**item, "weight": round(weight, 6)})
    return {"kept": kept, "dropped": dropped, "floor": EPSILON, "waist": WAIST}


# ── Eat bridge ─────────────────────────────────────────────────────────
NOISY = 0.5


def _envelope(candidate: dict[str, Any]) -> dict[str, Any]:
    # Provenance rides outside the claim. Only the claim fields reach Eat.
    return {"claim": candidate.get("claim"), "source": candidate.get("source", ""),
            "as_of": candidate.get("as_of"), "retrieved_at": candidate.get("retrieved_at")}


def eat_bridge(candidates: list[dict[str, Any]], *, titanos: Any = None, commit: bool = False,
               notes: Any = None, reviewer_kw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Every candidate goes through Eat. Prose abstains.

    ``commit=False`` previews with ``check_envelope`` (nothing written).
    ``commit=True`` uses ``eat_commit_envelopes``: only accepted structured
    claims reach Zeus, and Titanos is written only if every reviewer
    approves. On a noisy wave Hades gets one lesson-only note.
    """
    from resileos.kin.eat_envelope import check_envelope, eat_commit_envelopes

    envelopes = [_envelope(c) for c in candidates]
    if commit:
        if titanos is None:
            raise ValueError("commit needs a Titanos")
        out = eat_commit_envelopes(envelopes, titanos=titanos, notes=None, **dict(reviewer_kw or {}))
        results = out["results"]
    else:
        results = [check_envelope(e).to_dict() for e in envelopes]
        out = {"summary": {"committed": 0, "applied": False}}
    for res, cand in zip(results, candidates):
        res["as_of"] = cand.get("as_of")
        res["span"] = cand.get("span")
    good = {"accept", "committed"}
    kept = sum(1 for r in results if r.get("action") in good)
    noisy = bool(results) and (len(results) - kept) / len(results) >= NOISY
    if noisy and notes is not None:
        notes.append(
            lesson=f"noisy crawl wave: {len(results) - kept} of {len(results)} candidates held back",
            verified=False,
            outcome="inconclusive",
            metrics={"candidates": float(len(results)), "kept": float(kept)},
        )
    return {"results": results, "kept": kept, "held_back": len(results) - kept, "noisy": noisy,
            "committed": int(out["summary"].get("committed", 0)), "applied": bool(out["summary"].get("applied"))}


# ── Iris: crawl audit trace (read-only reader) ─────────────────────────
def trace_path() -> Path:
    return Path(os.environ.get("RESILEOS_HERMES_TRACE", "data/hermes_trace.jsonl"))


def _audit(path: Optional[Path], row: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def crawl_trace(path: str | Path | None = None, *, limit: int = 200) -> dict[str, Any]:
    """Read the crawl audit JSONL. Opens the file read-only; writes nothing."""
    p = Path(path) if path else trace_path()
    if not p.exists():
        return {"status": "EMPTY", "records": [], "waves": 0}
    rows = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows = rows[-max(1, int(limit)):]
    return {"status": "OK", "records": rows, "waves": len(rows),
            "kept": sum(int(r.get("kept") or 0) for r in rows)}


# ── the cascade of waves ───────────────────────────────────────────────
def run_waves(query: str, *, index: NativeIndex, depth: int = 1, fetch_fn: Optional[Callable[[str], Any]] = None,
              fallback: Optional[SearchFallback] = None, titanos: Any = None, commit: bool = False,
              notes: Any = None, audit_path: Optional[Path] = None, reviewer_kw: Optional[dict[str, Any]] = None,
              ) -> dict[str, Any]:
    """Run up to ``depth`` waves over frames (3, 5, 9, 12)."""
    depth = max(1, min(int(depth), len(CASCADE_FRAMES)))
    frames = CASCADE_FRAMES[:depth]
    packets_all: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    followed: list[str] = []
    q = query
    baseline: list[str] = []
    hints: list[dict[str, Any]] = []
    fallback_used = None
    for wave, frame in enumerate(frames, start=1):
        found = native_search(q, index=index, fallback=fallback, max_results=frame)
        fallback_used = fallback_used or found.get("fallback_used")
        wave_packets = [{**p, "wave": wave} for p in found["packets"] if p["url"] not in followed]
        packets_all.extend(wave_packets)
        ranked = phi_rank(wave_packets)["kept"]
        fan = ichnaea_fanout(ranked, max_follow=frame, index=index, fetch_fn=fetch_fn)
        followed.extend(fan["followed"])
        for cand in fan["candidates"]:
            cand["wave"] = wave
        candidates.extend(fan["candidates"])
        buzz = pheme_buzz([p["snippet"] for p in wave_packets], baseline)
        baseline.extend(p["snippet"] for p in wave_packets)
        hints.append({"wave": wave, "frame": frame, "routing_hint": buzz["routing_hint"][:3]})
        nxt = next((h["term"] for h in buzz["routing_hint"] if h["term"] not in _tokens(q)), None)
        if not nxt:
            break
        q = f"{query} {nxt}"
    ranked_all = phi_rank(packets_all)
    bridge = eat_bridge(candidates, titanos=titanos, commit=commit, notes=notes, reviewer_kw=reviewer_kw)
    report = {
        "query": query,
        "waves": len(hints),
        "frames": list(frames[: len(hints)]),
        "searched": len({p["url"] for p in packets_all}),
        "followed": len(followed),
        "candidates": len(candidates),
        "kept": bridge["kept"],
        "held_back": bridge["held_back"],
        "committed": bridge["committed"],
        "fallback_used": fallback_used,
        "sources": ranked_all["kept"],
        "dropped": ranked_all["dropped"],
        "routing_hints": hints,
        "results": bridge["results"],
    }
    report["summary"] = summary_line(report)
    _audit(audit_path, {"ts": _now(), "query_terms": len(_tokens(query)), "waves": report["waves"],
                        "searched": report["searched"], "followed": report["followed"], "kept": report["kept"],
                        "held_back": report["held_back"], "fallback_used": fallback_used})
    return report


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def summary_line(report: dict[str, Any]) -> str:
    """Plain words for the chat trail."""
    if not report.get("searched"):
        return "Searched our index: nothing found yet"
    line = f"Searched {_n(report['searched'], 'source')}"
    if report.get("followed"):
        line += f", followed {report['followed']} to the original pages"
    verb = "saved" if report.get("committed") else "kept"
    count = report.get("committed") or report.get("kept") or 0
    line += f", {verb} {_n(count, 'fact')}"
    if report.get("fallback_used"):
        line += " (some results came from the third-party fallback)"
    return line


# ── registration on the Kin ────────────────────────────────────────────
def register_hermes_crawl_legions(*, enable: bool = False, index: Optional[NativeIndex] = None,
                                  fetch_fn: Optional[Callable[[str], Any]] = None,
                                  fallback: Optional[SearchFallback] = None,
                                  audit_path: Optional[str] = None) -> list[str]:
    """Register the crawl legions. Off unless ``enable`` is true."""
    if not enable:
        return []
    from resileos.kin.legions import register_legion

    idx = index or NativeIndex()
    gen = {"writes_residual": False, "executes": True}

    def native(seen: dict[str, Any], **kw: Any) -> dict[str, Any]:
        """Search our own index; the labelled fallback only if it is on."""
        return native_search(str(kw.get("query") or ""), index=idx, fallback=fallback,
                             max_results=int(kw.get("max_results") or 8))

    def buzz(seen: dict[str, Any], **kw: Any) -> dict[str, Any]:
        """Rising terms and entity pairs: a routing hint, never a fact."""
        return pheme_buzz(kw.get("recent") or [], kw.get("baseline") or [])

    def fanout(seen: dict[str, Any], **kw: Any) -> dict[str, Any]:
        """Follow packets to origin pages (guarded fetch) and extract claim spans."""
        return ichnaea_fanout(list(kw.get("packets") or []), max_follow=int(kw.get("max_follow") or 3),
                              index=idx, fetch_fn=fetch_fn)

    def trace(seen: dict[str, Any], **kw: Any) -> dict[str, Any]:
        """Read-only crawl audit trace."""
        return crawl_trace(audit_path or kw.get("path"), limit=int(kw.get("limit") or 200))

    names = [
        register_legion("hermes", native, name="native_search", constraints={**gen, "action": "native search"}),
        register_legion("hermes", buzz, name="pheme_buzz", constraints={**gen, "action": "buzz hint"}),
        register_legion("hermes", fanout, name="ichnaea_fanout", constraints={**gen, "action": "origin fanout"}),
        register_legion("iris", trace, name="crawl_trace", constraints={**gen, "action": "read crawl trace"}),
    ]
    return names


RENAMES = {
    "hive search": "hermes.native_search (Agoraios)",
    "hive buzz": "hermes.pheme_buzz (Pheme)",
    "hive crawl / fan-out": "hermes.ichnaea_fanout (Ichnaea)",
    "hive filter": "eat_bridge -> eat_filter -> Zeus (SeparatedCycle)",
    "hive trace": "iris.crawl_trace (Iris)",
    "hive notes": "hades.lesson_note (Hades)",
}

__all__ = [
    "DuckDuckGoFallback", "FALLBACKS", "NativeIndex", "Quintuple", "RENAMES", "SearchFallback",
    "crawl_trace", "eat_bridge", "extract_claims", "fallback_from_env", "ichnaea_fanout", "make_packet",
    "native_search", "pheme_buzz", "phi_rank", "register_hermes_crawl_legions", "run_waves", "source_tier",
    "summary_line",
]
