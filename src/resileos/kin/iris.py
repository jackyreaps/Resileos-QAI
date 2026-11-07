"""Iris — observer kin. Does not answer user facts."""
from __future__ import annotations

from resileos.ui.attach_scale import attach_scale

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class IrisReport:
    """Structured observation only — never store rows."""

    hits: int = 0
    misses: int = 0
    teaches: int = 0
    assets: int = 0
    sessions: int = 0
    hit_rate: float = 0.0
    active_children: list[str] = field(default_factory=list)
    eaten_children: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_iris_observer():
    """
    Side interface: observe(metrics=None, agency_group=None) -> IrisReport.

    Query handler always declines (None) so Iris never competes with Zeus
    for subject/relation answers.
    """

    def observe(
        metrics: Optional[dict[str, Any]] = None,
        agency_group: Any = None,
    ) -> IrisReport:
        m = dict(metrics or {})
        report = IrisReport(
            hits=int(m.get("hits", 0)),
            misses=int(m.get("misses", 0)),
            teaches=int(m.get("teaches", 0)),
            assets=int(m.get("assets", 0)),
            sessions=int(m.get("sessions", 0)),
            hit_rate=float(m.get("hit_rate", 0.0)),
        )
        if agency_group is not None:
            children = getattr(agency_group, "children", None) or {}
            if isinstance(children, dict):
                iterable = children.values()
            else:
                iterable = children
            for ch in iterable:
                name = getattr(ch, "name", str(ch))
                if getattr(ch, "active", True):
                    report.active_children.append(str(name))
                else:
                    report.eaten_children.append(str(name))
        # Filter flags — operational, not "emotion"
        if report.hit_rate < 0.3 and report.hits + report.misses >= 5:
            report.flags.append("low_hit_rate")
        if report.misses > report.hits and report.misses >= 3:
            report.flags.append("miss_dominant")
        if report.teaches == 0 and report.sessions >= 3:
            report.flags.append("no_teaches")
        if report.eaten_children:
            report.flags.append("children_eaten")
        return report

    def handler(parent: Any, subject: str, relation: str, inverse: bool = False) -> None:
        # Always decline fact queries
        return None

    return observe, handler
