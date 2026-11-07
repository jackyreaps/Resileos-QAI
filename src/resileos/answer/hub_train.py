"""
Hub training for hosted Titanos.

Namespaces (RES-328-hub-ns):
  user:<id>   — operator preferences / notes
  world:<id>  — shared project / world
  org:<id>    — tenant

Train = learn() under those subjects.
Each trained subject gets a scale address via hub_address.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from resileos.answer.hub_address import address_for_hub_subject
from resileos.ui.shared_state import step_shared
from resileos.answer.workbench import Workbench, open_workbench, parse_fact_line

# Minimal workspace seed (no suite physics constants)
DEFAULT_WORKSPACE_FACTS: list[tuple[str, str, str]] = [
    ("world:materials", "status", "workspace"),
    ("world:materials", "store", "titanos"),
    ("world:materials", "mouth", "structured"),
]


def ensure_hub_subject(subject: str) -> str:
    s = subject.strip()
    if s.startswith(("user:", "world:", "org:")):
        return s
    raise ValueError(
        f"hub subject must be user:|world:|org: prefixed, got {subject!r}"
    )


def train_hub(
    wb: Workbench,
    facts: Iterable[tuple[str, str, str]],
    *,
    require_hub_prefix: bool = True,
) -> int:
    batch: list[tuple[str, str, str]] = []
    for s, r, o in facts:
        if require_hub_prefix:
            s = ensure_hub_subject(s)
        batch.append((s, r, o))
    if not batch:
        return 0
    if hasattr(wb.titan, "learn_many"):
        wb.titan.learn_many(batch, update_attractor=False)
    else:
        for s, r, o in batch:
            wb.titan.learn(s, r, o, update_attractor=False)
    # attach scale addresses for the subjects just trained
    seen = []
    addresses = []
    for s, _, _ in batch:
        if s not in seen:
            seen.append(s)
            addresses.append(address_for_hub_subject(s))
    wb.last_hub_addresses = addresses
    wb.last_core_step = step_shared()
    return len(batch)


def train_from_file(wb: Workbench, path: Path, **kw) -> int:
    facts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = parse_fact_line(line)
        if t:
            facts.append(t)
    return train_hub(wb, facts, **kw)


def seed_default_hubs(wb: Workbench) -> int:
    return train_hub(wb, DEFAULT_WORKSPACE_FACTS)


def open_hub_workbench(
    *,
    backend: str = "structured",
    state_path: Optional[Path] = None,
    seed: bool = True,
) -> Workbench:
    wb = open_workbench(backend=backend, use_attractor=False)
    if state_path and state_path.exists() and hasattr(wb.titan, "load"):
        try:
            wb.titan = type(wb.titan).load(str(state_path))
        except Exception:
            pass
    if seed:
        seed_default_hubs(wb)
    return wb
