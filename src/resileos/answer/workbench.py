"""
Workbench mouth: ingest fact lines, exact ask, pluggable render backend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from resileos.answer.hub_address import address_for_hub_subject
from resileos.answer.backends import (
    AnswerContext,
    list_backends,
    select_backend,
)


_TRIPLE_RE = re.compile(
    r"^\s*[(\[]?\s*([^,|]+)\s*[,|]\s*([^,|]+)\s*[,|]\s*([^)\]]+)\s*[)\]]?\s*$"
)
_ARROW_RE = re.compile(r"^\s*(.+?)\s*(?:->|→)\s*(.+?)\s*:\s*(.+?)\s*$")


def parse_fact_line(line: str) -> Optional[tuple[str, str, str]]:
    """Parse one working fact line into (s, r, o).

    Accepts:
      subject, relation, object
      (subject, relation, object)
      subject -> object : relation
    Ignores blank lines and # comments.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = _ARROW_RE.match(line)
    if m:
        s, o, r = (x.strip() for x in m.groups())
        if s and r and o:
            return (s, r, o)
    m = _TRIPLE_RE.match(line)
    if m:
        s, r, o = (x.strip().strip("'\"") for x in m.groups())
        if s and r and o:
            return (s, r, o)
    return None


def load_workbench_facts(path: Path) -> list[tuple[str, str, str]]:
    facts: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = parse_fact_line(line)
        if t:
            facts.append(t)
    return facts


@dataclass
class WorkbenchResult:
    subject: str
    relation: str
    rows: tuple[str, ...]
    answer_text: str
    backend: str
    empty: bool


@dataclass
class Workbench:
    """Exact store + mouth for advanced project sessions."""

    titan: object
    backend_name: str = "structured"
    _backend: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._backend = select_backend(self.backend_name)

    def ingest_lines(self, lines: Iterable[str]) -> int:
        n = 0
        batch: list[tuple[str, str, str]] = []
        for line in lines:
            t = parse_fact_line(line if isinstance(line, str) else str(line))
            if t:
                batch.append(t)
        if not batch:
            return 0
        if hasattr(self.titan, "learn_many"):
            self.titan.learn_many(batch, update_attractor=False)
            n = len(batch)
        else:
            for s, r, o in batch:
                self.titan.learn(s, r, o, update_attractor=False)
                n += 1
        return n

    def last_addresses(self) -> list:
        return getattr(self, "_addresses", [])

    def ingest_file(self, path: Path) -> int:
        return self.ingest_lines(path.read_text(encoding="utf-8").splitlines())

    def ask_rows(self, subject: str, relation: str) -> tuple[str, ...]:
        rows = self.titan.ask_list(subject, relation) or []
        return tuple(str(x) for x in rows)

    def answer(
        self,
        subject: str,
        relation: str,
        *,
        question: str = "",
        inverse: bool = False,
    ) -> WorkbenchResult:
        rows = self.ask_rows(subject, relation)
        ctx = AnswerContext(
            question=question or f"{subject} {relation}",
            subject=subject,
            relation=relation,
            inverse=inverse,
            rows=rows,
            confidence=1.0 if rows else 0.0,
            recovery_loss=0.0,
            path=(),
            loop_history=(),
            gate_state="",
            sector="",
        )
        text = self._backend.render(ctx)
        return WorkbenchResult(
            subject=subject,
            relation=relation,
            rows=rows,
            answer_text=text,
            backend=getattr(self._backend, "name", self.backend_name),
            empty=not bool(rows),
        )

    def session_snapshot(self) -> dict:
        return {
            "backend": self.backend_name,
            "backends_available": list(list_backends()),
        }


def open_workbench(
    *,
    backend: str = "structured",
    use_attractor: bool = False,
    seed_facts: Optional[list[tuple[str, str, str]]] = None,
) -> Workbench:
    from titanos import Titanos, TitanosConfig

    t = Titanos(TitanosConfig(use_attractor=use_attractor))
    wb = Workbench(titan=t, backend_name=backend)
    if seed_facts:
        if hasattr(t, "learn_many"):
            t.learn_many(seed_facts, update_attractor=False)
        else:
            for s, r, o in seed_facts:
                t.learn(s, r, o, update_attractor=False)
    return wb
